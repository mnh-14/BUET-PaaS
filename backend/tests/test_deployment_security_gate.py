import subprocess

import main
from config import SonarSettings
from services.sonarqube_service import SonarAnalysisResult, SonarScannerError


COMMIT = "b" * 40


class FakeCollection:
    def __init__(self, document):
        self.document = document
        self.updates = []

    def update_one(self, query, update):
        self.updates.append((query, update))
        for key, value in update.get("$set", {}).items():
            if "." not in key:
                self.document[key] = value

    def find_one(self, _query, *_args, **_kwargs):
        return self.document.copy()


def install_pipeline_fakes(monkeypatch, scan_outcome, enabled=True):
    deployments = FakeCollection({
        "deployment_id": "dep-test", "project_id": "proj-test",
        "commit_sha": COMMIT, "status": "queued",
    })
    projects = FakeCollection({
        "project_id": "proj-test", "user_id": "2105001",
        "project_name": "Project", "repo_url": "https://github.com/example/repo.git",
        "deploy_branch": "main", "instance_size": "small", "env_vars": {},
    })
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

    class FakeSonarService:
        def __init__(self, _settings): pass

        def scan_repository(self, *_args, **_kwargs):
            events.append("scan")
            if isinstance(scan_outcome, Exception):
                raise scan_outcome
            return scan_outcome

    class FakeKubernetes:
        def start_build(self, _config, _token):
            events.append("build")
            return {"status": "queued", "build_id": "build-1"}
        def start_deploy(self, _config):
            events.append("deploy")
            return {"status": "queued", "deploy_id": "deploy-1"}
        def wait_for_status(self, _config, operation, _timeout, on_update):
            if operation == "build":
                events.append("build-ready")
                on_update({"status": "started"})
                result = {"status": "completed"}
            else:
                events.append("ready")
                on_update({"status": "started"})
                result = {"status": "running", "url": "http://app.test"}
            on_update(result)
            return result

    monkeypatch.setattr(main, "deployments_col", lambda: deployments)
    monkeypatch.setattr(main, "projects_col", lambda: projects)
    monkeypatch.setattr(main.subprocess, "run", fake_run)
    monkeypatch.setattr(main, "safe_rmtree", lambda _path: None)
    monkeypatch.setattr(main, "find_dockerfile", lambda _path: "/tmp/buetpaas_dep-test")
    monkeypatch.setattr(main, "parse_expose_port", lambda _path: 8080)
    monkeypatch.setattr(main, "SonarQubeService", FakeSonarService)
    monkeypatch.setattr(main, "KubernetesService", FakeKubernetes)
    monkeypatch.setattr(
        main.SonarSettings,
        "from_env",
        classmethod(lambda cls: SonarSettings(
            enabled, "http://sonar:9000", "token", "sonar-scanner", 300
        )),
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
        "dep-test", "proj-test", "https://github.com/example/repo.git",
        expected_commit_sha=COMMIT,
    )


def statuses(collection):
    return [
        update["$set"]["status"]
        for _, update in collection.updates
        if "status" in update.get("$set", {})
    ]


def failures(collection):
    return [
        update["$set"]["failure"]
        for _, update in collection.updates
        if update.get("$set", {}).get("failure")
    ]


def test_successful_pipeline_scans_before_kubernetes_build_and_deploy(monkeypatch):
    events, deployments = install_pipeline_fakes(monkeypatch, result())
    run_deployment()
    assert events == [
        "clone", "checkout", "scan", "build",
        "build-ready", "deploy", "ready",
    ]
    assert "security_scan_passed" in statuses(deployments)
    assert statuses(deployments)[-1] == "running"


def test_scanner_error_stops_before_kubernetes(monkeypatch):
    events, deployments = install_pipeline_fakes(
        monkeypatch, SonarScannerError("scanner failed")
    )
    run_deployment()
    assert events == ["clone", "checkout", "scan"]
    assert statuses(deployments)[-1] == "security_scan_error"
    assert failures(deployments)[-1]["source"] == "sonarqube"
    assert failures(deployments)[-1]["reason"]


def test_quality_gate_failure_stops_before_kubernetes(monkeypatch):
    events, deployments = install_pipeline_fakes(monkeypatch, result(False))
    run_deployment()
    assert events == ["clone", "checkout", "scan"]
    assert statuses(deployments)[-1] == "security_scan_failed"
    assert failures(deployments)[-1]["title"] == "SonarQube Quality Gate failed"
    assert failures(deployments)[-1]["suggestion"]


def test_disabled_scanning_preserves_kubernetes_pipeline(monkeypatch):
    events, deployments = install_pipeline_fakes(monkeypatch, result(), enabled=False)
    run_deployment()
    assert events == [
        "clone", "checkout", "build",
        "build-ready", "deploy", "ready",
    ]
    assert statuses(deployments)[-1] == "running"
