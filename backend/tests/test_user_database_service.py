"""Unit tests for per-user database provisioning (no live cluster or deployer)."""

import pytest
from fastapi import HTTPException

from services import database_service as ds
from services.database_service import (
    ENGINE_ENV_KEY,
    RESERVED_ENV_KEYS,
    DatabaseService,
    mask_connection_url,
)
from config import DatabaseProvisionSettings


def mk_settings(**overrides):
    defaults = dict(
        enabled=True,
        deployer_url="http://deployer.test:5000",
        runtime="docker",
        default_size_gb=1,
        allowed_engines=("postgres", "mongodb", "redis"),
        allowed_sizes=(1, 5),
        max_per_user=2,
        max_per_project=1,
        storage_class="local-path",
        external_host="192.168.0.1",
        cost_credits=0,
    )
    defaults.update(overrides)
    return DatabaseProvisionSettings(**defaults)


def svc(**settings_overrides):
    return DatabaseService(mk_settings(**settings_overrides))


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status_code = status

    def json(self):
        return self.body


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args, **_kwargs):
        return self.docs[:]

    def __iter__(self):
        return iter(self.docs)


class FakeDatabases:
    """Minimal in-memory stand-in for the user_databases collection."""

    def __init__(self, docs=None):
        self.docs = docs or []
        self.inserted = []

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            if isinstance(expected, dict) and "$ne" in expected:
                if doc.get(key) == expected["$ne"]:
                    return False
            elif doc.get(key) != expected:
                return False
        return True

    def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        self.inserted.append(dict(doc))
        return _Result(doc)

    def update_one(self, query, update, **_kwargs):
        for doc in self.docs:
            if self._matches(doc, query):
                for key, value in (update or {}).get("$set", {}).items():
                    doc[key] = value
                return _Result(doc)
        return _Result()

    def count_documents(self, query, **_kwargs):
        return sum(1 for doc in self.docs if self._matches(doc, query))

    def find(self, query, *_args, **_kwargs):
        return FakeCursor([doc for doc in self.docs if self._matches(doc, query)])


class _Result:
    def __init__(self, document=None):
        self.document = document


class FakeProjects:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None


SAMPLE_PROJECT = {
    "project_id": "proj-abc123",
    "user_id": "2105085",
    "project_name": "demo",
    "repo_url": "https://github.com/student/demo.git",
    "env_vars": {"PORT": "8080"},
    "created_at": "now",
}

OWNER = {"user_id": "2105085"}


def patch_collections(monkeypatch, databases, projects=None):
    monkeypatch.setattr(ds, "user_databases_col", lambda: databases)
    monkeypatch.setattr(
        ds, "projects_col", lambda: (projects if projects is not None else FakeProjects([SAMPLE_PROJECT]))
    )
    monkeypatch.setattr(
        ds, "users_col",
        lambda: FakeDatabases([{"user_id": "2105085", "credit_balance": 100}]),
    )


def good_post(monkeypatch, **body_overrides):
    body = {"status": "success", "node_port": 31234}
    body.update(body_overrides)
    monkeypatch.setattr(ds.requests, "post", lambda *a, **k: FakeResponse(body))


# ─── Pure helpers ───────────────────────────────────────────────────────────

def test_reserved_env_keys_match_engine_env_keys():
    assert RESERVED_ENV_KEYS == {"DATABASE_URL", "MONGO_URL", "REDIS_URL"}
    assert set(ENGINE_ENV_KEY.values()) == RESERVED_ENV_KEYS


def test_mask_connection_url_hides_credentials_and_host():
    url = "postgresql://appuser:Super$ecret@192.168.0.1:31234/appdb"
    masked = mask_connection_url(url)
    assert "Super$ecret" not in masked
    assert "192.168.0.1" not in masked
    assert masked.startswith("postgresql://")
    assert masked.endswith("/appdb")


def test_mask_connection_url_handles_redis_style_url():
    masked = mask_connection_url("redis://:Secret@internal.svc:6379/0")
    assert "Secret" not in masked
    assert "internal.svc" not in masked


def test_build_connection_urls_postgres_internal_and_external():
    internal, external = ds._build_connection_urls(
        "postgres", "proj-abc123-postgres", "db-proj-abc123",
        {"user": "proj_abc123", "password": "p@ss/word", "database": "appdb"},
        external_host="192.168.0.1", node_port=31234,
    )
    assert internal == (
        "postgresql://proj_abc123:p%40ss%2Fword@"
        "proj-abc123-postgres-database-service.db-proj-abc123.svc.cluster.local:5432/appdb"
    )
    assert external == "postgresql://proj_abc123:p%40ss%2Fword@192.168.0.1:31234/appdb"


