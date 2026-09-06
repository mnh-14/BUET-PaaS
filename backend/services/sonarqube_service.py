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
MAX_DIAGNOSTIC_LINES = 200
MAX_DIAGNOSTIC_LINE_LENGTH = 500
DIAGNOSTIC_HEAD_LINES = 40
MAX_SOURCE_INVENTORY_FILES = 200
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
    "venv",
    ".venv",
    "__pycache__",
}
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
URL_CREDENTIALS_PATTERN = re.compile(
    r"(?P<scheme>https?://)(?P<credentials>[^/@\s]+)@", re.IGNORECASE
)
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)([\"']?\b(?:sonar[._-]?(?:token|login)|token|login|password|secret|"
    r"authorization|api[_-]?key|access[_-]?token|client[_-]?secret)\b[\"']?"
    r"\s*[:=]\s*[\"']?)([^\"'\s,;&}]+)"
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

    def __init__(
        self, message: str, *, diagnostics: list[str] | None = None
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or []


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
    diagnostics: list[str] = field(default_factory=list)

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
        if self.settings.verbose:
            command.append("-Dsonar.verbose=true")
        environment = os.environ.copy()
        environment["SONAR_HOST_URL"] = self.settings.host_url
        environment["SONAR_TOKEN"] = self.settings.token

        if self.settings.verbose:
            self._log_source_inventory(repository, commit_sha)
            logger.warning(
                "SonarScanner invocation (cwd=%s, command=%s)",
                repository,
                " ".join(command),
            )

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
            partial_output = "\n".join(
                self._output_text(value) for value in (exc.stdout, exc.stderr) if value
            )
            raise SonarScannerError(
                "SonarScanner timed out",
                diagnostics=self._sanitize_diagnostics(partial_output),
            ) from exc
        except OSError as exc:
            raise SonarScannerError(f"SonarScanner could not start: {self._safe_error(exc)}") from exc

        output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        diagnostics = self._sanitize_diagnostics(output)
        logger.warning(
            "SonarScanner finished (project_key=%s, exit_code=%s, diagnostic_lines=%s)",
            project_key,
            completed.returncode,
            len(diagnostics),
        )
        if self.settings.verbose:
            for line in diagnostics:
                logger.warning("SonarScanner output: %s", line)
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
                diagnostics=diagnostics,
            )

        if completed.returncode == 0:
            try:
                quality_gate, metadata_url, conditions = self._get_quality_gate_for_analysis(
                    repository
                )
            except SonarQubeError as exc:
                exc.diagnostics = diagnostics
                raise
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
                    diagnostics=diagnostics,
                )

            logger.info("Quality Gate passed (project_key=%s)", project_key)
            return SonarAnalysisResult(
                project_key=project_key,
                commit_sha=commit_sha.lower(),
                success=True,
                quality_gate="OK",
                scanner_exit_code=completed.returncode,
                analysis_url=analysis_url,
                diagnostics=diagnostics,
            )

        error = self._classify_scanner_failure(output)
        logger.error("Scanner failed (project_key=%s, exit_code=%s): %s", project_key, completed.returncode, error)
        raise SonarScannerError(error, diagnostics=diagnostics)

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

    def _log_source_inventory(self, repository: Path, commit_sha: str) -> None:
        """Log a bounded, content-free inventory of the checkout being scanned."""
        included_files: list[str] = []
        extension_counts: dict[str, int] = {}
        excluded_counts: dict[str, int] = {}

        for root, directory_names, file_names in os.walk(repository):
            kept_directories = []
            for directory_name in directory_names:
                if directory_name in EXCLUDED_DIRECTORY_NAMES:
                    excluded_counts[directory_name] = excluded_counts.get(directory_name, 0) + 1
                else:
                    kept_directories.append(directory_name)
            directory_names[:] = kept_directories

            root_path = Path(root)
            for file_name in file_names:
                path = root_path / file_name
                try:
                    relative_path = path.relative_to(repository).as_posix()
                except ValueError:
                    continue
                extension = path.suffix.lower() or "[no extension]"
                extension_counts[extension] = extension_counts.get(extension, 0) + 1
                if len(included_files) < MAX_SOURCE_INVENTORY_FILES:
                    included_files.append(relative_path)

        total_files = sum(extension_counts.values())
        logger.warning(
            "SonarScanner checkout inventory (cwd=%s, expected_commit=%s, files=%s, "
            "extensions=%s, excluded_directories=%s)",
            repository,
            commit_sha.lower(),
            total_files,
            dict(sorted(extension_counts.items())),
            dict(sorted(excluded_counts.items())),
        )
        for relative_path in included_files:
            logger.warning("SonarScanner candidate file: %s", relative_path)
        if total_files > len(included_files):
            logger.warning(
                "SonarScanner candidate file list truncated (%s of %s shown)",
                len(included_files),
                total_files,
            )

    def _classify_scanner_failure(self, output: str) -> str:
        lowered = output.lower()
        if "not authorized" in lowered or "authentication" in lowered or "unauthorized" in lowered:
            return "SonarQube authentication failed"
        if "connection refused" in lowered or "fail to get bootstrap index" in lowered:
            return "SonarQube became unavailable during analysis"
        if "outofmemoryerror" in lowered or "java heap space" in lowered:
            return "SonarScanner ran out of memory while analyzing the repository"
        if "unsupportedclassversionerror" in lowered:
            return "SonarScanner requires a newer Java runtime"
        if (
            "no files nor directories matching" in lowered
            or "no files to be analyzed" in lowered
            or "no supported source files" in lowered
        ):
            return "SonarScanner did not find supported source files to analyze"
        if "project not found" in lowered or "could not find a default branch" in lowered:
            return "SonarQube could not prepare the analysis project"

        safe_output = self._safe_error(output)
        informative_lines = []
        for raw_line in safe_output.splitlines():
            line = raw_line.strip()
            lowered = line.lower()
            if line and ("error" in lowered or "failed" in lowered or "exception" in lowered):
                informative_lines.append(line[:300])
        if informative_lines:
            return "SonarScanner analysis failed: " + " | ".join(informative_lines[-3:])
        return "SonarScanner analysis failed without a specific reason"

    def _safe_error(self, error: object) -> str:
        return self._redact_text(str(error))

    def _redact_text(self, message: str) -> str:
        token = self.settings.token
        if token:
            message = message.replace(token, "[REDACTED]")
        message = URL_CREDENTIALS_PATTERN.sub(
            lambda match: f"{match.group('scheme')}[REDACTED]@", message
        )
        message = BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED]", message)
        return SENSITIVE_VALUE_PATTERN.sub(r"\1[REDACTED]", message)

    def _sanitize_diagnostics(self, output: str) -> list[str]:
        """Return bounded scanner output suitable for persistence and display."""
        safe_output = ANSI_ESCAPE_PATTERN.sub("", self._redact_text(output))
        lines = [
            line.strip()[:MAX_DIAGNOSTIC_LINE_LENGTH]
            for line in safe_output.splitlines()
            if line.strip()
        ]
        if len(lines) <= MAX_DIAGNOSTIC_LINES:
            return lines

        tail_count = MAX_DIAGNOSTIC_LINES - DIAGNOSTIC_HEAD_LINES - 1
        omitted = len(lines) - DIAGNOSTIC_HEAD_LINES - tail_count
        return [
            *lines[:DIAGNOSTIC_HEAD_LINES],
            f"... {omitted} diagnostic lines omitted ...",
            *lines[-tail_count:],
        ]

    @staticmethod
    def _output_text(value: str | bytes) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value
