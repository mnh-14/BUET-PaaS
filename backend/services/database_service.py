"""Per-user database provisioning for BUET-PaaS.

Databases are not standalone services here. Each managed database is a small
stateful workload inside the same k3s cluster that hosts the student
applications (StatefulSet + headless-backed Service + credentials Secret).
The backend tracks metadata in MongoDB and performs the Kubernetes work
through the deployer service over HTTP.

Connection URLs are reserved to fixed environment variable names so student
apps simply read DATABASE_URL / MONGO_URL / REDIS_URL at runtime.
"""

import re
import secrets
import string
import uuid
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import requests
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from config import DatabaseProvisionSettings
from db import projects_col, user_databases_col, users_col

# ─── Engine registry (mirrors deployer/k3s_conf.py) ──────────────────────────

ENGINE_ENV_KEY = {
    "postgres": "DATABASE_URL",
    "mongodb": "MONGO_URL",
    "redis": "REDIS_URL",
}

ENGINE_PORTS = {
    "postgres": 5432,
    "mongodb": 27017,
    "redis": 6379,
}

# Names of the Secret keys the deployer's DatabaseManifestBuilder expects.
_ENGINE_SECRET_KEYS = {
    "postgres": {"user": "POSTGRES_USER", "password": "POSTGRES_PASSWORD", "database": "POSTGRES_DB"},
    "mongodb": {"user": "MONGO_INITDB_ROOT_USERNAME", "password": "MONGO_INITDB_ROOT_PASSWORD", "database": None},
    "redis": {"user": None, "password": "REDIS_PASSWORD", "database": None},
}

RESERVED_ENV_KEYS = frozenset(ENGINE_ENV_KEY.values())


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sanitize_k8s_name(value: str, *, default: str = "x") -> str:
    """Lowercase RFC-1123 subdomain name for Kubernetes resource identifiers."""
    cleaned = re.sub(r"[^a-z0-9-]+", "-", str(value).lower()).strip("-")
    cleaned = re.sub(r"-+", "-", cleaned)
    return (cleaned[:58] or default).rstrip("-")


def _generate_password(length: int = 24) -> str:
    """Cryptographically secure URL-encodable password (no quotes/slashes)."""
    alphabet = string.ascii_letters + string.digits + "_-+=@$*!"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in password) and any(c.isalpha() for c in password):
            return password


def _build_credentials(engine: str, project_id: str, password: str) -> dict:
    """Generic credential set stored with the database document."""
    username = _sanitize_k8s_name(project_id, default="appuser").replace("-", "_")
    credentials = {"user": username, "password": password, "database": "appdb"}
    if engine == "mongodb":
        credentials["database"] = "admin"
    if engine == "redis":
        credentials = {"password": password}
    return credentials


def _deployer_secret_payload(engine: str, credentials: dict) -> dict:
    """Translates generic credentials into the engine Secret keys."""
    keys = _ENGINE_SECRET_KEYS[engine]
    payload = {}
    if keys["user"] and credentials.get("user"):
        payload[keys["user"]] = credentials["user"]
    if keys["password"] and credentials.get("password"):
        payload[keys["password"]] = credentials["password"]
    if keys["database"] and credentials.get("database"):
        payload[keys["database"]] = credentials["database"]
    return payload


def _build_connection_urls(
    engine: str,
    app_name: str,
    namespace: str,
    credentials: dict,
    *,
    external_host: str,
    node_port: int,
) -> tuple:
    """Returns (internal_url, external_url_or_None)."""
    port = ENGINE_PORTS[engine]
    service_host = f"{app_name}-database-service.{namespace}.svc.cluster.local"
    password = quote_plus(credentials.get("password") or "")

    def make(hostport: str) -> str:
        """hostport already includes ':port'."""
        if engine == "postgres":
            return (
                f"postgresql://{quote_plus(credentials['user'])}:{password}"
                f"@{hostport}/{credentials['database']}"
            )
        if engine == "mongodb":
            return (
                f"mongodb://{quote_plus(credentials['user'])}:{password}"
                f"@{hostport}/{credentials['database']}?authSource=admin"
            )
        return f"redis://:{password}@{hostport}/0"

    internal_url = make(f"{service_host}:{port}")
    external_url = make(f"{external_host}:{node_port}") if node_port else None
    return internal_url, external_url


