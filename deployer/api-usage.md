# Deployer API usage

This document describes the deployer service endpoints in [deployer/deploy_service.py](deployer/deploy_service.py).

Base URL:
- Local: http://localhost:5000
- In Kubernetes: http://<service-name>.<namespace>.svc.cluster.local

Deployment service used by the integration test:
- http://deployment-service.buet-paas-system-team23.192.168.64.121.sslip.io
- http://deployment-service.buet-paas-system-team23.192.168.128.200.sslip.io

They are also the current deployment of deployment-service
The integration test can override this URL with the `DEPLOYER_URL` environment variable.

The deployer exposes 6 main API endpoints:

1. POST /api/build
2. POST /api/deploy
3. POST /api/build/status
4. POST /api/deploy/status
5. GET /api/build/logs
6. GET /api/deploy/logs

---

## User configuration contract

The build and deploy endpoints accept the application configuration in either a
`user_config` object or as top-level request fields. The following table is the
complete configuration surface currently supported by the deployer.

### Core fields

| Field | Type | Used by | Necessity | Description |
| --- | --- | --- | --- | --- |
| `app_name` | string | Build and deploy | mandatory | Unique application name. |
| `namespace` | string | Build and deploy | mandatory | Target Kubernetes namespace. |
| `git_url` | string | Build | mandatory | Git repository URL to clone. It is not needed by `/api/deploy`. |
| `image` | string | Build and deploy | never | Do not provide this field. The deployer generates `<app_name>-<namespace>-build:latest` and overwrites any supplied value. |

### Build fields

| Field | Type | Default | Necessity | Description |
| --- | --- | --- | --- | --- |
| `git_branch` | string | `main` | optional | Git branch to clone. |
| `dockerfile_path` | string | `Dockerfile` | optional | Dockerfile path relative to the repository root. |
| `build_args` | object of string values | `{}` | optional | Docker build arguments passed to Kaniko, for example `{"APP_ENV": "production"}`. Keep values token-safe; the current builder wrapper does not support spaces or shell-special characters in values. |

### Deployment fields

| Field | Type | Default | Necessity | Description |
| --- | --- | --- | --- | --- |
| `container_port` | integer | `80` | optional | Port exposed by the application container. |
| `replicas` | integer | `2` | optional | Desired number of application replicas. |
| `worker_ip` | string | empty | optional | Accepted for compatibility, but the current manifest builder does not use it to generate a domain because its fallback logic is disabled. |
| `domain_override` | string | empty | optional | Custom domain. When provided, it is added to the generated ingress domains. |
| `instance_tier` | string | empty | optional | Node selector value, such as `high-memory`. |
| `health_path` | string | `/` | optional | HTTP path used by liveness and readiness probes. |
| `grace_period_seconds` | integer | `30` | optional | Kubernetes pod termination grace period. |
| `cpu_request` | string | `100m` | optional | Reserved CPU for the application container. |
| `cpu_limit` | string | `250m` | optional | Maximum CPU for the application container. |
| `memory_request` | string | `128Mi` | optional | Reserved memory for the application container. |
| `memory_limit` | string | `256Mi` | optional | Maximum memory for the application container. |
| `env_vars` | object | `{}` | optional | Environment variables injected into the application and migration containers. Values are converted to strings. |
| `run_as_non_root` | boolean | `false` | optional | When true, configures the pod to run as UID/GID `10001`. |
| `read_only_rootfs` | boolean | `false` | optional | Makes the application container root filesystem read-only. |
| `pre_deploy_cmd` | string | empty | optional | Shell command run in an init container before the application starts. |

### Optional add-ons

| Field | Type | Necessity | Description |
| --- | --- | --- | --- |
| `persistent_storage` | object | optional | Enables a persistent volume claim. Supported keys are `size` (default `10Gi`) and `mount_path` (default `/app/data`). |
| `persistent_storage.size` | string | optional | Requested storage capacity, such as `20Gi`. |
| `persistent_storage.mount_path` | string | optional | Path where the volume is mounted in the application container. |
| `enable_ssl` | boolean | optional | Enables TLS-related ingress configuration when set to `true`. |
| `autoscaling` | object | optional | Enables an HPA when `enabled` is `true`. Supported keys are `min_replicas` (default `2`), `max_replicas` (default `10`), and `target_cpu_percent` (default `80`). |
| `autoscaling.enabled` | boolean | optional | Turns horizontal pod autoscaling on or off. |
| `autoscaling.min_replicas` | integer | optional | Minimum HPA replica count. |
| `autoscaling.max_replicas` | integer | optional | Maximum HPA replica count. |
| `autoscaling.target_cpu_percent` | integer | optional | Target average CPU utilization percentage. |
| `cron_jobs` | array | optional | Creates scheduled background jobs. Each item supports `name`, `schedule`, and `command`. |

### Fields callers should not provide

The following values are deployer internals and are not part of the API
payload contract:

