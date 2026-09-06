"""Central deployment creation and worker enqueueing."""

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import BackgroundTasks

from db import deployments_col, projects_col


Worker = Callable[..., None]


def queue_deployment(
    project: dict[str, Any],
    commit_sha: str,
    branch: str,
    trigger: str,
    *,
    worker: Worker,
    background_tasks: BackgroundTasks,
) -> tuple[dict[str, Any], bool]:
    """Persist and enqueue one explicitly requested deployment."""
    project_id = str(project["project_id"])
    commit_sha = commit_sha.lower()
    now = datetime.now(timezone.utc)
    deployment = {
        "deployment_id": f"dep-{uuid.uuid4().hex[:8]}",
        "project_id": project_id,
        "repo_url": project["repo_url"],
        "commit_sha": commit_sha,
        "branch": branch,
        "trigger": trigger,
        "status": "queued",
        "error_summary": None,
        "failure": None,
        "public_url": None,
        "instance_size": project.get("instance_size", "small"),
        "deployed_at": now,
        "updated_at": now,
    }
    deployments_col().insert_one(deployment)

    projects_col().update_one(
        {"project_id": project_id},
        {"$set": {"current_status": "queued", "updated_at": now}},
    )
    background_tasks.add_task(
        worker,
        deployment["deployment_id"],
        project_id,
        project["repo_url"],
        None,
        project.get("env_vars", {}),
        commit_sha,
        project.get("project_name"),
        project.get("github_installation_id"),
        project.get("github_repo_id"),
        project.get("github_full_name"),
        branch,
    )
    return deployment, True