def mask_connection_url(url: str) -> str:
    """Hides the password and host from a connection URL for safe display."""
    if not url:
        return ""
    parts = urlsplit(url)
    netloc = "*****@*****" if "@" in parts.netloc else "*****"
    masked = f"{parts.scheme}://{netloc}{parts.path}"
    if parts.query:
        masked += f"?{parts.query}"
    return masked


def _now():
    return datetime.now(timezone.utc)


# ─── Service ─────────────────────────────────────────────────────────────────

class DatabaseService:
    def __init__(self, settings: DatabaseProvisionSettings):
        self.settings = settings

    # -- clients ---------------------------------------------------------

    def _require_enabled(self):
        if not self.settings.enabled:
            raise HTTPException(
                status_code=503,
                detail="Database provisioning is disabled on this platform.",
            )

    def _deployer_call(self, path: str, payload: dict) -> dict:
        base = self.settings.deployer_url
        if not base:
            raise HTTPException(
                status_code=503,
                detail="Deployer service is not configured (DEPLOYER_URL missing).",
            )
        try:
            response = requests.post(f"{base}{path}", json=payload, timeout=45)
        except requests.exceptions.Timeout:
            raise HTTPException(status_code=504, detail="Deployer timed out.") from None
        except requests.exceptions.RequestException as exc:
            raise HTTPException(
                status_code=502, detail=f"Deployer service is unreachable: {exc}"
            ) from None

        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code not in (200, 201, 202) or body.get("status") != "success":
            raise HTTPException(
                status_code=502,
                detail=body.get("message") or f"Deployer error (HTTP {response.status_code}).",
            )
        return body

    # -- project helpers -------------------------------------------------

    def _get_owned_project(self, user: dict, project_id: str) -> dict:
        project = projects_col().find_one(
            {"project_id": project_id, "user_id": user["user_id"]}
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found.")
        return project

    def _validate_request(self, engine: str, size_gb: int | None):
        if engine not in self.settings.allowed_engines:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Database engine '{engine}' is not enabled on this platform. "
                    f"Allowed engines: {', '.join(self.settings.allowed_engines)}."
                ),
            )
        if engine not in ENGINE_ENV_KEY or engine not in _ENGINE_SECRET_KEYS:
            raise HTTPException(status_code=400, detail=f"Unsupported engine '{engine}'.")
        if size_gb is None:
            size_gb = self.settings.default_size_gb
        if size_gb not in self.settings.allowed_sizes:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported size {size_gb} GiB. Allowed sizes: {self.settings.allowed_sizes}.",
            )
        return size_gb

    def _check_quotas(self, user: dict, project_id: str):
        project_count = user_databases_col().count_documents({
            "project_id": project_id,
            "status": {"$ne": "deprovisioned"},
        })
        if project_count >= self.settings.max_per_project:
            raise HTTPException(
                status_code=409,
                detail=f"This project already has {project_count} active database(s) "
                       f"(max {self.settings.max_per_project}).",
            )
        user_count = user_databases_col().count_documents({
            "user_id": user["user_id"],
            "status": {"$ne": "deprovisioned"},
        })
        if user_count >= self.settings.max_per_user:
            raise HTTPException(
                status_code=409,
                detail=f"You have reached the per-user database limit ({self.settings.max_per_user}).",
            )

    def _check_reserved_key(self, project: dict, engine: str, overwrite: bool):
        key = ENGINE_ENV_KEY[engine]
        if not overwrite and key in (project.get("env_vars") or {}):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"'{key}' is reserved for the platform database and is already "
                    f"set in this project's environment variables. Re-provision with "
                    f"overwrite=true to replace it."
                ),
            )

    def _charge_credits(self, user: dict) -> None:
        cost = self.settings.cost_credits
        if cost <= 0:
            return
        record = users_col().find_one({"user_id": user["user_id"]})
        balance = int((record or {}).get("credit_balance", 0) or 0)
        if balance < cost:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits ({balance}) to provision a database ({cost} required).",
            )

    def _deduct_credits(self, user: dict) -> None:
        cost = self.settings.cost_credits
        if cost <= 0:
            return
        users_col().update_one(
            {"user_id": user["user_id"]},
            {"$inc": {"credit_balance": -cost}},
        )

    # -- public API -------------------------------------------------------

    def provision(
        self,
        user: dict,
        project_id: str,
        engine: str,
        size_gb: int | None = None,
        overwrite: bool = False,
    ) -> dict:
        """Idempotently provision one database per (project, engine)."""
        self._require_enabled()
        size_gb = self._validate_request(engine, size_gb)
        project = self._get_owned_project(user, project_id)
        self._check_reserved_key(project, engine, overwrite)

        idem_key = f"{project_id}:{engine}"
        existing = user_databases_col().find_one({"idem_key": idem_key})

        # Repeated request for an already-ready database → rotate credentials
        # and return a fresh connection URL (idempotent; never a duplicate DB).
        if existing and existing.get("status") == "ready":
            return self.rotate(user, project_id, existing["database_id"])

        self._check_quotas(user, project_id)
        self._charge_credits(user)

        now = _now()
        app_name = _sanitize_k8s_name(f"{project_id}-{engine}")
        namespace = f"db-{_sanitize_k8s_name(project_id)}"
        password = _generate_password()
        credentials = _build_credentials(engine, project_id, password)

        database_id = existing["database_id"] if existing else f"db-{uuid.uuid4().hex[:8]}"
        doc = {
            "database_id":   database_id,
            "project_id":    project_id,
            "user_id":       user["user_id"],
            "engine":        engine,
            "status":        "creating",
            "size_gb":       size_gb,
            "idem_key":      idem_key,
            "app_name":      app_name,
            "namespace":     namespace,
            "credentials":   credentials,
            "node_port":     None,
            "created_at":    now,
            "updated_at":    now,
            "deprovisioned_at": None,
        }

        if existing:
            doc.pop("database_id", None)
            user_databases_col().update_one(
                {"database_id": database_id}, {"$set": doc, "$setOnInsert": {"created_at": now}}
            )
        else:
            try:
                user_databases_col().insert_one(doc)
            except DuplicateKeyError:
                raise HTTPException(
                    status_code=409,
                    detail="A database for this project + engine is already being provisioned.",
                ) from None

        deployer_body = self._deployer_call(
            "/api/database/provision",
            {
                "database_config": {
                    "app_name":  app_name,
                    "namespace": namespace,
                    "engine":    engine,
                    "size":      f"{size_gb}Gi",
                    "storage_class": self.settings.storage_class,
                    "external":  self.settings.runtime != "k3s",
                    "credentials": _deployer_secret_payload(engine, credentials),
                }
            },
        )

        node_port = deployer_body.get("node_port")
        internal_url, external_url = _build_connection_urls(
            engine, app_name, namespace, credentials,
            external_host=self.settings.external_host,
            node_port=node_port,
        )

        user_databases_col().update_one(
            {"database_id": database_id},
            {"$set": {
                "status": "ready",
                "node_port": node_port,
                "connection_internal": internal_url,
                "connection_external": external_url,
                "updated_at": _now(),
            }},
        )
        self._deduct_credits(user)

        return self._full_response(
            database_id, engine, size_gb,
            internal_url, external_url, status="ready",
        )

    def rotate(self, user: dict, project_id: str, database_id: str) -> dict:
        """Rotate a database's credentials and return the new full URL."""
        self._require_enabled()
        db_doc = user_databases_col().find_one(
            {"database_id": database_id, "project_id": project_id, "user_id": user["user_id"]}
        )
        if not db_doc:
            raise HTTPException(status_code=404, detail="Database not found.")
        if db_doc.get("status") == "deprovisioned":
            raise HTTPException(status_code=409, detail="Database is deprovisioned.")

        password = _generate_password()
        credentials = _build_credentials(db_doc["engine"], project_id, password)
        node_port = db_doc.get("node_port")

        self._deployer_call(
            "/api/database/rotate",
            {
                "database_config": {
                    "app_name":  db_doc["app_name"],
                    "namespace": db_doc["namespace"],
                    "engine":    db_doc["engine"],
                    "credentials": _deployer_secret_payload(db_doc["engine"], credentials),
                }
            },
        )

        internal_url, external_url = _build_connection_urls(
            db_doc["engine"], db_doc["app_name"], db_doc["namespace"], credentials,
            external_host=self.settings.external_host,
            node_port=node_port,
        )
        user_databases_col().update_one(
            {"database_id": database_id},
            {"$set": {
                "credentials": credentials,
                "connection_internal": internal_url,
                "connection_external": external_url,
                "updated_at": _now(),
            }},
        )
        return self._full_response(
            database_id, db_doc["engine"], db_doc.get("size_gb"),
            internal_url, external_url, status=db_doc.get("status", "ready"),
        )

    def deprovision(self, user: dict, project_id: str, database_id: str) -> dict:
        """Stop and remove a database workload. Persistent data is retained."""
        self._require_enabled()
        db_doc = user_databases_col().find_one(
            {"database_id": database_id, "project_id": project_id, "user_id": user["user_id"]}
        )
        if not db_doc:
            raise HTTPException(status_code=404, detail="Database not found.")
        if db_doc.get("status") == "deprovisioned":
            return {"message": "Database was already deprovisioned."}

        self._deployer_call(
            "/api/database/deprovision",
            {"database_config": {
                "app_name": db_doc["app_name"],
                "namespace": db_doc["namespace"],
                "purge_data": False,
            }},
        )
        user_databases_col().update_one(
            {"database_id": database_id},
            {"$set": {
                "status": "deprovisioned",
                "connection_internal": None,
                "connection_external": None,
                "node_port": None,
                "credentials": None,
                "deprovisioned_at": _now(),
                "updated_at": _now(),
            }},
        )
        return {
            "message": f"Database {database_id} ({db_doc.get('engine')}) deprovisioned.",
            "database_id": database_id,
        }

    def list_databases(self, user: dict, project_id: str) -> list:
        self._get_owned_project(user, project_id)
        docs = user_databases_col().find(
            {"project_id": project_id}, {"_id": 0}
        ).sort("created_at", -1)
        result = []
        for doc in docs:
            url = doc.get("connection_external") or doc.get("connection_internal") or ""
            result.append({
                "database_id":         doc.get("database_id"),
                "engine":              doc.get("engine"),
                "status":              doc.get("status"),
                "size_gb":             doc.get("size_gb"),
                "node_port":           doc.get("node_port"),
                "connection_url":      mask_connection_url(url),
                "created_at":          doc.get("created_at"),
                "updated_at":          doc.get("updated_at"),
                "deprovisioned_at":    doc.get("deprovisioned_at"),
            })
        return result

    def refresh_status(self, user: dict, project_id: str, database_id: str) -> str:
        """Re-check a database against the cluster and return its live status."""
        self._get_owned_project(user, project_id)
        db_doc = user_databases_col().find_one(
            {"database_id": database_id, "project_id": project_id, "user_id": user["user_id"]}
        )
        if not db_doc:
            raise HTTPException(status_code=404, detail="Database not found.")
        if db_doc.get("status") == "deprovisioned":
            return "deprovisioned"

        deployer_status = self._deployer_call(
            "/api/database/status",
            {"name": db_doc["app_name"], "namespace": db_doc["namespace"]},
        ).get("result", "Unknown")

        mapped = "ready" if deployer_status == "Running" else (
            "creating" if deployer_status in ("Pending", "Unknown") else "failed"
        )
        user_databases_col().update_one(
            {"database_id": database_id},
            {"$set": {"status": mapped, "updated_at": _now()}},
        )
        return mapped

    # -- env injection ----------------------------------------------------

    def get_connection_env(self, project_id: str) -> dict:
        """Build {ENV_KEY: url} for every ready database of a project."""
        env = {}
        docs = user_databases_col().find(
            {"project_id": project_id, "status": "ready"}
        )
        for doc in docs:
            key = ENGINE_ENV_KEY[doc.get("engine", "")]
            if not key:
                continue
            if self.settings.runtime == "k3s":
                url = doc.get("connection_internal") or doc.get("connection_external")
            else:
                url = doc.get("connection_external") or doc.get("connection_internal")
            if url:
                env[key] = url
        return env

    def build_deploy_env(self, project_id: str, env_vars: dict | None = None) -> dict:
        """Merge student env vars with provisioned database URLs (DBs win)."""
        merged = dict(env_vars or {})
        merged.update(self.get_connection_env(project_id))
        return merged

    # -- response helpers ------------------------------------------------

    def _full_response(self, database_id, engine, size_gb, internal_url, external_url, status):
        return {
            "database_id": database_id,
            "engine": engine,
            "size_gb": size_gb,
            "status": status,
            "connection_internal": internal_url,
            "connection_external": external_url,
            "message": (
                "Database provisioned. The full connection URL is shown only once; "
                "your app can read it from the reserved environment variable."
            ),
        }