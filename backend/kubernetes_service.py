"""HTTP client for the teammate-owned deployment service on the Kubernetes VM."""

import os
import time
from typing import Any, Callable

import requests


class KubernetesDeploymentError(RuntimeError):
    pass


class KubernetesService:
    """Start builds/deployments and poll their status over the private network."""

    BUILD_STATUSES = {"queued", "started", "completed", "failed"}
    DEPLOY_STATUSES = {"queued", "started", "running", "failed"}

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        session: requests.Session | None = None,
        poll_interval: float | None = None,
        request_timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv(
            "KUBERNETES_DEPLOYER_URL", "http://127.0.0.1:8080"
        )).rstrip("/")
        self.token = token if token is not None else os.getenv(
            "KUBERNETES_DEPLOYER_TOKEN", ""
        )
        self.session = session or requests.Session()
        self.poll_interval = poll_interval if poll_interval is not None else float(
            os.getenv("KUBERNETES_STATUS_POLL_INTERVAL", "5")
        )
        self.request_timeout = request_timeout if request_timeout is not None else float(
            os.getenv("KUBERNETES_REQUEST_TIMEOUT", "15")
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=self.request_timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service is unavailable"
            ) from exc
        if response.status_code not in {200, 202}:
            raise KubernetesDeploymentError(
                f"The Kubernetes deployment service returned HTTP {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service returned invalid JSON"
            ) from exc
        if not isinstance(body, dict):
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service returned an invalid response"
            )
        return body

    @staticmethod
    def _identity(config: dict[str, Any]) -> dict[str, Any]:
        return {
            "deployment_id": config["deployment_id"],
            "project_id": config["project_id"],
            "project_name": config["app_name"],
            "namespace": config["namespace"],
        }

    def start_build(
        self, config: dict[str, Any], github_token: str | None = None
    ) -> dict[str, Any]:
        payload = {
            **self._identity(config),
            "git_url": config["git_url"],
            "git_branch": config["git_branch"],
            "dockerfile_path": config["dockerfile_path"],
            "image": config["image"],
        }
        if github_token:
            payload["github_auth"] = {"type": "installation_token", "token": github_token}
        return self._request("POST", "/api/v1/build", json=payload)

    def start_deploy(self, config: dict[str, Any]) -> dict[str, Any]:
        payload = {
            **self._identity(config),
            "image": config["image"],
            "container_port": config["container_port"],
            "replicas": config["replicas"],
            "resources": {
                "cpu_request": config["cpu_request"],
                "cpu_limit": config["cpu_limit"],
                "memory_request": config["memory_request"],
                "memory_limit": config["memory_limit"],
            },
            "env_vars": config["env_vars"],
            "grace_period_seconds": config["grace_period_seconds"],
            "read_only_rootfs": config["read_only_rootfs"],
        }
        return self._request("POST", "/api/v1/deploy", json=payload)

    def get_status(self, config: dict[str, Any], operation: str) -> dict[str, Any]:
        if operation not in {"build", "deploy"}:
            raise ValueError("operation must be build or deploy")
        result = self._request("GET", "/api/v1/status", params={
            "project_name": config["app_name"],
            "namespace": config["namespace"],
            "deployment_id": config["deployment_id"],
            "type": operation,
        })
        status = result.get("status")
        allowed = self.BUILD_STATUSES if operation == "build" else self.DEPLOY_STATUSES
        if status not in allowed:
            raise KubernetesDeploymentError(
                f"The deployment service returned an unknown {operation} status"
            )
        if operation == "deploy" and status == "running" and not result.get("url"):
            raise KubernetesDeploymentError(
                "The deployment service reported running without a public URL"
            )
        return result

    def wait_for_status(
        self,
        config: dict[str, Any],
        operation: str,
        timeout: float,
        on_update: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        previous_status = None
        consecutive_errors = 0
        while time.monotonic() < deadline:
            try:
                result = self.get_status(config, operation)
                consecutive_errors = 0
            except KubernetesDeploymentError:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    raise
                time.sleep(self.poll_interval)
                continue
            status = result["status"]
            if status == "failed":
                raise KubernetesDeploymentError(
                    str(result.get("error") or result.get("message") or f"{operation.title()} failed")
                )
            if status != previous_status:
                on_update(result)
                previous_status = status
            if (operation == "build" and status == "completed") or (
                operation == "deploy" and status == "running"
            ):
                return result
            time.sleep(self.poll_interval)
        raise KubernetesDeploymentError(f"Kubernetes {operation} status timed out")
