"""Run:
  source venv/bin/activate           # Linux/macOS
  venv\\Scripts\\activate            # Windows
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import os
import stat
import hashlib
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import (
    users_col,
    projects_col,
    deployments_col,
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

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# Lock that serialises port allocation + deployment record insertion.
# Prevents two simultaneous deploys from grabbing the same port.
# Per-project locks — ensures only ONE build runs per project at a time.
# Without this, concurrent deploys for the same project race to
# docker stop/rm/run the same container name and conflict.
_port_lock = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}
_project_locks_mutex = threading.Lock()


def get_project_lock(project_id: str) -> threading.Lock:
    with _project_locks_mutex:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]


def find_free_port() -> int:
    """Returns the lowest port in 9000–9999 not used by a running container."""
    used = {
        doc["port"]
        for doc in deployments_col().find(
            {"status": {"$in": ["queued", "cloning", "building", "starting", "running"]},
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


def parse_expose_port(dockerfile_dir: str) -> int:
    """
    Reads the Dockerfile in dockerfile_dir and extracts the first EXPOSE port.
    Works for any Dockerfile regardless of what port the app uses.
    """
    dockerfile_path = os.path.join(dockerfile_dir, "Dockerfile")
    try:
        with open(dockerfile_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.upper().startswith("EXPOSE"):
                    # handles "EXPOSE 8000" and "EXPOSE 8000/tcp"
                    parts = line.split()
                    if len(parts) >= 2:
                        port_str = parts[1].split("/")[0] 
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
    can be pointed at it directly.
    Returns the folder path containing the Dockerfile, or None if not found.
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
        # skip hidden folders like .git — they will never have a Dockerfile
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "Dockerfile" in files:
            rel = os.path.relpath(root, work_dir)
            print(f"  [BUILD] Dockerfile found in {rel}/")
            return root

    return None  # no Dockerfile 


def build_and_deploy(deployment_id: str, project_id: str, repo_url: str, port: int):
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

    project_lock = get_project_lock(project_id)
    with project_lock:
      try:
        set_status("cloning")
        safe_rmtree(work_dir)

        r = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, work_dir],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"git clone failed — is the repo PUBLIC?\n\n{r.stderr.strip()}"
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

       
        dockerfile_dir = find_dockerfile(work_dir)
        container_port = parse_expose_port(dockerfile_dir) if dockerfile_dir else DEFAULT_CONTAINER_PORT

        # Stop any existing container for this project.
        subprocess.run(["docker", "stop", project_id], capture_output=True)
        subprocess.run(["docker", "rm",   project_id], capture_output=True)
        time.sleep(1)   #time to release the port binding

        
        set_status("starting")
        r = subprocess.run(
            ["docker", "run", "-d",
             "--name", project_id,
             "-p", f"{port}:{container_port}",
             "--restart", "unless-stopped",
             image_tag],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed:\n\n{r.stderr.strip()}")

        url = f"http://localhost:{port}"
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
    yield


app = FastAPI(
    title="BUET-PaaS API",
    description="Backend orchestrator for the BUET DevSecOps prototype",
    version="0.2.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


class UserCreate(BaseModel):
    user_id:  str      
    name:     str       
    email:    str       
    password: str      

class UserLogin(BaseModel):
    user_id:  str
    password: str

class ProjectCreate(BaseModel):
    repo_url:     str
    user_id:      str
    project_name: str = "my-project"

class ProjectResponse(BaseModel):
    project_id:    str
    deployment_id: str
    message:       str




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
def login(body: UserLogin):
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

    if user["password_hash"] != hash_password(body.password):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    # Never return password_hash to the frontend
    user.pop("password_hash", None)

    return {"message": "Login successful.", "user": user}


@app.get("/api/v1/users/{user_id}")
def get_user(user_id: str):
    user = users_col().find_one(
        {"user_id": user_id},
        {"_id": 0, "password_hash": 0}  
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@app.get("/api/v1/users/{user_id}/projects")
def get_user_projects(user_id: str):
    if not users_col().find_one({"user_id": user_id}):
        raise HTTPException(status_code=404, detail="User not found.")

    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$sort":  {"created_at": -1}},
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


@app.post("/api/v1/projects", response_model=ProjectResponse, status_code=202)
def create_project(body: ProjectCreate, bg: BackgroundTasks):
    """
    Student submits their GitHub repo URL.
    Verifies the user exists first, then queues the build.
    Returns 202 immediately — build runs in background.
    """
    # Verify user exists before creating project
    if not users_col().find_one({"user_id": body.user_id}):
        raise HTTPException(
            status_code=404,
            detail="User not found. Please register first."
        )

    project_id    = f"proj-{uuid.uuid4().hex[:8]}"
    deployment_id = f"dep-{uuid.uuid4().hex[:8]}"
    now           = datetime.now(timezone.utc)

    # Lock ensures port is reserved atomically with the DB insert.
    # Without this, concurrent requests can grab the same port.
    with _port_lock:
        port = find_free_port()
        # Insert project document
        projects_col().insert_one({
        "project_id":     project_id,
        "user_id":        body.user_id,
        "project_name":   body.project_name,
        "repo_url":       body.repo_url,
        "current_status": "queued",
        "created_at":     now
    })

        # Insert first deployment document
        deployments_col().insert_one({
            "deployment_id": deployment_id,
            "project_id":    project_id,
            "repo_url":      body.repo_url,
            "status":        "queued",
            "error_summary": None,
            "public_url":    None,
            "port":          port,
            "deployed_at":   now,
            "updated_at":    now
        })
  
    bg.add_task(build_and_deploy, deployment_id, project_id, body.repo_url, port)

    return {
        "project_id":    project_id,
        "deployment_id": deployment_id,
        "message": f"Build queued. Poll /api/v1/deployments/{deployment_id} for status."
    }


@app.get("/api/v1/projects")
def list_projects():
    """
    Returns ALL projects joined with their latest deployment.
    Frontend uses this for the admin view.
    """
    pipeline = [
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
def get_project(project_id: str):
    """Returns a single project with its full deployment history."""
    project = projects_col().find_one(
        {"project_id": project_id},
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
def delete_project(project_id: str):
    """Stop and remove the running container for a project."""
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
    return {
        "message":       f"Project {project_id} stopped.",
        "docker_output": result.stdout
    }


@app.get("/api/v1/deployments/{deployment_id}")
def get_deployment(deployment_id: str):
    doc = deployments_col().find_one(
        {"deployment_id": deployment_id},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return doc


@app.post("/api/v1/deployments/redeploy/{project_id}")
def redeploy_project(project_id: str, bg: BackgroundTasks):
    project = projects_col().find_one({"project_id": project_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    deployment_id = f"dep-{uuid.uuid4().hex[:8]}"
    now           = datetime.now(timezone.utc)

    # Reuse the same port as the last deployment
    last = deployments_col().find_one(
        {"project_id": project_id},
        sort=[("deployed_at", -1)]
    )
    port = last["port"] if last else find_free_port()

    deployments_col().insert_one({
        "deployment_id": deployment_id,
        "project_id":    project_id,
        "repo_url":      project["repo_url"],
        "status":        "queued",
        "error_summary": None,
        "public_url":    None,
        "port":          port,
        "deployed_at":   now,
        "updated_at":    now
    })

    bg.add_task(
        build_and_deploy,
        deployment_id, project_id, project["repo_url"], port
    )
    return {
        "deployment_id": deployment_id,
        "message":       "Redeployment triggered."
    }

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