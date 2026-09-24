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

---

# Per-User Database endpoints

The deployer exposes 5 database endpoints:

1. GET /api/database/engines
2. POST /api/database/provision
3. POST /api/database/rotate
4. POST /api/database/deprovision
5. POST /api/database/status

These endpoints manage per-user, per-project databases running inside the k3s
cluster as StatefulSets. Supported engines are advertised by
`GET /api/database/engines` (PostgreSQL 16, MongoDB 7.0.14, Redis 7).

## 1) List supported engines

Endpoint:
- GET /api/database/engines

Response:

```json
{
  "status": "success",
  "engines": {
    "postgres": { "image": "postgres:16-alpine", "port": 5432, "credential_keys": ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"] },
    "mongodb":  { "image": "mongo:7.0.14", "port": 27017, "credential_keys": ["MONGO_INITDB_ROOT_USERNAME", "MONGO_INITDB_ROOT_PASSWORD"] },
    "redis":    { "image": "redis:7-alpine", "port": 6379, "credential_keys": ["REDIS_PASSWORD"] }
  }
}
```

## 2) Provision a database

Endpoint:
- POST /api/database/provision

Purpose:
- Creates a Namespace (if missing), a credentials Secret, a Service and a
  StatefulSet with a `volumeClaimTemplate` so data survives pod restarts.
- Idempotent: partial or repeated submissions skip resources that already exist.

Request body (`database_config` wrapper or flat fields):

```json
{
  "database_config": {
    "app_name": "proj-a1b2c3d4-postgres",
    "namespace": "db-proj-a1b2c3d4",
    "engine": "postgres",
    "size": "1Gi",
    "storage_class": "local-path",
    "external": true,
    "credentials": {
      "POSTGRES_USER": "appuser",
      "POSTGRES_PASSWORD": "s3cret",
      "POSTGRES_DB": "appdb"
    }
  }
}
```

Success response:

```json
{
  "status": "success",
  "message": "Database 'proj-a1b2c3d4-postgres' provisioning submitted.",
  "app_name": "proj-a1b2c3d4-postgres",
  "namespace": "db-proj-a1b2c3d4",
  "engine": "postgres",
  "node_port": 31234
}
```

`node_port` is only returned when `external: true`. It is the NodePort used by
Docker-runtime (non-cluster) apps to reach the database on each worker node.

## 3) Rotate a database's credentials

Endpoint:
- POST /api/database/rotate

Purpose:
- Replaces the credentials Secret with new values and restarts the single
  stateful pod so the engine picks up the new credentials. Data is preserved.

Request body: same shape as provision, `credentials` must contain the new values.

## 4) Deprovision a database

Endpoint:
- POST /api/database/deprovision

Purpose:
- Deletes the StatefulSet, Service and Secret. PersistentVolumeClaims are kept
  by default (`purge_data: false`) so data can be recovered by re-provisioning
  with the same `app_name`. Set `purge_data: true` to delete the volumes.

Request body:

```json
{
  "app_name": "proj-a1b2c3d4-postgres",
  "namespace": "db-proj-a1b2c3d4",
  "purge_data": false
}
```

## 5) Check database status

Endpoint:
- POST /api/database/status

Request body:

```json
{
  "name": "proj-a1b2c3d4-postgres",
  "namespace": "db-proj-a1b2c3d4"
}
```

Response:

```json
{
  "status": "success",
  "name": "proj-a1b2c3d4-postgres",
  "namespace": "db-proj-a1b2c3d4",
  "result": "Running",
  "summary": "Database 'proj-a1b2c3d4-postgres-database' is ready.",
  "reason": "The stateful pod is Running and its readiness probe succeeds.",
  "details": {
    "statefulset": "proj-a1b2c3d4-postgres-database",
    "replicas": 1,
    "ready_replicas": 1,
    "pods": [{ "name": "proj-a1b2c3d4-postgres-database-0", "phase": "Running", "ready": true, "restart_count": 0 }]
  }
}
```

Possible result values:
- Pending
- Running
- Failed
- Unknown

### Name resolution

For `app_name = proj-a1b2c3d4-postgres` in `namespace = db-proj-a1b2c3d4`:

- In-cluster host: `proj-a1b2c3d4-postgres-database-service.db-proj-a1b2c3d4.svc.cluster.local`
- External host: `<worker-ip>:<node_port>` (returned by provision)
- Connection URLs are constructed by the backend (see
  `backend/services/database_service.py`), which URL-encodes credentials.
