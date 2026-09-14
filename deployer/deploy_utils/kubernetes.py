"""Kubernetes client initialization shared by deployer operations."""

import os

from kubernetes import client, config


k3s_client = None
kube_error = None


def _initialize_kube_client():
    global k3s_client, kube_error
    k3s_client = None
    kube_error = None

    try:
        if os.getenv("KUBERNETES_SERVICE_HOST") or os.getenv("KUBERNETES_SERVICE_PORT"):
            config.load_incluster_config()
            k3s_client = client.ApiClient()
            return
    except Exception as exc:  # pragma: no cover - environment dependent
        kube_error = exc

    kubeconfig_path = os.getenv("KUBECONFIG") or os.path.expanduser("~/.kube/config")
    try:
        if kubeconfig_path and os.path.exists(kubeconfig_path):
            config.load_kube_config(config_file=kubeconfig_path)
            k3s_client = client.ApiClient()
            return
    except Exception as exc:  # pragma: no cover - environment dependent
        kube_error = exc

    try:
        config.load_kube_config()
        k3s_client = client.ApiClient()
    except Exception as exc:  # pragma: no cover - environment dependent
        k3s_client = None
        kube_error = exc


def _require_kube_client():
    if k3s_client is None:
        raise RuntimeError(f"Kubernetes client is unavailable: {kube_error}")
    return k3s_client


_initialize_kube_client()