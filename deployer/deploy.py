import os
import sys, pprint
from typing import Dict, Any, List
from k3s_conf import (
    DATABASE_ENGINES,
    DatabaseManifestBuilder,
    JobPipelineBuilder,
    PaaSManifestBuilder,
)
from kubernetes import client, config, utils


target_builder_image = "192.168.67.192:80/paas-system/random-guy-with-app:v1.0"
default_worker = "192.168.128.121"
builder_namespace = "buet-paas-system-team23"
DEFAULT_FLOATING_IP = os.getenv("DEFAULT_FLOATING_IP", "192.168.68.121")
# destination_image = "192.168.128.4/buet-paas-student-app"

_kube_error = None
k3s_client = None


def _initialize_kube_client():
    global k3s_client, _kube_error
    k3s_client = None
    _kube_error = None

    # Preferred: run inside the cluster using the pod service account.
    try:
        if os.getenv("KUBERNETES_SERVICE_HOST") or os.getenv("KUBERNETES_SERVICE_PORT"):
            config.load_incluster_config()
            k3s_client = client.ApiClient()
            return
    except Exception as exc:  # pragma: no cover - environment dependent
        _kube_error = exc

    # Secondary: run from the control VM / admin machine with a kubeconfig file.
    kubeconfig_path = os.getenv("KUBECONFIG") or os.path.expanduser("~/.kube/config")
    try:
        if kubeconfig_path and os.path.exists(kubeconfig_path):
            config.load_kube_config(config_file=kubeconfig_path)
            k3s_client = client.ApiClient()
            return
    except Exception as exc:  # pragma: no cover - environment dependent
        _kube_error = exc

    try:
        config.load_kube_config()
        k3s_client = client.ApiClient()
    except Exception as exc:  # pragma: no cover - environment dependent
        k3s_client = None
        _kube_error = exc


_initialize_kube_client()


def _require_kube_client():
    if k3s_client is None:
        raise RuntimeError(f"Kubernetes client is unavailable: {_kube_error}")
    return k3s_client



