import hashlib
import hmac
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import BackgroundTasks

import github_routes
import main
import deployment_service
from github_app import GitHubAccessError, GitHubAppService


SECRET = "webhook-secret"
SHA = "a" * 40


class FakeProjects:
    def __init__(self, documents=None):
        self.documents = documents or []
        self.updates = []

    def find(self, query):
        def matches(document):
            for key, expected in query.items():
                actual = document.get(key)
                if isinstance(expected, dict) and "$in" in expected:
                    if actual not in expected["$in"]:
                        return False
                elif actual != expected:
                    return False
            return True
        return [document for document in self.documents if matches(document)]

    def update_many(self, query, update):
        self.updates.append((query, update))

    def update_one(self, query, update, **_kwargs):
        self.updates.append((query, update))


@pytest.mark.parametrize("signature", [None, "sha256=invalid"])
def test_missing_and_invalid_webhook_signatures(signature):
    assert github_routes.verify_webhook_signature(b"{}", signature, SECRET) is False


def test_valid_webhook_signature_uses_raw_body():
    raw = b'{"zen":"Keep it logically awesome."}'
    signature = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert github_routes.verify_webhook_signature(raw, signature, SECRET) is True
    assert github_routes.verify_webhook_signature(raw + b" ", signature, SECRET) is False


def push_payload(ref="refs/heads/main", *, deleted=False, repository_id=99):
    return {
        "ref": ref,
        "after": "0" * 40 if deleted else SHA,
        "deleted": deleted,
        "installation": {"id": 12},
        "repository": {"id": repository_id, "full_name": "student/app"},
    }


def test_push_to_configured_branch_queues_exact_commit(monkeypatch):
    project = {
        "project_id": "proj-1", "github_installation_id": 12,
        "github_repo_id": 99, "deploy_branch": "main", "auto_deploy": True,
        "github_access_status": "active",
    }
    monkeypatch.setattr(github_routes, "projects_col", lambda: FakeProjects([project]))
    queued = Mock(return_value=({}, True))
    monkeypatch.setattr(github_routes, "queue_deployment", queued)
    status = github_routes._handle_push(
        push_payload(), "delivery-1", BackgroundTasks(), Mock()
    )
    assert status == "accepted"
    assert queued.call_args.args[1] == SHA
    assert queued.call_args.args[2:4] == ("main", "webhook")


@pytest.mark.parametrize(
    "payload",
    [
        push_payload("refs/heads/develop"),
        push_payload("refs/tags/v1.0.0"),
        push_payload(deleted=True),
        push_payload(repository_id=1000),
    ],
)
def test_nonmatching_tag_deleted_and_unknown_pushes_are_ignored(monkeypatch, payload):
    project = {
        "project_id": "proj-1", "github_installation_id": 12,
        "github_repo_id": 99, "deploy_branch": "main", "auto_deploy": True,
        "github_access_status": "active",
    }
    monkeypatch.setattr(github_routes, "projects_col", lambda: FakeProjects([project]))
    queued = Mock()
    monkeypatch.setattr(github_routes, "queue_deployment", queued)
    assert github_routes._handle_push(payload, "delivery", BackgroundTasks(), Mock()) == "ignored"
    queued.assert_not_called()


@pytest.mark.parametrize("action", ["deleted", "suspend"])
def test_installation_removal_or_suspension_disables_projects(monkeypatch, action):
    installations = FakeProjects()
    connections = FakeProjects()
    projects = FakeProjects()
    monkeypatch.setattr(github_routes, "github_installations_col", lambda: installations)
    monkeypatch.setattr(github_routes, "github_connections_col", lambda: connections)
    monkeypatch.setattr(github_routes, "projects_col", lambda: projects)
    payload = {"action": action, "installation": {"id": 12, "account": {"id": 1, "login": "student", "type": "User"}}}
    assert github_routes._handle_installation(payload) == "accepted"
    assert projects.updates[-1][1]["$set"]["auto_deploy"] is False


def test_repository_removal_disables_matching_projects(monkeypatch):
    installations = FakeProjects()
    projects = FakeProjects()
    monkeypatch.setattr(github_routes, "github_installations_col", lambda: installations)
    monkeypatch.setattr(github_routes, "projects_col", lambda: projects)
    payload = {
        "action": "removed", "installation": {"id": 12},
        "repositories_removed": [{"id": 99}],
    }
    github_routes._handle_installation_repositories(payload)
    assert projects.updates[0][0]["github_repo_id"] == {"$in": [99]}
    assert projects.updates[0][1]["$set"]["github_access_status"] == "repository_removed"


