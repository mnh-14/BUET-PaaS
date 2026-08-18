"""Submit and observe the teammate-owned Kubernetes build/deploy manifests."""

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from deployer.k3s_conf import JobPipelineBuilder, PaaSManifestBuilder  # noqa: E402


@dataclass(frozen=True)
class KubernetesResult:
    public_url: str
    build_job_name: str
    deployment_name: str
    service_name: str
    ingress_name: str


class KubernetesDeploymentError(RuntimeError):
    pass


class KubernetesService:
    """Small adapter around the official Kubernetes Python client."""

    def __init__(self) -> None:
        try:
            from kubernetes import client, config, utils, watch
        except ImportError as exc:
            raise KubernetesDeploymentError(
                "The Kubernetes Python client is not installed"
            ) from exc

        self.client = client
        self.utils = utils
        self.watch = watch
        try:
            if os.getenv("KUBERNETES_SERVICE_HOST"):
                config.load_incluster_config()
            else:
                config.load_kube_config(
                    config_file=os.getenv("KUBECONFIG") or None
                )
        except Exception as exc:
            raise KubernetesDeploymentError(
                "Kubernetes configuration is unavailable"
            ) from exc

        self.api_client = client.ApiClient()
        self.core_api = client.CoreV1Api(self.api_client)
        self.batch_api = client.BatchV1Api(self.api_client)
        self.apps_api = client.AppsV1Api(self.api_client)
        self.networking_api = client.NetworkingV1Api(self.api_client)

    def ensure_namespace(self, namespace: str) -> None:
        try:
            self.core_api.read_namespace(namespace)
        except self.client.ApiException as exc:
            if exc.status != 404:
                raise
            self.core_api.create_namespace(
                self.client.V1Namespace(
                    metadata=self.client.V1ObjectMeta(name=namespace)
                )
            )

    def create_github_secret(
        self, namespace: str, deployment_id: str, token: str
    ) -> str:
        name = f"github-clone-{deployment_id}"[:63].rstrip("-")
        body = self.client.V1Secret(
            metadata=self.client.V1ObjectMeta(
                name=name,
                namespace=namespace,
                labels={"managed-by": "paas-backend"},
            ),
            string_data={"token": token},
            type="Opaque",
        )
        try:
            self.core_api.create_namespaced_secret(namespace, body)
        except self.client.ApiException as exc:
            if exc.status != 409:
                raise
            self.core_api.replace_namespaced_secret(name, namespace, body)
        return name

    def delete_secret(self, namespace: str, name: str | None) -> None:
        if not name:
            return
        try:
            self.core_api.delete_namespaced_secret(name, namespace)
        except self.client.ApiException as exc:
            if exc.status != 404:
                raise

    def submit_build(self, config: dict[str, Any], secret_name: str | None) -> str:
        builder = JobPipelineBuilder(
            app_name=config["app_name"], namespace=config["namespace"]
        )
        builder.apply_git_cloner(
            git_url=config["git_url"],
            branch=config["git_branch"],
            github_secret_name=secret_name,
        )
        builder.apply_kaniko_build(
            image_destination=config["image"],
            dockerfile_path=config["dockerfile_path"],
        )
        manifest = builder.build()
        name = manifest["metadata"]["name"]
        try:
            self.batch_api.delete_namespaced_job(
                name, config["namespace"], propagation_policy="Foreground"
            )
        except self.client.ApiException as exc:
            if exc.status != 404:
                raise
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                self.batch_api.read_namespaced_job(name, config["namespace"])
            except self.client.ApiException as exc:
                if exc.status == 404:
                    break
                raise
            time.sleep(0.5)
        else:
            raise KubernetesDeploymentError("Previous Kubernetes build Job is still deleting")
        self.utils.create_from_dict(self.api_client, manifest)
        return name

    def wait_for_build(self, namespace: str, job_name: str, timeout: int) -> None:
        watcher = self.watch.Watch()
        try:
            for event in watcher.stream(
                self.batch_api.list_namespaced_job,
                namespace=namespace,
                field_selector=f"metadata.name={job_name}",
                timeout_seconds=timeout,
            ):
                job = event["object"]
                if job.status.succeeded:
                    return
                if job.status.failed and job.status.failed > 1:
                    raise KubernetesDeploymentError(self._build_failure(namespace, job_name))
        finally:
            watcher.stop()
        raise KubernetesDeploymentError("Kubernetes build timed out")

    def _build_failure(self, namespace: str, job_name: str) -> str:
        pods = self.core_api.list_namespaced_pod(
            namespace, label_selector=f"job-name={job_name}"
        ).items
        if not pods:
            return "Kubernetes build Job failed before creating a Pod"
        pod = pods[-1]
        try:
            logs = self.core_api.read_namespaced_pod_log(
                pod.metadata.name, namespace, tail_lines=40
            )
        except Exception:
            logs = ""
        reason = pod.status.reason or "Kubernetes build Job failed"
        return f"{reason}: {logs[-4000:]}" if logs else reason

    def submit_application(self, config: dict[str, Any]) -> dict[str, str]:
        manifests = PaaSManifestBuilder(config=config).build_all()
        for manifest in manifests.values():
            self._create_or_replace(manifest, config["namespace"])
        return {
            "deployment_name": f"{config['app_name']}-deployment",
            "service_name": f"{config['app_name']}-service",
            "ingress_name": f"{config['app_name']}-ingress",
        }

    def _create_or_replace(self, manifest: dict[str, Any], namespace: str) -> None:
        kind = manifest["kind"]
        name = manifest["metadata"]["name"]
        try:
            self.utils.create_from_dict(self.api_client, manifest)
            return
        except self.client.ApiException as exc:
            if exc.status != 409:
                raise
        if kind == "Deployment":
            self.apps_api.patch_namespaced_deployment(name, namespace, manifest)
        elif kind == "Service":
            self.core_api.patch_namespaced_service(name, namespace, manifest)
        elif kind == "Ingress":
            self.networking_api.patch_namespaced_ingress(name, namespace, manifest)
        else:
            raise KubernetesDeploymentError(f"Cannot replace Kubernetes {kind}")

    def wait_for_application(
        self, namespace: str, deployment_name: str, ingress_name: str, timeout: int
    ) -> str:
        watcher = self.watch.Watch()
        try:
            for event in watcher.stream(
                self.apps_api.list_namespaced_deployment,
                namespace=namespace,
                field_selector=f"metadata.name={deployment_name}",
                timeout_seconds=timeout,
            ):
                deployment = event["object"]
                desired = deployment.spec.replicas or 1
                if (deployment.status.available_replicas or 0) >= desired:
                    ingress = self.networking_api.read_namespaced_ingress(
                        ingress_name, namespace
                    )
                    rules = ingress.spec.rules or []
                    if not rules or not rules[0].host:
                        raise KubernetesDeploymentError(
                            "Deployment is ready but Ingress has no public host"
                        )
                    return f"http://{rules[0].host}"
        finally:
            watcher.stop()
        raise KubernetesDeploymentError("Application did not become ready in time")

    def delete_project(self, namespace: str, app_name: str) -> None:
        targets = (
            (self.apps_api.delete_namespaced_deployment, f"{app_name}-deployment"),
            (self.core_api.delete_namespaced_service, f"{app_name}-service"),
            (self.networking_api.delete_namespaced_ingress, f"{app_name}-ingress"),
            (self.batch_api.delete_namespaced_job, f"{app_name}-{namespace}-build-job"),
        )
        for delete, name in targets:
            try:
                delete(name, namespace)
            except self.client.ApiException as exc:
                if exc.status != 404:
                    raise
