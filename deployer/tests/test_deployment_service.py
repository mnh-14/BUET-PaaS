import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from kubernetes import client, config
from kubernetes.stream import stream
import yaml


NAMESPACE = "random-user-a"
BASE_URL = os.getenv("DEPLOYER_URL", "http://localhost:5000").rstrip("/")
POLL_INTERVAL_SECONDS = float(os.getenv("DEPLOYER_POLL_INTERVAL_SECONDS", "30"))
POLL_TIMEOUT_SECONDS = float(os.getenv("DEPLOYER_POLL_TIMEOUT_SECONDS", "1800"))
LOG_DIR = Path(__file__).resolve().parent / "log"


user_config = {
    "app_name": "calculator",
    "git_url": "https://github.com/mnh-14/calculator-tester.git",
    "git_branch": "main",
    "dockerfile_path": "Dockerfile",

    "container_port": 8080,
    "namespace": NAMESPACE,
    "replicas": 2,
    "grace_period_seconds": 30,

    "cpu_request": "100m",
    "cpu_limit": "500m",
    "memory_request": "256Mi",
    "memory_limit": "512Mi",
}

build_passed = None


def _load_kube_client():
    try:
        if os.getenv("KUBERNETES_SERVICE_HOST"):
            config.load_incluster_config()
        else:
            config.load_kube_config()
    except Exception as exc:
        pytest.fail(f"Unable to load Kubernetes configuration: {exc}")
    return client.CoreV1Api()


def _post(path, payload):
    request = Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            details = json.loads(body)
        except json.JSONDecodeError:
            details = body
        pytest.fail(f"POST {path} returned HTTP {exc.code}: {details}")
    except URLError as exc:
        pytest.fail(f"Unable to reach deployer at {BASE_URL}: {exc.reason}")


def _poll_status(path, terminal_states, pending_states):
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        _, response = _post(path, {"name": user_config["app_name"], "namespace": NAMESPACE})
        status = response.get("result")
        print(f"{path}: {status}")

        if status in terminal_states:
            return status
        if status not in pending_states:
            return status or "Unknown"
        if time.monotonic() >= deadline:
            return "Unknown"
        time.sleep(POLL_INTERVAL_SECONDS)


def _resource_dict(resource):
    return resource.to_dict() if hasattr(resource, "to_dict") else resource


def _format_kubectl_result(command, result):
    """Format one command and its output as a readable transcript section."""
    if isinstance(result, str):
        output = result
    else:
        output = yaml.safe_dump(result, sort_keys=False, default_flow_style=False)
    return f"$ {command}\n{output.rstrip()}\n"


def _safe_pod_log(api, pod_name, container_name, previous=False):
    """Read current or previous logs, preserving unavailable-log errors in the report."""
    try:
        return api.read_namespaced_pod_log(
            pod_name,
            NAMESPACE,
            container=container_name,
            previous=previous,
            timestamps=True,
        )
    except client.exceptions.ApiException as exc:
        return f"[Unable to read logs: {exc.reason}]"


