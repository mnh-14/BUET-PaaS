"""Validated project settings translated into the deployer's flat config."""

import re
from typing import Any


RESOURCE_TIERS: dict[str, dict[str, Any]] = {
    "small": {
        "replicas": 1,
        "cpu_request": "100m",
        "cpu_limit": "250m",
        "memory_request": "128Mi",
        "memory_limit": "256Mi",
    },
    "medium": {
        "replicas": 2,
        "cpu_request": "250m",
        "cpu_limit": "500m",
        "memory_request": "256Mi",
        "memory_limit": "512Mi",
    },
    "large": {
        "replicas": 2,
        "cpu_request": "500m",
        "cpu_limit": "1000m",
        "memory_request": "512Mi",
        "memory_limit": "1Gi",
    },
}

DEFAULT_CONTAINER_PORT = 8080


def kubernetes_name(value: str, *, maximum: int = 63) -> str:
    """Return a DNS-label-compatible Kubernetes resource name."""
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    normalized = re.sub(r"-+", "-", normalized)[:maximum].rstrip("-")
    if not normalized:
        raise ValueError("The value cannot produce a valid Kubernetes name")
    return normalized


def build_deployer_config(project: dict, deployment: dict) -> dict[str, Any]:
    size = project.get("instance_size", "small")
    if size not in RESOURCE_TIERS:
        raise ValueError(f"Unknown instance size: {size}")
    namespace = kubernetes_name(str(project["user_id"]))
    app_name = kubernetes_name(project.get("app_name") or project["project_name"])
    image_name = f"{app_name}-{namespace}-build:latest"
    return {
        "project_id": project["project_id"],
        "deployment_id": deployment["deployment_id"],
        "app_name": app_name,
        "namespace": namespace,
        "git_url": project["repo_url"],
        "git_branch": project.get("deploy_branch", "main"),
        "dockerfile_path": project.get("dockerfile_path", "Dockerfile"),
        "image": image_name,
        "container_port": int(project.get("container_port", DEFAULT_CONTAINER_PORT)),
        "env_vars": project.get("env_vars", {}),
        "grace_period_seconds": 30,
        "read_only_rootfs": False,
        **RESOURCE_TIERS[size],
    }
