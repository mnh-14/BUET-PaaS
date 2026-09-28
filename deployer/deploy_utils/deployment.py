"""Application deployment and deployment-observability operations."""

from typing import Any, Dict

from kubernetes import client, utils

from .config import default_floating_ip
from .kubernetes import _require_kube_client, k3s_client
from k3s_conf import PaaSManifestBuilder


def deploy_application(user_config: Dict[str, Any]):
	if not isinstance(user_config, dict):
		raise ValueError("user_config must be a dictionary")
	_require_kube_client()
	user_config["image"] = f"{user_config['app_name']}-{user_config['namespace']}-build:latest"
	manifest_builder = PaaSManifestBuilder(config=user_config)
	manifest_as_list = manifest_builder.build_all_listed()
	utils.create_from_dict(k3s_client, data=manifest_as_list)
	return manifest_as_list


def check_deploy_status(name: str, namespace: str):
	"""Return deployment status together with a human-readable summary and reason."""
	if not name or not namespace:
		raise ValueError("Both 'name' and 'namespace' are required.")

	if k3s_client is None:
		return {"status": "Unknown", "summary": "The deployment status could not be checked.", "reason": "Kubernetes client is not initialized.", "details": {}}

	try:
		deployment_name = f"{name}-deployment"
		app_api = client.AppsV1Api(k3s_client)
		deployment = app_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
		status = deployment.status
		details = {
			"deployment_name": deployment_name,
			"replicas": getattr(status, "replicas", 0) or 0 if status else 0,
			"ready_replicas": getattr(status, "ready_replicas", 0) or 0 if status else 0,
			"updated_replicas": getattr(status, "updated_replicas", 0) or 0 if status else 0,
			"available_replicas": getattr(status, "available_replicas", 0) or 0 if status else 0,
		}
		if status is None:
			return {"status": "Unknown", "summary": f"Deployment '{deployment_name}' has no status yet.", "reason": "Kubernetes returned an empty deployment status.", "details": details}

		conditions = status.conditions or []
		details["conditions"] = [condition.to_dict() if hasattr(condition, "to_dict") else str(condition) for condition in conditions]
		if any(condition.type == "Available" and condition.status == "True" for condition in conditions):
			condition = next(condition for condition in conditions if condition.type == "Available" and condition.status == "True")
			return {"status": "Running", "summary": f"Deployment '{deployment_name}' is running.", "reason": condition.reason or "Available replicas are ready.", "details": details, "url": f"http://{name}.{namespace}.{default_floating_ip}.sslip.io"}
		if any(condition.type == "Progressing" and condition.reason == "ProgressDeadlineExceeded" for condition in conditions):
			condition = next(condition for condition in conditions if condition.type == "Progressing" and condition.reason == "ProgressDeadlineExceeded")
			return {"status": "Failed", "summary": f"Deployment '{deployment_name}' failed to become ready.", "reason": condition.message or condition.reason, "details": details}
		if any(condition.type == "Progressing" and condition.status == "True" for condition in conditions):
			condition = next(condition for condition in conditions if condition.type == "Progressing" and condition.status == "True")
			return {"status": "Pending", "summary": f"Deployment '{deployment_name}' is progressing.", "reason": condition.message or condition.reason or "Deployment rollout is in progress.", "details": details}
		if details["ready_replicas"] > 0:
			return {"status": "Running", "summary": f"Deployment '{deployment_name}' has ready replicas.", "reason": "At least one replica is ready.", "details": details, "url": f"http://{name}.{namespace}.{default_floating_ip}.sslip.io"}
		if details["replicas"] > 0:
			return {"status": "Pending", "summary": f"Deployment '{deployment_name}' is waiting for replicas.", "reason": "Replicas exist but none are ready yet.", "details": details}
		# No conditions, no replica counts at all â this isn't a genuine
		# "unknown" state, it's the brief window immediately after a
		# Deployment is created, before Kubernetes has populated *any*
		# status fields yet. Treating this as terminal "Unknown" (as it
		# was previously) caused a real test failure: polling this
		# endpoint milliseconds after deploy_application() creates the
		# Deployment would see this exact empty-everything state and stop
		# polling immediately, even though pods were already
		# ContainerCreating normally moments later. "Pending" is the
		# honest description â rollout hasn't reported in yet, not that
		# something is actually wrong or unclear.
		return {"status": "Pending", "summary": f"Deployment '{deployment_name}' has not reported status yet.", "reason": "No conditions or replica counts have been reported yet â this is normal immediately after creation.", "details": details}
	except client.exceptions.ApiException as exc:
		if exc.status == 404:
			return {"status": "Unknown", "summary": f"Deployment '{deployment_name}' was not found.", "reason": f"Kubernetes returned HTTP 404 in namespace '{namespace}'.", "details": {"deployment_name": deployment_name, "http_status": exc.status}}
		return {"status": "Unknown", "summary": f"Unable to read deployment '{deployment_name}'.", "reason": str(exc), "details": {"deployment_name": deployment_name, "http_status": exc.status}}


def get_deploy_logs(name: str, namespace: str):
	"""Return logs from every Pod selected by the app deployment label."""
	if not name or not namespace:
		raise ValueError("Both 'name' and 'namespace' are required.")

	_require_kube_client()
	core_api = client.CoreV1Api(k3s_client)
	pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={name}").items
	logs = []
	for pod in pods:
		pod_name = pod.metadata.name
		container_names = [container.name for container in (pod.spec.containers or [])]
		pod_logs = []
		for container_name in container_names:
			try:
				container_logs = core_api.read_namespaced_pod_log(name=pod_name, namespace=namespace, container=container_name)
				pod_logs.append({"container": container_name, "logs": container_logs})
			except client.exceptions.ApiException as exc:
				pod_logs.append({"container": container_name, "logs": None, "error": str(exc), "http_status": exc.status})
			except Exception as exc:
				pod_logs.append({"container": container_name, "logs": None, "error": str(exc), "http_status": 500})
		logs.append({"pod_name": pod_name, "containers": pod_logs})
	return {"deployment_name": f"{name}-deployment", "namespace": namespace, "logs": logs}


def redeploy_application(user_config: Dict[str, Any]):
	pass


def rollback_application(user_config: Dict[str, Any]):
	print("Rollback functionality is not yet implemented.")


__all__ = [
	"check_deploy_status",
	"deploy_application",
	"get_deploy_logs",
	"redeploy_application",
	"rollback_application",
]