user_config = {
    # ==============================================================================
    # 1. ESSENTIAL PARAMETERS (Required) [PS: Follows our design scheme, app-name provided by user, unique to user, image are handled by us]
    # ==============================================================================
    "app_name": "calculator",                  # Unique application name Provided by the user
    # "image": target_image,                        # [PS: Target container image to deploy, we decide what it is
                                                  # we create it, store it, use it, and deploy it. (e.g., "myregistry.com/myapp:latest")]
    "git_url": "https://github.com/mnh-14/calculator-tester.git",
    "git_branch": "main",                       # Git branch to clone for building the image
    "dockerfile_path": "Dockerfile",              # Path to Dockerfile in the repo (relative to repo root)
    
    # Domain Resolution: Provide at least one (domain_override takes precedence)
    # "worker_ip": "192.168.10.101",               # K3s Node IP -> my-custom-app.192.168.10.101.sslip.io
    # "domain_override": "",                       # e.g., "app.example.com" (Leave empty to use worker_ip)

    # ==============================================================================
    # 2. CORE DEPLOYMENT & NETWORKING (Optional with Defaults)
    # ==============================================================================
    "container_port": 8080,                      # Port your application code actively listens on [PS: Should be fetched from Dockerfile, or default to 8080]
    "namespace": "random-user-a",                   # Target Kubernetes namespace [PS: Based on the username]
    "replicas": 2,                               # Number of running Pod instances (default: 2) [PS: Default 2, ocasionally changable by user]
    # "instance_tier": "standard",                 # Hardware nodeSelector label (e.g., "high-memory") [PS: Not needed as of now]
    
    # Environment Variables [Definitely user input, but can be empty]
    # "env_vars": {
    #     "PORT": "8080",
    #     "NODE_ENV": "production",
    #     "DATABASE_URL": "postgres://user:pass@db-service:5432/mydb"
    # },

    # Health Checks & Lifecycle [healt_path is advanced settings, by default no health checks are configured]
    # "health_path": "/healthz",                   # HTTP GET path for Liveness/Readiness probes
    "grace_period_seconds": 30,                  # Wait time before force-killing a Pod during shutdown

    # Resource Allocations [PS: 2-3 Options Provided for User Convenience, with defaults]
    "cpu_request": "100m",                       # Reserved CPU (100m = 0.1 CPU core)
    "cpu_limit": "500m",                         # Max CPU cap
    "memory_request": "256Mi",                   # Reserved RAM
    "memory_limit": "512Mi",                     # Max RAM cap before OOM kill

    # Pod & Security Context [Always Same for All Apps]
    # "run_as_non_root": True,                     # Force pod to run as non-root user (UID 10001)
    "read_only_rootfs": False,                   # Make container root filesystem read-only

    # ==============================================================================
    # 3. ADVANCED FEATURES & ADD-ONS (Optional Structures)
    # ==============================================================================
    
    # [PS: Taken from frontend backend db]
    # Pre-Deployment Hooks (Init Containers)
    # "pre_deploy_cmd": "python manage.py migrate",# Migration command run before app starts

    # Ingress SSL / TLS
    # "enable_ssl": True,                          # Enable Let's Encrypt TLS via Cert-Manager

    # Persistent Storage Add-On [PS: ]
    # "persistent_storage": {
    #     "size": "20Gi",                          # Storage volume capacity
    #     "mount_path": "/app/storage"             # Path mounted inside the container
    # },

    # Horizontal Pod Autoscaler (HPA)
    # "autoscaling": {
    #     "enabled": True,                         # Enable HPA manifest generation
    #     "min_replicas": 2,                       # Minimum number of pods
    #     "max_replicas": 8,                       # Maximum scale-up capacity
    #     "target_cpu_percent": 80                 # Target CPU utilization percentage
    # },

    # Scheduled Background Tasks (CronJobs) [PS: Only necessary if we include as extra feature]
    # "cron_jobs": [
    #     {
    #         "name": "daily-backup",
    #         "schedule": "0 2 * * *",             # Standard cron expression (2:00 AM daily)
    #         "command": "python manage.py run_backup"
    #     },
    #     {
    #         "name": "hourly-cache-clean",
    #         "schedule": "0 * * * *",             # Hourly execution
    #         "command": "redis-cli flushdb"
    #     }
    # ]
}


def build_image(user_config: Dict[str, Any]):
    if not isinstance(user_config, dict):
        raise ValueError("user_config must be a dictionary")
    _require_kube_client()
    builder = JobPipelineBuilder(app_name=user_config["app_name"], namespace=user_config["namespace"])
    builder.apply_git_cloner(git_url=user_config["git_url"], branch=user_config.get("git_branch", "main"))
    # builder.apply_trivy_scan(severity="CRITICAL,HIGH", fail_on_cve=True)
    user_config["image"] = f"{user_config['app_name']}-{user_config['namespace']}-build:latest"
    builder.apply_kaniko_build(image_destination=user_config["image"], dockerfile_path=user_config.get("dockerfile_path", "Dockerfile"))
    build_conf = builder.build()
    utils.create_from_dict(k3s_client, build_conf)
    return build_conf


def deploy_application(user_config: Dict[str, Any]):
    if not isinstance(user_config, dict):
        raise ValueError("user_config must be a dictionary")
    _require_kube_client()
    user_config["image"] = f"{user_config['app_name']}-{user_config['namespace']}-build:latest"
    manifest_builder = PaaSManifestBuilder(config=user_config)

    manifest_as_list = manifest_builder.build_all_listed()
    utils.create_from_dict(k3s_client, data=manifest_as_list)
    return manifest_as_list


