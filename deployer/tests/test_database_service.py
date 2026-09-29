import sys
from pathlib import Path

import pytest

# Allow deploy.py and k3s_conf.py to resolve their absolute imports.
DEPLOYER_DIR = Path(__file__).resolve().parents[1]
if str(DEPLOYER_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOYER_DIR))

import deploy  # noqa: E402
from k3s_conf import DATABASE_ENGINES, DatabaseManifestBuilder  # noqa: E402


def credentials_for(engine):
    return {
        key: f"test-{key.lower()}"
        for key in DATABASE_ENGINES[engine]["credentials"]
    }


def config_for(engine="postgres", **overrides):
    config = {
        "app_name": "test-db",
        "namespace": "test-namespace",
        "engine": engine,
        "credentials": (
            credentials_for(engine)
            if engine in DATABASE_ENGINES
            else {}
        ),
    }
    config.update(overrides)
    return config


@pytest.mark.parametrize("engine", ["postgres", "mongodb", "mysql", "redis"])
def test_supported_engines_build_connection_details(engine):
    builder = DatabaseManifestBuilder(config_for(engine))

    details = builder.build_connection_details()

    assert details["host"] == (
        "test-db-database-service.test-namespace.svc.cluster.local"
    )
    assert details["port"] == DATABASE_ENGINES[engine]["port"]
    assert "database_name" in details


@pytest.mark.parametrize(
    ("engine", "prefix"),
    [
        ("postgres", "postgresql://"),
        ("mongodb", "mongodb://"),
        ("mysql", "mysql://"),
        ("redis", "redis://"),
    ],
)
def test_supported_engines_build_connection_strings(engine, prefix):
    builder = DatabaseManifestBuilder(config_for(engine))

    assert builder.build_connection_string().startswith(prefix)


def test_custom_external_host_and_port():
    builder = DatabaseManifestBuilder(
        config_for("postgres", external=True, node_port=30432)
    )

    details = builder.build_connection_details(
        host="192.168.68.121",
        port=30432,
    )

    assert details["host"] == "192.168.68.121"
    assert details["port"] == 30432


def test_internal_service_is_cluster_ip():
    service = DatabaseManifestBuilder(
        config_for("postgres")
    ).build_service()

    assert service["spec"]["type"] == "ClusterIP"
    assert service["metadata"]["name"] == "test-db-database-service"
    assert service["spec"]["ports"][0]["port"] == 5432


def test_external_service_is_node_port():
    service = DatabaseManifestBuilder(
        config_for("postgres", external=True, node_port=30432)
    ).build_service()

    assert service["spec"]["type"] == "NodePort"
    assert service["spec"]["ports"][0]["nodePort"] == 30432


def test_external_service_without_node_port_allows_kubernetes_assignment():
    service = DatabaseManifestBuilder(
        config_for("postgres", external=True)
    ).build_service()

    assert service["spec"]["type"] == "NodePort"


@pytest.mark.parametrize("engine", ["", "oracle", "invalid", None])
def test_invalid_engine_is_rejected(engine):
    with pytest.raises((ValueError, TypeError)):
        DatabaseManifestBuilder(config_for(engine))


def test_missing_required_credentials_is_rejected():
    config = config_for("postgres")
    config["credentials"] = {}

    with pytest.raises(ValueError):
        DatabaseManifestBuilder(config)


@pytest.mark.parametrize("port", [0, -1, 65536, "invalid"])
def test_invalid_database_port_is_rejected(port):
    with pytest.raises((ValueError, TypeError)):
        DatabaseManifestBuilder(config_for("postgres", port=port))


@pytest.mark.parametrize("node_port", [0, -1, 65536, "invalid"])
def test_invalid_node_port_is_rejected(node_port):
    with pytest.raises((ValueError, TypeError)):
        DatabaseManifestBuilder(
            config_for("postgres", node_port=node_port)
        )


@pytest.mark.parametrize("port", [0, -1, 65536, "invalid"])
def test_invalid_connection_port_override_is_rejected(port):
    builder = DatabaseManifestBuilder(config_for("postgres"))

    with pytest.raises((ValueError, TypeError)):
        builder.build_connection_details(port=port)