def _safe_exec(api, pod_name, command, container_name):
    """Run a diagnostic command inside a pod without hiding command failures."""
    try:
        result = stream(
            api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=NAMESPACE,
            command=command,
            container=container_name,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        return result or "[Command returned no output]"
    except client.exceptions.ApiException as exc:
        return f"[Unable to execute command: {exc.reason}]"


def _write_pod_diagnostics(api, label_selector, filename, parent_reader=None, parent_command=None):
    """Write a standard kubectl-style diagnostic transcript for the selected pods."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    pods = api.list_namespaced_pod(NAMESPACE, label_selector=label_selector).items
    sections = [
        "BUET-PaaS Kubernetes Diagnostic Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Namespace: {NAMESPACE}",
        f"Pod selector: {label_selector}",
        "",
        "Each section shows the kubectl command to reproduce the captured output.",
        "",
    ]

    # This is equivalent to: kubectl get deployment,service,ingress,pods -n random-user-a
    apps_api = client.AppsV1Api(api.api_client)
    networking_api = client.NetworkingV1Api(api.api_client)
    deployments = apps_api.list_namespaced_deployment(NAMESPACE).items
    services = api.list_namespaced_service(NAMESPACE).items
    ingresses = networking_api.list_namespaced_ingress(NAMESPACE).items
    sections.append("## Resource listing\n")
    sections.append(_format_kubectl_result(
        f"kubectl get deployment,service,ingress,pods -n {NAMESPACE}",
        {
            "deployments": [_resource_dict(item) for item in deployments],
            "services": [_resource_dict(item) for item in services],
            "ingresses": [_resource_dict(item) for item in ingresses],
            "pods": [_resource_dict(item) for item in pods],
        },
    ))

    # This is equivalent to: kubectl get deployment calculator-deployment -n random-user-a -o yaml
    deployment_name = f"{user_config['app_name']}-deployment"
    try:
        deployment = apps_api.read_namespaced_deployment(deployment_name, NAMESPACE)
        sections.append("## Deployment manifest\n")
        sections.append(_format_kubectl_result(
            f"kubectl get deployment {deployment_name} -n {NAMESPACE} -o yaml",
            _resource_dict(deployment),
        ))
    except client.exceptions.ApiException as exc:
        sections.append(_format_kubectl_result(
            f"kubectl get deployment {deployment_name} -n {NAMESPACE} -o yaml",
            f"[Unable to read deployment: {exc.reason}]",
        ))

    for pod in pods:
        pod_name = pod.metadata.name
        container_specs = list(pod.spec.init_containers or []) + list(pod.spec.containers or [])
        for container in container_specs:
            # This is equivalent to: kubectl logs <POD NAME> -f
            sections.append(f"## Current logs: {pod_name} / {container.name}\n")
            sections.append(_format_kubectl_result(
                f"kubectl logs {pod_name} -n {NAMESPACE} -c {container.name} -f",
                _safe_pod_log(api, pod_name, container.name),
            ))

            # This is equivalent to: kubectl logs -l app=calculator -n random-user-a --previous
            sections.append(f"## Previous logs: {pod_name} / {container.name}\n")
            sections.append(_format_kubectl_result(
                f"kubectl logs -l app={user_config['app_name']} -n {NAMESPACE} -c {container.name} --previous",
                _safe_pod_log(api, pod_name, container.name, previous=True),
            ))

            # This is equivalent to: kubectl exec -it <POD NAME> -n random-user-a -- cat /etc/nginx/conf.d/default.conf
            sections.append(f"## Nginx configuration: {pod_name} / {container.name}\n")
            sections.append(_format_kubectl_result(
                f"kubectl exec -it {pod_name} -n {NAMESPACE} -c {container.name} -- cat /etc/nginx/conf.d/default.conf",
                _safe_exec(api, pod_name, ["cat", "/etc/nginx/conf.d/default.conf"], container.name),
            ))

    if parent_reader is not None:
        sections.append("## Parent resource\n")
        sections.append(_format_kubectl_result(parent_command or "kubectl get job -o yaml", _resource_dict(parent_reader())))

    # Events explain scheduling, image-pull, probe, and mount failures behind pod states.
    event_selector = f"involvedObject.namespace={NAMESPACE}"
    events = api.list_namespaced_event(NAMESPACE, field_selector=event_selector).items
    sections.append("## Kubernetes events\n")
    sections.append(_format_kubectl_result(
        f"kubectl get events -n {NAMESPACE} --field-selector involvedObject.namespace={NAMESPACE}",
        [_resource_dict(event) for event in events],
    ))

    output_path = LOG_DIR / filename
    output_path.write_text("\n".join(sections) + "\n", encoding="utf-8")
    print(f"Kubernetes diagnostics written to {output_path}")
    print(output_path.read_text(encoding="utf-8"))


def _diagnostic_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def create_namespace():
    api = _load_kube_client()
    try:
        api.read_namespace(NAMESPACE)
    except client.exceptions.ApiException as exc:
        if exc.status != 404:
            pytest.fail(f"Unable to inspect namespace {NAMESPACE}: {exc}")
    else:
        api.delete_namespace(NAMESPACE)
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                api.read_namespace(NAMESPACE)
            except client.exceptions.ApiException as exc:
                if exc.status == 404:
                    break
                pytest.fail(f"Unable to wait for namespace deletion: {exc}")
            time.sleep(min(POLL_INTERVAL_SECONDS, 5))
        else:
            pytest.fail(f"Timed out deleting namespace {NAMESPACE}")

    status, response = _post("/api/namespace", {"namespace": NAMESPACE})
    assert status == 201
    assert response.get("status") == "success"


def check_build_status():
    return _poll_status(
        "/api/build/status",
        terminal_states={"Succeeded", "Failed", "Unknown"},
        pending_states={"Pending", "Running"},
    )


def check_deployment_status():
    return _poll_status(
        "/api/deploy/status",
        terminal_states={"Running", "Failed", "Unknown"},
        pending_states={"Pending"},
    )


@pytest.mark.run(order=1)
def test_health_check():
    status, response = _post("/health", {})
    assert status == 200
    assert response.get("status") == "ok"
    if status != 200 or response.get("status") != "ok":
        pytest.exit("CRITICAL: Deployer service is not healthy; aborting tests.", returncode=1)

@pytest.mark.run(order=2)
def test_build_pipeline():
    global build_passed
    create_namespace()
    status, response = _post("/api/build", {"user_config": user_config})
    assert status == 202
    assert response.get("status") == "success"

    build_status = check_build_status()
    api = _load_kube_client()
    job_name = f"{user_config['app_name']}-{NAMESPACE}-build-job"
    _write_pod_diagnostics(
        api,
        f"app={user_config['app_name']},paas-stage=build-job",
        f"build_logs-{_diagnostic_timestamp()}.txt",
        parent_reader=lambda: client.BatchV1Api(api.api_client).read_namespaced_job(job_name, NAMESPACE),
        parent_command=f"kubectl get job {job_name} -n {NAMESPACE} -o yaml",
    )
    build_passed = build_status == "Succeeded"
    assert build_status == "Succeeded", f"Build ended with status {build_status}"

@pytest.mark.run(order=3)
def test_deploy_pipeline():
    if build_passed is False:
        pytest.skip("Build pipeline did not succeed")

    status, response = _post("/api/deploy", {"user_config": user_config})
    assert status == 202
    assert response.get("status") == "success"

    deployment_status = check_deployment_status()
    api = _load_kube_client()
    deployment_name = f"{user_config['app_name']}-deployment"
    _write_pod_diagnostics(
        api,
        f"app={user_config['app_name']}",
        f"deploy_logs-{_diagnostic_timestamp()}.txt",
        parent_reader=lambda: client.AppsV1Api(api.api_client).read_namespaced_deployment(deployment_name, NAMESPACE),
        parent_command=f"kubectl get deployment {deployment_name} -n {NAMESPACE} -o yaml",
    )
    assert deployment_status == "Running", f"Deployment ended with status {deployment_status}"