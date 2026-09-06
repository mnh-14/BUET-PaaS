"""Run:
  source venv/bin/activate           # Linux/macOS
  venv\\Scripts\\activate            # Windows
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import os
import stat
import asyncio
import shutil
import subprocess
import threading
import uuid
import re
import tempfile
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, Literal

from auth import (
    clear_session_cookie,
    enforce_same_origin,
    hash_password,
    require_user,
    set_session_cookie,
    verify_password,
)
from config import GitHubAppSettings, SonarSettings
from deployment_service import queue_deployment
from deployment_config import (
    DEFAULT_CONTAINER_PORT as KUBERNETES_DEFAULT_CONTAINER_PORT,
    build_deployer_config,
    kubernetes_name,
)
from kubernetes_service import KubernetesDeploymentError, KubernetesService
from github_app import GitHubAppService
from github_routes import create_github_router
from services.sonarqube_service import (
    SonarQubeError,
    SonarQubeService,
)

from db import (
    users_col,
    projects_col,
    deployments_col,
    github_connections_col,
    github_installations_col,
    init_indexes,
    ping
)

def _force_remove_readonly(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def safe_rmtree(path: str):
    if os.path.exists(path):
        shutil.rmtree(path, onexc=_force_remove_readonly)

DEFAULT_CONTAINER_PORT = KUBERNETES_DEFAULT_CONTAINER_PORT
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

_project_locks: dict[str, threading.Lock] = {}
_project_locks_mutex = threading.Lock()


def get_project_lock(project_id: str) -> threading.Lock:
    """Returns a dedicated lock for a given project_id, creating it if needed."""
    with _project_locks_mutex:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]


def parse_expose_port(dockerfile_dir: str) -> int:
    dockerfile_path = os.path.join(dockerfile_dir, "Dockerfile")
    try:
        with open(dockerfile_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.upper().startswith("EXPOSE"):
                    # handles "EXPOSE 8000" and "EXPOSE 8000/tcp"
                    parts = line.split()
                    if len(parts) >= 2:
                        port_str = parts[1].split("/")[0]  # strip /tcp or /udp
                        port = int(port_str)
                        print(f"  [BUILD] Detected EXPOSE port: {port}")
                        return port
    except Exception as e:
        print(f"  [BUILD] Could not parse Dockerfile for EXPOSE: {e}")

    print(f"  [BUILD] No EXPOSE found — using default port {DEFAULT_CONTAINER_PORT}")
    return DEFAULT_CONTAINER_PORT


def find_dockerfile(work_dir: str) -> str | None:
    """
    Searches the entire cloned repo for a Dockerfile — not just the root.
    Returns the DIRECTORY containing the Dockerfile so docker build
    """
    # 1. Check root first
    if os.path.exists(os.path.join(work_dir, "Dockerfile")):
        print(f"  [BUILD] Dockerfile found at repo root")
        return work_dir

    # 2. Check common subdirectory names before doing a full walk
    common_subdirs = ["server", "app", "backend", "src", "docker", "api", "web"]
    for subdir in common_subdirs:
        candidate = os.path.join(work_dir, subdir, "Dockerfile")
        if os.path.exists(candidate):
            print(f"  [BUILD] Dockerfile found in {subdir}/")
            return os.path.join(work_dir, subdir)

    # 3. Full recursive walk — finds it anywhere
    for root, dirs, files in os.walk(work_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "Dockerfile" in files:
            rel = os.path.relpath(root, work_dir)
            print(f"  [BUILD] Dockerfile found in {rel}/")
            return root

    return None


COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
GIT_CLONE_TIMEOUT_SECONDS = int(os.getenv("GIT_CLONE_TIMEOUT_SECONDS", "300"))
GIT_CHECKOUT_TIMEOUT_SECONDS = int(os.getenv("GIT_CHECKOUT_TIMEOUT_SECONDS", "300"))


def deployment_failure(
    *,
    source: str,
    stage: str,
    title: str,
    summary: str,
    reason: str,
    suggestion: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded, user-displayable failure without credentials or tracebacks."""
    failure: dict[str, Any] = {
        "source": source,
        "stage": stage,
        "title": title[:200],
        "summary": summary[:1000],
        "reason": reason[:1500],
        "suggestion": suggestion[:1000],
    }
    if details:
        failure["details"] = details
    return failure


