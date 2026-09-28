"""Standalone database provisioning for BUET-PaaS.

Each provisioned database is its own project: it owns a dedicated Kubernetes
namespace (``db-<name>``) inside the deployer cluster and is never nested
under an app project, so deleting or redeploying an app never touches it.

Workflow (mirrors the instructions in my_markdown.md):
  1. user picks an engine (postgres / mongodb / mysql / redis only)
  2. user supplies the connection details they want
     (host hint, port hint, storage class, size, optional credentials)
  3. the deployer creates a standalone DB workload per that exact config
  4. the platform hands back internal + external connection URLs
  5. status and pod logs are exposed so provisioning progress can be tracked
Programmers connect to the returned host:port directly.
"""

import re
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import requests
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from config import DatabaseProvisionSettings
from db import user_databases_col, users_col

# ─── Engine registry (mirrors deployer/k3s_conf.py) ──────────────────────────

ENGINE_PORTS = {
    "postgres": 5432,
    "mongodb": 27017,
    "mysql": 3306,
    "redis": 6379,
}

# Names of the Secret keys the deployer's DatabaseManifestBuilder expects.
_ENGINE_SECRET_KEYS = {
    "postgres": {
        "user": "POSTGRES_USER",
        "password": "POSTGRES_PASSWORD",
        "database": "POSTGRES_DB",
    },
    "mongodb": {
        "user": "MONGO_INITDB_ROOT_USERNAME",
        "password": "MONGO_INITDB_ROOT_PASSWORD",
        "database": None,
    },
    "mysql": {
        "user": "MYSQL_USER",
        "password": "MYSQL_PASSWORD",
        "database": "MYSQL_DATABASE",
        "root_password": "MYSQL_ROOT_PASSWORD",
    },
    "redis": {
        "user": None,
        "password": "REDIS_PASSWORD",
        "database": None,
    },
}


@dataclass(frozen=True)
class EngineInfo:
    port: int
    credential_keys: tuple
    url_scheme: str


