"""Safe SonarQube health checks and local SonarScanner execution."""

import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests

from config import SonarSettings


logger = logging.getLogger(__name__)

PROJECT_KEY_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
ANALYSIS_URL_PATTERN = re.compile(
    r"ANALYSIS SUCCESSFUL, you can find the results at:\s*(https?://\S+)",
    re.IGNORECASE,
)
QUALITY_GATE_FAILURE_PATTERNS = (
    "quality gate status: failed",
    "quality gate status: error",
    "quality gate failed",
)
REPORT_TASK_PATH = Path(".scannerwork/report-task.txt")
DEFAULT_EXCLUSIONS = ",".join(
    (
        ".git/**",
        "node_modules/**",
        ".next/**",
        "dist/**",
        "build/**",
        "coverage/**",
        "venv/**",
        ".venv/**",
        "__pycache__/**",
    )
)


class SonarQubeError(RuntimeError):
    """Base error for safe, user-displayable SonarQube failures."""


class SonarQubeUnavailableError(SonarQubeError):
    """The configured SonarQube server is not ready or reachable."""


class SonarScannerError(SonarQubeError):
    """SonarScanner could not complete analysis."""


@dataclass(frozen=True)
class SonarAnalysisResult:
    project_key: str
    commit_sha: str
    success: bool
    quality_gate: str | None
    scanner_exit_code: int
    analysis_url: str | None = None
    error: str | None = None
    conditions: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_project_key(repository_id: str) -> str:
    """Create a stable SonarQube key from an internal repository identifier."""
    cleaned = PROJECT_KEY_PATTERN.sub("-", repository_id.strip()).strip("-.:_")
    if not cleaned:
        raise SonarScannerError("Repository identifier cannot form a SonarQube project key")
    return f"buet-paas:{cleaned}"[:400]