def sonarqube_error_failure(error: SonarQubeError) -> dict[str, Any]:
    message = str(error)
    lowered = message.lower()
    if "invalid sonarqube configuration" in lowered:
        return deployment_failure(
            source="sonarqube",
            stage="security_scan",
            title="SonarQube configuration is invalid",
            summary=message,
            reason="A required SonarQube backend setting has an invalid value.",
            suggestion="Ask the backend administrator to correct the named SONAR_* setting and restart the backend.",
        )
    if "authentication" in lowered or "sonar_token" in lowered:
        return deployment_failure(
            source="sonarqube",
            stage="security_scan",
            title="SonarQube authentication failed",
            summary=message,
            reason="The backend could not authenticate to SonarQube with its configured token.",
            suggestion="Ask the platform administrator to verify SONAR_TOKEN and its project permissions.",
        )
    if "unavailable" in lowered or "status=down" in lowered:
        return deployment_failure(
            source="sonarqube",
            stage="security_scan",
            title="SonarQube is unavailable",
            summary=message,
            reason="The SonarQube server was not reachable or was not ready during this scan.",
            suggestion="Retry later. If it repeats, ask the SonarQube administrator to check service health and network access.",
        )
    if "executable was not found" in lowered:
        return deployment_failure(
            source="sonarqube",
            stage="security_scan",
            title="SonarScanner is not installed",
            summary=message,
            reason="The backend could not find the configured sonar-scanner executable.",
            suggestion="Ask the backend administrator to install SonarScanner or correct SONAR_SCANNER_BIN.",
        )
    if "timed out" in lowered:
        return deployment_failure(
            source="sonarqube",
            stage="security_scan",
            title="SonarQube scan timed out",
            summary=message,
            reason="The repository analysis did not finish within the configured scan timeout.",
            suggestion="Retry once; for a large repository, ask the backend administrator to increase SONAR_SCAN_TIMEOUT.",
        )
    if "out of memory" in lowered:
        return deployment_failure(
            source="sonarqube",
            stage="security_scan",
            title="SonarScanner ran out of memory",
            summary=message,
            reason="The scanner did not have enough memory to analyze this repository.",
            suggestion="Ask the backend administrator to increase the scanner's Java heap or available memory, then retry.",
        )
    if "newer java runtime" in lowered:
        return deployment_failure(
            source="sonarqube",
            stage="security_scan",
            title="SonarScanner Java version is incompatible",
            summary=message,
            reason="The installed Java runtime is older than the version required by SonarScanner.",
            suggestion="Ask the backend administrator to upgrade Java or use a compatible SonarScanner version.",
        )
    if "supported source files" in lowered:
        return deployment_failure(
            source="sonarqube",
            stage="security_scan",
            title="No supported source files were found",
            summary=message,
            reason="SonarScanner could not find files eligible for analysis in the checked-out repository.",
            suggestion="Verify the repository contains source code and that SonarQube exclusions are not filtering it all out.",
        )
    return deployment_failure(
        source="sonarqube",
        stage="security_scan",
        title="SonarQube analysis could not complete",
        summary=message,
        reason="SonarScanner or the SonarQube API returned an analysis error.",
        suggestion="Review the reason above and the SonarQube analysis link when available, then retry after correcting the reported problem.",
    )


def sonarqube_gate_failure(scan_result: Any) -> dict[str, Any]:
    failed_conditions = [
        condition
        for condition in scan_result.conditions
        if condition.get("status") != "OK"
    ]
    if failed_conditions:
        condition = failed_conditions[0]
        metric = str(condition.get("metric", "quality metric")).replace("_", " ")
        actual = condition.get("actual_value")
        threshold = condition.get("error_threshold")
        reason = f"The failing metric was {metric}"
        if actual is not None:
            reason += f" with an actual value of {actual}"
        if threshold is not None:
            reason += f" against the required threshold {threshold}"
        reason += "."
    else:
        reason = "SonarQube returned a failing Quality Gate result without condition details."
    return deployment_failure(
        source="sonarqube",
        stage="security_scan",
        title="SonarQube Quality Gate failed",
        summary=str(scan_result.error or "The code did not satisfy the configured Quality Gate."),
        reason=reason,
        suggestion="Fix the failed conditions or listed issues, push a new commit, and redeploy.",
        details={
            "quality_gate": scan_result.quality_gate,
            "failed_condition_count": len(failed_conditions),
            "issue_count": len(scan_result.issues),
        },
    )


def pipeline_failure(error: Exception, stage: str) -> dict[str, Any]:
    if isinstance(error, KubernetesDeploymentError):
        is_build = stage.startswith("build")
        return deployment_failure(
            source="kubernetes",
            stage="image_build" if is_build else "application_deployment",
            title="Kubernetes image build failed" if is_build else "Kubernetes deployment failed",
            summary=error.summary,
            reason=error.reason,
            suggestion=(
                "Check the repository Dockerfile and build configuration, then retry. "
                "If the service or cluster is unavailable, contact the Kubernetes administrator."
                if is_build
                else "Check the container port, health endpoint, environment variables, and resource settings. "
                "Contact the Kubernetes administrator if the cluster rejected the manifest."
            ),
            details=error.details,
        )
    if isinstance(error, subprocess.TimeoutExpired):
        timeout = error.timeout
        return deployment_failure(
            source="git",
            stage="source_checkout",
            title="Repository preparation timed out",
            summary=f"Git did not finish within {timeout} seconds.",
            reason="The repository may be large, use Git LFS, or the GitHub connection may be slow.",
            suggestion="Retry once. If it repeats, increase GIT_CLONE_TIMEOUT_SECONDS and GIT_CHECKOUT_TIMEOUT_SECONDS.",
            details={"timeout_seconds": timeout},
        )

    message = str(error)
    if "dockerfile" in message.lower():
        return deployment_failure(
            source="backend",
            stage="source_inspection",
            title="Dockerfile preparation failed",
            summary=message,
            reason="The backend could not locate or prepare the Dockerfile needed for the image build.",
            suggestion="Add a valid Dockerfile to the repository, commit it, and redeploy.",
        )
    if stage == "cloning":
        return deployment_failure(
            source="git",
            stage="source_checkout",
            title="Repository preparation failed",
            summary=message[:1000] or "The repository could not be prepared.",
            reason="GitHub access, the selected commit, or local checkout failed before analysis began.",
            suggestion="Verify repository access and the deployment branch, then retry.",
        )
    return deployment_failure(
        source="backend",
        stage=stage,
        title="Deployment orchestration failed",
        summary="The backend could not complete this deployment stage.",
        reason="An unexpected backend error occurred. Internal details were withheld for safety.",
        suggestion="Retry once. If it repeats, give the deployment ID and failed stage to the platform administrator.",
    )


