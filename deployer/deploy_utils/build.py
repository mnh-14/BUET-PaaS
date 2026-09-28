"""Build operations exposed by the deployer service."""

import time
from typing import Any, Dict

from kubernetes import client, utils

from .config import builder_namespace
from .kubernetes import _require_kube_client, k3s_client
from k3s_conf import JobPipelineBuilder


def _delete_finished_job_if_present(job_name: str, wait_timeout_seconds: float = 30.0) -> None:
	"""If a Job with this name already exists and has genuinely finished
	(succeeded or failed, not still active), delete it before creating a
	new one with the same name.

	Job names here are deterministic ({app_name}-{namespace}-build-job), and
	completed Jobs have a ttlSecondsAfterFinished (see k3s_conf.py) that
	cleans them up automatically, but that TTL exists to give a supervisor
	a window to inspect a recent failure, not to block a legitimate rebuild
	that happens to land inside that window. Without this check, rebuilding
	the same app twice within the TTL window fails with a raw Kubernetes
	409 Conflict instead of just... rebuilding.

	Deliberately does NOT touch a Job that's still active, deleting a
	build that's genuinely in progress out from under the person who
	started it would be a much worse failure mode than a clear "already
	running" error.

	CORRECTNESS NOTE (fixed after a real failure): propagation_policy=
	"Foreground" does NOT make delete_namespaced_job() block until the Job
	is actually gone -- the API call returns as soon as deletion is
	initiated (the object enters Terminating state), not when it is fully
	removed. An earlier version of this function assumed otherwise and
	immediately tried to create the replacement Job, which Kubernetes
	correctly rejected with "object is being deleted... already exists".
	This version actually polls for the Job to disappear (404) before
	returning.
	"""
	batch_api = client.BatchV1Api(k3s_client)
	try:
		existing = batch_api.read_namespaced_job(name=job_name, namespace=builder_namespace)
	except client.exceptions.ApiException as exc:
		if exc.status == 404:
			return
		raise

	status = existing.status
	is_finished = bool(getattr(status, "succeeded", 0) or getattr(status, "failed", 0))
	if not is_finished:
		raise RuntimeError(
			f"Build job '{job_name}' is already running. Wait for it to "
			f"finish, or check /api/build/status before starting a new one."
		)

	batch_api.delete_namespaced_job(
		name=job_name,
		namespace=builder_namespace,
		body=client.V1DeleteOptions(propagation_policy="Foreground"),
	)

	deadline = time.monotonic() + wait_timeout_seconds
	while time.monotonic() < deadline:
		try:
			batch_api.read_namespaced_job(name=job_name, namespace=builder_namespace)
		except client.exceptions.ApiException as exc:
			if exc.status == 404:
				return
			raise
		time.sleep(0.5)

	raise RuntimeError(
		f"Timed out waiting for old build job '{job_name}' to finish "
		f"deleting after {wait_timeout_seconds}s. Try again shortly."
	)


def build_image(user_config: Dict[str, Any]):
	if not isinstance(user_config, dict):
		raise ValueError("user_config must be a dictionary")
	_require_kube_client()
	builder = JobPipelineBuilder(app_name=user_config["app_name"], namespace=user_config["namespace"])
	builder.apply_git_cloner(git_url=user_config["git_url"], branch=user_config.get("git_branch", "main"))
	user_config["image"] = f"{user_config['app_name']}-{user_config['namespace']}-build:latest"
	builder.apply_kaniko_build(
		image_destination=user_config["image"],
		dockerfile_path=user_config.get("dockerfile_path", "Dockerfile"),
		build_args=user_config.get("build_args", {}),
	)
	build_conf = builder.build()
	_delete_finished_job_if_present(build_conf["metadata"]["name"])
	utils.create_from_dict(k3s_client, build_conf)
	return build_conf


def check_build_status(name: str, namespace: str):
	"""Return build status together with a human-readable summary and reason."""
	if not name or not namespace:
		raise ValueError("Both 'name' and 'namespace' are required.")

	if k3s_client is None:
		return {
			"status": "Unknown",
			"summary": "The build status could not be checked.",
			"reason": "Kubernetes client is not initialized.",
			"details": {},
		}

	try:
		job_name = f"{name}-{namespace}-build-job"
		batch_api = client.BatchV1Api(k3s_client)
		job = batch_api.read_namespaced_job(name=job_name, namespace=builder_namespace)
		job_status = job.status
		details = {
			"job_name": job_name,
			"active": getattr(job_status, "active", 0) or 0,
			"succeeded": getattr(job_status, "succeeded", 0) or 0,
			"failed": getattr(job_status, "failed", 0) or 0,
			"start_time": str(getattr(job_status, "start_time", None)),
			"completion_time": str(getattr(job_status, "completion_time", None)),
		}
		if details["succeeded"]:
			return {"status": "Succeeded", "summary": f"Build job '{job_name}' completed successfully.", "reason": "Job completed successfully.", "details": details}
		if details["failed"]:
			conditions = [condition.to_dict() if hasattr(condition, "to_dict") else str(condition) for condition in (getattr(job_status, "conditions", None) or [])]
			details["conditions"] = conditions
			return {"status": "Failed", "summary": f"Build job '{job_name}' failed.", "reason": conditions[0].get("reason", "Job reported failed") if conditions and isinstance(conditions[0], dict) else "Job reported failed.", "details": details}
		if details["active"]:
			return {"status": "Running", "summary": f"Build job '{job_name}' is currently running.", "reason": "Job has active pods.", "details": details}
		return {"status": "Pending", "summary": f"Build job '{job_name}' is waiting to start.", "reason": "Job has not started and has no completion result.", "details": details}
	except client.exceptions.ApiException as exc:
		if exc.status == 404:
			return {"status": "Unknown", "summary": f"Build job '{job_name}' was not found.", "reason": f"Kubernetes returned HTTP 404 in namespace '{namespace}'.", "details": {"job_name": job_name, "http_status": exc.status}}
		return {"status": "Unknown", "summary": f"Unable to read build job '{job_name}'.", "reason": str(exc), "details": {"job_name": job_name, "http_status": exc.status}}


def get_build_logs(name: str, namespace: str):
	"""Return logs from every Pod created for the app's build Job."""
	if not name or not namespace:
		raise ValueError("Both 'name' and 'namespace' are required.")

	_require_kube_client()
	job_name = f"{name}-{namespace}-build-job"
	core_api = client.CoreV1Api(k3s_client)
	pods = core_api.list_namespaced_pod(namespace=builder_namespace, label_selector=f"job-name={job_name}").items
	logs = []
	for pod in pods:
		container_name = "paas-builder"
		try:
			pod_logs = core_api.read_namespaced_pod_log(name=pod.metadata.name, namespace=builder_namespace, container=container_name)
			logs.append({"pod_name": pod.metadata.name, "container": container_name, "logs": pod_logs})
		except client.exceptions.ApiException as exc:
			logs.append({"pod_name": pod.metadata.name, "container": container_name, "logs": None, "error": str(exc), "http_status": exc.status})
	return {"job_name": job_name, "namespace": builder_namespace, "logs": logs}

__all__ = ["build_image", "check_build_status", "get_build_logs"]