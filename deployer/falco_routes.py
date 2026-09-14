"""Receives security incident notifications from the Deployer
(deployer/falco_routes.py) and stores them for the dashboard.

"""

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError

from db import security_events_col


SECURITY_NOTIFY_TOKEN = os.getenv("SECURITY_NOTIFY_TOKEN")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_security_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/security", tags=["security"])

    @router.post("/incident", status_code=202)
    async def receive_incident(request: Request):
        if SECURITY_NOTIFY_TOKEN:
            provided = request.headers.get("x-security-token")
            if provided != SECURITY_NOTIFY_TOKEN:
                raise HTTPException(status_code=401, detail="Invalid or missing token")

        payload: dict[str, Any] = await request.json()

        doc = {
            "alert_uuid": payload.get("alert_uuid"),
            "rule": payload.get("rule"),
            "priority": payload.get("priority"),
            "tier": payload.get("tier"),
            "output": payload.get("output"),
            "k8s_namespace": payload.get("k8s_namespace"),
            "k8s_pod_name": payload.get("k8s_pod_name"),
            "deployment_name": payload.get("deployment_name"),
            "action_taken": payload.get("action_taken"),
            "hostname": payload.get("hostname"),
            "event_time": payload.get("event_time"),
            "notified_at": payload.get("notified_at"),
            "received_at": _now(),
        }

        try:
            # alert_uuid is unique per Falco event, so this also absorbs
            # duplicate-delivered notifications (mirrors how
            # github_webhook_deliveries_col dedupes by delivery_id).
            security_events_col().insert_one(doc)
        except DuplicateKeyError:
            pass  # already recorded, not an error

        return {"status": "received"}

    @router.get("/events")
    def list_events(
        namespace: str | None = Query(default=None),
        limit: int = Query(default=50, le=200),
    ):
        query: dict[str, Any] = {}
        if namespace:
            query["k8s_namespace"] = namespace

        cursor = (
            security_events_col()
            .find(query, {"_id": 0})
            .sort("received_at", -1)
            .limit(limit)
        )
        return {"events": list(cursor)}

    return router