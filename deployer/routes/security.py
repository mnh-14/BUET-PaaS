"""Receives Falco alerts (via Falcosidekick) and reacts directly, using the
Deployer's existing k8s access — instead of just recording the alert and
waiting on a dashboard.

Flow per alert:
  1. Falcosidekick POSTs here (shared-secret header, not HMAC — Falcosidekick
     doesn't sign requests the way GitHub does).
  2. Map the alert's priority to a tier: AUTO_ACTION tier mitigates the
     owning resource immediately (scale a Deployment to 0, or delete a
     build Job); NOTIFY_ONLY tier just forwards a record, no action taken.
  3. Either way, POST a notification to the Backend (FastAPI) so it lands in
     security_events_col for the dashboard. The Backend is downstream here —
     it does not decide or perform the mitigation, only records it.

No in-process alert dedup is done here on purpose: deploy_service.py runs
under gunicorn with multiple worker processes, which don't share memory, so
an in-memory dedup set would be unreliable. Instead:
  - The mitigation actions (scale-to-0, delete Job) are naturally idempotent
    — applying them twice for the same duplicate-delivered alert is harmless.
  - Final dedup happens at the Backend, which has a real database and
    enforces a unique index on alert_uuid.
"""

import os
import logging
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, request
from kubernetes import client

from deploy_utils.kubernetes import _require_kube_client


logger = logging.getLogger(__name__)
# Python's root logger defaults to WARNING, and the "handler of last resort"
# that made our earlier error/warning logs visible in `kubectl logs` only
# applies to WARNING+ — a plain logger.info() here would be silently
# swallowed without this. Scoped to just this module (own handler,
# propagate=False) rather than a global logging.basicConfig(), so this
# doesn't also make the kubernetes client / urllib3's own loggers verbose.
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.propagate = False

security_routes = Blueprint("security_routes", __name__)

FALCO_WEBHOOK_TOKEN = os.getenv("FALCO_WEBHOOK_TOKEN")

BACKEND_NOTIFY_URL = os.getenv(
    "BACKEND_NOTIFY_URL", "http://backend-vm:8000/api/v1/security/incident"
)
SECURITY_NOTIFY_TOKEN = os.getenv("SECURITY_NOTIFY_TOKEN")

# Warning and above triggers real mitigation; below that is notify-only.
# Tune this if you want it more/less aggressive.
AUTO_ACTION_PRIORITIES = {"Emergency", "Alert", "Critical", "Error", "Warning"}

