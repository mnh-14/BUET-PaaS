"""Live integration test for the application deployment deletion endpoint.

This script calls the real deployer HTTP API and the real Kubernetes API.
It intentionally deletes the selected deployment and its persistent volume.

Default deployment target:
    namespace: test-user-002
    project: prob-electronics

Optional environment variables:
    DEPLOY_NAMESPACE
    DEPLOY_PROJECT_NAME

Optional environment variables:
    DEPLOYER_URL
    DEPLOY_DELETE_TIMEOUT_SECONDS
    DEPLOY_DELETE_POLL_SECONDS
"""

import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from kubernetes import client, config


BASE_URL = os.getenv(
    "DEPLOYER_URL",
    "http://deployment-service.buet-paas-system-team23.192.168.64.121.sslip.io",
).rstrip("/")
NAMESPACE = os.getenv("DEPLOY_NAMESPACE", "test-user-002").strip()
PROJECT_NAME = os.getenv("DEPLOY_PROJECT_NAME", "prob-electronics").strip()
TIMEOUT_SECONDS = float(os.getenv("DEPLOY_DELETE_TIMEOUT_SECONDS", "180"))
POLL_SECONDS = float(os.getenv("DEPLOY_DELETE_POLL_SECONDS", "5"))


def request_delete():
    payload = json.dumps({
        "namespace": NAMESPACE,
        "project_name": PROJECT_NAME,
    }).encode("utf-8")
    request = Request(
        f"{BASE_URL}/api/deploy",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(
            f"DELETE /api/deploy returned HTTP {exc.code}: {body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach deployer at {BASE_URL}: {exc}") from exc

    if result.get("status") != "success":
        raise RuntimeError(f"Deletion endpoint reported failure: {result}")

    print(json.dumps(result, indent=2, sort_keys=True))


def load_kubernetes_clients():
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        config.load_incluster_config()
    else:
        config.load_kube_config()

    api_client = client.ApiClient()
    return (
        client.CoreV1Api(api_client),
        client.AppsV1Api(api_client),
        client.NetworkingV1Api(api_client),
        client.AutoscalingV2Api(api_client),
    )


def resource_exists(read_resource):
    try:
        read_resource()
        return True
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return False
        raise


def remaining_resources(clients):
    core_api, apps_api, networking_api, autoscaling_api = clients
    remaining = []

    checks = [
        (
            "Deployment",
            lambda: apps_api.read_namespaced_deployment(
                name=f"{PROJECT_NAME}-deployment", namespace=NAMESPACE
            ),
        ),
        (
            "Service",
            lambda: core_api.read_namespaced_service(
                name=f"{PROJECT_NAME}-service", namespace=NAMESPACE
            ),
        ),
        (
            "Ingress",
            lambda: networking_api.read_namespaced_ingress(
                name=f"{PROJECT_NAME}-ingress", namespace=NAMESPACE
            ),
        ),
        (
            "HorizontalPodAutoscaler",
            lambda: autoscaling_api.read_namespaced_horizontal_pod_autoscaler(
                name=f"{PROJECT_NAME}-hpa", namespace=NAMESPACE
            ),
        ),
        (
            "PersistentVolumeClaim",
            lambda: core_api.read_namespaced_persistent_volume_claim(
                name=f"{PROJECT_NAME}-pvc", namespace=NAMESPACE
            ),
        ),
    ]

    for kind, read_resource in checks:
        if resource_exists(read_resource):
            remaining.append(f"{kind}/{PROJECT_NAME}")

    replica_sets = apps_api.list_namespaced_replica_set(
        namespace=NAMESPACE,
        label_selector=f"app={PROJECT_NAME}",
    ).items
    remaining.extend(f"ReplicaSet/{item.metadata.name}" for item in replica_sets)

    pods = core_api.list_namespaced_pod(
        namespace=NAMESPACE,
        label_selector=f"app={PROJECT_NAME}",
    ).items
    remaining.extend(f"Pod/{item.metadata.name}" for item in pods)

    return remaining


def wait_for_deletion(clients):
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while True:
        remaining = remaining_resources(clients)
        if not remaining:
            return

        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Resources still exist after deletion timeout: "
                + ", ".join(remaining)
            )

        print("Waiting for deletion: " + ", ".join(remaining))
        time.sleep(POLL_SECONDS)


def main():
    try:
        print(
            f"Deleting deployment '{PROJECT_NAME}' in namespace '{NAMESPACE}' "
            f"through {BASE_URL}"
        )
        request_delete()
        clients = load_kubernetes_clients()
        wait_for_deletion(clients)
        print("Deployment resources and controller-owned Pods are deleted.")
        return 0
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