def redeploy_application(user_config: Dict[str, Any]):
    # user_config["image"] = f"{user_config['app_name']}-{user_config['namespace']}-build:latest"
    # manifest_builder = PaaSManifestBuilder(config=user_config)

    # manifest_as_list = manifest_builder.build_all_listed()
    # utils.replace_from_dict(k3s_client, data=manifest_as_list)
    pass

def rollback_application(user_config: Dict[str, Any]):
    # Implement rollback logic here
    print("Rollback functionality is not yet implemented.")


def check_build_status(name: str, namespace: str):
    """Return build status together with a human-readable summary and reason."""
    if not name or not namespace:
        raise ValueError("Both 'name' and 'namespace' are required.")

    if k3s_client is None:
        return {
            "status": "Unknown",
            "summary": "The build status could not be checked.",
            "reason": "Kubernetes client is not initialized.",
            "details": {},
        }

    try:
        job_name = f"{name}-{namespace}-build-job"
        batch_api = client.BatchV1Api(k3s_client)
        job = batch_api.read_namespaced_job(name=job_name, namespace=builder_namespace)
        job_status = job.status
        details = {
            "job_name": job_name,
            "active": getattr(job_status, "active", 0) or 0,
            "succeeded": getattr(job_status, "succeeded", 0) or 0,
            "failed": getattr(job_status, "failed", 0) or 0,
            "start_time": str(getattr(job_status, "start_time", None)),
            "completion_time": str(getattr(job_status, "completion_time", None)),
        }

        if details["succeeded"]:
            return {
                "status": "Succeeded",
                "summary": f"Build job '{job_name}' completed successfully.",
                "reason": "Job completed successfully.",
                "details": details,
            }
        if details["failed"]:
            conditions = [
                condition.to_dict() if hasattr(condition, "to_dict") else str(condition)
                for condition in (getattr(job_status, "conditions", None) or [])
            ]
            details["conditions"] = conditions
            return {
                "status": "Failed",
                "summary": f"Build job '{job_name}' failed.",
                "reason": conditions[0].get("reason", "Job reported failed") if conditions and isinstance(conditions[0], dict) else "Job reported failed.",
                "details": details,
            }
        if details["active"]:
            return {
                "status": "Running",
                "summary": f"Build job '{job_name}' is currently running.",
                "reason": "Job has active pods.",
                "details": details,
            }
        return {
            "status": "Pending",
            "summary": f"Build job '{job_name}' is waiting to start.",
            "reason": "Job has not started and has no completion result.",
            "details": details,
        }
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return {
                "status": "Unknown",
                "summary": f"Build job '{job_name}' was not found.",
                "reason": f"Kubernetes returned HTTP 404 in namespace '{namespace}'.",
                "details": {"job_name": job_name, "http_status": exc.status},
            }
        return {
            "status": "Unknown",
            "summary": f"Unable to read build job '{job_name}'.",
            "reason": str(exc),
            "details": {"job_name": job_name, "http_status": exc.status},
        }


