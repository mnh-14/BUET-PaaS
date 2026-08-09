import subprocess
from unittest.mock import Mock

import main
from config import SonarSettings
from services.sonarqube_service import SonarAnalysisResult, SonarScannerError


COMMIT = "b" * 40


class FakeCollection:
    def __init__(self):
        self.updates = []

    def update_one(self, query, update):
        self.updates.append((query, update))


def install_pipeline_fakes(monkeypatch, scan_outcome, enabled=True):
    deployments = FakeCollection()
    projects = FakeCollection()
    events = []

    def fake_run(command, **kwargs):
        if command[:2] == ["git", "clone"]:
            events.append("clone")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["git", "-C", "/tmp/buetpaas_dep-test"]:
            if "rev-parse" in command:
                return subprocess.CompletedProcess(command, 0, COMMIT + "\n", "")
            events.append("checkout")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["pack", "build"]:
            events.append("build")
        elif command[:2] == ["docker", "run"]:
            events.append("deploy")
        return subprocess.CompletedProcess(command, 0, "", "")

    class FakeSonarService:
        def __init__(self, _settings):
            pass

        def scan_repository(self, *_args, **_kwargs):
            events.append("scan")
            if isinstance(scan_outcome, Exception):
                raise scan_outcome
            return scan_outcome

    monkeypatch.setattr(main, "deployments_col", lambda: deployments)
    monkeypatch.setattr(main, "projects_col", lambda: projects)
    monkeypatch.setattr(main.subprocess, "run", fake_run)
    monkeypatch.setattr(main, "safe_rmtree", lambda _path: None)
    monkeypatch.setattr(main, "pack_available", lambda: True)
    monkeypatch.setattr(main, "find_dockerfile", lambda _path: None)
    monkeypatch.setattr(main, "get_or_create_tunnel", lambda *_args: "http://example")
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(main, "SonarQubeService", FakeSonarService)
    monkeypatch.setattr(
        main.SonarSettings,
        "from_env",
        classmethod(
            lambda cls: SonarSettings(
                enabled, "http://sonar:9000", "token", "sonar-scanner", 300
            )
        ),
    )
    return events, deployments


def result(success=True):
    return SonarAnalysisResult(
        project_key="buet-paas:proj-test",
        commit_sha=COMMIT,
        success=success,
        quality_gate="OK" if success else "ERROR",
        scanner_exit_code=0 if success else 2,
        error=None if success else "SonarQube Quality Gate failed",
    )


def run_deployment():
    main.build_and_deploy(
        "dep-test", "proj-test", "https://github.com/example/repo.git", 9001,
        expected_commit_sha=COMMIT,
    )


def statuses(collection):
    return [
        update["$set"]["status"]
        for _, update in collection.updates
        if "status" in update.get("$set", {})
    ]


def test_successful_pipeline_scans_before_build_and_deploy(monkeypatch):
    events, deployments = install_pipeline_fakes(monkeypatch, result())
    run_deployment()
    assert events == ["clone", "checkout", "scan", "build", "deploy"]
    assert "security_scan_passed" in statuses(deployments)
    assert statuses(deployments)[-1] == "running"


def test_scanner_error_stops_before_build(monkeypatch):
    events, deployments = install_pipeline_fakes(
        monkeypatch, SonarScannerError("scanner failed")
    )
    run_deployment()
    assert events == ["clone", "checkout", "scan"]
    assert statuses(deployments)[-1] == "security_scan_error"


def test_quality_gate_failure_stops_before_build(monkeypatch):
    events, deployments = install_pipeline_fakes(monkeypatch, result(False))
    run_deployment()
    assert events == ["clone", "checkout", "scan"]
    assert statuses(deployments)[-1] == "security_scan_failed"


def test_disabled_scanning_preserves_build_and_deploy(monkeypatch):
    events, deployments = install_pipeline_fakes(monkeypatch, result(), enabled=False)
    run_deployment()
    assert events == ["clone", "checkout", "build", "deploy"]
    assert statuses(deployments)[-1] == "running"
