import os
import sys, pprint
from typing import Dict, Any
from k3s_conf import JobPipelineBuilder, PaaSManifestBuilder
from kubernetes import client, config, utils


target_builder_image = "192.168.67.192:80/paas-system/random-guy-with-app:v1.0"
default_worker = "192.168.128.121"
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
    builder = JobPipelineBuilder(app_name=user_config["app_name"])
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
    """Return one of: 'Pending', 'Running', 'Succeeded', 'Failed', 'Unknown'."""
    if not name or not namespace:
        raise ValueError("Both 'name' and 'namespace' are required.")

    if k3s_client is None:
        return "Unknown"

    try:
        job_name = f"{name}-{namespace}-build-job"
        batch_api = client.BatchV1Api(k3s_client)
        job = batch_api.read_namespaced_job(name=job_name, namespace=namespace)

        if getattr(job.status, "succeeded", 0):
            return "Succeeded"
        if getattr(job.status, "failed", 0):
            return "Failed"
        if getattr(job.status, "active", 0):
            return "Running"
        return "Pending"
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return "Unknown"
        print(f"Exception when checking build status: {exc}")
        return "Unknown"


def check_deploy_status(name: str, namespace: str):
    """Return one of: 'Pending', 'Running', 'Succeeded', 'Failed', 'Unknown'."""
    if not name or not namespace:
        raise ValueError("Both 'name' and 'namespace' are required.")

    if k3s_client is None:
        return "Unknown"

    try:
        deployment_name = f"{name}-deployment"
        app_api = client.AppsV1Api(k3s_client)
        deployment = app_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        status = deployment.status

        if status is None:
            return "Unknown"
        if status.conditions:
            for condition in status.conditions:
                if condition.type == "Available" and condition.status == "True":
                    return "Running"
                if condition.type == "Progressing" and condition.reason == "ProgressDeadlineExceeded":
                    return "Failed"
        if status.ready_replicas and status.ready_replicas > 0:
            return "Running"
        if status.replicas and status.replicas > 0:
            return "Pending"
        return "Unknown"
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return "Unknown"
        print(f"Exception when checking deploy status: {exc}")
        return "Unknown"


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