| Field | Necessity | Reason |
| --- | --- | --- |
| `target_builder_image` | never | Internal builder configuration. |
| `default_worker` | never | Internal worker configuration. |
| `builder_namespace` | never | Internal Kubernetes namespace used for build jobs. |
| `default_floating_ip` | never | Internal URL generation setting. |
| `k3s_client` | never | Internal Kubernetes client instance. |
| Kubernetes client or manifest-builder objects | never | Internal runtime objects, not JSON payload values. |

The deployer generates the build image name in the form
`<app_name>-<namespace>-build:latest`. An `image` field may appear in older
examples, but build and deploy currently derive and overwrite it, so callers
should not rely on supplying it.

### Complete example

This example includes every caller-configurable field. Optional fields can be
removed when they are not needed.

```json
{
  "user_config": {
    "app_name": "calculator",
    "namespace": "random-user-a",
    "git_url": "https://github.com/mnh-14/calculator-tester.git",
    "git_branch": "main",
    "dockerfile_path": "Dockerfile",
    "build_args": {
      "APP_ENV": "production",
      "VERSION": "1.0.0"
    },
    "container_port": 8080,
    "replicas": 2,
    "worker_ip": "192.168.10.101",
    "domain_override": "app.example.com",
    "instance_tier": "standard",
    "health_path": "/healthz",
    "grace_period_seconds": 30,
    "cpu_request": "100m",
    "cpu_limit": "500m",
    "memory_request": "256Mi",
    "memory_limit": "512Mi",
    "env_vars": {
      "PORT": "8080",
      "NODE_ENV": "production"
    },
    "run_as_non_root": true,
    "read_only_rootfs": false,
    "pre_deploy_cmd": "python manage.py migrate",
    "enable_ssl": true,
    "persistent_storage": {
      "size": "20Gi",
      "mount_path": "/app/storage"
    },
    "autoscaling": {
      "enabled": true,
      "min_replicas": 2,
      "max_replicas": 8,
      "target_cpu_percent": 80
    },
    "cron_jobs": [
      {
        "name": "daily-backup",
        "schedule": "0 2 * * *",
        "command": "python manage.py run_backup"
      }
    ]
  }
}
```

The build endpoint needs the Git fields and uses the build-related options.
The deploy endpoint uses the deployment and add-on fields. Sending the full
configuration to both endpoints is allowed, but build-only fields are ignored
by the deployment manifest builder.

---

## 1) Build an application image

Endpoint:
- POST /api/build

Purpose:
- Submits a Kubernetes build job for the app source and builds a container image.

Request body:
- You may send either:
  - a wrapped object with user_config, or
  - the config fields directly

Example payload with user_config:

```json
{
  "user_config": {
    "app_name": "calculator",
    "namespace": "random-user-a",
    "git_url": "https://github.com/mnh-14/calculator-tester.git",
    "git_branch": "main",
    "dockerfile_path": "Dockerfile",
    "build_args": {
      "APP_ENV": "production",
      "VERSION": "1.0.0"
    },
    "container_port": 8080,
    "replicas": 2,
    "cpu_request": "100m",
    "cpu_limit": "500m",
    "memory_request": "256Mi",
    "memory_limit": "512Mi"
  }
}
```

`build_args` is optional and is passed to Kaniko as Docker build arguments. Its
value must be an object whose keys are argument names and whose values are
token-safe strings, for example `{"APP_ENV": "production"}`. Values containing
spaces or shell-special characters are not supported by the current builder
wrapper.

Example payload without user_config wrapper:

```json
{
  "app_name": "calculator",
  "namespace": "random-user-a",
  "git_url": "https://github.com/mnh-14/calculator-tester.git",
  "git_branch": "main",
  "dockerfile_path": "Dockerfile",
  "container_port": 8080
}
```

Success response:

```json
{
  "status": "success",
  "message": "Build job submitted.",
  "app_name": "calculator",
  "namespace": "random-user-a",
  "image": "calculator-random-user-a-build:latest",
  "job": { ...kubernetes job manifest... }
}
```

---

## 2) Deploy an application

Endpoint:
- POST /api/deploy

Purpose:
- Creates the Kubernetes deployment manifests for the app.

Request body:
- Same format as build endpoint.

Example:

```json
{
  "user_config": {
    "app_name": "calculator",
    "namespace": "random-user-a",
    "image": "calculator-random-user-a-build:latest",
    "container_port": 8080,
    "replicas": 2,
    "cpu_request": "100m",
    "cpu_limit": "500m",
    "memory_request": "256Mi",
    "memory_limit": "512Mi",
    "health_path": "/",
    "grace_period_seconds": 30
  }
}
```

Success response:

```json
{
  "status": "success",
  "message": "Deployment manifest applied.",
  "app_name": "calculator",
  "namespace": "random-user-a",
  "manifest": { ...kubernetes list manifest... }
}
```

---

## 3) Check build status

Endpoint:
- POST /api/build/status

Purpose:
- Polls the Kubernetes Job status for the app build.

Required body:

```json
{
  "name": "calculator",
  "namespace": "random-user-a"
}
```

You may also send:

```json
{
  "app_name": "calculator",
  "namespace": "random-user-a"
}
```

Success response:

