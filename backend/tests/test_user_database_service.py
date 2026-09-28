"""Unit tests for standalone database provisioning (no live cluster or deployer)."""

import pytest
from fastapi import HTTPException

from services import database_service as ds
from services.database_service import (
    DatabaseService,
    ENGINE_PORTS,
    mask_connection_url,
)
from config import DatabaseProvisionSettings


def mk_settings(**overrides):
    defaults = dict(
        enabled=True,
        deployer_url="http://deployer.test:5000",
        runtime="docker",
        default_size_gb=1,
        allowed_engines=("postgres", "mongodb", "mysql", "redis"),
        allowed_sizes=(1, 5),
        max_per_user=2,
        default_storage_class="local-path",
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


class FakeUsers:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def update_one(self, query, update, **_kwargs):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                for key, value in (update or {}).get("$inc", {}).items():
                    doc[key] = doc.get(key, 0) + value
                return _Result(doc)
        return _Result()


OWNER = {"user_id": "2105085"}


def patch_collections(monkeypatch, databases, balance=100):
    monkeypatch.setattr(ds, "user_databases_col", lambda: databases)
    monkeypatch.setattr(
        ds, "users_col",
        lambda: FakeUsers([{"user_id": "2105085", "credit_balance": balance}]),
    )


def good_post(monkeypatch, **body_overrides):
    body = {"status": "success", "node_port": 31234}
    body.update(body_overrides)
    monkeypatch.setattr(ds.requests, "post", lambda *a, **k: FakeResponse(body))


# ─── Pure helpers ───────────────────────────────────────────────────────────

def test_advertise_engines_exposes_only_allowed_engines(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    info = svc().advertise_engines()
    assert set(info["engines"]) == {"postgres", "mongodb", "mysql", "redis"}
    assert info["engines"]["mysql"]["port"] == 3306
    assert info["engines"]["postgres"]["port"] == 5432
    assert info["engines"]["mongodb"]["url_scheme"] == "mongodb"
    assert info["engines"]["redis"]["port"] == 6379
    assert info["engines"]["redis"]["credential_keys"] == ["REDIS_PASSWORD"]
    assert info["default_storage_class"] == "local-path"

    filtered = svc(allowed_engines=("postgres", "redis")).advertise_engines()
    assert set(filtered["engines"]) == {"postgres", "redis"}


def test_engine_ports_include_all_supported():
    assert ENGINE_PORTS == {
        "postgres": 5432, "mongodb": 27017, "mysql": 3306, "redis": 6379,
    }


def test_mask_connection_url_hides_credentials_and_host():
    url = "postgresql://appuser:Super$ecret@192.168.0.1:31234/appdb"
    masked = mask_connection_url(url)
    assert "Super$ecret" not in masked
    assert "192.168.0.1" not in masked
    assert masked.startswith("postgresql://")
    assert masked.endswith("/appdb")


def test_build_connection_urls_postgres_internal_and_external():
    internal, external = ds._build_connection_urls(
        "postgres", "mydb", "db-mydb",
        {"user": "mydb", "password": "p@ss/word", "database": "mydb"},
        external_host="192.168.0.1", port=5432, node_port=31234,
    )
    assert internal == (
        "postgresql://mydb:p%40ss%2Fword@"
        "mydb-database-service.db-mydb.svc.cluster.local:5432/mydb"
    )
    assert external == "postgresql://mydb:p%40ss%2Fword@192.168.0.1:31234/mydb"


def test_build_connection_urls_uses_user_port_override():
    internal, external = ds._build_connection_urls(
        "postgres", "mydb", "db-mydb",
        {"user": "mydb", "password": "pw", "database": "mydb"},
        external_host="10.0.0.5", port=5555, node_port=None,
    )
    assert "mydb-database-service.db-mydb.svc.cluster.local:5555/mydb" in internal
    assert external is None


def test_build_connection_urls_mysql_uses_pymysql_scheme():
    internal, _ = ds._build_connection_urls(
        "mysql", "mydb", "db-mydb",
        {"user": "mydb", "password": "pw", "database": "mydb"},
        external_host="192.168.0.1", port=3306, node_port=None,
    )
    assert internal.startswith("mysql+pymysql://mydb:pw@")
    assert internal.endswith(":3306/mydb")


def test_build_connection_urls_mongodb_uses_auth_source():
    internal, external = ds._build_connection_urls(
        "mongodb", "mydb", "db-mydb",
        {"user": "mydb", "password": "pw", "database": "admin"},
        external_host="192.168.0.1", port=27017, node_port=None,
    )
    assert "authSource=admin" in internal
    assert internal.startswith("mongodb://mydb:pw@")
    assert external is None


def test_build_connection_urls_redis_omits_user_and_uses_db_0():
    internal, external = ds._build_connection_urls(
        "redis", "cache", "db-cache",
        {"user": "default", "password": "p@ss/word", "database": "0"},
        external_host="192.168.0.1", port=6379, node_port=31234,
    )
    assert internal == (
        "redis://:p%40ss%2Fword@"
        "cache-database-service.db-cache.svc.cluster.local:6379/0"
    )
    assert external == "redis://:p%40ss%2Fword@192.168.0.1:31234/0"


def test_deployer_secret_payload_mysql_includes_root_password():
    payload = ds._deployer_secret_payload(
        "mysql", {"user": "mydb", "password": "pw", "database": "mydb",
                  "root_password": "rootpw"}
    )
    assert payload == {
        "MYSQL_USER": "mydb",
        "MYSQL_PASSWORD": "pw",
        "MYSQL_DATABASE": "mydb",
        "MYSQL_ROOT_PASSWORD": "rootpw",
    }


def test_deployer_secret_payload_redis_only_sets_password():
    payload = ds._deployer_secret_payload(
        "redis", {"user": "default", "password": "rw", "database": "0"}
    )
    assert payload == {"REDIS_PASSWORD": "rw"}


def test_build_credentials_redis_uses_default_user_and_db_zero():
    creds = ds._build_credentials("redis", "cache", "s3cret")
    assert creds == {"user": "default", "password": "s3cret", "database": "0"}


# ─── Validation / quotas / collisions ──────────────────────────────────────

def test_provision_rejects_unallowed_engine(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc(allowed_engines=("postgres",)).provision(OWNER, engine="mysql", db_name="mydb")
    assert exc.value.status_code == 400


def test_provision_rejects_unallowed_size(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc().provision(OWNER, engine="postgres", db_name="mydb", size_gb=100)
    assert exc.value.status_code == 400


def test_provision_rejects_reserved_db_name_prefix(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc().provision(OWNER, engine="postgres", db_name="db-something")
    assert exc.value.status_code == 400


def test_provision_rejects_invalid_port(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc().provision(OWNER, engine="postgres", db_name="mydb", port=70000)
    assert exc.value.status_code == 400


def test_provision_reports_deployer_missing_cleanly(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc(deployer_url="").provision(OWNER, engine="postgres", db_name="mydb")
    assert exc.value.status_code == 503


def test_provision_enforces_per_user_quota(monkeypatch):
    databases = FakeDatabases([
        {"user_id": "2105085", "status": "ready", "engine": "postgres", "db_name": "a"},
        {"user_id": "2105085", "status": "ready", "engine": "mongodb", "db_name": "b"},
    ])
    patch_collections(monkeypatch, databases)
    with pytest.raises(HTTPException) as exc:
        svc().provision(OWNER, engine="postgres", db_name="c")
    assert exc.value.status_code == 409


def test_provision_checks_credits_before_deployer(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases(), balance=5)
    with pytest.raises(HTTPException) as exc:
        svc(cost_credits=50).provision(OWNER, engine="postgres", db_name="mydb")
    assert exc.value.status_code == 402


# ─── Provision happy path / idempotency / rotate / deprovision ─────────────

def test_provision_creates_doc_and_calls_deployer(monkeypatch):
    databases = FakeDatabases()
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse({"status": "success", "node_port": 32001})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().provision(OWNER, engine="postgres", db_name="mydb",
                             host="10.0.0.5", port=5544)

    assert result["status"] == "ready"
    assert result["db_name"] == "mydb"
    assert result["host"] == "10.0.0.5"
    assert result["port"] == 5544
    assert any(call.endswith("/api/database/provision") for call in calls)
    created = databases.find_one({"idem_key": "2105085:mydb"})
    assert created is not None
    assert created["status"] == "ready"
    assert created["node_port"] == 32001
    assert created["namespace"] == "db-mydb"
    assert created["connection_internal"].startswith("postgresql://")
    assert created["connection_internal"].endswith(":5544/mydb")
    assert created["connection_external"].endswith("10.0.0.5:32001/mydb")
    assert created["credentials"]["password"]


def test_provision_mysql_calls_deployer_with_root_password(monkeypatch):
    databases = FakeDatabases()
    bodies = []

    def fake_post(url, json=None, **_kwargs):
        bodies.append(json)
        return FakeResponse({"status": "success", "node_port": None})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().provision(OWNER, engine="mysql", db_name="shop",
                             username="shopuser", password="pw123")

    config = bodies[0]["database_config"]
    assert config["engine"] == "mysql"
    assert config["credentials"]["MYSQL_USER"] == "shopuser"
    assert config["credentials"]["MYSQL_PASSWORD"] == "pw123"
    assert config["credentials"]["MYSQL_DATABASE"] == "shop"
    assert config["credentials"]["MYSQL_ROOT_PASSWORD"]
    assert result["connection_internal"].startswith("mysql+pymysql://shopuser:pw123@")


def test_provision_redis_calls_deployer_with_password_only(monkeypatch):
    databases = FakeDatabases()
    bodies = []

    def fake_post(url, json=None, **_kwargs):
        bodies.append(json)
        return FakeResponse({"status": "success", "node_port": 30099})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().provision(OWNER, engine="redis", db_name="cache",
                             username="ignored", password="cachepw")

    config = bodies[0]["database_config"]
    assert config["engine"] == "redis"
    assert config["credentials"] == {"REDIS_PASSWORD": "cachepw"}
    assert result["db_name"] == "cache"
    assert result["connection_internal"].startswith("redis://:cachepw@")
    assert result["connection_internal"].endswith(":6379/0")
    assert result["connection_external"].endswith("192.168.0.1:30099/0")
    created = databases.find_one({"idem_key": "2105085:cache"})
    assert created["credentials"]["user"] == "default"


def test_reprovision_ready_database_rotates_instead_of_duplicating(monkeypatch):
    existing = {
        "database_id": "db-1111", "user_id": "2105085", "db_name": "mydb",
        "engine": "postgres", "status": "ready", "size_gb": 1,
        "idem_key": "2105085:mydb",
        "app_name": "mydb", "namespace": "db-mydb",
        "host": "192.168.0.1", "port": 5432,
        "credentials": {"user": "u", "password": "old", "database": "mydb"},
        "node_port": 31234,
    }
    databases = FakeDatabases([existing])
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse({"status": "success"})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().provision(OWNER, engine="postgres", db_name="mydb")

    assert result["database_id"] == "db-1111"
    assert any(call.endswith("/api/database/rotate") for call in calls), (
        "re-provision must rotate, not create a duplicate"
    )
    updated = databases.find_one({"database_id": "db-1111"})
    assert updated["credentials"]["password"] != "old"


def test_provision_in_flight_database_conflicts(monkeypatch):
    existing = {
        "database_id": "db-1111", "user_id": "2105085", "db_name": "mydb",
        "engine": "postgres", "status": "creating",
        "idem_key": "2105085:mydb", "app_name": "mydb", "namespace": "db-mydb",
    }
    patch_collections(monkeypatch, FakeDatabases([existing]))
    with pytest.raises(HTTPException) as exc:
        svc().provision(OWNER, engine="postgres", db_name="mydb")
    assert exc.value.status_code == 409
    assert "still being provisioned" in exc.value.detail


def test_rotate_updates_credentials_and_returns_new_url(monkeypatch):
    doc = {
        "database_id": "db-2222", "user_id": "2105085", "db_name": "mydb",
        "engine": "postgres", "status": "ready", "size_gb": 1,
        "app_name": "mydb", "namespace": "db-mydb",
        "host": "192.168.0.1", "port": 5432,
        "credentials": {"user": "u", "password": "before", "database": "mydb"},
        "node_port": 31234,
    }
    databases = FakeDatabases([doc])
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse({"status": "success"})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().rotate(OWNER, "db-2222")

    assert any(call.endswith("/api/database/rotate") for call in calls)
    assert result["connection_external"].endswith("192.168.0.1:31234/mydb")
    assert databases.find_one({"database_id": "db-2222"})["credentials"]["password"] != "before"


def test_rotate_unknown_database_404(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc().rotate(OWNER, "db-missing")
    assert exc.value.status_code == 404


def test_rotate_deprovisioned_database_409(monkeypatch):
    doc = {
        "database_id": "db-9999", "user_id": "2105085", "db_name": "x",
        "status": "deprovisioned", "app_name": "x", "namespace": "db-x",
    }
    patch_collections(monkeypatch, FakeDatabases([doc]))
    with pytest.raises(HTTPException) as exc:
        svc().rotate(OWNER, "db-9999")
    assert exc.value.status_code == 409


def test_deprovision_marks_deprovisioned(monkeypatch):
    doc = {
        "database_id": "db-3333", "user_id": "2105085", "db_name": "mydb",
        "engine": "postgres", "status": "ready",
        "app_name": "mydb", "namespace": "db-mydb",
    }
    databases = FakeDatabases([doc])
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse({"status": "success"})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    result = svc().deprovision(OWNER, "db-3333")

    assert any(call.endswith("/api/database/deprovision") for call in calls)
    assert result["message"].startswith("Database db-3333")
    assert databases.find_one({"database_id": "db-3333"})["status"] == "deprovisioned"


def test_deprovision_unknown_database_404(monkeypatch):
    patch_collections(monkeypatch, FakeDatabases())
    with pytest.raises(HTTPException) as exc:
        svc().deprovision(OWNER, "db-missing")
    assert exc.value.status_code == 404


# ─── Status / logs ──────────────────────────────────────────────────────────

def test_refresh_status_maps_cluster_ready(monkeypatch):
    doc = {
        "database_id": "db-4444", "user_id": "2105085", "db_name": "mydb",
        "status": "creating", "app_name": "mydb", "namespace": "db-mydb",
    }
    databases = FakeDatabases([doc])

    def fake_post(url, **_kwargs):
        if url.endswith("/api/database/status"):
            return FakeResponse({"status": "success", "result": "Running"})
        return FakeResponse({"status": "success"})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    assert svc().refresh_status(OWNER, "db-4444") == "ready"
    assert databases.find_one({"database_id": "db-4444"})["status"] == "ready"


def test_refresh_status_maps_cluster_pending(monkeypatch):
    doc = {
        "database_id": "db-4444", "user_id": "2105085", "db_name": "mydb",
        "status": "creating", "app_name": "mydb", "namespace": "db-mydb",
    }
    databases = FakeDatabases([doc])

    def fake_post(url, **_kwargs):
        return FakeResponse({"status": "success", "result": "Pending"})

    patch_collections(monkeypatch, databases)
    monkeypatch.setattr(ds.requests, "post", fake_post)

    assert svc().refresh_status(OWNER, "db-4444") == "creating"


def test_get_logs_uses_deployer_get(monkeypatch):
    doc = {
        "database_id": "db-5555", "user_id": "2105085", "db_name": "mydb",
        "status": "ready", "app_name": "mydb", "namespace": "db-mydb",
    }
    patch_collections(monkeypatch, FakeDatabases([doc]))
    params_seen = {}

    def fake_get(url, params=None, **_kwargs):
        params_seen.update(params or {})
        return FakeResponse({
            "status": "success",
            "database_name": "mydb-database",
            "namespace": "db-mydb",
            "logs": [{"pod_name": "mydb-database-0", "containers": []}],
        })

    monkeypatch.setattr(ds.requests, "get", fake_get)

    result = svc().get_logs(OWNER, "db-5555")

    assert params_seen == {"name": "mydb", "namespace": "db-mydb"}
    assert result["database_name"] == "mydb-database"
    assert result["logs"][0]["pod_name"] == "mydb-database-0"


def test_get_logs_deprovisioned_409(monkeypatch):
    doc = {
        "database_id": "db-6666", "user_id": "2105085", "db_name": "x",
        "status": "deprovisioned", "app_name": "x", "namespace": "db-x",
    }
    patch_collections(monkeypatch, FakeDatabases([doc]))
    with pytest.raises(HTTPException) as exc:
        svc().get_logs(OWNER, "db-6666")
    assert exc.value.status_code == 409


# ─── Listing / detail mask credentials ─────────────────────────────────────

def test_list_databases_masks_connection_urls(monkeypatch):
    databases = FakeDatabases([
        {
            "database_id": "db-7777", "user_id": "2105085", "db_name": "mydb",
            "engine": "postgres", "status": "ready", "size_gb": 1,
            "host": "192.168.0.1", "port": 5432, "node_port": 31234,
            "external": True, "storage_class": "local-path",
            "connection_internal": "postgresql://u:TopSecret@internal:5432/mydb",
            "connection_external": "postgresql://u:TopSecret@192.168.0.1:31234/mydb",
            "created_at": "now", "updated_at": "now", "deprovisioned_at": None,
        },
    ])
    patch_collections(monkeypatch, databases)

    listed = svc().list_databases(OWNER)

    assert len(listed) == 1
    assert listed[0]["db_name"] == "mydb"
    assert listed[0]["host"] == "192.168.0.1"
    assert listed[0]["port"] == 5432
    assert "TopSecret" not in listed[0]["connection_url"]
    assert "192.168.0.1" not in listed[0]["connection_url"]
    assert "*****" in listed[0]["connection_url"]


def test_get_database_detail_returns_metadata_and_masked_url(monkeypatch):
    databases = FakeDatabases([
        {
            "database_id": "db-8888", "user_id": "2105085", "db_name": "mydb",
            "engine": "mysql", "status": "ready", "size_gb": 5,
            "host": "192.168.0.1", "port": 3306, "node_port": 30080,
            "external": True, "storage_class": "local-path", "namespace": "db-mydb",
            "credentials": {"user": "u", "password": "Secret", "database": "mydb"},
            "connection_internal": "mysql+pymysql://u:Secret@internal:3306/mydb",
            "connection_external": None,
            "created_at": "now", "updated_at": "now", "deprovisioned_at": None,
        },
    ])
    patch_collections(monkeypatch, databases)

    detail = svc().get_database(OWNER, "db-8888")

    assert detail["engine"] == "mysql"
    assert detail["port"] == 3306
    assert detail["node_port"] == 30080
    assert detail["username"] == "u"
    assert "Secret" not in detail["connection_url"]

    with pytest.raises(HTTPException) as exc:
        svc().get_database(OWNER, "db-nope")
    assert exc.value.status_code == 404