_ENGINE_INFO = {
    "postgres": EngineInfo(5432, ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"), "postgresql"),
    "mongodb": EngineInfo(27017, ("MONGO_INITDB_ROOT_USERNAME", "MONGO_INITDB_ROOT_PASSWORD"), "mongodb"),
    "mysql": EngineInfo(3306, ("MYSQL_ROOT_PASSWORD", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"), "mysql+pymysql"),
    "redis": EngineInfo(6379, ("REDIS_PASSWORD",), "redis"),
}


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


def _build_credentials(engine: str, db_name: str, password: str,
                       username: str | None = None) -> dict:
    """Generic credential set stored with the database document."""
    username = (username or _sanitize_k8s_name(db_name, default="appuser")).replace("-", "_")
    credentials = {"user": username, "password": password, "database": db_name}
    if engine == "mongodb":
        credentials["database"] = "admin"
    elif engine == "redis":
        credentials["user"] = "default"
        credentials["database"] = "0"
    return credentials


def _deployer_secret_payload(engine: str, credentials: dict) -> dict:
    """Translates generic credentials into the engine Secret keys."""
    keys = _ENGINE_SECRET_KEYS[engine]
    payload = {}
    if keys.get("user") and credentials.get("user"):
        payload[keys["user"]] = credentials["user"]
    if keys.get("password") and credentials.get("password"):
        payload[keys["password"]] = credentials["password"]
    if keys.get("database") and credentials.get("database"):
        payload[keys["database"]] = credentials["database"]
    if keys.get("root_password"):
        payload[keys["root_password"]] = credentials.get("root_password") or _generate_password()
    return payload


def _build_connection_urls(
    engine: str,
    app_name: str,
    namespace: str,
    credentials: dict,
    *,
    external_host: str,
    port: int,
    node_port: int,
) -> tuple:
    """Returns (internal_url, external_url_or_None)."""
    service_host = f"{app_name}-database-service.{namespace}.svc.cluster.local"
    password = quote_plus(credentials.get("password") or "")
    scheme = _ENGINE_INFO[engine].url_scheme

    def make(hostport: str) -> str:
        if engine == "mongodb":
            return (
                f"mongodb://{quote_plus(credentials['user'])}:{password}"
                f"@{hostport}/{credentials['database']}?authSource=admin"
            )
        if engine == "redis":
            return f"redis://:{password}@{hostport}/{credentials['database']}"
        return (
            f"{scheme}://{quote_plus(credentials['user'])}:{password}"
            f"@{hostport}/{credentials['database']}"
        )

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

    def _deployer_post(self, path: str, payload: dict) -> dict:
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

    def _deployer_get(self, path: str, params: dict) -> dict:
        base = self.settings.deployer_url
        if not base:
            raise HTTPException(
                status_code=503,
                detail="Deployer service is not configured (DEPLOYER_URL missing).",
            )
        try:
            response = requests.get(f"{base}{path}", params=params, timeout=45)
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

    # -- validation ------------------------------------------------------

    def _validate_engine(self, engine: str) -> None:
        if engine not in self.settings.allowed_engines:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Database engine '{engine}' is not enabled on this platform. "
                    f"Allowed engines: {', '.join(self.settings.allowed_engines)}."
                ),
            )
        if engine not in _ENGINE_INFO:
            raise HTTPException(status_code=400, detail=f"Unsupported engine '{engine}'.")

    def _get_db_doc(self, user: dict, database_id: str) -> dict:
        doc = user_databases_col().find_one({
            "database_id": database_id, "user_id": user["user_id"]
        })
        if not doc:
            raise HTTPException(status_code=404, detail="Database not found.")
        return doc

    def _check_quota(self, user: dict) -> None:
        user_count = user_databases_col().count_documents({
            "user_id": user["user_id"],
            "status": {"$ne": "deprovisioned"},
        })
        if user_count >= self.settings.max_per_user:
            raise HTTPException(
                status_code=409,
                detail=f"You have reached the per-user database limit ({self.settings.max_per_user}).",
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

    def advertise_engines(self) -> dict:
        """Engine metadata the frontend renders into the creation form."""
        engines = {}
        for engine in ENGINE_PORTS:
            if engine not in self.settings.allowed_engines:
                continue
            info = _ENGINE_INFO[engine]
            engines[engine] = {
                "port": info.port,
                "default_port": info.port,
                "credential_keys": list(info.credential_keys),
                "url_scheme": info.url_scheme,
            }
        return {
            "engines": engines,
            "default_storage_class": self.settings.default_storage_class,
            "external_host": self.settings.external_host,
            "allowed_sizes_gb": list(self.settings.allowed_sizes),
        }

    def provision(
        self,
        user: dict,
        *,
        engine: str,
        db_name: str,
        username: str | None = None,
        password: str | None = None,
        size_gb: int | None = None,
        host: str | None = None,
        port: int | None = None,
        storage_class: str | None = None,
        external: bool | None = None,
        node_port: int | None = None,
    ) -> dict:
        """Provision a standalone database and return its connection URLs."""
        self._require_enabled()
        self._validate_engine(engine)

        db_name = _sanitize_k8s_name(db_name)
        if not db_name or db_name.startswith("db-"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "A valid database name is required and must not start with 'db-' "
                    "(reserved namespace prefix)."
                ),
            )

        size_gb = size_gb or self.settings.default_size_gb
        if size_gb not in self.settings.allowed_sizes:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported size {size_gb} GiB. Allowed sizes: {self.settings.allowed_sizes}.",
            )

        port = port or ENGINE_PORTS[engine]
        if not 1 <= port <= 65535:
            raise HTTPException(status_code=400, detail=f"Invalid port '{port}'.")
        if node_port is not None and not 1 <= node_port <= 65535:
            raise HTTPException(status_code=400, detail=f"Invalid node port '{node_port}'.")
        host = (host or self.settings.external_host).strip()
        if not host:
            raise HTTPException(status_code=400, detail="A host is required.")
        storage_class = (storage_class or self.settings.default_storage_class).strip()
        external = self.settings.runtime != "k3s" if external is None else bool(external)

        idem_key = f"{user['user_id']}:{db_name}"
        existing = user_databases_col().find_one({"idem_key": idem_key})

        # Idempotency: a ready DB with this name → rotate and hand back a fresh
        # URL. One still spinning up → conflict. Failed → re-run in place.
        if existing and existing.get("status") == "ready":
            return self.rotate(user, existing["database_id"])
        if existing and existing.get("status") == "creating":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A database named '{db_name}' is still being provisioned. "
                    "Check its status or logs before trying again."
                ),
            )

        self._check_quota(user)
        self._charge_credits(user)

        now = _now()
        app_name = db_name
        namespace = f"db-{db_name}"
        generated_password = password or _generate_password()
        credentials = _build_credentials(engine, db_name, generated_password, username)
        credentials["root_password"] = _generate_password()

        database_id = existing["database_id"] if existing else f"db-{uuid.uuid4().hex[:8]}"
        doc = {
            "database_id":   database_id,
            "user_id":       user["user_id"],
            "db_name":       db_name,
            "engine":        engine,
            "host":          host,
            "port":          port,
            "status":        "creating",
            "size_gb":       size_gb,
            "storage_class": storage_class,
            "external":      external,
            "idem_key":      idem_key,
            "app_name":      app_name,
            "namespace":     namespace,
            "credentials":   credentials,
            "node_port":     node_port,
            "created_at":    now,
            "updated_at":    now,
            "deprovisioned_at": None,
        }

        if existing:
            doc.pop("database_id", None)
            user_databases_col().update_one(
                {"database_id": database_id}, {"$set": doc}
            )
        else:
            try:
                user_databases_col().insert_one(doc)
            except DuplicateKeyError:
                raise HTTPException(
                    status_code=409,
                    detail=f"A database named '{db_name}' is already being provisioned.",
                ) from None

        deployer_config = {
            "app_name":  app_name,
            "namespace": namespace,
            "engine":    engine,
            "port":      port,
            "size":      f"{size_gb}Gi",
            "storage_class": storage_class,
            "external":  external,
            "credentials": _deployer_secret_payload(engine, credentials),
        }
        if node_port is not None:
            deployer_config["node_port"] = node_port

        deployer_body = self._deployer_post("/api/database/provision", {"database_config": deployer_config})

        node_port = node_port or deployer_body.get("node_port")
        internal_url, external_url = _build_connection_urls(
            engine, app_name, namespace, credentials,
            external_host=host, port=port, node_port=node_port,
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
            database_id, db_name, engine, size_gb,
            internal_url, external_url, status="ready", host=host, port=port,
        )

    def rotate(self, user: dict, database_id: str) -> dict:
        """Rotate a database's credentials and return the new full URLs."""
        self._require_enabled()
        db_doc = self._get_db_doc(user, database_id)
        if db_doc.get("status") == "deprovisioned":
            raise HTTPException(status_code=409, detail="Database is deprovisioned.")

        password = _generate_password()
        credentials = _build_credentials(
            db_doc["engine"], db_doc["db_name"], password,
            (db_doc.get("credentials") or {}).get("user"),
        )
        credentials["root_password"] = _generate_password()
        node_port = db_doc.get("node_port")

        self._deployer_post(
            "/api/database/rotate",
            {"database_config": {
                "app_name":  db_doc["app_name"],
                "namespace": db_doc["namespace"],
                "engine":    db_doc["engine"],
                "credentials": _deployer_secret_payload(db_doc["engine"], credentials),
            }},
        )

        internal_url, external_url = _build_connection_urls(
            db_doc["engine"], db_doc["app_name"], db_doc["namespace"], credentials,
            external_host=db_doc.get("host") or self.settings.external_host,
            port=db_doc.get("port") or ENGINE_PORTS[db_doc["engine"]],
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
            database_id, db_doc["db_name"], db_doc["engine"], db_doc.get("size_gb"),
            internal_url, external_url, status=db_doc.get("status", "ready"),
            host=db_doc.get("host") or self.settings.external_host,
            port=db_doc.get("port") or ENGINE_PORTS[db_doc["engine"]],
        )

    def deprovision(self, user: dict, database_id: str) -> dict:
        """Stop and remove a database workload. Persistent data is retained."""
        self._require_enabled()
        db_doc = self._get_db_doc(user, database_id)
        if db_doc.get("status") == "deprovisioned":
            return {"message": "Database was already deprovisioned."}

        self._deployer_post(
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

    def list_databases(self, user: dict) -> list:
        docs = user_databases_col().find(
            {"user_id": user["user_id"]}, {"_id": 0}
        ).sort("created_at", -1)
        result = []
        for doc in docs:
            url = doc.get("connection_external") or doc.get("connection_internal") or ""
            result.append({
                "database_id":         doc.get("database_id"),
                "db_name":             doc.get("db_name"),
                "engine":              doc.get("engine"),
                "status":              doc.get("status"),
                "size_gb":             doc.get("size_gb"),
                "storage_class":       doc.get("storage_class"),
                "host":                doc.get("host"),
                "port":                doc.get("port"),
                "node_port":           doc.get("node_port"),
                "external":            bool(doc.get("external")),
                "connection_url":      mask_connection_url(url),
                "created_at":          doc.get("created_at"),
                "updated_at":          doc.get("updated_at"),
                "deprovisioned_at":    doc.get("deprovisioned_at"),
            })
        return result

    def get_database(self, user: dict, database_id: str) -> dict:
        doc = self._get_db_doc(user, database_id)
        url = doc.get("connection_external") or doc.get("connection_internal") or ""
        return {
            "database_id":       doc.get("database_id"),
            "db_name":           doc.get("db_name"),
            "engine":            doc.get("engine"),
            "status":            doc.get("status"),
            "size_gb":           doc.get("size_gb"),
            "storage_class":     doc.get("storage_class"),
            "host":              doc.get("host") or self.settings.external_host,
            "port":              doc.get("port") or ENGINE_PORTS[doc["engine"]],
            "node_port":         doc.get("node_port"),
            "external":          bool(doc.get("external")),
            "connection_url":    mask_connection_url(url),
            "namespace":         doc.get("namespace"),
            "username":          (doc.get("credentials") or {}).get("user"),
            "created_at":        doc.get("created_at"),
            "updated_at":        doc.get("updated_at"),
            "deprovisioned_at":  doc.get("deprovisioned_at"),
        }

    def refresh_status(self, user: dict, database_id: str) -> str:
        """Re-check a database against the cluster and return its live status."""
        db_doc = self._get_db_doc(user, database_id)
        if db_doc.get("status") == "deprovisioned":
            return "deprovisioned"

        deployer_status = self._deployer_post(
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

    def get_logs(self, user: dict, database_id: str) -> dict:
        """Fetch the database pod logs so provisioning progress is visible."""
        db_doc = self._get_db_doc(user, database_id)
        if db_doc.get("status") == "deprovisioned":
            raise HTTPException(status_code=409, detail="Database is deprovisioned.")
        result = self._deployer_get(
            "/api/database/logs",
            {"name": db_doc["app_name"], "namespace": db_doc["namespace"]},
        )
        return {key: result[key] for key in ("database_name", "namespace", "logs") if key in result}

    # -- response helpers ------------------------------------------------

    def _full_response(self, database_id, db_name, engine, size_gb,
                       internal_url, external_url, status, host, port):
        return {
            "database_id":   database_id,
            "db_name":       db_name,
            "engine":        engine,
            "size_gb":       size_gb,
            "status":        status,
            "host":          host,
            "port":          port,
            "connection_internal": internal_url,
            "connection_external": external_url,
            "message": (
                "Standalone database provisioned. Connect to the returned "
                "host:port with the credentials shown above (full URLs are "
                "returned only once)."
            ),
        }