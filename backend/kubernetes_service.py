"""HTTP client for the teammate-owned deployment service on the Kubernetes VM."""

import os
import time
from typing import Any, Callable

import requests


class KubernetesDeploymentError(RuntimeError):
    pass


class KubernetesService:
    """Start builds/deployments and poll their status over the private network."""

    BUILD_STATUS_MAP = {
        "Pending": "queued",
        "Running": "started",
        "Succeeded": "completed",
        "Failed": "failed",
        "Unknown": "unknown",
    }
    DEPLOY_STATUS_MAP = {
        "Pending": "queued",
        "Running": "running",
        "Failed": "failed",
        "Unknown": "unknown",
    }

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        session: requests.Session | None = None,
        poll_interval: float | None = None,
        request_timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv(
            "KUBERNETES_DEPLOYER_URL", "http://127.0.0.1:5000"
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
        if not 200 <= response.status_code < 300:
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

    def create_namespace(self, namespace: str) -> dict[str, Any]:
        result = self._request(
            "POST", "/api/namespace", json={"namespace": namespace}
        )
        self._require_success(result, "namespace creation")
        return result

    def start_build(
        self, config: dict[str, Any], github_token: str | None = None
    ) -> dict[str, Any]:
        payload = {
            "deployment_id": config["deployment_id"],
            "project_id": config["project_id"],
            "app_name": config["app_name"],
            "namespace": config["namespace"],
            "git_url": config["git_url"],
            "git_branch": config["git_branch"],
            "dockerfile_path": config["dockerfile_path"],
            "image": config["image"],
        }
        if github_token:
            payload["github_auth"] = {"type": "installation_token", "token": github_token}
        result = self._request("POST", "/api/build", json=payload)
        self._require_success(result, "build")
        return result

    def start_deploy(self, config: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "deployment_id": config["deployment_id"],
            "project_id": config["project_id"],
            "app_name": config["app_name"],
            "namespace": config["namespace"],
            "image": config["image"],
            "container_port": config["container_port"],
            "replicas": config["replicas"],
            "cpu_request": config["cpu_request"],
            "cpu_limit": config["cpu_limit"],
            "memory_request": config["memory_request"],
            "memory_limit": config["memory_limit"],
            "env_vars": config["env_vars"],
            "grace_period_seconds": config["grace_period_seconds"],
            "read_only_rootfs": config["read_only_rootfs"],
        }
        result = self._request("POST", "/api/deploy", json=payload)
        self._require_success(result, "deploy")
        return result

    @staticmethod
    def _require_success(result: dict[str, Any], operation: str) -> None:
        if result.get("status") != "success":
            raise KubernetesDeploymentError(
                str(result.get("message") or f"The {operation} request was rejected")
            )

    def get_status(self, config: dict[str, Any], operation: str) -> dict[str, Any]:
        if operation not in {"build", "deploy"}:
            raise ValueError("operation must be build or deploy")
        path = "/api/build/status" if operation == "build" else "/api/deploy/status"
        result = self._request("POST", path, json={
            "name": config["app_name"],
            "namespace": config["namespace"],
        })
        self._require_success(result, f"{operation} status")
        raw_status = result.get("result")
        status_map = self.BUILD_STATUS_MAP if operation == "build" else self.DEPLOY_STATUS_MAP
        if raw_status not in status_map:
            raise KubernetesDeploymentError(
                f"The deployment service returned an unknown {operation} status"
            )
        return {**result, "raw_status": raw_status, "status": status_map[raw_status]}

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
            if status == "unknown":
                time.sleep(self.poll_interval)
                continue
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
