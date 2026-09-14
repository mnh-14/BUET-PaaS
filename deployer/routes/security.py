"""Receives Falco alerts (via Falcosidekick) and reacts directly, using the
Deployer's existing k8s access — instead of just recording the alert and
waiting on a dashboard.

Flow per alert:
  1. Falcosidekick POSTs here (shared-secret header, not HMAC — Falcosidekick
     doesn't sign requests the way GitHub does).
  2. Map the alert's priority to a tier: AUTO_ACTION tier scales the owning
     Deployment to 0 replicas immediately; NOTIFY_ONLY tier just forwards a
     record, no action taken.
  3. Either way, POST a notification to the Backend (FastAPI) so it lands in
     security_events_col for the dashboard. The Backend is downstream here —
     it does not decide or perform the mitigation, only records it.

No in-process alert dedup is done here on purpose: deploy_service.py runs
under gunicorn with multiple worker processes, which don't share memory, so
an in-memory dedup set would be unreliable. Instead:
  - The mitigation action (scale-to-0) is naturally idempotent — applying it
    twice for the same duplicate-delivered alert is harmless.
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

security_routes = Blueprint("security_routes", __name__)

FALCO_WEBHOOK_TOKEN = os.getenv("FALCO_WEBHOOK_TOKEN")

BACKEND_NOTIFY_URL = os.getenv(
    "BACKEND_NOTIFY_URL", "http://backend-vm:8000/api/v1/security/incident"
)
SECURITY_NOTIFY_TOKEN = os.getenv("SECURITY_NOTIFY_TOKEN")

# Warning and above triggers real mitigation; below that is notify-only.
# Tune this if you want it more/less aggressive.
AUTO_ACTION_PRIORITIES = {"Emergency", "Alert", "Critical", "Error", "Warning"}

# Namespaces that are never auto-actioned, regardless of alert priority —
# self-preservation so a Falco/Deployer alert about itself can't take down
# the thing doing the watching/acting. Set to "" (empty string) via env var
# to disable this and truly act on everything Falco watches, no exceptions.
_default_protect = "falco,buet-paas-system-team23"
SELF_PROTECT_NAMESPACES = {
    ns.strip()
    for ns in os.getenv("SELF_PROTECT_NAMESPACES", _default_protect).split(",")
    if ns.strip()
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_owning_deployment(namespace: str, pod_name: str) -> str | None:
    """Pod -> ReplicaSet -> Deployment, via ownerReferences. Returns the
    Deployment name, or None if it can't be resolved (e.g. a bare pod, a
    Job-owned build pod with no Deployment ancestor, or the pod's already
    gone)."""
    k3s_client = _require_kube_client()
    core_api = client.CoreV1Api(k3s_client)
    apps_api = client.AppsV1Api(k3s_client)

    try:
        pod = core_api.read_namespaced_pod(name=pod_name, namespace=namespace)
    except client.exceptions.ApiException as exc:
        logger.warning("Could not read pod %s/%s: %s", namespace, pod_name, exc)
        return None

    owners = pod.metadata.owner_references or []
    rs_owner = next((o for o in owners if o.kind == "ReplicaSet"), None)
    if not rs_owner:
        return None

    try:
        rs = apps_api.read_namespaced_replica_set(name=rs_owner.name, namespace=namespace)
    except client.exceptions.ApiException as exc:
        logger.warning("Could not read ReplicaSet %s/%s: %s", namespace, rs_owner.name, exc)
        return None

    rs_owners = rs.metadata.owner_references or []
    deploy_owner = next((o for o in rs_owners if o.kind == "Deployment"), None)
    return deploy_owner.name if deploy_owner else None


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
    deployment_name = None

    if not namespace or not pod_name:
        # Alert didn't carry pod context (e.g. a host-level event, not a
        # container one) — nothing to act on, just forward for visibility.
        tier = "notify_only"
    elif namespace in SELF_PROTECT_NAMESPACES:
        action_taken = "skipped_self_protect_namespace"
    elif tier == "auto_action":
        deployment_name = _resolve_owning_deployment(namespace, pod_name)
        if deployment_name:
            scaled = _scale_to_zero(namespace, deployment_name)
            action_taken = "scaled_to_zero" if scaled else "scale_failed"
        else:
            # Common for build-Job pods: owned by a Job, not a Deployment,
            # so there's nothing to scale down. Notify-only in that case.
            action_taken = "no_owning_deployment_found"

    record = {
        "alert_uuid": payload.get("uuid"),
        "rule": rule,
        "priority": priority,
        "tier": tier,
        "output": payload.get("output"),
        "k8s_namespace": namespace,
        "k8s_pod_name": pod_name,
        "deployment_name": deployment_name,
        "action_taken": action_taken,
        "hostname": payload.get("hostname"),
        "event_time": payload.get("time"),
        "notified_at": _now_iso(),
    }

    _notify_backend(record)

    return jsonify({"status": "received", "tier": tier, "action_taken": action_taken}), 202