def test_secret_contains_database_credentials():
    builder = DatabaseManifestBuilder(config_for("postgres"))

    secret = builder.build_secret()

    assert secret["kind"] == "Secret"
    assert secret["metadata"]["name"] == "test-db-database-secret"
    assert secret["metadata"]["namespace"] == "test-namespace"
    assert secret["stringData"] == credentials_for("postgres")


def test_provision_database_returns_connection_information(monkeypatch):
    class FakeBuilder:
        app_name = "test-db"
        namespace = "test-namespace"
        engine = "postgres"

        def __init__(self, config):
            pass

        def build_all_listed(self):
            return {"items": []}

        def build_connection_string(self):
            return "postgresql://user:password@host:5432/test"

        def build_connection_details(self):
            return {
                "host": "host",
                "port": 5432,
                "database_name": "test",
            }

        def build_connection_credentials(self):
            return {
                "POSTGRES_USER": "test-user",
                "POSTGRES_PASSWORD": "test-password",
                "POSTGRES_DB": "test",
            }

    monkeypatch.setattr(deploy, "_require_kube_client", lambda: object())
    monkeypatch.setattr(
        deploy,
        "create_namespace_if_not_exists",
        lambda namespace: None,
    )
    monkeypatch.setattr(deploy, "DatabaseManifestBuilder", FakeBuilder)
    monkeypatch.setattr(
        deploy,
        "_apply_database_manifests",
        lambda manifests, namespace: None,
    )

    result = deploy.provision_database(config_for("postgres"))

    assert result["status"] == "success"
    assert result["host"] == "host"
    assert result["port"] == 5432
    assert result["database_name"] == "test"
    assert result["connection_details"]["credentials"]["POSTGRES_USER"] == "test-user"
    assert "manifest" not in result
    assert result["node_port"] is None
    assert result["connection_string"].startswith("postgresql://")


def test_external_provisioning_returns_node_port(monkeypatch):
    class FakeBuilder:
        app_name = "test-db"
        namespace = "test-namespace"
        engine = "postgres"

        def __init__(self, config):
            pass

        def build_all_listed(self):
            return {"items": []}

        def build_connection_string(self):
            return "postgresql://user:password@host:5432/test"

        def build_connection_details(self):
            return {
                "host": "host",
                "port": 5432,
                "database_name": "test",
            }

        def build_connection_credentials(self):
            return {
                "POSTGRES_USER": "test-user",
                "POSTGRES_PASSWORD": "test-password",
                "POSTGRES_DB": "test",
            }

    class FakePort:
        node_port = 30432

    class FakeService:
        class Spec:
            ports = [FakePort()]

        spec = Spec()

    class FakeCoreApi:
        def read_namespaced_service(self, name, namespace):
            assert name == "test-db-database-service"
            assert namespace == "test-namespace"
            return FakeService()

    monkeypatch.setattr(deploy, "_require_kube_client", lambda: object())
    monkeypatch.setattr(
        deploy,
        "create_namespace_if_not_exists",
        lambda namespace: None,
    )
    monkeypatch.setattr(deploy, "DatabaseManifestBuilder", FakeBuilder)
    monkeypatch.setattr(
        deploy,
        "_apply_database_manifests",
        lambda manifests, namespace: None,
    )
    monkeypatch.setattr(
        deploy.client,
        "CoreV1Api",
        lambda client: FakeCoreApi(),
    )

    result = deploy.provision_database(
        config_for("postgres", external=True)
    )

    assert result["node_port"] == 30432


@pytest.mark.parametrize("value", [None, [], "invalid", 123])
def test_provision_database_rejects_non_dictionary(value):
    with pytest.raises(ValueError):
        deploy.provision_database(value)


def test_provision_database_requires_namespace(monkeypatch):
    config = config_for("postgres")
    del config["namespace"]

    monkeypatch.setattr(deploy, "_require_kube_client", lambda: object())

    with pytest.raises(KeyError):
        deploy.provision_database(config)