```json
{
  "status": "success",
  "name": "calculator",
  "namespace": "random-user-a",
  "result": "Pending",
  "summary": "Build job 'calculator-random-user-a-build-job' is waiting to start.",
  "reason": "Job has not started and has no completion result.",
  "details": {
    "job_name": "calculator-random-user-a-build-job",
    "active": 0,
    "succeeded": 0,
    "failed": 0
  }
}
```

Possible result values:
- Pending
- Running
- Succeeded
- Failed
- Unknown

---

## 4) Get build logs

Endpoint:
- GET /api/build/logs

Purpose:
- Returns logs from every Pod created for the build Job. Multiple Pods produce multiple entries in the `logs` array.

Query parameters:
- `name` or `app_name`: application name
- `namespace`: application namespace; mandatory. Build Pods are read from the builder namespace internally.

Example:

```text
GET /api/build/logs?name=calculator&namespace=random-user-a
```

Success response:

```json
{
  "status": "success",
  "name": "calculator",
  "namespace": "random-user-a",
  "job_name": "calculator-random-user-a-build-job",
  "logs": [
    {
      "pod_name": "calculator-random-user-a-build-job-abc12",
      "container": "paas-builder",
      "logs": "...build output..."
    }
  ]
}
```

If a Pod exists but its logs cannot be read, that entry contains `logs: null`,
`error`, and `http_status` instead of build output.

---

## 5) Check deployment status

Endpoint:
- POST /api/deploy/status

Purpose:
- Polls the Kubernetes Deployment status for the app.

Required body:

```json
{
  "name": "calculator",
  "namespace": "random-user-a"
}
```

You may also send:

```json
{
  "app_name": "calculator",
  "namespace": "random-user-a"
}
```

Success response:

```json
{
  "status": "success",
  "name": "calculator",
  "namespace": "random-user-a",
  "result": "Running",
  "summary": "Deployment 'calculator-deployment' is running.",
  "reason": "Available replicas are ready.",
  "details": {
    "deployment_name": "calculator-deployment",
    "replicas": 2,
    "ready_replicas": 2,
    "updated_replicas": 2,
    "available_replicas": 2
  },
  "url": "http://calculator.random-user-a.192.168.68.121.sslip.io"
}
```

When `result` is `Running`, the response includes `url`, which is the public URL for
the deployed application. The `url` field is omitted for `Pending`, `Failed`, and
`Unknown` results.

Possible result values:
- Pending
- Running
- Failed
- Unknown

---

## 6) Get deployment logs

Endpoint:
- GET /api/deploy/logs

Purpose:
- Returns logs from every Pod selected by the deployment's `app=<name>` label. Multiple Pods and multiple containers are represented in the response.

Query parameters:
- `name` or `app_name`: application name
- `namespace`: Kubernetes namespace; mandatory

Example:

```text
GET /api/deploy/logs?name=calculator&namespace=random-user-a
```

Success response:

```json
{
  "status": "success",
  "name": "calculator",
  "namespace": "random-user-a",
  "deployment_name": "calculator-deployment",
  "logs": [
    {
      "pod_name": "calculator-deployment-abc12",
      "containers": [
        {
          "container": "calculator",
          "logs": "...application output..."
        }
      ]
    }
  ]
}
```

---

## Notes on request structure

The deployer is designed to accept either:

1. A wrapped config object:

```json
{
  "user_config": { ... }
}
```

2. A flat object of config fields:

```json
{
  "app_name": "calculator",
  "namespace": "random-user-a",
  "git_url": "https://example.com/repo.git"
}
```

For the status endpoints, the body should include either:
- name, or
- app_name

and optionally:
- namespace

`namespace` is mandatory for all build, deploy, status, and log requests.

---

## Example curl calls

Build:

```bash
curl -X POST http://localhost:5000/api/build \
  -H "Content-Type: application/json" \
  -d '{
    "user_config": {
      "app_name": "calculator",
      "namespace": "random-user-a",
      "git_url": "https://github.com/mnh-14/calculator-tester.git",
      "git_branch": "main",
      "dockerfile_path": "Dockerfile",
      "container_port": 8080
    }
  }'
```

Deploy:

```bash
curl -X POST http://localhost:5000/api/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "user_config": {
      "app_name": "calculator",
      "namespace": "random-user-a",
      "image": "calculator-random-user-a-build:latest",
      "container_port": 8080,
      "replicas": 2
    }
  }'
```

Check build status:

```bash
curl -X POST http://localhost:5000/api/build/status \
  -H "Content-Type: application/json" \
  -d '{
    "name": "calculator",
    "namespace": "random-user-a"
  }'
```

Check deploy status:

```bash
curl -X POST http://localhost:5000/api/deploy/status \
  -H "Content-Type: application/json" \
  -d '{
    "name": "calculator",
    "namespace": "random-user-a"
  }'
```

Get build logs:

```bash
curl "http://localhost:5000/api/build/logs?name=calculator&namespace=random-user-a"
```

Get deployment logs:

```bash
curl "http://localhost:5000/api/deploy/logs?name=calculator&namespace=random-user-a"
```