def test_build_connection_urls_redis_omits_username():
    internal, external = ds._build_connection_urls(
        "redis", "proj-abc123-redis", "db-proj-abc123",
        {"password": "p@ss/word"}, external_host="192.168.0.1", node_port=35001,
    )
    assert internal == "redis://:p%40ss%2Fword@proj-abc123-redis-database-service.db-proj-abc123.svc.cluster.local:6379/0"
    assert external == "redis://:p%40ss%2Fword@192.168.0.1:35001/0"


def test_build_connection_urls_mongodb_uses_auth_source():
    internal, external = ds._build_connection_urls(
        "mongodb", "proj-abc123-mongodb", "db-proj-abc123",
        {"user": "proj_abc123", "password": "pw", "database": "admin"},
        external_host="192.168.0.1", node_port=None,
    )
    assert "authSource=admin" in internal
    assert internal.startswith("mongodb://proj_abc123:pw@")
    assert external is None


# ─── Validation / quotas / collisions ──────────────────────────────────────

def test_provision_rejects_unallowed_engine(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc(allowed_engines=("postgres",)).provision(OWNER, "proj-abc123", "mysql", 1)
    assert exc.value.status_code == 400


def test_provision_rejects_unallowed_size(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc().provision(OWNER, "proj-abc123", "postgres", 100)
    assert exc.value.status_code == 400


def test_provision_reports_deployer_missing_cleanly(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc(deployer_url="").provision(OWNER, "proj-abc123", "postgres", 1)
    assert exc.value.status_code == 503


def test_provision_reserved_env_key_collision(monkeypatch):
    databases = FakeDatabases()
    projects = FakeProjects([{**SAMPLE_PROJECT, "env_vars": {"DATABASE_URL": "mysql://x@y/z"}}])
    patch_collections(monkeypatch, databases, projects)
    with pytest.raises(HTTPException) as exc:
        svc().provision(OWNER, "proj-abc123", "postgres", 1)
    assert exc.value.status_code == 409
    assert "DATABASE_URL" in exc.value.detail
    # overwrite=true bypasses the collision guard
    good_post(monkeypatch)
    result = svc().provision(OWNER, "proj-abc123", "postgres", 1, overwrite=True)
    assert result["status"] == "ready"


def test_provision_enforces_per_project_quota(monkeypatch):
    databases = FakeDatabases([{
        "project_id": "proj-abc123", "user_id": "2105085",
        "status": "ready", "engine": "mongodb",
    }])
    patch_collections(monkeypatch, databases)
    with pytest.raises(HTTPException) as exc:
        svc().provision(OWNER, "proj-abc123", "postgres", 1)
    assert exc.value.status_code == 409


def test_provision_checks_credits_before_deployer(monkeypatch):
    databases = FakeDatabases()
    monkeypatch.setattr(ds, "user_databases_col", lambda: databases)
    monkeypatch.setattr(ds, "projects_col", lambda: FakeProjects([SAMPLE_PROJECT]))
    monkeypatch.setattr(
        ds, "users_col",
        lambda: FakeDatabases([{"user_id": "2105085", "credit_balance": 5}]),
    )
    with pytest.raises(HTTPException) as exc:
        svc(cost_credits=50).provision(OWNER, "proj-abc123", "postgres", 1)
    assert exc.value.status_code == 402


# ─── Provision happy path / idempotency / rotate / deprovision ─────────────

def test_provision_creates_doc_and_calls_deployer(monkeypatch):
    databases = FakeDatabases()
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse({"status": "success", "node_port": 31234})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().provision(OWNER, "proj-abc123", "postgres", 1)

    assert result["status"] == "ready"
    assert result["database_id"].startswith("db-")
    assert any(call.endswith("/api/database/provision") for call in calls)
    created = databases.find_one({"idem_key": "proj-abc123:postgres"})
    assert created is not None
    assert created["status"] == "ready"
    assert created["node_port"] == 31234
    assert created["connection_internal"].startswith("postgresql://")
    assert created["connection_external"].endswith("192.168.0.1:31234/appdb")
    assert created["credentials"]["password"]


def test_reprovision_ready_database_rotates_instead_of_duplicating(monkeypatch):
    existing = {
        "database_id": "db-1111", "project_id": "proj-abc123", "user_id": "2105085",
        "engine": "postgres", "status": "ready", "size_gb": 1,
        "idem_key": "proj-abc123:postgres",
        "app_name": "proj-abc123-postgres", "namespace": "db-proj-abc123",
        "credentials": {"user": "u", "password": "old", "database": "appdb"},
        "node_port": 31234,
    }
    databases = FakeDatabases([existing])
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse({"status": "success"})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().provision(OWNER, "proj-abc123", "postgres", 1)

    assert result["database_id"] == "db-1111"
    assert any(call.endswith("/api/database/rotate") for call in calls), (
        "re-provision must rotate, not create a duplicate"
    )
    updated = databases.find_one({"database_id": "db-1111"})
    assert updated["credentials"]["password"] != "old"


def test_rotate_updates_credentials_and_returns_new_url(monkeypatch):
    doc = {
        "database_id": "db-2222", "project_id": "proj-abc123", "user_id": "2105085",
        "engine": "redis", "status": "ready", "size_gb": 1,
        "app_name": "proj-abc123-redis", "namespace": "db-proj-abc123",
        "credentials": {"password": "before"}, "node_port": 35001,
    }
    databases = FakeDatabases([doc])
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse({"status": "success"})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().rotate(OWNER, "proj-abc123", "db-2222")

    assert any(call.endswith("/api/database/rotate") for call in calls)
    assert result["connection_external"].endswith("192.168.0.1:35001/0")
    assert databases.find_one({"database_id": "db-2222"})["credentials"]["password"] != "before"


def test_deprovision_marks_deprovisioned(monkeypatch):
    doc = {
        "database_id": "db-3333", "project_id": "proj-abc123", "user_id": "2105085",
        "engine": "postgres", "status": "ready",
        "app_name": "proj-abc123-postgres", "namespace": "db-proj-abc123",
    }
    databases = FakeDatabases([doc])
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse({"status": "success"})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().deprovision(OWNER, "proj-abc123", "db-3333")

    assert any(call.endswith("/api/database/deprovision") for call in calls)
    assert result["message"].startswith("Database db-3333")
    assert databases.find_one({"database_id": "db-3333"})["status"] == "deprovisioned"


def test_deprovision_unknown_database_404(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc().deprovision(OWNER, "proj-abc123", "db-missing")
    assert exc.value.status_code == 404


# ─── Env injection helpers (used by build_and_deploy) ──────────────────────

def test_build_deploy_env_wires_ready_database_url(monkeypatch):
    databases = FakeDatabases([
        {
            "project_id": "proj-abc123", "engine": "postgres", "status": "ready",
            "connection_internal": "postgresql://u:p@internal:5432/appdb",
            "connection_external": "postgresql://u:p@192.168.0.1:31234/appdb",
        },
        {
            "project_id": "proj-abc123", "engine": "redis", "status": "deprovisioned",
            "connection_internal": None, "connection_external": None,
        },
    ])
    monkeypatch.setattr(ds, "user_databases_col", lambda: databases)

    env = svc(runtime="docker").build_deploy_env(
        "proj-abc123", {"PORT": "8080", "DATABASE_URL": "overridden-by-platform"},
    )

    assert env["DATABASE_URL"] == "postgresql://u:p@192.168.0.1:31234/appdb"
    assert env["PORT"] == "8080"


def test_build_deploy_env_uses_internal_url_for_k3s_runtime(monkeypatch):
    databases = FakeDatabases([
        {
            "project_id": "proj-abc123", "engine": "postgres", "status": "ready",
            "connection_internal": "postgresql://u:p@internal:5432/appdb",
            "connection_external": "postgresql://u:p@192.168.0.1:31234/appdb",
        },
    ])
    monkeypatch.setattr(ds, "user_databases_col", lambda: databases)
    env = svc(runtime="k3s").build_deploy_env("proj-abc123", {})
    assert env["DATABASE_URL"] == "postgresql://u:p@internal:5432/appdb"


# ─── Listing masks credentials ─────────────────────────────────────────────

def test_list_databases_masks_connection_urls(monkeypatch):
    databases = FakeDatabases([
        {
            "database_id": "db-7777", "project_id": "proj-abc123", "user_id": "2105085",
            "engine": "postgres", "status": "ready", "size_gb": 1, "node_port": 31234,
            "connection_internal": "postgresql://u:TopSecret@internal:5432/appdb",
            "connection_external": "postgresql://u:TopSecret@192.168.0.1:31234/appdb",
            "created_at": "now", "updated_at": "now", "deprovisioned_at": None,
        },
    ])
    patch_collections(monkeypatch, databases)

    listed = svc().list_databases(OWNER, "proj-abc123")

    assert len(listed) == 1
    assert "TopSecret" not in listed[0]["connection_url"]
    assert "192.168.0.1" not in listed[0]["connection_url"]
    assert "*****" in listed[0]["connection_url"]