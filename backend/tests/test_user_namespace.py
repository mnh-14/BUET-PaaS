import pytest
from fastapi import HTTPException

import main
from kubernetes_service import KubernetesDeploymentError


class FakeUsersCollection:
    def __init__(self):
        self.inserted = None

    def find_one(self, _query):
        return None

    def insert_one(self, document):
        self.inserted = document


def user_body():
    return main.UserCreate(
        user_id="2105001",
        name="Test User",
        email="2105001@cse.buet.ac.bd",
        password="password",
    )


def test_signup_creates_namespace_before_inserting_user(monkeypatch):
    users = FakeUsersCollection()
    events = []

    class FakeKubernetesService:
        def create_namespace(self, namespace):
            events.append(("namespace", namespace))
            return {"status": "success", "namespace": namespace}

    def insert_user(document):
        events.append(("user", document["user_id"]))
        users.inserted = document

    users.insert_one = insert_user
    monkeypatch.setattr(main, "users_col", lambda: users)
    monkeypatch.setattr(main, "KubernetesService", FakeKubernetesService)
    monkeypatch.setattr(main, "hash_password", lambda _password: "hashed")

    result = main.create_user(user_body())

    assert events == [("namespace", "2105001"), ("user", "2105001")]
    assert users.inserted["namespace"] == "2105001"
    assert result["namespace"] == "2105001"


def test_signup_does_not_insert_user_when_namespace_creation_fails(monkeypatch):
    users = FakeUsersCollection()

    class FailingKubernetesService:
        def create_namespace(self, _namespace):
            raise KubernetesDeploymentError("service unavailable")

    monkeypatch.setattr(main, "users_col", lambda: users)
    monkeypatch.setattr(main, "KubernetesService", FailingKubernetesService)

    with pytest.raises(HTTPException) as error:
        main.create_user(user_body())

    assert error.value.status_code == 503
    assert users.inserted is None
