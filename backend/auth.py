"""Signed cookie sessions and migration-compatible password hashing."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request, Response

from config import GitHubAppSettings
from db import users_col


SESSION_COOKIE = "buetpaas_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> tuple[bool, str | None]:
    """Verify Argon2id, or migrate the legacy unsalted SHA-256 hash on login."""
    if stored_hash.startswith("$argon2"):
        try:
            valid = _hasher.verify(stored_hash, password)
            replacement = _hasher.hash(password) if _hasher.check_needs_rehash(stored_hash) else None
            return valid, replacement
        except (VerifyMismatchError, InvalidHashError):
            return False, None
    legacy = hashlib.sha256(password.encode()).hexdigest()
    if hmac.compare_digest(legacy, stored_hash):
        return True, _hasher.hash(password)
    return False, None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session(user_id: str, secret: str) -> str:
    payload = _b64encode(
        json.dumps(
            {"user_id": user_id, "exp": int(time.time()) + SESSION_TTL_SECONDS},
            separators=(",", ":"),
        ).encode()
    )
    signature = _b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def read_session(value: str | None, secret: str) -> str | None:
    if not value or not secret or "." not in value:
        return None
    payload, signature = value.rsplit(".", 1)
    expected = _b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        data: dict[str, Any] = json.loads(_b64decode(payload))
        if int(data["exp"]) < int(time.time()):
            return None
        return str(data["user_id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def set_session_cookie(response: Response, user_id: str) -> None:
    settings = GitHubAppSettings.from_env()
    if not settings.session_secret:
        raise HTTPException(status_code=503, detail="Session authentication is not configured")
    response.set_cookie(
        SESSION_COOKIE,
        create_session(user_id, settings.session_secret),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.frontend_url.startswith("https://"),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")


def require_user(request: Request) -> dict[str, Any]:
    settings = GitHubAppSettings.from_env()
    user_id = read_session(request.cookies.get(SESSION_COOKIE), settings.session_secret)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = users_col().find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Session user no longer exists")
    return user


def enforce_same_origin(request: Request) -> None:
    """Reject cross-origin cookie-authenticated state changes."""
    origin = request.headers.get("origin")
    if not origin:
        return
    expected = GitHubAppSettings.from_env().frontend_url
    if origin.rstrip("/") != expected:
        raise HTTPException(status_code=403, detail="Origin is not allowed")
