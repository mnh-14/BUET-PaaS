"""Kubernetes namespace operations."""

from kubernetes import client

from .kubernetes import _require_kube_client, k3s_client


def create_namespace_if_not_exists(namespace: str):
	if not namespace:
		raise ValueError("Namespace cannot be empty.")
	_require_kube_client()
	core_api = client.CoreV1Api(k3s_client)
	try:
		core_api.read_namespace(name=namespace)
		print(f"Namespace '{namespace}' already exists.")
	except client.exceptions.ApiException as exc:
		if exc.status == 404:
			namespace_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
			core_api.create_namespace(namespace_body)
			print(f"Namespace '{namespace}' created.")
		else:
			raise

__all__ = ["create_namespace_if_not_exists"]