def check_deploy_status(name: str, namespace: str):
    """Return deployment status together with a human-readable summary and reason."""
    if not name or not namespace:
        raise ValueError("Both 'name' and 'namespace' are required.")

    if k3s_client is None:
        return {
            "status": "Unknown",
            "summary": "The deployment status could not be checked.",
            "reason": "Kubernetes client is not initialized.",
            "details": {},
        }

    try:
        deployment_name = f"{name}-deployment"
        app_api = client.AppsV1Api(k3s_client)
        deployment = app_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        status = deployment.status
        details = {
            "deployment_name": deployment_name,
            "replicas": getattr(status, "replicas", 0) or 0 if status else 0,
            "ready_replicas": getattr(status, "ready_replicas", 0) or 0 if status else 0,
            "updated_replicas": getattr(status, "updated_replicas", 0) or 0 if status else 0,
            "available_replicas": getattr(status, "available_replicas", 0) or 0 if status else 0,
        }

        if status is None:
            return {
                "status": "Unknown",
                "summary": f"Deployment '{deployment_name}' has no status yet.",
                "reason": "Kubernetes returned an empty deployment status.",
                "details": details,
            }

        conditions = status.conditions or []
        details["conditions"] = [
            condition.to_dict() if hasattr(condition, "to_dict") else str(condition)
            for condition in conditions
        ]
        for condition in conditions:
            if condition.type == "Available" and condition.status == "True":
                return {
                    "status": "Running",
                    "summary": f"Deployment '{deployment_name}' is running.",
                    "reason": condition.reason or "Available replicas are ready.",
                    "details": details,
                    "url": f"http://{name}.{namespace}.{DEFAULT_FLOATING_IP}.sslip.io"  
                }
            if condition.type == "Progressing" and condition.reason == "ProgressDeadlineExceeded":
                return {
                    "status": "Failed",
                    "summary": f"Deployment '{deployment_name}' failed to become ready.",
                    "reason": condition.message or condition.reason,
                    "details": details,
                }
        if details["ready_replicas"] > 0:
            return {
                "status": "Running",
                "summary": f"Deployment '{deployment_name}' has ready replicas.",
                "reason": "At least one replica is ready.",
                "details": details,
                "url": f"http://{name}.{namespace}.{DEFAULT_FLOATING_IP}.sslip.io"  
            }
        if details["replicas"] > 0:
            return {
                "status": "Pending",
                "summary": f"Deployment '{deployment_name}' is waiting for replicas.",
                "reason": "Replicas exist but none are ready yet.",
                "details": details,
            }
        return {
            "status": "Unknown",
            "summary": f"Deployment '{deployment_name}' has no active replicas.",
            "reason": "No ready or desired replicas were reported.",
            "details": details,
        }
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return {
                "status": "Unknown",
                "summary": f"Deployment '{deployment_name}' was not found.",
                "reason": f"Kubernetes returned HTTP 404 in namespace '{namespace}'.",
                "details": {"deployment_name": deployment_name, "http_status": exc.status},
            }
        return {
            "status": "Unknown",
            "summary": f"Unable to read deployment '{deployment_name}'.",
            "reason": str(exc),
            "details": {"deployment_name": deployment_name, "http_status": exc.status},
        }


def create_namespace_if_not_exists(namespace: str):
    if not namespace:
        raise ValueError("Namespace cannot be empty.")
    _require_kube_client()
    core_api = client.CoreV1Api(k3s_client)
    try:
        core_api.read_namespace(name=namespace)
        print(f"Namespace '{namespace}' already exists.")
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            ns_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
            core_api.create_namespace(ns_body)
            print(f"Namespace '{namespace}' created.")
        else:
            raise 


# ==============================================================================
# PER-USER DATABASE ORCHESTRATION (PostgreSQL / MongoDB / Redis on k3s)
# ==============================================================================

def _apply_database_manifests(manifest_list: Dict[str, Any], namespace: str) -> None:
    """
    Applies Secret → Service → StatefulSet individually so a rerun of the same
    provision request is idempotent (already-existing resources are skipped).
    """
    _require_kube_client()
    core_api = client.CoreV1Api(k3s_client)
    apps_api = client.AppsV1Api(k3s_client)

    for manifest in manifest_list["items"]:
        kind = manifest["kind"]
        name = manifest["metadata"]["name"]
        try:
            if kind == "Secret":
                core_api.create_namespaced_secret(namespace, manifest)
            elif kind == "Service":
                core_api.create_namespaced_service(namespace, manifest)
            elif kind == "StatefulSet":
                apps_api.create_namespaced_stateful_set(namespace, manifest)
            else:  # pragma: no cover - defensive
                continue
            print(f"  [DB] Created {kind} '{name}' in '{namespace}'.")
        except client.exceptions.ApiException as exc:
            if exc.status == 409:
                print(f"  [DB] {kind} '{name}' already exists — skipping.")
            else:
                raise


