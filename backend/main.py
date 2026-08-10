"""Run:
  source venv/bin/activate           # Linux/macOS
  venv\\Scripts\\activate            # Windows
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import os
import stat
import hashlib
import asyncio
import shutil
import subprocess
import threading
import time
import uuid
import re
import socket
import tempfile
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

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
from github_app import GitHubAppService
from github_routes import create_github_router
from services.sonarqube_service import (
    SonarQubeError,
    SonarQubeService,
)

import tunnel
from db import (
    users_col,
    projects_col,
    deployments_col,
    tunnels_col,
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

PORT_START      = 9000
PORT_END        = 9999
PACK_BUILDER    = "paketobuildpacks/builder-jammy-base"
DEFAULT_CONTAINER_PORT = 3000  
# tunnel.CLOUDFLARED_EXECUTABLE= "paketobuildpacks/builder-jammy-base"
DOCKER_NETWORK = "BUET-PaaS-network-v1.0"  # ensure this Docker network exists
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

_port_lock = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}
_project_locks_mutex = threading.Lock()


def get_project_lock(project_id: str) -> threading.Lock:
    """Returns a dedicated lock for a given project_id, creating it if needed."""
    with _project_locks_mutex:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]


def find_free_port() -> int:
    """Returns the lowest port in 9000–9999 not used by a running container."""
    used = {
        doc["port"]
        for doc in deployments_col().find(
            {"status": {"$in": [
                "queued", "cloning", "security_scan_running",
                "security_scan_passed", "building", "starting", "running"
            ]},
             "port": {"$exists": True}},
            {"port": 1}
        )
    }
    for port in range(PORT_START, PORT_END + 1):
        if port not in used:
            return port
    raise RuntimeError("All ports 9000–9999 are occupied.")


def pack_available() -> bool:
    return shutil.which("pack") is not None


def get_or_create_tunnel(port: int, project_id: str) -> str:
    """
    Returns a public Cloudflare tunnel URL for the given host port.
    Logic:
      1. Check tunnels collection — if a tunnel already exists for this
         port, reuse its URL (no need to open a new one)
      2. If not, call cloudflared to open a new tunnel, store URL in DB
      3. If CLOUDFLARED_PATH is not set, fall back to localhost URL
    """
    if not tunnel.CLOUDFLARED_EXECUTABLE:
        return f"http://localhost:{port}"

    # Check if tunnel already exists for this port
    existing = tunnels_col().find_one({"port": port})
    if existing:
        print(f"  [TUNNEL] Reusing existing tunnel for port {port}: {existing['tunnel_url']}")
        return existing["tunnel_url"]

    # Open a new tunnel by importing and calling tunnel.py's start_tunnel
    try:
        # import importlib.util, sys as _sys
        # tunnel_path = os.path.join(os.path.dirname(__file__), "tunnel.py")
        # spec = importlib.util.spec_from_file_location("tunnel", tunnel_path)
        # tunnel_mod = importlib.util.module_from_spec(spec)
        # spec.loader.exec_module(tunnel_mod)
        # tunnel_mod.CLOUDFLARED_EXECUTABLE = CLOUDFLARED_PATH
        # # spec.loader.exec_module(tunnel_mod)

        tunnel_url = tunnel.start_tunnel(f"localhost:{port}")

        if tunnel_url:
            tunnels_col().insert_one({
                "port":       port,
                "tunnel_url": tunnel_url,
                "project_id": project_id,
                "created_at": datetime.now(timezone.utc)
            })
            print(f"  [TUNNEL] New tunnel for port {port}: {tunnel_url}")
            return tunnel_url
        else:
            print(f"  [TUNNEL] Failed to create tunnel — falling back to localhost")
            return f"http://localhost:{port}"

    except Exception as e:
        print(f"  [TUNNEL] Error creating tunnel: {e} — falling back to localhost")
        return f"http://localhost:{port}"


def stop_all_tunnels():
    """
    Stops all running cloudflared tunnels and clears the tunnels collection.
    Called when a project is deleted or all projects are stopped.
    """
    if not tunnel.CLOUDFLARED_EXECUTABLE:
        return

    try:
        tunnel.stop_tunnels()
        tunnels_col().delete_many({})
        print("  [TUNNEL] All tunnels stopped and collection cleared.")
    except Exception as e:
        print(f"  [TUNNEL] Error stopping tunnels: {e}")


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


def wait_for_container_ready(project_id: str, port: int, timeout: int = 30) -> None:
    """Require the container to stay alive and accept TCP before publishing a URL."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        inspection = subprocess.run(
            [
                "docker", "inspect", "--format",
                "{{.State.Running}} {{.State.Status}} {{.State.ExitCode}}",
                project_id,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        state = inspection.stdout.strip().lower()
        if inspection.returncode != 0 or not state.startswith("true "):
            raise RuntimeError(
                "Container exited before becoming ready. Check the container logs."
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(1)

    raise RuntimeError(
        f"Container is running but did not accept connections on host port {port} "
        f"within {timeout} seconds. Verify the Dockerfile EXPOSE port."
    )


COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


def _run_git(work_dir: str, *arguments: str, timeout: int = 60) -> str:
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
            timeout=120,
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
            capture_output=True, text=True, timeout=60, shell=False, env=environment,
        )
        if checkout.returncode != 0:
            fetch = subprocess.run(
                ["git", "-C", work_dir, "fetch", "--depth", "1", "origin", target],
                capture_output=True, text=True, timeout=60, shell=False, env=environment,
            )
            if fetch.returncode != 0:
                raise RuntimeError("Requested commit is no longer fetchable from GitHub")
            checkout = subprocess.run(
                ["git", "-C", work_dir, "checkout", "--detach", target],
                capture_output=True, text=True, timeout=60, shell=False, env=environment,
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
    port: int,
    env_vars: dict | None = None,
    expected_commit_sha: str | None = None,
    project_name: str | None = None,
    github_installation_id: int | None = None,
    github_repo_id: int | None = None,
    github_full_name: str | None = None,
    branch: str = "main",
):
    work_dir  = f"/tmp/buetpaas_{deployment_id}"
    image_tag = f"buetpaas/{project_id}:latest"

    def set_status(status: str, error: str = None, url: str = None):
        """Updates deployment document and parent project status."""
        deployments_col().update_one(
            {"deployment_id": deployment_id},
            {"$set": {
                "status":        status,
                "error_summary": error,
                "public_url":    url,
                "updated_at":    datetime.now(timezone.utc)
            }}
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
            {"$set": {"last_deployed_sha": commit_sha, "deploy_branch": branch}},
        )

        try:
            sonar_settings = SonarSettings.from_env()
        except ValueError as exc:
            error = f"Invalid SonarQube configuration: {exc}"
            set_security_scan(
                commit_sha=commit_sha,
                status="error",
                quality_gate=None,
                started_at=None,
                completed_at=datetime.now(timezone.utc),
                error=error,
            )
            set_status("security_scan_error", error=error)
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
                set_security_scan(
                    status="error",
                    completed_at=datetime.now(timezone.utc),
                    error=str(exc),
                )
                set_status("security_scan_error", error=str(exc))
                return
            except Exception:
                # Fail closed without returning an internal traceback or environment data.
                error = "Security scan could not complete"
                set_security_scan(
                    status="error",
                    completed_at=datetime.now(timezone.utc),
                    error=error,
                )
                set_status("security_scan_error", error=error)
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
                set_status("security_scan_failed", error=scan_result.error)
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

        set_status("building")

        if pack_available():
            print(f"  [{deployment_id[:8]}] Using pack build (CNB)")
            r = subprocess.run(
                ["pack", "build", image_tag,
                 "--path", work_dir,
                 "--builder", PACK_BUILDER],
                capture_output=True, text=True, timeout=600
            )
            if r.returncode != 0:
                raise RuntimeError(f"pack build failed:\n\n{r.stderr.strip()}")

        else:
            dockerfile_dir = find_dockerfile(work_dir)
            if dockerfile_dir:
                print(f"  [{deployment_id[:8]}] Using docker build")
                r = subprocess.run(
                    ["docker", "build", "-t", image_tag, dockerfile_dir],
                    capture_output=True, text=True, timeout=300
                )
                if r.returncode != 0:
                    raise RuntimeError(f"docker build failed:\n\n{r.stderr.strip()}")
            else:
                raise RuntimeError(
                    "No Dockerfile found anywhere in the repo and pack CLI is not installed.\n\n"
                    "Fix: add a Dockerfile to your repo (root or a subfolder like server/, app/, backend/).\n"
                    "The Dockerfile must have an EXPOSE instruction (e.g. EXPOSE 8000)."
                )

        # ── 3. Detect container port from Dockerfile ────────────
        dockerfile_dir = find_dockerfile(work_dir)
        container_port = parse_expose_port(dockerfile_dir) if dockerfile_dir else DEFAULT_CONTAINER_PORT
        subprocess.run(["docker", "stop", project_id], capture_output=True)
        subprocess.run(["docker", "rm",   project_id], capture_output=True)
        time.sleep(1)   # give OS time to release the port binding

        # ── 5. Run ──────────────────────────────────────────────
        set_status("starting")
        # Build docker run command — inject env vars if provided
        docker_cmd = [
            "docker", "run", "-d",
            "--name", project_id,
            "--network", DOCKER_NETWORK,    # ensure container is on the same network as other containers
            "-p", f"{port}:{container_port}",
            "--restart", "unless-stopped",
        ]
        if env_vars:
            for key, value in env_vars.items():
                docker_cmd += ["-e", f"{key}={value}"]
        docker_cmd.append(image_tag)

        r = subprocess.run(
            docker_cmd,
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed:\n\n{r.stderr.strip()}")

        wait_for_container_ready(project_id, port)
        url = get_or_create_tunnel(port, project_id)
        set_status("running", url=url)
        print(f"  [{deployment_id[:8]}] ✓ Running at {url}")

      except Exception as exc:
        print(f"  [{deployment_id[:8]}] ✗ FAILED: {exc}")
        set_status("failed", error=str(exc))

      finally:
        safe_rmtree(work_dir)

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
    env_vars:     dict[str, str] = {}
class ProjectResponse(BaseModel):
    project_id:    str
    deployment_id: str
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

    users_col().insert_one({
        "user_id":        body.user_id,
        "name":           body.name,
        "email":          body.email,
        "password_hash":  hash_password(body.password),
        "credit_balance": 100,
        "created_at":     datetime.now(timezone.utc)
    })

    return {
        "message":  "User registered successfully.",
        "user_id":  body.user_id,
        "name":     body.name
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
            "auto_deploy": True,
        }
    else:
        if not body.repo_url:
            raise HTTPException(status_code=400, detail="Select a GitHub App repository")
        repo_url = body.repo_url
        commit_sha = resolve_public_branch(repo_url, body.deploy_branch)
        github_fields = {
            "github_access_status": "legacy_public",
            "auto_deploy": False,
        }

    with _port_lock:
        port = find_free_port()
        project = {
            "project_id": project_id,
            "user_id": user["user_id"],
            "project_name": body.project_name,
            "repo_url": repo_url,
            "env_vars": body.env_vars,
            "port": port,
            "deploy_branch": body.deploy_branch,
            "current_status": "queued",
            "created_at": now,
            **github_fields,
        }
        projects_col().insert_one(project)

    deployment, _ = queue_deployment(
        project,
        commit_sha,
        body.deploy_branch,
        "initial",
        worker=build_and_deploy,
        background_tasks=bg,
    )

    return {
        "project_id":    project_id,
        "deployment_id": deployment["deployment_id"],
        "message": f"Build queued. Poll /api/v1/deployments/{deployment['deployment_id']} for status."
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
                "port":           "$deployments.port",
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
    """Stop and remove the running container for a project."""
    enforce_same_origin(request)
    if not projects_col().find_one({"project_id": project_id, "user_id": user["user_id"]}):
        raise HTTPException(status_code=404, detail="Project not found.")
    result = subprocess.run(
        ["docker", "rm", "-f", project_id],
        capture_output=True, text=True
    )
    deployments_col().update_many(
        {"project_id": project_id},
        {"$set": {"status": "stopped", "public_url": None}}
    )
    projects_col().update_one(
        {"project_id": project_id},
        {"$set": {"current_status": "stopped"}}
    )
    tunnels_col().delete_many({"project_id": project_id})
    return {
        "message":       f"Project {project_id} stopped.",
        "docker_output": result.stdout
    }


@app.delete("/api/v1/tunnels")
def stop_tunnels_endpoint(request: Request, user: dict = Depends(require_user)):
    enforce_same_origin(request)
    stop_all_tunnels()
    return {"message": "All tunnels stopped and tunnel records cleared."}


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

    branch = project.get("deploy_branch", "main")
    if project.get("github_installation_id"):
        try:
            commit_sha = GitHubAppService(
                GitHubAppSettings.from_env(require_complete=True)
            ).resolve_branch_head(
                project["github_installation_id"],
                project["github_full_name"],
                project["github_repo_id"],
                branch,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    else:
        commit_sha = resolve_public_branch(project["repo_url"], branch)
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


app.include_router(create_github_router(build_and_deploy))
