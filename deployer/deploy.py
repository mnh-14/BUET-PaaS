import os
import sys, pprint
from typing import Dict, Any
from k3s_conf import JobPipelineBuilder, PaaSManifestBuilder
from kubernetes import client, config, utils


target_builder_image = "192.168.67.192:80/paas-system/random-guy-with-app:v1.0"
default_worker = "192.168.128.121"
# destination_image = "192.168.128.4/buet-paas-student-app"

config.load_kube_config()  # Load kubeconfig from default location (~/.kube/config)
k3s_client = client.ApiClient()  # Create an API client instance



user_config = {
    # ==============================================================================
    # 1. ESSENTIAL PARAMETERS (Required) [PS: Follows our design scheme, app-name provided by user, unique to user, image are handled by us]
    # ==============================================================================
    "app_name": "calculator",                  # Unique application name Provided by the user
    # "image": target_image,                        # [PS: Target container image to deploy, we decide what it is
                                                  # we create it, store it, use it, and deploy it. (e.g., "myregistry.com/myapp:latest")]
    
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
    builder = JobPipelineBuilder(app_name=user_config["app_name"])
    builder.apply_git_cloner(git_url="https://github.com/mnh-14/calculator-tester.git", branch="main")
    # builder.apply_trivy_scan(severity="CRITICAL,HIGH", fail_on_cve=True)
    user_config["image"] = f"{user_config['app_name']}-{user_config['namespace']}-build:latest"
    builder.apply_kaniko_build(image_destination=user_config["image"], dockerfile_path="Dockerfile")
    build_conf = builder.build()
    utils.create_from_dict(k3s_client, build_conf)


def deploy_application(user_config: Dict[str, Any]):
    user_config["image"] = f"{user_config['app_name']}-{user_config['namespace']}-build:latest"
    manifest_builder = PaaSManifestBuilder(config=user_config)

    manifest_as_list = manifest_builder.build_all_listed()
    for item in manifest_as_list['items']:
        if type(item)==str:
            print(item)
    utils.create_from_dict(k3s_client, data=manifest_as_list)


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
