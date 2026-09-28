# Database Implementation & Assumptions

This document explains how per-user databases work in BUET-PaaS: what was built,
where it lives, and the assumptions behind the design. A student (or a grader)
opening this repo for the first time should be able to understand the feature
without reading the platform backend internals.

---

## 1. The Big Picture

Every project can attach a managed database (PostgreSQL, MongoDB, or Redis).
When a database is provisioned, the platform:

1. Deploys the real database engine **inside the same k3s cluster** that also
   runs student applications (the "deployer" side).
2. Generates strong credentials and stores them as a Kubernetes Secret.
3. Creates a StatefulSet (PostgreSQL/MongoDB) so the database data survives
   restarts and even re-creations.
4. Hands the student a connection string. The same string is also injected
   automatically into every deployment of their project as a reserved
   environment variable (`DATABASE_URL`, `MONGO_URL`, or `REDIS_URL`).

The design goal is "database as an add-on to your project", not a standalone
external service. Databases live and die with their project's cluster namespace.

**Design decision (per project owner):** the database is provisioned in the
k3s-oriented cluster via the deployer agent, *not* as a standalone externally
hosted service.

---

## 2. What Gets Created in Kubernetes

For engine `E` on project `proj-abc123`:

| Kind | Name |
| --- | --- |
| Namespace | `db-proj-abc123` (shared by all DBs of the project) |
| StatefulSet | `{app_name}-database` where `app_name = proj-abc123-E` |
| Service | `{app_name}-database-service` |
| Secret | `{app_name}-database-secret` |
| PVC (Postgres/Mongo) | `{app_name}-database-data-0` via `volumeClaimTemplates` |
| PriorityClass | `data-rank` (value 2,000,000) so DB pods preempt lower-priority work |

Inside the cluster the database is reachable as
`{app_name}-database-service.db-proj-abc123.svc.cluster.local:<port>`.

- **Redis** is intentionally *not* given a persistent volume — it is treated as
  a cache. Deprovisioning Redis loses its data; Postgres/Mongo keep their data
  (see "Deprovisioning vs deleting" below).
- The Service is `ClusterIP` by default. When the platform runs in **Docker**
  mode (`APP_RUNTIME=docker`), the Service becomes `NodePort` and the app uses
  an external `host : nodePort` URL, because a Docker container cannot resolve
  cluster DNS. In **k3s** mode the internal DNS URL is used.
- There is no Ingress for databases; applications talk to them over the
  cluster/NodePort network only.

---

## 3. Supported Engines

