"""HTTP client for the teammate-owned deployment service on the Kubernetes VM."""

import os
import time
from typing import Any, Callable

import requests


class KubernetesDeploymentError(RuntimeError):
    """Safe, structured failure returned by the deployment-service client."""

    def __init__(
        self,
        summary: str,
        *,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(summary)
        self.summary = summary
        self.reason = reason or summary
        self.details = details or {}


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
        except requests.Timeout as exc:
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service timed out",
                reason=(
                    f"No response was received for {path} within "
                    f"{self.request_timeout:g} seconds."
                ),
                details={"endpoint": path, "timeout_seconds": self.request_timeout},
            ) from exc
        except requests.ConnectionError as exc:
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service is unreachable",
                reason="The backend could not establish a connection to the deployment service.",
                details={"endpoint": path},
            ) from exc
        except requests.RequestException as exc:
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service request failed",
                reason="The HTTP request ended before a valid response was received.",
                details={"endpoint": path},
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            if not 200 <= response.status_code < 300:
                raise KubernetesDeploymentError(
                    "The Kubernetes deployment service rejected the request",
                    reason=f"The service returned HTTP {response.status_code} without JSON details.",
                    details={"endpoint": path, "http_status": response.status_code},
                ) from exc
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service returned invalid JSON",
                reason="The service responded successfully, but its response was not valid JSON.",
                details={"endpoint": path, "http_status": response.status_code},
            ) from exc

        if not 200 <= response.status_code < 300:
            api_message = body.get("message") if isinstance(body, dict) else None
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service rejected the request",
                reason=str(api_message or f"The service returned HTTP {response.status_code}."),
                details={"endpoint": path, "http_status": response.status_code},
            )
        if not isinstance(body, dict):
            raise KubernetesDeploymentError(
                "The Kubernetes deployment service returned an invalid response",
                reason="The response JSON must be an object.",
                details={"endpoint": path, "http_status": response.status_code},
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
                f"Kubernetes {operation} request was rejected",
                reason=str(result.get("message") or "The service did not report success."),
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
                f"The deployment service returned an unknown {operation} status",
                reason=f"Received result value {raw_status!r}.",
                details={"operation": operation, "result": raw_status},
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
        last_result: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                result = self.get_status(config, operation)
                consecutive_errors = 0
                last_result = result
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
                api_summary = result.get("summary")
                api_reason = result.get("reason")
                raise KubernetesDeploymentError(
                    str(api_summary or f"Kubernetes {operation} failed"),
                    reason=str(
                        api_reason
                        or result.get("error")
                        or result.get("message")
                        or f"The Kubernetes {operation} reported failure."
                    ),
                    details=result.get("details")
                    if isinstance(result.get("details"), dict)
                    else {},
                )
            if status != previous_status:
                on_update(result)
                previous_status = status
            if (operation == "build" and status == "completed") or (
                operation == "deploy" and status == "running"
            ):
                return result
            time.sleep(self.poll_interval)
        reason = f"The {operation} did not reach a successful state within {timeout:g} seconds."
        details: dict[str, Any] = {"operation": operation, "timeout_seconds": timeout}
        if last_result:
            if last_result.get("summary"):
                reason = f"{reason} Last update: {last_result['summary']}"
            if last_result.get("reason"):
                details["last_reason"] = last_result["reason"]
            if isinstance(last_result.get("details"), dict):
                details["last_details"] = last_result["details"]
            details["last_status"] = last_result.get("raw_status")
        raise KubernetesDeploymentError(
            f"Kubernetes {operation} status timed out",
            reason=reason,
            details=details,
        )
