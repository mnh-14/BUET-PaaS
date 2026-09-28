"""Project-scoped database provisioning and lifecycle helpers."""

from typing import Any, Dict, List

from kubernetes import client, utils

from k3s_conf import DatabaseManifestBuilder

from .kubernetes import _require_kube_client, k3s_client


def provision_database(user_config: Dict[str, Any]):
    """Apply the DatabaseManifestBuilder resources for the given project namespace."""
    if not isinstance(user_config, dict):
        raise ValueError("user_config must be a dictionary")

    _require_kube_client()

    if not user_config.get("app_name"):
        raise ValueError("'app_name' is required.")
    if not user_config.get("namespace"):
        raise ValueError("'namespace' is required.")
    if not user_config.get("engine"):
        raise ValueError("'engine' is required.")

    manifest_builder = DatabaseManifestBuilder(user_config)
    manifest_as_list = manifest_builder.build_all_listed()
    utils.create_from_dict(k3s_client, data=manifest_as_list)
    return manifest_as_list


def check_database_status(name: str, namespace: str):
    """Return database workload status together with a summary and reason."""
    if not name or not namespace:
        raise ValueError("Both 'name' and 'namespace' are required.")

    if k3s_client is None:
        return {
            "status": "Unknown",
            "summary": "The database status could not be checked.",
            "reason": "Kubernetes client is not initialized.",
            "details": {},
        }

    statefulset_name = f"{name}-database"
    try:
        apps_api = client.AppsV1Api(k3s_client)
        statefulset = apps_api.read_namespaced_statefulset(name=statefulset_name, namespace=namespace)
        status = statefulset.status or {}
        details = {
            "statefulset_name": statefulset_name,
            "ready_replicas": getattr(status, "ready_replicas", 0) or 0,
            "replicas": getattr(status, "replicas", 0) or 0,
            "updated_replicas": getattr(status, "updated_replicas", 0) or 0,
            "current_replicas": getattr(status, "current_replicas", 0) or 0,
        }

        if getattr(status, "ready_replicas", 0) or 0:
            return {
                "status": "Running",
                "summary": f"Database '{statefulset_name}' is running.",
                "reason": "At least one database replica is ready.",
                "details": details,
            }

        if getattr(status, "replicas", 0) or getattr(status, "current_replicas", 0):
            return {
                "status": "Pending",
                "summary": f"Database '{statefulset_name}' is provisioning.",
                "reason": "The StatefulSet exists, but no replica is ready yet.",
                "details": details,
            }

        return {
            "status": "Pending",
            "summary": f"Database '{statefulset_name}' has not reported readiness yet.",
            "reason": "The StatefulSet exists but has not published readiness information yet.",
            "details": details,
        }
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return {
                "status": "Unknown",
                "summary": f"Database '{statefulset_name}' was not found.",
                "reason": f"Kubernetes returned HTTP 404 in namespace '{namespace}'.",
                "details": {"statefulset_name": statefulset_name, "http_status": exc.status},
            }
        return {
            "status": "Unknown",
            "summary": f"Unable to read database '{statefulset_name}'.",
            "reason": str(exc),
            "details": {"statefulset_name": statefulset_name, "http_status": exc.status},
        }


def get_database_logs(name: str, namespace: str):
    """Return logs from every pod matching the database workload label."""
    if not name or not namespace:
        raise ValueError("Both 'name' and 'namespace' are required.")

    _require_kube_client()

    core_api = client.CoreV1Api(k3s_client)
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={name}").items
    logs: List[Dict[str, Any]] = []

    for pod in pods:
        pod_name = pod.metadata.name
        container_names = [container.name for container in (pod.spec.containers or [])]
        pod_logs = []

        for container_name in container_names:
            try:
                container_logs = core_api.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=namespace,
                    container=container_name,
                )
                pod_logs.append({"container": container_name, "logs": container_logs})
            except client.exceptions.ApiException as exc:
                pod_logs.append({
                    "container": container_name,
                    "logs": None,
                    "error": str(exc),
                    "http_status": exc.status,
                })
            except Exception as exc:  # pragma: no cover - defensive fallback
                pod_logs.append({
                    "container": container_name,
                    "logs": None,
                    "error": str(exc),
                    "http_status": 500,
                })

        logs.append({"pod_name": pod_name, "containers": pod_logs})

    return {
        "statefulset_name": f"{name}-database",
        "namespace": namespace,
        "logs": logs,
    }


def deprovision_database(name: str, namespace: str):
    """Delete the database Secret, Service, and StatefulSet in the project namespace."""
    if not name or not namespace:
        raise ValueError("Both 'name' and 'namespace' are required.")

    _require_kube_client()

    core_api = client.CoreV1Api(k3s_client)
    apps_api = client.AppsV1Api(k3s_client)

    deleted = []
    for resource, kind, delete_func in (
        (f"{name}-database-secret", "Secret", lambda: core_api.delete_namespaced_secret(name=f"{name}-database-secret", namespace=namespace)),
        (f"{name}-database-service", "Service", lambda: core_api.delete_namespaced_service(name=f"{name}-database-service", namespace=namespace)),
        (f"{name}-database", "StatefulSet", lambda: apps_api.delete_namespaced_stateful_set(name=f"{name}-database", namespace=namespace)),
    ):
        try:
            delete_func()
            deleted.append({"kind": kind, "name": resource, "namespace": namespace})
        except client.exceptions.ApiException as exc:
            if exc.status != 404:
                raise

    return {
        "status": "success",
        "name": name,
        "namespace": namespace,
        "deleted": deleted,
        "message": "Database resources are deleted if they existed.",
    }


__all__ = [
    "provision_database",
    "check_database_status",
    "get_database_logs",
    "deprovision_database",
]