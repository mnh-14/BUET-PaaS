"""
BUET-PaaS Commit Poller (Module A — Synchronization Gateway)

Watches GitHub every POLL_INTERVAL seconds.
If a student pushed new code, tells the backend to redeploy it.

Run in a separate terminal AFTER main.py is already running:
    python poller.py
"""

import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from db import projects_col, polling_col

load_dotenv()

#Configuration

ORCHESTRATOR_URL = "http://localhost:8000"   # where main.py is running
POLL_INTERVAL    = 30                        # seconds between polls
DEFAULT_BRANCH   = "main"                    # change to "master" if needed
# GITHUB_PAT       = ""                        # optional, for higher rate limit
GITHUB_PAT       = os.getenv("GITHUB_PAT", "")

#Helpers 

def parse_github_url(repo_url: str) -> tuple[str, str] | tuple[None, None]:
    """
    "https://github.com/username/my-app"     → ("username", "my-app")
    "https://github.com/username/my-app.git" → ("username", "my-app")
    """
    cleaned = repo_url.rstrip("/").removesuffix(".git")
    parts = cleaned.split("github.com/")
    if len(parts) < 2:
        return None, None
    owner, repo = parts[1].split("/", 1)
    return owner, repo


def get_latest_sha(owner: str, repo: str) -> str | None:
    """Asks GitHub API for the latest commit SHA on DEFAULT_BRANCH."""
    url = f"https://api.github.com/repos/{owner}/{repo}/branches/{DEFAULT_BRANCH}"

    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_PAT:
        headers["Authorization"] = f"Bearer {GITHUB_PAT}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as exc:
        print(f"    [ERROR] Network error reaching GitHub: {exc}")
        return None

    if resp.status_code == 404:
        print(f"    [WARN] Repo {owner}/{repo} or branch '{DEFAULT_BRANCH}' not found (404)")
        return None
    if resp.status_code == 403:
        print("    [WARN] GitHub rate limit hit. Set GITHUB_PAT for 5000 req/hr.")
        return None
    if resp.status_code != 200:
        print(f"    [WARN] GitHub returned status {resp.status_code}")
        return None

    return resp.json()["commit"]["sha"]


def trigger_redeploy(project_id: str):
    """Sends POST /api/v1/deployments/redeploy/{project_id} to main.py."""
    url = f"{ORCHESTRATOR_URL}/api/v1/deployments/redeploy/{project_id}"
    try:
        resp = requests.post(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            dep_id = data.get("deployment_id", "???")
            print(f"    [OK] Triggered redeploy -> deployment_id={dep_id}")
        else:
            print(f"    [WARN] Redeploy returned status {resp.status_code}: {resp.text}")
    except requests.RequestException as exc:
        print(f"    [ERROR] Could not reach orchestrator: {exc}")


#  Main Loop 

def poll_once():
    """Checks all active projects for new commits. Triggers redeploy if found."""
    print("\n--- Poll cycle " + "-" * 40)

    try:
        cursor = projects_col().find(
            {"current_status": {"$ne": "stopped"}},
            {"project_id": 1, "repo_url": 1},
        )
        projects = list(cursor)
    except Exception as exc:
        print(f"  [ERROR] Could not read projects from MongoDB: {exc}")
        return

    if not projects:
        print("  No active projects to poll.")
        return

    for proj in projects:
        project_id = proj["project_id"]
        repo_url   = proj.get("repo_url", "")

        owner, repo = parse_github_url(repo_url)
        if owner is None or repo is None:
            print(f"  Skipping {project_id}: invalid URL '{repo_url}'")
            continue

        print(f"  Checking {owner}/{repo} (project: {project_id})...")

        try:
            # 1. Get latest SHA from GitHub
            latest_sha = get_latest_sha(owner, repo)
            if latest_sha is None:
                continue

            # 2. Get last known SHA from MongoDB
            doc = polling_col().find_one({"project_id": project_id})
            last_sha = doc["last_known_sha"] if doc else None

            # 3. Compare
            if last_sha is None:
                # First time polling — just record the SHA, don't redeploy
                print(f"    [INIT] First poll. Recording SHA {latest_sha[:8]}...")
                polling_col().update_one(
                    {"project_id": project_id},
                    {"$set": {
                        "last_known_sha":  latest_sha,
                        "last_checked_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                )

            elif latest_sha == last_sha:
                print(f"    [NO CHANGE] Still at {last_sha[:8]}")

            else:
                # New commit detected
                print(f"    [NEW COMMIT] {last_sha[:8]} -> {latest_sha[:8]}")

                # Update SHA in MongoDB first (prevents double-deploy)
                polling_col().update_one(
                    {"project_id": project_id},
                    {"$set": {
                        "last_known_sha":  latest_sha,
                        "last_checked_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                )

                # Trigger redeploy via HTTP
                trigger_redeploy(project_id)

        except Exception as exc:
            print(f"    [ERROR] {exc}")
            continue


#  Entry Point 

if __name__ == "__main__":
    print("BUET-PaaS Commit Poller starting...")
    print(f"Polling every {POLL_INTERVAL} seconds. Press Ctrl+C to stop.\n")

    try:
        while True:
            poll_once()
            print(f"\nNext poll in {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nPoller stopped.")
