import logging
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from config import SonarSettings
from services.sonarqube_service import (
    SonarQubeService,
    SonarQubeUnavailableError,
    SonarScannerError,
    generate_project_key,
)


TOKEN = "top-secret-sonar-token"
COMMIT = "a" * 40


def settings(**overrides):
    values = {
        "enabled": True,
        "host_url": "http://sonarqube:9000",
        "token": TOKEN,
        "scanner_bin": "sonar-scanner",
        "scan_timeout": 300,
    }
    values.update(overrides)
    return SonarSettings(**values)


def response(status="UP", status_code=200, payload=None):
    result = Mock()
    result.status_code = status_code
    result.json.return_value = payload if payload is not None else {"status": status}
    if status_code >= 400:
        error = requests.HTTPError("request failed")
        error.response = result
        result.raise_for_status.side_effect = error
    return result


@pytest.mark.parametrize(
    ("server_status", "available"),
    [("UP", True), ("STARTING", False)],
)
def test_health_statuses(server_status, available):
    session = Mock()
    session.get.return_value = response(server_status)
    service = SonarQubeService(settings(), session=session)

    assert service.check_health() == {
        "available": available,
        "status": server_status,
    }
    session.get.assert_called_once_with(
        "http://sonarqube:9000/api/system/status", timeout=5.0
    )


@pytest.mark.parametrize(
    "error",
    [requests.ConnectionError("offline"), requests.Timeout("slow")],
)
def test_health_connection_and_timeout_failures(error):
    session = Mock()
    session.get.side_effect = error
    assert SonarQubeService(settings(), session=session).check_health() == {
        "available": False,
        "status": "DOWN",
    }


def make_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    scannerwork = repository / ".scannerwork"
    scannerwork.mkdir()
    (scannerwork / "report-task.txt").write_text(
        "ceTaskId=ce-task-1\ndashboardUrl=http://sonar/dashboard\n",
        encoding="utf-8",
    )
    return repository


def service_with_up_health(tmp_path: Path, gate_status="OK") -> SonarQubeService:
    session = Mock()
    def get(url, **_kwargs):
        if url.endswith("/api/system/status"):
            return response()
        if url.endswith("/api/ce/task"):
            return response(payload={"task": {"status": "SUCCESS", "analysisId": "analysis-1"}})
        if url.endswith("/api/qualitygates/project_status"):
            return response(payload={"projectStatus": {
                "status": gate_status,
                "conditions": [{
                    "status": gate_status,
                    "metricKey": "new_security_rating",
                    "comparator": "GT",
                    "actualValue": "3",
                    "errorThreshold": "1",
                }],
            }})
        if url.endswith("/api/issues/search"):
            return response(payload={"issues": [{
                "key": "issue-1",
                "message": "Use a parameterized query",
                "severity": "CRITICAL",
                "type": "VULNERABILITY",
                "rule": "python:S3649",
                "component": "buet-paas:proj-1:app.py",
                "line": 42,
            }]})
        raise AssertionError(f"Unexpected URL: {url}")

    session.get.side_effect = get
    return SonarQubeService(settings(), session=session, workspace_root=tmp_path)


def test_scanner_uses_safe_arguments_environment_and_repository(monkeypatch, tmp_path):
    repository = make_repository(tmp_path)
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, "ANALYSIS SUCCESSFUL, you can find the results at: http://sonar/dashboard", ""
        )
    )
    monkeypatch.setattr(subprocess, "run", run)

    result = service_with_up_health(tmp_path).scan_repository(
        repository, "proj/unsafe value", "Student Project", COMMIT
    )

    assert result.success is True
    assert result.quality_gate == "OK"
    assert result.project_key == generate_project_key("proj/unsafe value")
    command = run.call_args.args[0]
    kwargs = run.call_args.kwargs
    assert kwargs["cwd"] == str(repository)
    assert kwargs["shell"] is False
    assert f"-Dsonar.projectKey={result.project_key}" in command
    assert f"-Dsonar.scm.revision={COMMIT}" in command
    assert TOKEN not in " ".join(command)
    assert kwargs["env"]["SONAR_HOST_URL"] == "http://sonarqube:9000"
    assert kwargs["env"]["SONAR_TOKEN"] == TOKEN


def test_quality_gate_failure_returns_failed_result(monkeypatch, tmp_path):
    repository = make_repository(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess([], 2, "QUALITY GATE STATUS: FAILED", "")),
    )
    result = service_with_up_health(tmp_path).scan_repository(
        repository, "proj-1", "Project", COMMIT
    )
    assert result.success is False
    assert result.quality_gate == "ERROR"
    assert result.conditions[0]["metric"] == "new_security_rating"
    assert result.issues[0]["file"] == "app.py"
    assert result.issues[0]["line"] == 42


def test_successful_scanner_still_stops_when_api_quality_gate_failed(
    monkeypatch, tmp_path
):
    repository = make_repository(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess([], 0, "EXECUTION SUCCESS", "")),
    )
    result = service_with_up_health(tmp_path, gate_status="ERROR").scan_repository(
        repository, "proj-1", "Project", COMMIT
    )
    assert result.success is False
    assert result.quality_gate == "ERROR"


@pytest.mark.parametrize(
    ("side_effect", "message"),
    [
        (FileNotFoundError(), "executable was not found"),
        (subprocess.TimeoutExpired("sonar-scanner", 315), "timed out"),
    ],
)
def test_scanner_missing_and_timeout(monkeypatch, tmp_path, side_effect, message):
    repository = make_repository(tmp_path)
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=side_effect))
    with pytest.raises(SonarScannerError, match=message):
        service_with_up_health(tmp_path).scan_repository(
            repository, "proj-1", "Project", COMMIT
        )


def test_authentication_failure_is_normalized_and_token_not_logged(
    monkeypatch, tmp_path, caplog
):
    repository = make_repository(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                [], 1, "", f"Authentication failed for token {TOKEN}"
            )
        ),
    )
    with caplog.at_level(logging.ERROR), pytest.raises(
        SonarScannerError, match="authentication failed"
    ) as raised:
        service_with_up_health(tmp_path).scan_repository(
            repository, "proj-1", "Project", COMMIT
        )
    assert TOKEN not in str(raised.value)
    assert TOKEN not in caplog.text


def test_unavailable_sonarqube_does_not_start_scanner(monkeypatch, tmp_path):
    repository = make_repository(tmp_path)
    session = Mock()
    session.get.side_effect = requests.ConnectionError("offline")
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    service = SonarQubeService(settings(), session=session, workspace_root=tmp_path)

    with pytest.raises(SonarQubeUnavailableError):
        service.scan_repository(repository, "proj-1", "Project", COMMIT)
    run.assert_not_called()


def test_scanner_failure_when_server_drops_is_normalized(monkeypatch, tmp_path):
    repository = make_repository(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                [], 1, "", "Fail to get bootstrap index: Connection refused"
            )
        ),
    )
    with pytest.raises(SonarScannerError, match="became unavailable"):
        service_with_up_health(tmp_path).scan_repository(
            repository, "proj-1", "Project", COMMIT
        )
