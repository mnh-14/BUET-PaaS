import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

import github_routes
import main
from github_app import GitHubAccessError, GitHubAppService


SHA = "a" * 40


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


def test_clone_uses_configured_timeout(monkeypatch, tmp_path):
    captured = {}

    def run(command, **kwargs):
        captured["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(main, "GIT_CLONE_TIMEOUT_SECONDS", 420)
    monkeypatch.setattr(main.subprocess, "run", run)

    main.clone_repository(
        "https://github.com/student/public.git", str(tmp_path / "repo"),
        installation_id=None, repository_id=None,
    )

    assert captured["timeout"] == 420


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