class SonarQubeService:
    def __init__(
        self,
        settings: SonarSettings,
        *,
        session: requests.Session | None = None,
        workspace_root: str | Path = "/tmp",
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.workspace_root = Path(workspace_root).resolve()

    def check_health(self, timeout: float = 5.0) -> dict[str, Any]:
        logger.info("SonarQube health check started")
        try:
            response = self.session.get(
                f"{self.settings.host_url}/api/system/status", timeout=timeout
            )
            response.raise_for_status()
            status = str(response.json().get("status", "UNKNOWN")).upper()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("SonarQube health check failed: %s", self._safe_error(exc))
            return {"available": False, "status": "DOWN"}

        available = status == "UP"
        logger.info(
            "SonarQube health check %s (status=%s)",
            "passed" if available else "failed",
            status,
        )
        return {"available": available, "status": status}

    def scan_repository(
        self,
        repository_path: str | Path,
        repository_id: str,
        project_name: str,
        commit_sha: str,
    ) -> SonarAnalysisResult:
        if not self.settings.enabled:
            raise SonarScannerError("SonarQube scanning is disabled")
        if not self.settings.token:
            raise SonarScannerError("SONAR_TOKEN is required when SonarQube scanning is enabled")
        if not COMMIT_SHA_PATTERN.fullmatch(commit_sha):
            raise SonarScannerError("Invalid commit SHA for SonarQube analysis")

        repository = self._validate_workspace(repository_path)
        health = self.check_health()
        if not health["available"]:
            raise SonarQubeUnavailableError(
                f"SonarQube is unavailable (status={health['status']})"
            )

        project_key = generate_project_key(repository_id)
        safe_name = PROJECT_KEY_PATTERN.sub("-", project_name.strip())[:200] or project_key
        command = [
            self.settings.scanner_bin,
            f"-Dsonar.projectKey={project_key}",
            f"-Dsonar.projectName={safe_name}",
            "-Dsonar.sources=.",
            f"-Dsonar.scm.revision={commit_sha.lower()}",
            "-Dsonar.qualitygate.wait=true",
            f"-Dsonar.qualitygate.timeout={self.settings.scan_timeout}",
            f"-Dsonar.exclusions={DEFAULT_EXCLUSIONS}",
        ]
        environment = os.environ.copy()
        environment["SONAR_HOST_URL"] = self.settings.host_url
        environment["SONAR_TOKEN"] = self.settings.token

        logger.info(
            "Security scan started (repository=%s, project_key=%s, commit=%s)",
            repository_id,
            project_key,
            commit_sha,
        )
        try:
            completed = subprocess.run(
                command,
                cwd=str(repository),
                env=environment,
                capture_output=True,
                text=True,
                timeout=self.settings.scan_timeout + 15,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise SonarScannerError("SonarScanner executable was not found") from exc
        except subprocess.TimeoutExpired as exc:
            logger.error("Security scan timed out (project_key=%s)", project_key)
            raise SonarScannerError("SonarScanner timed out") from exc
        except OSError as exc:
            raise SonarScannerError(f"SonarScanner could not start: {self._safe_error(exc)}") from exc

        output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        lowered = output.lower()
        analysis_url_match = ANALYSIS_URL_PATTERN.search(output)
        analysis_url = analysis_url_match.group(1) if analysis_url_match else None

        if any(pattern in lowered for pattern in QUALITY_GATE_FAILURE_PATTERNS):
            quality_gate = "ERROR"
            conditions: list[dict[str, Any]] = []
            issues: list[dict[str, Any]] = []
            try:
                api_gate, metadata_url, conditions = self._get_quality_gate_for_analysis(
                    repository
                )
                if api_gate != "OK":
                    quality_gate = api_gate
                analysis_url = metadata_url or analysis_url
                issues = self._get_open_issues(project_key)
            except SonarQubeError:
                logger.warning(
                    "Quality Gate details were unavailable (project_key=%s)", project_key
                )
            logger.warning("Quality Gate failed (project_key=%s)", project_key)
            return SonarAnalysisResult(
                project_key=project_key,
                commit_sha=commit_sha.lower(),
                success=False,
                quality_gate=quality_gate,
                scanner_exit_code=completed.returncode,
                analysis_url=analysis_url,
                error="SonarQube Quality Gate failed",
                conditions=conditions,
                issues=issues,
            )

        if completed.returncode == 0:
            quality_gate, metadata_url, conditions = self._get_quality_gate_for_analysis(
                repository
            )
            analysis_url = metadata_url or analysis_url
            if quality_gate != "OK":
                issues = self._get_open_issues(project_key)
                logger.warning(
                    "Quality Gate failed (project_key=%s, status=%s)",
                    project_key,
                    quality_gate,
                )
                return SonarAnalysisResult(
                    project_key=project_key,
                    commit_sha=commit_sha.lower(),
                    success=False,
                    quality_gate=quality_gate,
                    scanner_exit_code=completed.returncode,
                    analysis_url=analysis_url,
                    error=f"SonarQube Quality Gate status is {quality_gate}",
                    conditions=conditions,
                    issues=issues,
                )

            logger.info("Quality Gate passed (project_key=%s)", project_key)
            return SonarAnalysisResult(
                project_key=project_key,
                commit_sha=commit_sha.lower(),
                success=True,
                quality_gate="OK",
                scanner_exit_code=completed.returncode,
                analysis_url=analysis_url,
            )

        error = self._classify_scanner_failure(lowered)
        logger.error("Scanner failed (project_key=%s, exit_code=%s): %s", project_key, completed.returncode, error)
        raise SonarScannerError(error)

    def _get_quality_gate_for_analysis(
        self, repository: Path
    ) -> tuple[str, str | None, list[dict[str, Any]]]:
        """Read the scanner task metadata and verify this exact analysis via Web API."""
        metadata_path = repository / REPORT_TASK_PATH
        try:
            metadata = {
                key: value
                for line in metadata_path.read_text(encoding="utf-8").splitlines()
                if "=" in line
                for key, value in [line.split("=", 1)]
            }
        except OSError as exc:
            raise SonarScannerError(
                "SonarScanner completed without analysis task metadata"
            ) from exc

        ce_task_id = metadata.get("ceTaskId")
        if not ce_task_id:
            raise SonarScannerError("SonarScanner analysis task ID is missing")

        task_payload = self._api_get("/api/ce/task", params={"id": ce_task_id})
        task = task_payload.get("task", {})
        if str(task.get("status", "")).upper() != "SUCCESS":
            raise SonarScannerError(
                f"SonarQube analysis processing failed (status={task.get('status', 'UNKNOWN')})"
            )
        analysis_id = task.get("analysisId")
        if not analysis_id:
            raise SonarScannerError("SonarQube analysis ID is missing")

        gate_payload = self._api_get(
            "/api/qualitygates/project_status", params={"analysisId": analysis_id}
        )
        gate_status = str(
            gate_payload.get("projectStatus", {}).get("status", "NONE")
        ).upper()
        if gate_status == "NONE":
            raise SonarScannerError("No SonarQube Quality Gate result was returned")
        conditions = [
            {
                "status": str(condition.get("status", "UNKNOWN")).upper(),
                "metric": str(condition.get("metricKey", "unknown")),
                "comparator": condition.get("comparator"),
                "actual_value": condition.get("actualValue"),
                "error_threshold": condition.get("errorThreshold"),
            }
            for condition in gate_payload.get("projectStatus", {}).get("conditions", [])
            if isinstance(condition, dict)
        ]
        return gate_status, metadata.get("dashboardUrl"), conditions

    def _get_open_issues(self, project_key: str) -> list[dict[str, Any]]:
        """Return a bounded, display-safe issue summary with locations when available."""
        try:
            payload = self._api_get(
                "/api/issues/search",
                params={
                    "componentKeys": project_key,
                    "resolved": "false",
                    "ps": "20",
                },
            )
        except SonarQubeError as exc:
            logger.warning(
                "Could not load SonarQube issue details (project_key=%s): %s",
                project_key,
                exc,
            )
            return []

        issues: list[dict[str, Any]] = []
        component_prefix = f"{project_key}:"
        for issue in payload.get("issues", []):
            if not isinstance(issue, dict):
                continue
            component = str(issue.get("component", ""))
            path = (
                component.removeprefix(component_prefix)
                if component.startswith(component_prefix)
                else component
            )
            issues.append(
                {
                    "key": issue.get("key"),
                    "message": str(issue.get("message", "Security issue detected"))[:500],
                    "severity": issue.get("severity"),
                    "type": issue.get("type"),
                    "rule": issue.get("rule"),
                    "file": path or None,
                    "line": issue.get("line"),
                }
            )
        return issues

    def _api_get(self, path: str, *, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.settings.host_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.settings.token}"},
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code in {401, 403}:
                raise SonarScannerError("SonarQube authentication failed") from exc
            raise SonarScannerError("SonarQube API request failed") from exc
        except (requests.RequestException, ValueError) as exc:
            raise SonarQubeUnavailableError(
                "SonarQube became unavailable while checking the Quality Gate"
            ) from exc

    def _validate_workspace(self, repository_path: str | Path) -> Path:
        repository = Path(repository_path).resolve()
        try:
            repository.relative_to(self.workspace_root)
        except ValueError as exc:
            raise SonarScannerError("Repository workspace is outside the allowed root") from exc
        if not repository.is_dir() or not (repository / ".git").exists():
            raise SonarScannerError("Repository workspace is not a checked-out Git repository")
        return repository

    def _classify_scanner_failure(self, output: str) -> str:
        if "not authorized" in output or "authentication" in output or "unauthorized" in output:
            return "SonarQube authentication failed"
        if "connection refused" in output or "fail to get bootstrap index" in output:
            return "SonarQube became unavailable during analysis"
        return "SonarScanner analysis failed"

    def _safe_error(self, error: object) -> str:
        message = str(error)
        token = self.settings.token
        return message.replace(token, "[REDACTED]") if token else message