| Engine | Image | Default port | Credentials in Secret |
| --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine` | 5432 | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| `mongo` | `mongo:7.0.14` | 27017 | `MONGO_INITDB_ROOT_USERNAME`, `MONGO_INITDB_ROOT_PASSWORD` |
| `redis` | `redis:7-alpine` | 6379 | `REDIS_PASSWORD` |

Allowed sizes (GiB): `1`, `5` (default `1`). Allowed to choose from a fixed
whitelist to keep the prototype honest about what it supports.

---

## 4. How a Deployment Gets Its Connection String

During `build_and_deploy` (the Docker/k3s app pipeline) the backend merges:

- the student's own environment variables, and
- the connection strings of every `ready` database of that project.

Database strings **always win** over student variables with the same key, so a
student cannot accidentally point their app at a fake URL. The merge is
best-effort: if the deployer or the database catalog is unreachable, the
deployment proceeds with the student's variables unchanged (a database outage
must never take down the app pipeline).

Reserved environment keys, enforced platform-wide:

- `DATABASE_URL` → PostgreSQL
- `MONGO_URL` → MongoDB
- `REDIS_URL` → Redis

Creating a project, updating env vars, or provisioning with a value that
collides with a reserved key is rejected with HTTP `409` unless the caller
explicitly passes `overwrite = true` (only relevant to the provision call).

---

## 5. Idempotency & Quotas

- **One database per (project, engine).** Identical documents are identified by
  `idem_key = "<project_id>:<engine>"`.
- Calling provision again for a database whose status is already `ready` does
  **not** create a duplicate. Instead it rotates the credentials and returns a
  fresh connection URL. This makes "provision" safe to retry.
- Quotas (configurable, requires platform restart to change in the prototype):
  - at most **1** active database per project,
  - at most **2** active databases per user,
  - a database may be blocked if its project/user hit those limits (HTTP `409`).
- Engine, size, storage class, external host, and credit cost are read from
  environment variables (`DATABASE_*`, see `.env.example`).

---

## 6. Deprovisioning vs Deleting (Data Safety)

- **Deprovision** (the `DELETE` endpoint / "Deprovision" button) stops the
  StatefulSet and removes the Service. The PVCs and the data are **retained**
  (`purge_data: false` always in the prototype). The database record is marked
  `deprovisioned` and its connection info is cleared.
- Deleting a project cascades a best-effort deprovision of all of its
  databases.
- There is intentionally **no hard delete / purge** path exposed on the
  platform yet. Clearing a disk is a hostile operation and is left as future
  work (or an admin action directly on the cluster via `kubectl`).

---

## 7. Where the Code Lives

**Deployer (talks to k3s):**
- `deployer/k3s_conf.py` — `DATA_PRIORITY`, `DATABASE_ENGINES` registry, and
  `DatabaseManifestBuilder` that turns a `database_config` into Secret, Service,
  and StatefulSet manifests.
- `deployer/deploy.py` — `provision_database`, `rotate_database_credentials`,
  `deprovision_database`, `check_database_status`.
- `deployer/deploy_service.py` — HTTP endpoints:
  `POST  /api/database/provision | rotate | deprovision | status`,
  `GET   /api/database/engines`.
- `deployer/priority-classes.yaml` — the `data-rank` PriorityClass manifest.
- `service-config/deploy-service-config.yaml` — RBAC grants for
  `statefulsets` (apps) and `persistentvolumeclaims` (core), plus secrets,
  pods, services.
- `deployer/api-usage.md` — worked examples of the database endpoints.

**Backend (the platform API):**
- `backend/services/database_service.py` — the whole domain service:
  validation, quotas, idempotency, deployer calls, URL building, masking.
- `backend/db.py` — `user_databases_col()` and its indexes
  (`database_id` unique, `idem_key` unique + partial, project/user lookups).
- `backend/config.py` — `DatabaseProvisionSettings`.
- `backend/main.py` — `POST/GET /api/v1/projects/{id}/databases`,
  `DELETE .../{database_id}`, `POST .../{database_id}/rotate`,
  `GET .../{database_id}/status`; env-var injection into the deploy pipeline;
  reserved-key guards on project/env creation.
- `backend/.env.example` — every `DATABASE_*` variable, documented.

**Frontend:**
- `frontend/lib/api.ts` — database types + API client functions.
- `frontend/components/DatabasePanel.tsx` — provision / list / rotate /
  deprovision / status-refresh UI, rendered on the project detail page.

**Tests:**
- `backend/tests/test_user_database_service.py` — 20 unit tests covering
  URL building, quotas, idempotent re-provision, rotate, deprovision, credits,
  reserved keys, and masking. Run from `backend/` with
  `python -m pytest tests/test_user_database_service.py -q`.
- Note: the existing `test_github_app_architecture.py` has two failures on
  Windows (`PermissionError` while unlinking a Git askpass temp file) that are
  **pre-existing and unrelated** to this feature.

---

## 8. Configuration (all via environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_PROVISIONING_ENABLED` | (`true` if set) | master switch for the feature |
| `DEPLOYER_URL` | `http://192.168.68.121:5000` | where the deployer HTTP service lives |
| `APP_RUNTIME` | `docker` | `docker` → external NodePort URL is injected; `k3s` → internal cluster DNS URL |
| `DATABASE_DEFAULT_SIZE_GB` | `1` | default size for new databases |
| `DATABASE_ALLOWED_ENGINES` | `postgres,mongo,redis` | comma-separated whitelist |
| `DATABASE_ALLOWED_SIZES_GB` | `1,5` | comma-separated whitelist |
| `DATABASE_MAX_PER_USER` | `2` | active-database quota per user |
| `DATABASE_MAX_PER_PROJECT` | `1` | active-database quota per project |
| `DATABASE_STORAGE_CLASS` | `local-path` | PVC storage class on the cluster |
| `DATABASE_EXTERNAL_HOST` | — | host shown in external NodePort URLs |
| `DATABASE_COST_CREDITS` | `0` | credits charged per provision (0 disables charging) |

---

## 9. Security Notes

- Passwords are generated with `secrets.token_urlsafe` and only ever stored in
  a Kubernetes Secret and in the backend catalog (credentials stored per
  database document). Connection strings embedded in URLs are percent-encoded
  with `quote_plus` so special characters cannot break the URL.
- List responses **mask** connection URLs (`postgresql://*****@*****:5432/...`)
  so the dashboard never leaks credentials. The full string is returned only by
  provision/rotate, and is immediately exported to the app's reserved env var.
- Rotating credentials replaces the Secret and the stored URLs; the running app
  picks the new value up on its next deployment/restart.

---

## 10. Assumptions & Known Limits (Prototype)

- **Single replica, single cluster.** High availability, failover, and
  cross-node replicas are out of scope.
- **`local-path` storage** on the single k3s node. RAID/network storage is not
  assumed and not configured.
- **No full deletes.** Data is retained on deprovision by design.
- **No per-DB backups** (no volume snapshots, no dumps) yet.
- **Rotate returns only the new URL once**; treat the summary responses as
  secrets.
- The deployer provisions synchronously over HTTP; long cluster apply times are
  handled with the standard `timeout`/retry behavior already in the deployer.
- Frontend quota display is static ("Provision" disappears once 2 active DBs
  exist); the authoritative check is server-side.