def provision_database(user_config: Dict[str, Any]) -> Dict[str, Any]:
    """Create the per-user database workload and return the exposed node port."""
    if not isinstance(user_config, dict):
        raise ValueError("user_config must be a dictionary")
    _require_kube_client()

    namespace = user_config["namespace"]
    create_namespace_if_not_exists(namespace)

    builder = DatabaseManifestBuilder(config=user_config)
    manifest_list = builder.build_all_listed()
    _apply_database_manifests(manifest_list, namespace)

    node_port = None
    if user_config.get("external", False):
        service_name = f"{builder.app_name}-database-service"
        core_api = client.CoreV1Api(k3s_client)
        service = core_api.read_namespaced_service(name=service_name, namespace=namespace)
        ports = getattr(service.spec, "ports", []) or []
        for entry in ports:
            if getattr(entry, "node_port", None):
                node_port = int(entry.node_port)
                break

    return {
        "status": "success",
        "app_name": builder.app_name,
        "namespace": namespace,
        "engine": builder.engine,
        "node_port": node_port,
        "message": f"Database '{builder.app_name}' provisioning submitted.",
        "manifest": manifest_list,
    }


def rotate_database_credentials(user_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace the DB credentials Secret with new values and force the pod to
    restart so the engine picks up the rotated credentials. Data is preserved.
    """
    if not isinstance(user_config, dict):
        raise ValueError("user_config must be a dictionary")
    _require_kube_client()

    builder = DatabaseManifestBuilder(config=user_config)
    namespace = builder.namespace
    secret_name = f"{builder.app_name}-database-secret"
    core_api = client.CoreV1Api(k3s_client)

    secret_manifest = builder.build_secret()
    try:
        core_api.replace_namespaced_secret(
            name=secret_name, namespace=namespace, body=secret_manifest
        )
        print(f"  [DB] Rotated Secret '{secret_name}' in '{namespace}'.")
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            core_api.create_namespaced_secret(namespace, secret_manifest)
            print(f"  [DB] Recreated missing Secret '{secret_name}'.")
        else:
            raise

    # Restart the single stateful pod so it re-reads credentials from the Secret.
    pod_name = f"{builder.app_name}-database-0"
    try:
        core_api.delete_namespaced_pod(name=pod_name, namespace=namespace)
        print(f"  [DB] Restarting pod '{pod_name}'.")
    except client.exceptions.ApiException as exc:
        if exc.status != 404:
            raise

    return {
        "status": "success",
        "app_name": builder.app_name,
        "namespace": namespace,
        "message": "Database credentials rotated and pod restarted.",
    }


def deprovision_database(user_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete the StatefulSet (+ its pods), Service and Secret. By default the
    underlying PersistentVolumeClaims are kept so data can be recovered by
    re-provisioning with the same app_name; pass purge_data=True to delete them.
    """
    if not isinstance(user_config, dict):
        raise ValueError("user_config must be a dictionary")

    app_name = str(user_config.get("app_name", "")).lower().strip()
    namespace = str(user_config.get("namespace", "")).lower().strip()
    if not app_name or not namespace:
        raise ValueError("Both 'app_name' and 'namespace' are required.")

    purge_data = bool(user_config.get("purge_data", False))
    _require_kube_client()

    core_api = client.CoreV1Api(k3s_client)
    apps_api = client.AppsV1Api(k3s_client)

    statefulset_name = f"{app_name}-database"
    service_name = f"{app_name}-database-service"
    secret_name = f"{app_name}-database-secret"

    try:
        apps_api.delete_namespaced_stateful_set(
            name=statefulset_name, namespace=namespace,
        )
        print(f"  [DB] Deleted StatefulSet '{statefulset_name}'.")
    except client.exceptions.ApiException as exc:
        if exc.status != 404:
            raise
    try:
        core_api.delete_namespaced_service(name=service_name, namespace=namespace)
        print(f"  [DB] Deleted Service '{service_name}'.")
    except client.exceptions.ApiException as exc:
        if exc.status != 404:
            raise
    try:
        core_api.delete_namespaced_secret(name=secret_name, namespace=namespace)
        print(f"  [DB] Deleted Secret '{secret_name}'.")
    except client.exceptions.ApiException as exc:
        if exc.status != 404:
            raise

    deleted_claims: List[str] = []
    if purge_data:
        claims = core_api.list_namespaced_persistent_volume_claim(
            namespace, label_selector=f"app={app_name},managed-by=paas-backend"
        )
        for claim in claims.items:
            name = claim.metadata.name
            core_api.delete_namespaced_persistent_volume_claim(name=name, namespace=namespace)
            deleted_claims.append(name)
            print(f"  [DB] Deleted PersistentVolumeClaim '{name}' (purge).")

    return {
        "status": "success",
        "app_name": app_name,
        "namespace": namespace,
        "purge_data": purge_data,
        "deleted_claims": deleted_claims,
        "message": f"Database '{app_name}' deprovisioned.",
    }


def check_database_status(name: str, namespace: str) -> Dict[str, Any]:
    """Report StatefulSet + pod readiness for a per-user database."""
    if not name or not namespace:
        raise ValueError("Both 'name' and 'namespace' are required.")

    if k3s_client is None:
        return {
            "status": "Unknown",
            "summary": "The database status could not be checked.",
            "reason": "Kubernetes client is not initialized.",
            "details": {},
        }

    statefulset_name = f"{name}-database"
    try:
        apps_api = client.AppsV1Api(k3s_client)
        core_api = client.CoreV1Api(k3s_client)

        stateful = apps_api.read_namespaced_stateful_set(
            name=statefulset_name, namespace=namespace
        )
        status = stateful.status
        details = {
            "statefulset": statefulset_name,
            "replicas": getattr(status, "replicas", 0) or 0 if status else 0,
            "ready_replicas": getattr(status, "ready_replicas", 0) or 0 if status else 0,
        }

        pods = core_api.list_namespaced_pod(
            namespace, label_selector=f"app={name}"
        )
        pod_states = []
        for pod in pods.items:
            container = pod.status.container_statuses[0] if pod.status.container_statuses else None
            pod_states.append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "ready": bool(container and container.ready),
                "restart_count": int(container.restart_count) if container else 0,
            })
        details["pods"] = pod_states

        if details["ready_replicas"] >= 1:
            return {
                "status": "Running",
                "summary": f"Database '{statefulset_name}' is ready.",
                "reason": "The stateful pod is Running and its readiness probe succeeds.",
                "details": details,
            }
        if any(p["phase"] == "Failed" or p["phase"] == "CrashLoopBackOff"
               for p in pod_states):
            reason = f"Pod '{statefulset_name}-0' is not healthy."
            return {
                "status": "Failed",
                "summary": f"Database '{statefulset_name}' failed to become ready.",
                "reason": reason,
                "details": details,
            }
        return {
            "status": "Pending",
            "summary": f"Database '{statefulset_name}' is starting.",
            "reason": "The stateful pod exists but is not ready yet.",
            "details": details,
        }
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return {
                "status": "Unknown",
                "summary": f"Database '{statefulset_name}' was not found.",
                "reason": f"Kubernetes returned HTTP 404 in namespace '{namespace}'.",
                "details": {"statefulset": statefulset_name, "http_status": exc.status},
            }
        return {
            "status": "Unknown",
            "summary": f"Unable to read database '{statefulset_name}'.",
            "reason": str(exc),
            "details": {"statefulset": statefulset_name, "http_status": exc.status},
        }


if __name__ == "__main__":
    # take command line input and decide whethere to build image or deploy application, write it yourself
    
    if len(sys.argv) < 2:
        print("Usage: python deploy.py [build|deploy]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "build":
        build_image(user_config)
    elif action == "deploy":
        deploy_application(user_config)
    else:
        print("Invalid action. Use 'build' or 'deploy'.")
        sys.exit(1)