class StateCollection:
    def __init__(self, document):
        self.document = document

    def find_one_and_delete(self, query, **_kwargs):
        if self.document and self.document["state_hash"] == query["state_hash"]:
            result, self.document = self.document, None
            return result
        return None


def test_oauth_state_valid_then_reuse_rejected(monkeypatch):
    state = "one-time-state"
    collection = StateCollection({
        "state_hash": github_routes._state_hash(state),
        "user_id": "2105001",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    })
    monkeypatch.setattr(github_routes, "github_oauth_states_col", lambda: collection)
    assert github_routes.consume_oauth_state(state)["user_id"] == "2105001"
    assert github_routes.consume_oauth_state(state) is None


def test_expired_oauth_state_rejected(monkeypatch):
    state = "expired-state"
    collection = StateCollection({
        "state_hash": github_routes._state_hash(state),
        "user_id": "2105001",
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    })
    monkeypatch.setattr(github_routes, "github_oauth_states_col", lambda: collection)
    assert github_routes.consume_oauth_state(state) is None


def test_repository_access_rejects_spoofed_repository_id(monkeypatch):
    service = GitHubAppService(Mock())
    monkeypatch.setattr(service, "list_installation_repositories", lambda _id: [{"id": 1}])
    with pytest.raises(GitHubAccessError):
        service.verify_repository_access(12, 999)


def test_private_clone_uses_environment_and_cleans_askpass(monkeypatch, tmp_path):
    class Service:
        def __init__(self, _settings): pass
        def create_installation_token(self, *_args): return "private-token-value"

    captured = {}
    def run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"].copy()
        captured["askpass"] = kwargs["env"]["GIT_ASKPASS"]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(main, "GitHubAppService", Service)
    monkeypatch.setattr(main.GitHubAppSettings, "from_env", classmethod(lambda cls, **_kwargs: Mock()))
    monkeypatch.setattr(main.subprocess, "run", run)
    main.clone_repository(
        "https://github.com/student/private.git", str(tmp_path / "repo"),
        installation_id=12, repository_id=99,
    )
    assert "private-token-value" not in " ".join(captured["command"])
    assert captured["env"]["BUETPAAS_GIT_TOKEN"] == "private-token-value"
    assert not __import__("pathlib").Path(captured["askpass"]).exists()


def test_same_commit_automatic_deployment_is_idempotent(monkeypatch):
    existing = {"deployment_id": "dep-existing", "automatic_key": f"proj-1:{SHA}"}
    deployments = Mock()
    deployments.find_one.return_value = existing
    monkeypatch.setattr(deployment_service, "deployments_col", lambda: deployments)
    project = {"project_id": "proj-1", "repo_url": "https://github.com/student/app.git", "port": 9000}
    result, created = deployment_service.queue_deployment(
        project, SHA, "main", "webhook", worker=Mock(), background_tasks=BackgroundTasks()
    )
    assert created is False
    assert result["deployment_id"] == "dep-existing"
    deployments.insert_one.assert_not_called()


def test_clone_error_does_not_expose_installation_token(monkeypatch, tmp_path):
    class Service:
        def __init__(self, _settings): pass
        def create_installation_token(self, *_args): return "never-store-this-token"

    helper_path = None
    def run(command, **kwargs):
        nonlocal helper_path
        helper_path = kwargs["env"]["GIT_ASKPASS"]
        return subprocess.CompletedProcess(command, 1, "", "authentication failed never-store-this-token")

    monkeypatch.setattr(main, "GitHubAppService", Service)
    monkeypatch.setattr(main.GitHubAppSettings, "from_env", classmethod(lambda cls, **_kwargs: Mock()))
    monkeypatch.setattr(main.subprocess, "run", run)
    with pytest.raises(RuntimeError) as raised:
        main.clone_repository(
            "https://github.com/student/private.git", str(tmp_path / "repo"),
            installation_id=12, repository_id=99,
        )
    assert "never-store-this-token" not in str(raised.value)
    assert helper_path and not __import__("pathlib").Path(helper_path).exists()