# Self-protection is scoped by POD NAME PREFIX, not namespace. Build-job
# pods (owned by a Job) and the Deployer's own pod (paas-deployer-...) both
# live in buet-paas-system-team23 — an earlier revision of this file
# excluded that whole namespace, which correctly protected the Deployer but
# ALSO silently blocked any action on build jobs, defeating the point of
# watching them. Matching only the Deployer's own pod name prefix fixes
# that: build-job pods (named "{app}-{user}-build-job-{hash}") are never
# matched by "paas-deployer" and remain fully actionable.
# Set to "" (empty string) via env var to disable this entirely.
_default_protect_prefixes = "paas-deployer"
SELF_PROTECT_POD_PREFIXES = {
    p.strip()
    for p in os.getenv("SELF_PROTECT_POD_PREFIXES", _default_protect_prefixes).split(",")
    if p.strip()
}
# Falco's own namespace is still fully excluded by namespace — nothing else
# (no build jobs, no student apps) ever runs there, so this is a harmless,
# simple guard rather than a namespace-wide loophole like the old one was.
SELF_PROTECT_NAMESPACES = {"falco"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_action_target(namespace: str, pod_name: str):
    """Pod -> owner, classified as either a Deployment (via ReplicaSet) or
    a Job (direct owner). Returns (kind, name) where kind is "deployment"
    or "job", or (None, None) if it can't be resolved.

    A 404 here is expected, not an error: Falcosidekick can (and does)
    deliver the same alert more than once, and by the time a duplicate
    arrives the first delivery may have already deleted the Job (which
    cascades to deleting its pod too). Logged at INFO, not WARNING/ERROR,
    so real problems aren't lost in routine duplicate-alert noise."""
    k3s_client = _require_kube_client()
    core_api = client.CoreV1Api(k3s_client)
    apps_api = client.AppsV1Api(k3s_client)

    try:
        pod = core_api.read_namespaced_pod(name=pod_name, namespace=namespace)
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            logger.info(
                "Pod %s/%s already gone (likely a duplicate alert for an "
                "already-mitigated target) — nothing to do.",
                namespace, pod_name,
            )
        else:
            logger.warning("Could not read pod %s/%s: %s", namespace, pod_name, exc)
        return None, None

    owners = pod.metadata.owner_references or []

    job_owner = next((o for o in owners if o.kind == "Job"), None)
    if job_owner:
        return "job", job_owner.name

    rs_owner = next((o for o in owners if o.kind == "ReplicaSet"), None)
    if not rs_owner:
        return None, None

    try:
        rs = apps_api.read_namespaced_replica_set(name=rs_owner.name, namespace=namespace)
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            logger.info(
                "ReplicaSet %s/%s already gone (likely a duplicate alert) — "
                "nothing to do.", namespace, rs_owner.name,
            )
        else:
            logger.warning("Could not read ReplicaSet %s/%s: %s", namespace, rs_owner.name, exc)
        return None, None

    rs_owners = rs.metadata.owner_references or []
    deploy_owner = next((o for o in rs_owners if o.kind == "Deployment"), None)
    if deploy_owner:
        return "deployment", deploy_owner.name
    return None, None


def _scale_to_zero(namespace: str, deployment_name: str) -> bool:
    """Idempotent: scaling an already-0-replica Deployment to 0 again is a
    harmless no-op, so duplicate-delivered alerts are safe to re-apply."""
    k3s_client = _require_kube_client()
    apps_api = client.AppsV1Api(k3s_client)
    try:
        apps_api.patch_namespaced_deployment_scale(
            name=deployment_name,
            namespace=namespace,
            body={"spec": {"replicas": 0}},
        )
        return True
    except client.exceptions.ApiException as exc:
        logger.error("Failed to scale %s/%s to 0: %s", namespace, deployment_name, exc)
        return False


def _delete_job(namespace: str, job_name: str) -> bool:
    """Deletes the Job immediately (Background propagation — doesn't wait
    for the pod to finish terminating). Kaniko only pushes the finished
    image to Harbor as its LAST step, after every Dockerfile instruction
    has run — killing the Job before that point prevents a compromised
    image from ever landing in the registry, even though it can't undo
    whatever already executed.

    Treats a 404 (already deleted, e.g. a duplicate-delivered alert) as
    success rather than an error — keeps this idempotent like scale-to-0."""
    k3s_client = _require_kube_client()
    batch_api = client.BatchV1Api(k3s_client)
    try:
        batch_api.delete_namespaced_job(
            name=job_name,
            namespace=namespace,
            body=client.V1DeleteOptions(propagation_policy="Background"),
        )
        return True
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return True
        logger.error("Failed to delete job %s/%s: %s", namespace, job_name, exc)
        return False


def _notify_backend(record: dict) -> None:
    headers = {}
    if SECURITY_NOTIFY_TOKEN:
        headers["X-Security-Token"] = SECURITY_NOTIFY_TOKEN
    try:
        requests.post(BACKEND_NOTIFY_URL, json=record, headers=headers, timeout=5)
    except requests.RequestException as exc:
        # Don't fail the Falcosidekick request over a Backend hiccup — the
        # mitigation already happened; the dashboard record is best-effort.
        logger.error("Failed to notify backend at %s: %s", BACKEND_NOTIFY_URL, exc)


@security_routes.route("/api/security/falco-alert", methods=["POST"])
def receive_falco_alert():
    if FALCO_WEBHOOK_TOKEN:
        provided = request.headers.get("X-Falco-Token")
        if provided != FALCO_WEBHOOK_TOKEN:
            return jsonify({"status": "error", "message": "Invalid or missing token"}), 401

    payload = request.get_json(silent=True) or {}
    output_fields = payload.get("output_fields") or {}

    namespace = output_fields.get("k8s.ns.name")
    pod_name = output_fields.get("k8s.pod.name")
    priority = payload.get("priority", "Informational")
    rule = payload.get("rule")

    tier = "auto_action" if priority in AUTO_ACTION_PRIORITIES else "notify_only"
    action_taken = "none"
    target_kind = None
    target_name = None

    is_self_protected = (
        namespace in SELF_PROTECT_NAMESPACES
        or (pod_name and any(pod_name.startswith(p) for p in SELF_PROTECT_POD_PREFIXES))
    )

    if not namespace or not pod_name:
        # Alert didn't carry pod context (e.g. a host-level event, not a
        # container one) — nothing to act on, just forward for visibility.
        tier = "notify_only"
    elif is_self_protected:
        action_taken = "skipped_self_protect"
    elif tier == "auto_action":
        target_kind, target_name = _resolve_action_target(namespace, pod_name)
        if target_kind == "job":
            deleted = _delete_job(namespace, target_name)
            action_taken = "job_deleted" if deleted else "job_delete_failed"
        elif target_kind == "deployment":
            scaled = _scale_to_zero(namespace, target_name)
            action_taken = "scaled_to_zero" if scaled else "scale_failed"
        else:
            action_taken = "no_owning_resource_found"

    record = {
        "alert_uuid": payload.get("uuid"),
        "rule": rule,
        "priority": priority,
        "tier": tier,
        "output": payload.get("output"),
        "k8s_namespace": namespace,
        "k8s_pod_name": pod_name,
        "target_kind": target_kind,
        "target_name": target_name,
        "action_taken": action_taken,
        "hostname": payload.get("hostname"),
        "event_time": payload.get("time"),
        "notified_at": _now_iso(),
    }

    # Always logged, success or not — previously this route only logged on
    # failure paths (inside the helper functions), so confirming what
    # actually happened to a given alert required cross-referencing Falco's
    # own pod logs by hand. This line alone should answer "what did the
    # Deployer do with alert X" from `kubectl logs deployment/paas-deployer`.
    logger.info(
        "Falco alert processed | rule=%r priority=%s tier=%s pod=%s/%s "
        "target=%s/%s action=%s",
        rule, priority, tier, namespace, pod_name, target_kind, target_name, action_taken,
    )

    _notify_backend(record)

    return jsonify({"status": "received", "tier": tier, "action_taken": action_taken}), 202
