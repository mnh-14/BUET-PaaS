"""Configuration shared by deployment operations."""

import os


target_builder_image = "192.168.67.192:80/paas-system/random-guy-with-app:v1.0"
default_worker = "192.168.128.121"
builder_namespace = "buet-paas-system-team23"
default_floating_ip = os.getenv("DEFAULT_FLOATING_IP", "192.168.68.121")

user_config = {
    "app_name": "calculator",
    "git_url": "https://github.com/mnh-14/calculator-tester.git",
    "git_branch": "main",
    "dockerfile_path": "Dockerfile",
    "container_port": 8080,
    "namespace": "random-user-a",
    "replicas": 2,
    "grace_period_seconds": 30,
    "cpu_request": "100m",
    "cpu_limit": "500m",
    "memory_request": "256Mi",
    "memory_limit": "512Mi",
    "read_only_rootfs": False,
}