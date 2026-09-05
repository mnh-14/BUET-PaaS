# Deployer API usage

This document describes the deployer service endpoints in [deployer/deploy_service.py](deployer/deploy_service.py).

Base URL:
- Local: http://localhost:5000
- In Kubernetes: http://<service-name>.<namespace>.svc.cluster.local

Deployment service used by the integration test:
- http://deployment-service.buet-paas-system-team23.192.168.64.121.sslip.io

The integration test can override this URL with the `DEPLOYER_URL` environment variable.

The deployer exposes 4 main API endpoints:

1. POST /api/build
2. POST /api/deploy
3. POST /api/build/status
4. POST /api/deploy/status

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
    "container_port": 8080,
    "replicas": 2,
    "cpu_request": "100m",
    "cpu_limit": "500m",
    "memory_request": "256Mi",
    "memory_limit": "512Mi"
  }
}
```

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

## 4) Check deployment status

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

If namespace is missing, the default is:

```json
"namespace": "default"
```

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
