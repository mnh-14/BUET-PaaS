from unittest.mock import Mock

import pytest

from kubernetes_service import KubernetesDeploymentError, KubernetesService


CONFIG = {
    "deployment_id": "dep-1", "project_id": "proj-1", "app_name": "my-app",
    "namespace": "2105001", "git_url": "https://github.com/a/private.git",
    "git_branch": "main", "dockerfile_path": "Dockerfile", "image": "my-app:latest",
    "container_port": 8080, "replicas": 1, "cpu_request": "100m",
    "cpu_limit": "250m", "memory_request": "128Mi", "memory_limit": "256Mi",
    "env_vars": {}, "grace_period_seconds": 30, "read_only_rootfs": False,
}


def response(status_code=202, body=None):
    result = Mock(status_code=status_code)
    result.json.return_value = body or {"status": "queued"}
    return result


def test_build_request_sends_private_token_only_in_body():
    session = Mock()
    session.request.return_value = response()
    service = KubernetesService("http://vm:8080", "service-secret", session, 0, 1)
    service.start_build(CONFIG, "github-token")
    call = session.request.call_args
    assert call.args[:2] == ("POST", "http://vm:8080/api/v1/build")
    assert call.kwargs["headers"]["Authorization"] == "Bearer service-secret"
    assert call.kwargs["json"]["github_auth"]["token"] == "github-token"
    assert call.kwargs["json"]["namespace"] == "2105001"


def test_status_query_contains_operation_and_identity():
    session = Mock()
    session.request.return_value = response(200, {"status": "started"})
    service = KubernetesService("http://vm:8080", session=session, poll_interval=0)
    assert service.get_status(CONFIG, "build")["status"] == "started"
    params = session.request.call_args.kwargs["params"]
    assert params == {
        "project_name": "my-app", "namespace": "2105001",
        "deployment_id": "dep-1", "type": "build",
    }


def test_unknown_status_fails_closed():
    session = Mock()
    session.request.return_value = response(200, {"status": "mystery"})
    service = KubernetesService("http://vm:8080", session=session)
    with pytest.raises(KubernetesDeploymentError, match="unknown build status"):
        service.get_status(CONFIG, "build")
