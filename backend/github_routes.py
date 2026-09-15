"""Authenticated GitHub App installation APIs and the single App webhook."""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth import enforce_same_origin, require_user
from config import GitHubAppSettings
from db import (
    github_connections_col,
    github_installations_col,
    github_oauth_states_col,
    github_webhook_deliveries_col,
    projects_col,
)
from deployment_service import queue_deployment
from github_app import GitHubAccessError, GitHubAppError, GitHubAppService


STATE_TTL_MINUTES = 10
DELIVERY_TTL_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def consume_oauth_state(state: str) -> dict[str, Any] | None:
    state_doc = github_oauth_states_col().find_one_and_delete(
        {"state_hash": _state_hash(state)},
        return_document=ReturnDocument.BEFORE,
    )

    if not state_doc:
        return None

    expires_at = state_doc["expires_at"]

    # PyMongo may return UTC datetime without tzinfo.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= _now():
        return None

    return state_doc


def _installation_document(payload: dict[str, Any], status: str = "active") -> dict[str, Any]:
    account = payload.get("account") or {}
    return {
        "installation_id": int(payload["id"]),
        "account_id": account.get("id"),
        "account_login": account.get("login"),
        "account_type": account.get("type") or payload.get("target_type"),
        "repository_selection": payload.get("repository_selection"),
        "status": status,
        "updated_at": _now(),
    }


