"""Central deployment creation and idempotent worker enqueueing."""

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import BackgroundTasks
from pymongo.errors import DuplicateKeyError

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
    webhook_delivery_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Persist and enqueue a deployment; automatic triggers are commit-idempotent."""
    project_id = str(project["project_id"])
    commit_sha = commit_sha.lower()
    automatic_key = (
        f"{project_id}:{commit_sha}" if trigger in {"initial", "webhook"} else None
    )
    if automatic_key:
        existing = deployments_col().find_one({"automatic_key": automatic_key}, {"_id": 0})
        if existing:
            return existing, False

    port = project.get("port")
    if port is None:
        last = deployments_col().find_one(
            {"project_id": project_id}, sort=[("deployed_at", -1)]
        )
        if not last:
            raise RuntimeError("Project does not have an assigned deployment port")
        port = last["port"]

    now = datetime.now(timezone.utc)
    deployment = {
        "deployment_id": f"dep-{uuid.uuid4().hex[:8]}",
        "project_id": project_id,
        "repo_url": project["repo_url"],
        "commit_sha": commit_sha,
        "branch": branch,
        "trigger": trigger,
        "webhook_delivery_id": webhook_delivery_id,
        "status": "queued",
        "error_summary": None,
        "public_url": None,
        "port": port,
        "deployed_at": now,
        "updated_at": now,
    }
    if automatic_key:
        deployment["automatic_key"] = automatic_key
    try:
        deployments_col().insert_one(deployment)
    except DuplicateKeyError:
        existing = deployments_col().find_one({"automatic_key": automatic_key}, {"_id": 0})
        if existing:
            return existing, False
        raise

    projects_col().update_one(
        {"project_id": project_id},
        {"$set": {"current_status": "queued", "port": port}},
    )
    background_tasks.add_task(
        worker,
        deployment["deployment_id"],
        project_id,
        project["repo_url"],
        port,
        project.get("env_vars", {}),
        commit_sha,
        project.get("project_name"),
        project.get("github_installation_id"),
        project.get("github_repo_id"),
        project.get("github_full_name"),
        branch,
    )
    return {key: value for key, value in deployment.items() if key != "automatic_key"}, True