def _run_git(
    work_dir: str,
    *arguments: str,
    timeout: int = GIT_CHECKOUT_TIMEOUT_SECONDS,
) -> str:
    result = subprocess.run(
        ["git", "-C", work_dir, *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def checkout_and_verify_commit(work_dir: str, expected_commit_sha: str | None) -> str:
    """Checkout one immutable revision and return the verified full SHA."""
    if expected_commit_sha and not COMMIT_SHA_PATTERN.fullmatch(expected_commit_sha):
        raise RuntimeError("Invalid expected commit SHA")

    current_head = _run_git(work_dir, "rev-parse", "HEAD").lower()
    target_sha = (expected_commit_sha or current_head).lower()
    if expected_commit_sha and current_head != target_sha:
        _run_git(work_dir, "fetch", "--depth", "1", "origin", target_sha)
    _run_git(work_dir, "checkout", "--detach", target_sha)
    verified_head = _run_git(work_dir, "rev-parse", "HEAD").lower()
    if verified_head != target_sha:
        raise RuntimeError(
            f"Checked-out commit mismatch: expected {target_sha}, got {verified_head}"
        )
    return verified_head


def resolve_public_branch(repo_url: str, branch: str) -> str:
    result = subprocess.run(
        ["git", "ls-remote", repo_url, f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise HTTPException(status_code=400, detail="Repository branch could not be resolved")
    commit_sha = result.stdout.split()[0].lower()
    if not COMMIT_SHA_PATTERN.fullmatch(commit_sha):
        raise HTTPException(status_code=502, detail="GitHub returned an invalid commit SHA")
    return commit_sha


def clone_repository(
    repo_url: str,
    work_dir: str,
    *,
    installation_id: int | None,
    repository_id: int | None,
    expected_commit_sha: str | None = None,
) -> str | None:
    """Clone public or GitHub App repository without putting credentials in argv."""
    environment = os.environ.copy()
    askpass_path: str | None = None
    try:
        if installation_id is not None:
            if repository_id is None:
                raise RuntimeError("GitHub repository identity is incomplete")
            token = GitHubAppService(
                GitHubAppSettings.from_env(require_complete=True)
            ).create_installation_token(installation_id, repository_id)
            helper = tempfile.NamedTemporaryFile(
                mode="w", prefix="buetpaas-askpass-", suffix=".py", delete=False
            )
            askpass_path = helper.name
            helper.write(
                "#!/usr/bin/env python3\n"
                "import os, sys\n"
                "prompt = sys.argv[1].lower() if len(sys.argv) > 1 else ''\n"
                "print('x-access-token' if 'username' in prompt else os.environ['BUETPAAS_GIT_TOKEN'])\n"
            )
            helper.close()
            os.chmod(askpass_path, stat.S_IRUSR | stat.S_IXUSR)
            environment.update({
                "GIT_ASKPASS": askpass_path,
                "GIT_TERMINAL_PROMPT": "0",
                "BUETPAAS_GIT_TOKEN": token,
            })
        result = subprocess.run(
            ["git", "clone", "--no-checkout", "--filter=blob:none", repo_url, work_dir],
            capture_output=True,
            text=True,
            timeout=GIT_CLONE_TIMEOUT_SECONDS,
            shell=False,
            env=environment,
        )
        if result.returncode != 0:
            message = result.stderr.lower()
            if "authentication" in message or "not found" in message:
                raise RuntimeError("GitHub repository access was denied or revoked")
            raise RuntimeError("Git repository clone failed")
        if expected_commit_sha is None:
            return None
        if not COMMIT_SHA_PATTERN.fullmatch(expected_commit_sha):
            raise RuntimeError("Invalid expected commit SHA")
        target = expected_commit_sha.lower()
        checkout = subprocess.run(
            ["git", "-C", work_dir, "checkout", "--detach", target],
            capture_output=True, text=True, timeout=GIT_CHECKOUT_TIMEOUT_SECONDS,
            shell=False, env=environment,
        )
        if checkout.returncode != 0:
            fetch = subprocess.run(
                ["git", "-C", work_dir, "fetch", "--depth", "1", "origin", target],
                capture_output=True, text=True, timeout=GIT_CLONE_TIMEOUT_SECONDS,
                shell=False, env=environment,
            )
            if fetch.returncode != 0:
                raise RuntimeError("Requested commit is no longer fetchable from GitHub")
            checkout = subprocess.run(
                ["git", "-C", work_dir, "checkout", "--detach", target],
                capture_output=True, text=True, timeout=GIT_CHECKOUT_TIMEOUT_SECONDS,
                shell=False, env=environment,
            )
            if checkout.returncode != 0:
                raise RuntimeError("Requested commit could not be checked out")
        verified = subprocess.run(
            ["git", "-C", work_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, shell=False, env=environment,
        )
        if verified.returncode != 0 or verified.stdout.strip().lower() != target:
            raise RuntimeError("Checked-out commit does not match the requested SHA")
        return target
    finally:
        environment.pop("BUETPAAS_GIT_TOKEN", None)
        if askpass_path:
            try:
                os.unlink(askpass_path)
            except FileNotFoundError:
                pass


def build_and_deploy(
    deployment_id: str,
    project_id: str,
    repo_url: str,
    port: int | None = None,
    env_vars: dict | None = None,
    expected_commit_sha: str | None = None,
    project_name: str | None = None,
    github_installation_id: int | None = None,
    github_repo_id: int | None = None,
    github_full_name: str | None = None,
    branch: str = "main",
):
    work_dir  = f"/tmp/buetpaas_{deployment_id}"
    current_stage = "queued"

    def set_status(
        status: str,
        error: str | None = None,
        url: str | None = None,
        failure: dict[str, Any] | None = None,
    ):
        """Updates deployment document and parent project status."""
        nonlocal current_stage
        if status == current_stage and error is None and url is None:
            return
        previous_stage = current_stage
        current_stage = status
        messages = {
            "cloning": "Fetching source from GitHub",
            "security_scan_running": "Running the SonarQube quality gate",
            "security_scan_passed": "Security quality gate passed",
            "build_queued": "Build is queued on the Kubernetes VM",
            "build_started": "Kubernetes is building and pushing the image",
            "build_done": "Image build completed",
            "deploy_queued": "Deployment is queued on the Kubernetes VM",
            "deploy_started": "Kubernetes is starting the application",
            "running": "Deployment is live",
            "failed": "Deployment failed",
            "security_scan_failed": "Security quality gate failed",
            "security_scan_error": "Security scan could not complete",
        }
        error_summary = failure.get("summary") if failure else error
        fields = {
            "status": status,
            "current_stage": status,
            "status_message": failure.get("title") if failure else messages.get(status, status.replace("_", " ").title()),
            "error_summary": error_summary,
            "failure": failure,
            "public_url": url,
            "updated_at": datetime.now(timezone.utc),
        }
        if status in {"failed", "security_scan_failed", "security_scan_error"}:
            fields["failed_stage"] = previous_stage
        deployments_col().update_one(
            {"deployment_id": deployment_id},
            {"$set": fields}
        )
        projects_col().update_one(
            {"project_id": project_id},
            {"$set": {"current_status": status}}
        )
        print(f"  [{deployment_id[:8]}] status → {status}")

    def set_security_scan(**fields):
        fields["provider"] = "sonarqube"
        deployments_col().update_one(
            {"deployment_id": deployment_id},
            {"$set": {f"security_scan.{key}": value for key, value in fields.items()}},
        )

    project_lock = get_project_lock(project_id)
    with project_lock:
      try:
        set_status("cloning")
        safe_rmtree(work_dir)

        commit_sha = clone_repository(
            repo_url,
            work_dir,
            installation_id=github_installation_id,
            repository_id=github_repo_id,
            expected_commit_sha=expected_commit_sha,
        )
        if commit_sha is None:
            commit_sha = checkout_and_verify_commit(work_dir, expected_commit_sha)
        print(f"  [{deployment_id[:8]}] verified commit {commit_sha}")
        deployments_col().update_one(
            {"deployment_id": deployment_id},
            {"$set": {"commit_sha": commit_sha}},
        )
        projects_col().update_one(
            {"project_id": project_id},
            {"$set": {"deploy_branch": branch}},
        )

        try:
            sonar_settings = SonarSettings.from_env()
        except ValueError as exc:
            error = f"Invalid SonarQube configuration: {exc}"
            failure = sonarqube_error_failure(SonarQubeError(error))
            set_security_scan(
                commit_sha=commit_sha,
                status="error",
                quality_gate=None,
                started_at=None,
                completed_at=datetime.now(timezone.utc),
                error=error,
            )
            set_status("security_scan_error", error=error, failure=failure)
            return
        if sonar_settings.enabled:
            scan_started_at = datetime.now(timezone.utc)
            set_status("security_scan_running")
            set_security_scan(
                project_key=None,
                commit_sha=commit_sha,
                status="running",
                quality_gate=None,
                started_at=scan_started_at,
                completed_at=None,
                error=None,
            )
            try:
                scan_result = SonarQubeService(sonar_settings).scan_repository(
                    work_dir,
                    repository_id=project_id,
                    project_name=project_name or project_id,
                    commit_sha=commit_sha,
                )
            except SonarQubeError as exc:
                failure = sonarqube_error_failure(exc)
                set_security_scan(
                    status="error",
                    completed_at=datetime.now(timezone.utc),
                    error=str(exc),
                )
                set_status("security_scan_error", error=str(exc), failure=failure)
                return
            except Exception:
                # Fail closed without returning an internal traceback or environment data.
                error = "Security scan could not complete"
                set_security_scan(
                    status="error",
                    completed_at=datetime.now(timezone.utc),
                    error=error,
                )
                failure = deployment_failure(
                    source="sonarqube",
                    stage="security_scan",
                    title="Security scan could not complete",
                    summary=error,
                    reason="An unexpected error occurred while coordinating the SonarQube scan.",
                    suggestion="Retry once. If it repeats, give the deployment ID to the backend administrator.",
                )
                set_status("security_scan_error", error=error, failure=failure)
                return

            set_security_scan(
                project_key=scan_result.project_key,
                status="passed" if scan_result.success else "failed",
                quality_gate=scan_result.quality_gate,
                analysis_url=scan_result.analysis_url,
                scanner_exit_code=scan_result.scanner_exit_code,
                conditions=scan_result.conditions,
                issues=scan_result.issues,
                completed_at=datetime.now(timezone.utc),
                error=scan_result.error,
            )
            if not scan_result.success:
                failure = sonarqube_gate_failure(scan_result)
                set_status(
                    "security_scan_failed",
                    error=scan_result.error,
                    failure=failure,
                )
                return
            set_status("security_scan_passed")
        else:
            set_security_scan(
                commit_sha=commit_sha,
                status="skipped",
                quality_gate=None,
                started_at=None,
                completed_at=datetime.now(timezone.utc),
                error=None,
            )

        dockerfile_dir = find_dockerfile(work_dir)
        if not dockerfile_dir:
            raise RuntimeError("No Dockerfile was found in the repository")
        relative_dir = os.path.relpath(dockerfile_dir, work_dir)
        dockerfile_path = (
            "Dockerfile" if relative_dir == "." else f"{relative_dir}/Dockerfile"
        )
        container_port = parse_expose_port(dockerfile_dir)
        if not container_port:
            container_port = KUBERNETES_DEFAULT_CONTAINER_PORT
        projects_col().update_one(
            {"project_id": project_id},
            {"$set": {
                "dockerfile_path": dockerfile_path,
                "container_port": container_port,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        project = projects_col().find_one({"project_id": project_id})
        deployment = deployments_col().find_one({"deployment_id": deployment_id})
        if not project or not deployment:
            raise RuntimeError("Deployment state disappeared before Kubernetes submission")
        deployer_config = build_deployer_config(project, deployment)
        resources = {
            key: deployer_config[key]
            for key in (
                "replicas", "cpu_request", "cpu_limit",
                "memory_request", "memory_limit",
            )
        }
        deployments_col().update_one(
            {"deployment_id": deployment_id},
            {"$set": {
                "dockerfile_path": dockerfile_path,
                "container_port": container_port,
                "image_destination": deployer_config["image"],
                "resources": resources,
            }},
        )

        set_status("build_queued")
        kube = KubernetesService()
        github_token = None
        if github_installation_id is not None:
            github_token = GitHubAppService(
                GitHubAppSettings.from_env(require_complete=True)
            ).create_installation_token(github_installation_id, github_repo_id)
        build_response = kube.start_build(deployer_config, github_token)
        github_token = None
        deployments_col().update_one(
            {"deployment_id": deployment_id},
            {"$set": {
                "deployer.namespace": deployer_config["namespace"],
                "deployer.build_reference": build_response.get("build_id"),
            }},
        )

        build_status_map = {
            "queued": "build_queued",
            "started": "build_started",
            "completed": "build_done",
        }
        kube.wait_for_status(
            deployer_config, "build",
            float(os.getenv("KUBERNETES_BUILD_TIMEOUT", "1800")),
            lambda result: set_status(build_status_map[result["status"]]),
        )

        set_status("deploy_queued")
        deploy_response = kube.start_deploy(deployer_config)
        deployments_col().update_one(
            {"deployment_id": deployment_id},
            {"$set": {"deployer.deploy_reference": deploy_response.get("deploy_id")}},
        )
        deploy_status_map = {
            "queued": "deploy_queued",
            "started": "deploy_started",
            "running": "running",
        }
        final_result = kube.wait_for_status(
            deployer_config, "deploy",
            float(os.getenv("KUBERNETES_DEPLOY_TIMEOUT", "600")),
            lambda result: set_status(
                deploy_status_map[result["status"]], url=result.get("url")
            ),
        )
        url = final_result.get("url")
        projects_col().update_one(
            {"project_id": project_id},
            {"$set": {
                "last_deployed_sha": commit_sha,
                "latest_remote_sha": commit_sha,
                "public_url": url,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        print(f"  [{deployment_id[:8]}] ✓ Running at {url}")

      except Exception as exc:
        failure = pipeline_failure(exc, current_stage)
        print(
            f"  [{deployment_id[:8]}] ✗ FAILED at {failure['stage']}: "
            f"{failure['summary']}"
        )
        set_status("failed", error=failure["summary"], failure=failure)

      finally:
        safe_rmtree(work_dir)


def resume_incomplete_deployments() -> None:
    """Restart interrupted orchestration from MongoDB after a backend restart."""
    active_statuses = [
        "queued", "cloning", "security_scan_running", "security_scan_passed",
        "build_queued", "build_started", "build_done",
        "deploy_queued", "deploy_started",
    ]
    for deployment in deployments_col().find({"status": {"$in": active_statuses}}):
        project = projects_col().find_one({"project_id": deployment["project_id"]})
        if not project:
            continue
        deployments_col().update_one(
            {"deployment_id": deployment["deployment_id"]},
            {"$set": {
                "status": "queued",
                "status_message": "Resuming after backend restart",
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        thread = threading.Thread(
            target=build_and_deploy,
            args=(
                deployment["deployment_id"],
                project["project_id"],
                project["repo_url"],
                None,
                project.get("env_vars", {}),
                deployment.get("commit_sha"),
                project.get("project_name"),
                project.get("github_installation_id"),
                project.get("github_repo_id"),
                project.get("github_full_name"),
                project.get("deploy_branch", "main"),
            ),
            daemon=True,
            name=f"resume-{deployment['deployment_id']}",
        )
        thread.start()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ping()
        print("[DB] MongoDB connection OK.")
    except Exception as e:
        raise RuntimeError(
            f"Cannot connect to MongoDB: {e}\n"
            "Check MONGO_URI in your .env file."
        )
    init_indexes()
    GitHubAppSettings.from_env(require_complete=True)
    resume_incomplete_deployments()
    yield


app = FastAPI(
    title="BUET-PaaS API",
    description="Backend orchestrator for the BUET DevSecOps prototype",
    version="0.2.0",
    lifespan=lifespan
)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BACKEND_DIR, "static")),
    name="static",
)

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(os.path.join(BACKEND_DIR, "static", "index.html"))

class UserCreate(BaseModel):
    user_id:  str       # student roll
    name:     str       # full name
    email:    str       # institutional email
    password: str       # plain text hash

class UserLogin(BaseModel):
    user_id:  str
    password: str

class ProjectCreate(BaseModel):
    github_installation_id: int | None = None
    github_repo_id: int | None = None
    deploy_branch: str = "main"
    repo_url: str | None = None
    user_id: str | None = None  # accepted for legacy clients, never trusted
    project_name: str = "my-project"
    instance_size: Literal["small", "medium", "large"] = "small"
    env_vars: dict[str, str] = Field(default_factory=dict)
class ProjectResponse(BaseModel):
    project_id:    str
    deployment_id: str | None = None
    message:       str


# ──────────────────────────────────────────────────────────────────
# User endpoints
# ──────────────────────────────────────────────────────────────────

@app.post("/api/v1/users", status_code=201)
def create_user(body: UserCreate):
    """
    Register a new student.
    Checks for duplicate roll number and email before inserting.

    Document stored in users collection:
    {
        user_id:        "2105085"
        namespace:      "2105085"
        name:           "Suprio Paul"
        email:          "2105085@cse.buet.ac.bd"
        password_hash:  "sha256_hashed_string"   ← never store plain password
        credit_balance: 100                       ← starting credits
        created_at:     ISODate(...)
    }
    """
    # Check duplicate roll number
    if users_col().find_one({"user_id": body.user_id}):
        raise HTTPException(
            status_code=409,
            detail=f"User with roll {body.user_id} already exists."
        )

    # Check duplicate email
    if users_col().find_one({"email": body.email}):
        raise HTTPException(
            status_code=409,
            detail=f"Email {body.email} is already registered."
        )

    try:
        namespace = kubernetes_name(body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    try:
        KubernetesService().create_namespace(namespace)
    except KubernetesDeploymentError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not provision the user's Kubernetes namespace: {exc}",
        ) from None

    users_col().insert_one({
        "user_id":        body.user_id,
        "namespace":      namespace,
        "name":           body.name,
        "email":          body.email,
        "password_hash":  hash_password(body.password),
        "credit_balance": 100,
        "created_at":     datetime.now(timezone.utc)
    })

    return {
        "message":  "User registered successfully.",
        "user_id":  body.user_id,
        "name":     body.name,
        "namespace": namespace,
    }


@app.post("/api/v1/users/login")
def login(body: UserLogin, response: Response):
    """
    Verify student credentials.
    Returns user profile on success (without password_hash).
    """
    user = users_col().find_one(
        {"user_id": body.user_id},
        {"_id": 0}
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    valid, replacement = verify_password(body.password, user["password_hash"])
    if not valid:
        raise HTTPException(status_code=401, detail="Incorrect password.")
    if replacement:
        users_col().update_one(
            {"user_id": body.user_id}, {"$set": {"password_hash": replacement}}
        )

    # Never return password_hash to the frontend
    user.pop("password_hash", None)
    set_session_cookie(response, body.user_id)

    return {"message": "Login successful.", "user": user}


@app.get("/api/v1/session")
def current_session(user: dict = Depends(require_user)):
    return {"user": user}


@app.post("/api/v1/users/logout")
def logout(request: Request, response: Response):
    enforce_same_origin(request)
    clear_session_cookie(response)
    return {"message": "Logged out."}


@app.get("/api/v1/users/{user_id}")
def get_user(user_id: str, current_user: dict = Depends(require_user)):
    """
    Get a student's profile.
    Never returns password_hash.
    """
    if user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Cannot access another user")
    user = users_col().find_one(
        {"user_id": user_id},
        {"_id": 0, "password_hash": 0}   # exclude sensitive fields
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@app.get("/api/v1/users/{user_id}/projects")
def get_user_projects(user_id: str, current_user: dict = Depends(require_user)):
    """
    Get all projects belonging to a specific student.
    Useful for the dashboard — "show only my projects".
    """
    if user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Cannot access another user's projects")

    projects = list(
        projects_col().find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
    )
    for project in projects:
        latest = deployments_col().find_one(
            {"project_id": project["project_id"]},
            {"_id": 0},
            sort=[("deployed_at", -1)],
        )
        project["deployments"] = [latest] if latest else []
    return projects


@app.post("/api/v1/projects", response_model=ProjectResponse, status_code=202)
def create_project(
    body: ProjectCreate,
    bg: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_user),
):
    enforce_same_origin(request)
    now = datetime.now(timezone.utc)
    project_id = f"proj-{uuid.uuid4().hex[:8]}"

    if body.github_installation_id is not None or body.github_repo_id is not None:
        if body.github_installation_id is None or body.github_repo_id is None:
            raise HTTPException(status_code=400, detail="GitHub installation and repository IDs are both required")
        connection = github_connections_col().find_one({
            "user_id": user["user_id"],
            "installation_id": body.github_installation_id,
            "status": "active",
        })
        installation = github_installations_col().find_one({
            "installation_id": body.github_installation_id, "status": "active"
        })
        if not connection or not installation:
            raise HTTPException(status_code=403, detail="GitHub installation is not connected")
        try:
            github = GitHubAppService(GitHubAppSettings.from_env(require_complete=True))
            repository = github.verify_repository_access(
                body.github_installation_id, body.github_repo_id
            )
            commit_sha = github.resolve_branch_head(
                body.github_installation_id,
                repository["full_name"],
                body.github_repo_id,
                body.deploy_branch,
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        repo_url = f"https://github.com/{repository['full_name']}.git"
        github_fields = {
            "github_repo_id": body.github_repo_id,
            "github_full_name": repository["full_name"],
            "github_installation_id": body.github_installation_id,
            "github_access_status": "active",
        }
    else:
        if not body.repo_url:
            raise HTTPException(status_code=400, detail="Select a GitHub App repository")
        repo_url = body.repo_url
        commit_sha = resolve_public_branch(repo_url, body.deploy_branch)
        github_fields = {
            "github_access_status": "legacy_public",
        }

    app_name = kubernetes_name(body.project_name)
    namespace = kubernetes_name(user.get("namespace") or user["user_id"])
    if projects_col().find_one({"namespace": namespace, "app_name": app_name}):
        raise HTTPException(
            status_code=409,
            detail="A project with this application name already exists",
        )
    project = {
        "project_id": project_id,
        "user_id": user["user_id"],
        "project_name": body.project_name,
        "app_name": app_name,
        "namespace": namespace,
        "repo_url": repo_url,
        "env_vars": body.env_vars,
        "instance_size": body.instance_size,
        "deploy_branch": body.deploy_branch,
        "latest_remote_sha": commit_sha,
        "last_deployed_sha": None,
        "last_commit_checked_at": now,
        "current_status": "not_deployed",
        "created_at": now,
        "updated_at": now,
        **github_fields,
    }
    projects_col().insert_one(project)

    return {
        "project_id":    project_id,
        "deployment_id": None,
        "message": "Project created. Deploy the latest commit when ready."
    }


@app.get("/api/v1/projects")
def list_projects(user: dict = Depends(require_user)):
    """
    Returns ALL projects joined with their latest deployment.
    Frontend uses this for the admin view.
    """
    pipeline = [
        {"$match": {"user_id": user["user_id"]}},
        {"$sort": {"created_at": -1}},
        {
            "$lookup": {
                "from":         "deployments",
                "localField":   "project_id",
                "foreignField": "project_id",
                "as":           "deployments",
                "pipeline": [
                    {"$sort":  {"deployed_at": -1}},
                    {"$limit": 1}
                ]
            }
        },
        {"$unwind": {"path": "$deployments", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id":            0,
                "project_id":     1,
                "user_id":        1,
                "project_name":   1,
                "repo_url":       1,
                "current_status": 1,
                "created_at":     1,
                "deployment_id":  "$deployments.deployment_id",
                "status":         "$deployments.status",
                "public_url":     "$deployments.public_url",
                "error_summary":  "$deployments.error_summary",
                "failure":        "$deployments.failure",
                "failed_stage":   "$deployments.failed_stage",
                "status_message": "$deployments.status_message",
                "instance_size":  1,
                "deployed_at":    "$deployments.deployed_at"
            }
        }
    ]
    return list(projects_col().aggregate(pipeline))


@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str, user: dict = Depends(require_user)):
    project = projects_col().find_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    deployments = list(
        deployments_col()
        .find({"project_id": project_id}, {"_id": 0})
        .sort("deployed_at", -1)
    )

    return {**project, "deployments": deployments}


@app.delete("/api/v1/projects/{project_id}")
def delete_project(
    project_id: str, request: Request, user: dict = Depends(require_user)
):
    """Archive a project locally; the VM API currently has no teardown function."""
    enforce_same_origin(request)
    project = projects_col().find_one(
        {"project_id": project_id, "user_id": user["user_id"]}
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    deployments_col().update_many(
        {"project_id": project_id},
        {"$set": {"status": "stopped", "public_url": None}}
    )
    projects_col().update_one(
        {"project_id": project_id},
        {"$set": {"current_status": "stopped"}}
    )
    return {"message": f"Project {project_id} stopped."}


@app.get("/api/v1/deployments/{deployment_id}")
def get_deployment(deployment_id: str, user: dict = Depends(require_user)):
    owned_project_ids = projects_col().distinct("project_id", {"user_id": user["user_id"]})
    doc = deployments_col().find_one(
        {"deployment_id": deployment_id, "project_id": {"$in": owned_project_ids}},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return doc


@app.get("/api/v1/deployments/{deployment_id}/events")
async def deployment_events(deployment_id: str, user: dict = Depends(require_user)):
    project_ids = projects_col().distinct("project_id", {"user_id": user["user_id"]})
    if not deployments_col().find_one({
        "deployment_id": deployment_id, "project_id": {"$in": project_ids}
    }):
        raise HTTPException(status_code=404, detail="Deployment not found.")

    async def stream():
        previous = None
        while True:
            document = await asyncio.to_thread(
                deployments_col().find_one,
                {"deployment_id": deployment_id},
                {"_id": 0},
            )
            if not document:
                yield "event: error\ndata: {\"detail\":\"Deployment removed\"}\n\n"
                return
            payload = json.dumps(document, default=str, separators=(",", ":"))
            if payload != previous:
                yield f"data: {payload}\n\n"
                previous = payload
            if document.get("status") in {
                "running", "failed", "security_scan_failed",
                "security_scan_error", "stopped",
            }:
                return
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def resolve_project_head(project: dict) -> str:
    branch = project.get("deploy_branch", "main")
    if project.get("github_installation_id"):
        return GitHubAppService(
            GitHubAppSettings.from_env(require_complete=True)
        ).resolve_branch_head(
            project["github_installation_id"],
            project["github_full_name"],
            project["github_repo_id"],
            branch,
        )
    return resolve_public_branch(project["repo_url"], branch)


@app.post("/api/v1/projects/{project_id}/check-update")
def check_project_update(
    project_id: str, request: Request, user: dict = Depends(require_user)
):
    enforce_same_origin(request)
    project = projects_col().find_one(
        {"project_id": project_id, "user_id": user["user_id"]}
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    try:
        latest = resolve_project_head(project)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    checked_at = datetime.now(timezone.utc)
    projects_col().update_one(
        {"project_id": project_id},
        {"$set": {
            "latest_remote_sha": latest,
            "last_commit_checked_at": checked_at,
            "updated_at": checked_at,
        }},
    )
    deployed = project.get("last_deployed_sha")
    return {
        "project_id": project_id,
        "branch": project.get("deploy_branch", "main"),
        "last_deployed_sha": deployed,
        "latest_remote_sha": latest,
        "update_available": deployed != latest,
        "checked_at": checked_at,
    }


@app.post("/api/v1/deployments/redeploy/{project_id}")
def redeploy_project(
    project_id: str,
    bg: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_user),
):
    enforce_same_origin(request)
    project = projects_col().find_one({"project_id": project_id, "user_id": user["user_id"]})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    active = deployments_col().find_one({
        "project_id": project_id,
        "status": {"$in": [
            "queued", "cloning", "security_scan_running",
            "security_scan_passed", "build_queued", "build_started", "build_done",
            "deploy_queued", "deploy_started",
        ]},
    })
    if active:
        raise HTTPException(status_code=409, detail="A deployment is already running")
    branch = project.get("deploy_branch", "main")
    try:
        commit_sha = resolve_project_head(project)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if project.get("last_deployed_sha") == commit_sha:
        raise HTTPException(status_code=409, detail="The latest commit is already deployed")
    projects_col().update_one(
        {"project_id": project_id},
        {"$set": {
            "latest_remote_sha": commit_sha,
            "last_commit_checked_at": datetime.now(timezone.utc),
        }},
    )
    deployment, _ = queue_deployment(
        project,
        commit_sha,
        branch,
        "manual",
        worker=build_and_deploy,
        background_tasks=bg,
    )
    return {
        "deployment_id": deployment["deployment_id"],
        "commit_sha": commit_sha,
        "message":       "Redeployment triggered."
    }

class EnvVarsUpdate(BaseModel):
    env_vars: dict[str, str]

@app.put("/api/v1/projects/{project_id}/env")
def update_env_vars(
    project_id: str, body: EnvVarsUpdate, request: Request,
    user: dict = Depends(require_user),
):
    enforce_same_origin(request)
    project = projects_col().find_one({"project_id": project_id, "user_id": user["user_id"]})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    projects_col().update_one(
        {"project_id": project_id},
        {"$set": {"env_vars": body.env_vars}}
    )
    return {
        "message":  "Env vars updated. They will apply on the next deployment.",
        "env_vars": body.env_vars
    }


@app.get("/api/v1/projects/{project_id}/env")
def get_env_vars(project_id: str, user: dict = Depends(require_user)):
    """Get current env vars for a project (for the frontend to display)."""
    project = projects_col().find_one(
        {"project_id": project_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"env_vars": project.get("env_vars", {})}


@app.get("/health")
def health():
    """Liveness probe — also reports MongoDB connectivity."""
    try:
        ping()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"
    return {
        "status":  "ok",
        "version": app.version,
        "mongodb": db_status
    }


@app.get("/api/v1/sonarqube/health")
async def sonarqube_health():
    """Report SonarQube readiness without exposing configuration or credentials."""
    try:
        settings = SonarSettings.from_env()
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "sonarqube": "CONFIGURATION_ERROR"},
        ) from None
    result = await asyncio.to_thread(SonarQubeService(settings).check_health)
    if not result["available"]:
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "sonarqube": result["status"]},
        )
    return {"status": "ok", "sonarqube": result["status"]}


app.include_router(create_github_router())