def create_github_router(worker: Callable[..., None]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/github", tags=["github-app"])

    def service(*, complete: bool = True) -> GitHubAppService:
        try:
            settings = GitHubAppSettings.from_env(require_complete=complete)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        return GitHubAppService(settings)

    @router.get("/connect")
    def connect_github(
        request: Request,
        user: dict[str, Any] = Depends(require_user),
    ):
        settings = GitHubAppSettings.from_env(require_complete=True)
        state = secrets.token_urlsafe(32)
        now = _now()
        github_oauth_states_col().insert_one(
            {
                "state_hash": _state_hash(state),
                "user_id": user["user_id"],
                "created_at": now,
                "expires_at": now + timedelta(minutes=STATE_TTL_MINUTES),
            }
        )
        install_url = settings.install_url or (
            f"https://github.com/apps/{settings.app_slug}/installations/new"
        )
        return RedirectResponse(f"{install_url}?{urlencode({'state': state})}", status_code=302)

    @router.get("/callback")
    def github_callback(
        state: str,
        code: str | None = None,
        installation_id: int | None = Query(default=None),
        setup_action: str | None = Query(default=None),
    ):
        state_doc = consume_oauth_state(state)
        if not state_doc:
            raise HTTPException(status_code=400, detail="OAuth state is invalid, expired, or already used")

        settings = GitHubAppSettings.from_env()
        if not code and setup_action in {"request", "requested"}:
            return RedirectResponse(
                f"{settings.frontend_url}/projects/new?github=pending", status_code=302
            )
        if not code:
            raise HTTPException(status_code=400, detail="GitHub OAuth code is missing")

        github = service()
        user_token = github.exchange_oauth_code(code)
        github_user = github.get_user(user_token)
        accessible = github.list_user_installations(user_token)
        accessible_by_id = {int(item["id"]): item for item in accessible}
        if installation_id is not None:
            if installation_id not in accessible_by_id:
                raise HTTPException(status_code=403, detail="GitHub installation is not accessible to this user")
            verified = [accessible_by_id[installation_id]]
        else:
            verified = accessible
        if not verified:
            raise HTTPException(status_code=409, detail="No approved GitHub App installation was found")

        now = _now()
        for installation in verified:
            document = _installation_document(installation)
            github_installations_col().update_one(
                {"installation_id": document["installation_id"]},
                {"$set": document, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            github_connections_col().update_one(
                {
                    "user_id": state_doc["user_id"],
                    "installation_id": document["installation_id"],
                },
                {"$set": {
                    "github_user_id": github_user.get("id"),
                    "github_login": github_user.get("login"),
                    "verified_at": now,
                    "status": "active",
                }},
                upsert=True,
            )
        return RedirectResponse(f"{settings.frontend_url}/projects/new?github=connected", status_code=302)

    @router.get("/installations")
    def list_installations(user: dict[str, Any] = Depends(require_user)):
        connections = list(github_connections_col().find(
            {"user_id": user["user_id"]}, {"_id": 0}
        ))
        result = []
        for connection in connections:
            installation = github_installations_col().find_one(
                {"installation_id": connection["installation_id"]}, {"_id": 0}
            ) or {}
            result.append({**installation, "connection_status": connection.get("status")})
        return {"installations": result}

    def require_connection(user_id: str, installation_id: int) -> None:
        connection = github_connections_col().find_one({
            "user_id": user_id,
            "installation_id": installation_id,
            "status": "active",
        })
        installation = github_installations_col().find_one({
            "installation_id": installation_id, "status": "active"
        })
        if not connection or not installation:
            raise HTTPException(status_code=403, detail="GitHub installation is not connected or active")

    @router.get("/repositories")
    def list_repositories(
        installation_id: int | None = None,
        user: dict[str, Any] = Depends(require_user),
    ):
        if installation_id is None:
            connections = list(github_connections_col().find({
                "user_id": user["user_id"], "status": "active"
            }))
            installation_ids = [int(item["installation_id"]) for item in connections]
        else:
            require_connection(user["user_id"], installation_id)
            installation_ids = [installation_id]
        github = service()
        repositories = []
        for current_id in installation_ids:
            require_connection(user["user_id"], current_id)
            installation = github_installations_col().find_one({"installation_id": current_id}) or {}
            try:
                accessible = github.list_installation_repositories(current_id)
            except GitHubAccessError:
                github_installations_col().update_one(
                    {"installation_id": current_id}, {"$set": {"status": "revoked", "updated_at": _now()}}
                )
                continue
            for repository in accessible:
                repositories.append({
                    "installation_id": current_id,
                    "account_login": installation.get("account_login"),
                    "id": repository.get("id"),
                    "name": repository.get("name"),
                    "full_name": repository.get("full_name"),
                    "private": repository.get("private", False),
                    "default_branch": repository.get("default_branch"),
                    "html_url": repository.get("html_url"),
                })
        return {"repositories": repositories}

    @router.get("/repositories/{repository_id}/branches")
    def list_branches(
        repository_id: int,
        installation_id: int,
        user: dict[str, Any] = Depends(require_user),
    ):
        require_connection(user["user_id"], installation_id)
        github = service()
        repository = github.verify_repository_access(installation_id, repository_id)
        branches = github.list_branches(installation_id, repository["full_name"], repository_id)
        return {"branches": [{"name": item.get("name"), "sha": item.get("commit", {}).get("sha")} for item in branches]}

    @router.delete("/connections/{installation_id}")
    def disconnect(
        installation_id: int,
        request: Request,
        user: dict[str, Any] = Depends(require_user),
    ):
        enforce_same_origin(request)
        result = github_connections_col().update_one(
            {"user_id": user["user_id"], "installation_id": installation_id},
            {"$set": {"status": "disconnected", "updated_at": _now()}},
        )
        if not result.matched_count:
            raise HTTPException(status_code=404, detail="GitHub connection not found")
        projects_col().update_many(
            {"user_id": user["user_id"], "github_installation_id": installation_id},
            {"$set": {"github_access_status": "disconnected", "auto_deploy": False}},
        )
        return {"status": "disconnected"}

    @router.post("/webhook", status_code=202)
    async def github_webhook(request: Request, background_tasks: BackgroundTasks):
        raw_body = await request.body()
        settings = GitHubAppSettings.from_env()
        signature = request.headers.get("x-hub-signature-256")
        if not settings.webhook_secret:
            raise HTTPException(status_code=503, detail="GitHub webhook is not configured")
        if not verify_webhook_signature(raw_body, signature, settings.webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")

        event = request.headers.get("x-github-event")
        delivery_id = request.headers.get("x-github-delivery")
        if not event or not delivery_id:
            raise HTTPException(status_code=400, detail="Missing GitHub webhook headers")
        now = _now()
        try:
            github_webhook_deliveries_col().insert_one({
                "delivery_id": delivery_id,
                "event": event,
                "received_at": now,
                "expires_at": now + timedelta(days=DELIVERY_TTL_DAYS),
                "status": "received",
            })
        except DuplicateKeyError:
            return {"status": "duplicate", "delivery_id": delivery_id}

        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            github_webhook_deliveries_col().update_one(
                {"delivery_id": delivery_id}, {"$set": {"status": "invalid_json"}}
            )
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from None

        installation_id = (payload.get("installation") or {}).get("id")
        repository_id = (payload.get("repository") or {}).get("id")
        github_webhook_deliveries_col().update_one(
            {"delivery_id": delivery_id},
            {"$set": {"installation_id": installation_id, "repository_id": repository_id}},
        )

        if event == "ping":
            status = "accepted"
        elif event == "push":
            status = _handle_push(payload, delivery_id, background_tasks, worker)
        elif event == "installation":
            status = _handle_installation(payload)
        elif event == "installation_repositories":
            status = _handle_installation_repositories(payload)
        else:
            status = "ignored"
        github_webhook_deliveries_col().update_one(
            {"delivery_id": delivery_id}, {"$set": {"status": status}}
        )
        return {"status": status, "delivery_id": delivery_id}

    return router


def _handle_push(
    payload: dict[str, Any],
    delivery_id: str,
    background_tasks: BackgroundTasks,
    worker: Callable[..., None],
) -> str:
    ref = str(payload.get("ref", ""))
    commit_sha = str(payload.get("after", ""))
    if payload.get("deleted") or not ref.startswith("refs/heads/") or set(commit_sha) == {"0"}:
        return "ignored"
    installation_id = (payload.get("installation") or {}).get("id")
    repository_id = (payload.get("repository") or {}).get("id")
    if installation_id is None or repository_id is None or len(commit_sha) != 40:
        return "ignored"
    branch = ref.removeprefix("refs/heads/")
    projects = list(projects_col().find({
        "github_installation_id": int(installation_id),
        "github_repo_id": int(repository_id),
        "deploy_branch": branch,
        "auto_deploy": True,
        "github_access_status": "active",
    }))
    queued = 0
    for project in projects:
        _, created = queue_deployment(
            project,
            commit_sha,
            branch,
            "webhook",
            worker=worker,
            background_tasks=background_tasks,
            webhook_delivery_id=delivery_id,
        )
        queued += int(created)
    return "accepted" if queued else "ignored"


def _handle_installation(payload: dict[str, Any]) -> str:
    action = payload.get("action")
    installation = payload.get("installation") or {}
    if not installation.get("id"):
        return "ignored"
    installation_id = int(installation["id"])
    status_map = {"created": "active", "unsuspend": "active", "deleted": "deleted", "suspend": "suspended"}
    status = status_map.get(str(action), "active")
    document = _installation_document(installation, status)
    github_installations_col().update_one(
        {"installation_id": installation_id},
        {"$set": document, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    if action in {"deleted", "suspend"}:
        github_connections_col().update_many(
            {"installation_id": installation_id}, {"$set": {"status": status, "updated_at": _now()}}
        )
        projects_col().update_many(
            {"github_installation_id": installation_id},
            {"$set": {"github_access_status": status, "auto_deploy": False}},
        )
    return "accepted"


def _handle_installation_repositories(payload: dict[str, Any]) -> str:
    installation_id = (payload.get("installation") or {}).get("id")
    if installation_id is None:
        return "ignored"
    if payload.get("action") == "removed":
        removed_ids = [item.get("id") for item in payload.get("repositories_removed", [])]
        projects_col().update_many(
            {"github_installation_id": int(installation_id), "github_repo_id": {"$in": removed_ids}},
            {"$set": {"github_access_status": "repository_removed", "auto_deploy": False}},
        )
    github_installations_col().update_one(
        {"installation_id": int(installation_id)}, {"$set": {"updated_at": _now()}}
    )
    return "accepted"
