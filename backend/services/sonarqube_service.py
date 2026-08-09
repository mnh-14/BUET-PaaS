"""Safe SonarQube health checks and local SonarScanner execution."""

import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass
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
            logger.warning("Quality Gate failed (project_key=%s)", project_key)
            return SonarAnalysisResult(
                project_key=project_key,
                commit_sha=commit_sha.lower(),
                success=False,
                quality_gate="ERROR",
                scanner_exit_code=completed.returncode,
                analysis_url=analysis_url,
                error="SonarQube Quality Gate failed",
            )

        if completed.returncode == 0:
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
