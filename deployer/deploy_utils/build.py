"""Build operations exposed by the deployer service."""

from typing import Any, Dict

from kubernetes import client, utils

from .config import builder_namespace
from .kubernetes import _require_kube_client, k3s_client
from k3s_conf import JobPipelineBuilder


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