import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from kubernetes import client, config
from kubernetes.stream import stream
import yaml


NAMESPACE = "random-user-a"
BASE_URL = os.getenv(
	"DEPLOYER_URL",
	"http://deployment-service.buet-paas-system-team23.192.168.64.121.sslip.io",
).rstrip("/")
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


def _fail(message):
	"""Print the only normal script output: a concise failure statement."""
	print(f"FAIL: {message}")


def _progress(message):
	"""Print a short description of the current test phase."""
	print(f"[INFO] {message}")


def _load_kube_client():
	_progress("Loading Kubernetes client configuration")
	try:
		if os.getenv("KUBERNETES_SERVICE_HOST"):
			config.load_incluster_config()
		else:
			config.load_kube_config()
		return client.CoreV1Api()
	except Exception as exc:
		_fail(f"Unable to load Kubernetes configuration: {exc}")
		return None


def _request(method, path, payload=None):
	data = None if payload is None else json.dumps(payload).encode("utf-8")
	headers = {"Content-Type": "application/json"} if payload is not None else {}
	request = Request(
		f"{BASE_URL}{path}",
		data=data,
		headers=headers,
		method=method,
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
		_fail(f"{method} {path} returned HTTP {exc.code}: {details}")
	except URLError as exc:
		_fail(f"Unable to reach deployer at {BASE_URL}: {exc.reason}")
	return None, None


def _post(path, payload):
	return _request("POST", path, payload)


def _get(path):
	return _request("GET", path)


def _poll_status(path, terminal_states, pending_states):
	_progress(f"Starting status polling for {path}")
	deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
	last_status = None
	while True:
		status_code, response = _post(
			path,
			{"name": user_config["app_name"], "namespace": NAMESPACE},
		)
		if status_code is None or response is None:
			return "Unknown"

		status = response.get("result")
		if status != last_status:
			_progress(f"{path} status: {status}")
			last_status = status
		if status in terminal_states:
			_progress(f"{path} reached terminal status: {status}")
			return status
		if status not in pending_states:
			return status or "Unknown"
		if time.monotonic() >= deadline:
			_fail(f"{path} polling timed out after {POLL_TIMEOUT_SECONDS} seconds")
			return "Unknown"
		time.sleep(POLL_INTERVAL_SECONDS)


def _resource_dict(resource):
	return resource.to_dict() if hasattr(resource, "to_dict") else resource


def _format_kubectl_result(command, result):
	"""Format a command and its captured output for the diagnostic transcript."""
	if isinstance(result, str):
		output = result
	else:
		output = yaml.safe_dump(result, sort_keys=False, default_flow_style=False)
	return f"$ {command}\n{output.rstrip()}\n"


def _safe_pod_log(api, pod_name, container_name, previous=False):
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
	"""Write kubectl-style diagnostics without printing the report to the terminal."""
	_progress(f"Collecting Kubernetes diagnostics for selector '{label_selector}'")
	LOG_DIR.mkdir(parents=True, exist_ok=True)
	sections = [
		"BUET-PaaS Kubernetes Diagnostic Report",
		f"Generated: {datetime.now(timezone.utc).isoformat()}",
		f"Namespace: {NAMESPACE}",
		f"Pod selector: {label_selector}",
		"",
		"Each section shows the kubectl command to reproduce the captured output.",
		"",
	]

	try:
		# Equivalent to: kubectl get deployment,service,ingress,pods -n random-user-a
		pods = api.list_namespaced_pod(NAMESPACE, label_selector=label_selector).items
		apps_api = client.AppsV1Api(api.api_client)
		networking_api = client.NetworkingV1Api(api.api_client)
		deployments = apps_api.list_namespaced_deployment(NAMESPACE).items
		services = api.list_namespaced_service(NAMESPACE).items
		ingresses = networking_api.list_namespaced_ingress(NAMESPACE).items
		sections.extend([
			"## Resource listing\n",
			_format_kubectl_result(
				f"kubectl get deployment,service,ingress,pods -n {NAMESPACE}",
				{
					"deployments": [_resource_dict(item) for item in deployments],
					"services": [_resource_dict(item) for item in services],
					"ingresses": [_resource_dict(item) for item in ingresses],
					"pods": [_resource_dict(item) for item in pods],
				},
			),
		])

		# Equivalent to: kubectl get deployment calculator-deployment -n random-user-a -o yaml
		deployment_name = f"{user_config['app_name']}-deployment"
		try:
			deployment = apps_api.read_namespaced_deployment(deployment_name, NAMESPACE)
			deployment_result = _resource_dict(deployment)
		except client.exceptions.ApiException as exc:
			deployment_result = f"[Unable to read deployment: {exc.reason}]"
		sections.extend([
			"## Deployment manifest\n",
			_format_kubectl_result(
				f"kubectl get deployment {deployment_name} -n {NAMESPACE} -o yaml",
				deployment_result,
			),
		])

		for pod in pods:
			pod_name = pod.metadata.name
			containers = list(pod.spec.init_containers or []) + list(pod.spec.containers or [])
			for container in containers:
				# Equivalent to: kubectl logs <POD NAME> -f
				sections.extend([
					f"## Current logs: {pod_name} / {container.name}\n",
					_format_kubectl_result(
						f"kubectl logs {pod_name} -n {NAMESPACE} -c {container.name} -f",
						_safe_pod_log(api, pod_name, container.name),
					),
				])

				# Equivalent to: kubectl logs -l app=calculator -n random-user-a --previous
				sections.extend([
					f"## Previous logs: {pod_name} / {container.name}\n",
					_format_kubectl_result(
						f"kubectl logs -l app={user_config['app_name']} -n {NAMESPACE} -c {container.name} --previous",
						_safe_pod_log(api, pod_name, container.name, previous=True),
					),
				])

				# Equivalent to: kubectl exec -it <POD NAME> -n random-user-a -- cat /etc/nginx/conf.d/default.conf
				sections.extend([
					f"## Nginx configuration: {pod_name} / {container.name}\n",
					_format_kubectl_result(
						f"kubectl exec -it {pod_name} -n {NAMESPACE} -c {container.name} -- cat /etc/nginx/conf.d/default.conf",
						_safe_exec(api, pod_name, ["cat", "/etc/nginx/conf.d/default.conf"], container.name),
					),
				])

		if parent_reader is not None:
			sections.extend([
				"## Parent resource\n",
				_format_kubectl_result(
					parent_command or "kubectl get job -o yaml",
					_resource_dict(parent_reader()),
				),
			])

		# Events explain scheduling, image-pull, probe, and mount failures.
		events = api.list_namespaced_event(
			NAMESPACE,
			field_selector=f"involvedObject.namespace={NAMESPACE}",
		).items
		sections.extend([
			"## Kubernetes events\n",
			_format_kubectl_result(
				f"kubectl get events -n {NAMESPACE} --field-selector involvedObject.namespace={NAMESPACE}",
				[_resource_dict(event) for event in events],
			),
		])
	except Exception as exc:
		sections.append(f"## Diagnostic collection error\n{exc}\n")
		_fail(f"Could not collect all Kubernetes diagnostics: {exc}")

	output_path = LOG_DIR / filename
	output_path.write_text("\n".join(sections) + "\n", encoding="utf-8")
	_progress(f"Kubernetes diagnostics written to {output_path}")


def _diagnostic_timestamp():
	return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_namespace():
	_progress(f"Starting namespace preparation for '{NAMESPACE}'")
	api = _load_kube_client()
	if api is None:
		return False

	try:
		_progress(f"Checking whether namespace '{NAMESPACE}' already exists")
		api.read_namespace(NAMESPACE)
		_progress(f"Namespace '{NAMESPACE}' exists; deleting it")
		api.delete_namespace(NAMESPACE)
		deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
		while time.monotonic() < deadline:
			try:
				api.read_namespace(NAMESPACE)
			except client.exceptions.ApiException as exc:
				if exc.status == 404:
					_progress(f"Namespace '{NAMESPACE}' deleted")
					break
				_fail(f"Unable to wait for namespace deletion: {exc}")
				return False
			time.sleep(min(POLL_INTERVAL_SECONDS, 5))
		else:
			_fail(f"Timed out deleting namespace {NAMESPACE}")
			return False
	except client.exceptions.ApiException as exc:
		if exc.status != 404:
			_fail(f"Unable to inspect namespace {NAMESPACE}: {exc}")
			return False

	status, response = _post("/api/namespace", {"namespace": NAMESPACE})
	if status != 201 or not response or response.get("status") != "success":
		_fail(f"Namespace creation failed: HTTP {status}, response={response}")
		return False
	_progress(f"New namespace '{NAMESPACE}' created")
	return True


def test_health_check():
	_progress("Starting deployer health check")
	status, response = _get("/health")
	if status != 200 or not response or response.get("status") != "ok":
		_fail(f"Deployer service is not healthy: HTTP {status}, response={response}")
		return False
	_progress("Deployer health check passed")
	return True


def test_build_pipeline():
	_progress("Starting build pipeline test")
	if not create_namespace():
		return False

	_progress("Submitting build request")
	status, response = _post("/api/build", {"user_config": user_config})
	if status != 202 or not response or response.get("status") != "success":
		_fail(f"Build request failed: HTTP {status}, response={response}")
		return False

	build_status = _poll_status(
		"/api/build/status",
		terminal_states={"Succeeded", "Failed", "Unknown"},
		pending_states={"Pending", "Running"},
	)
	api = _load_kube_client()
	if api is not None:
		job_name = f"{user_config['app_name']}-{NAMESPACE}-build-job"
		_write_pod_diagnostics(
			api,
			f"app={user_config['app_name']},paas-stage=build-job",
			f"build_logs-{_diagnostic_timestamp()}.txt",
			parent_reader=lambda: client.BatchV1Api(api.api_client).read_namespaced_job(job_name, NAMESPACE),
			parent_command=f"kubectl get job {job_name} -n {NAMESPACE} -o yaml",
		)

	if build_status != "Succeeded":
		_fail(f"Build ended with status {build_status}")
		return False
	_progress("Build pipeline test passed")
	return True


def test_deploy_pipeline():
	_progress("Starting deployment pipeline test")
	_progress("Submitting deployment request")
	status, response = _post("/api/deploy", {"user_config": user_config})
	if status != 202 or not response or response.get("status") != "success":
		_fail(f"Deploy request failed: HTTP {status}, response={response}")
		return False

	deployment_status = _poll_status(
		"/api/deploy/status",
		terminal_states={"Running", "Failed", "Unknown"},
		pending_states={"Pending"},
	)
	api = _load_kube_client()
	if api is not None:
		deployment_name = f"{user_config['app_name']}-deployment"
		_write_pod_diagnostics(
			api,
			f"app={user_config['app_name']}",
			f"deploy_logs-{_diagnostic_timestamp()}.txt",
			parent_reader=lambda: client.AppsV1Api(api.api_client).read_namespaced_deployment(deployment_name, NAMESPACE),
			parent_command=f"kubectl get deployment {deployment_name} -n {NAMESPACE} -o yaml",
		)

	if deployment_status != "Running":
		_fail(f"Deployment ended with status {deployment_status}")
		return False
	_progress("Deployment pipeline test passed")
	return True


def main():
	"""Run health, build, and deploy tests sequentially."""
	_progress("Starting deployment service test script")
	if not test_health_check():
		return 1
	if not test_build_pipeline():
		return 1
	if not test_deploy_pipeline():
		return 1
	_progress("All deployment service tests passed")
	return 0


if __name__ == "__main__":
	sys.exit(main())
