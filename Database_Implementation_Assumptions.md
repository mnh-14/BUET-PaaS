# Database Implementation & Assumptions

This document explains how standalone databases work in BUET-PaaS: what was
built, where it lives, and the assumptions behind the design. A student (or a
grader) opening this repo for the first time should be able to understand the
feature without reading the platform backend internals.

---

## 1. The Big Picture

Each database is its **own standalone project**. When a database is
provisioned, the platform:

1. Deploys the real database engine **inside the same k3s cluster** that also
   runs student applications (the "deployer" side).
2. Gives the workload its **own Kubernetes namespace** (`db-<name>`), so it is
   never affected by an application project's lifecycle.
3. Generates (or accepts) credentials and stores them as a Kubernetes Secret.
4. Creates a StatefulSet with a `volumeClaimTemplate` so the database data
   survives restarts and even re-creations.
5. Hands the student a connection URL (`host:port`) built from the exact
   host/port/storage-class values they supplied.

The design goal is "database as a service you manage yourself", not "database
as an add-on to a project". Deleting an application never touches its
databases, and the top-level `/api/v1/databases` endpoints live outside the
project API.

Following the project instructions (my_markdown.md): **PostgreSQL**, **MySQL**,
**MongoDB**, and **Redis** are supported. The user supplies the connection
details (host, port, storage class, size, optional username / password); the
deployer applies those values literally to the manifests and the returned URLs.
Status and **log** endpoints let the user track provisioning progress while the
pod comes up.

---

## 2. What Gets Created in Kubernetes

For a standalone database named `analytics` with engine `E`:

| Kind | Name |
| --- | --- |
| Namespace | `db-analytics` (owned exclusively by this database) |
| StatefulSet | `analytics-database` |
| Service | `analytics-database-service` |
| Secret | `analytics-database-secret` |
| PVC | `analytics-database-data-0` via `volumeClaimTemplates` |
| PriorityClass | `data-rank` (value 2,000,000) so DB pods preempt lower-priority work |

Inside the cluster the database is reachable as
`analytics-database-service.db-analytics.svc.cluster.local:<port>`.

- Every engine gets a persistent volume (Postgres/MySQL/MongoDB/Redis) — data
  always survives pod restarts.
- The service is `ClusterIP` by default. When the platform runs in **Docker**
  mode (`APP_RUNTIME=docker`), the service becomes `NodePort` and the external
  URL uses `host : nodePort`, because a Docker container cannot resolve cluster
  DNS. In **k3s** mode the internal DNS URL is used.
- The user's `port` hint is applied literally as the container + service port;
  an optional `node_port` hint pins the NodePort for external access.
- There is no Ingress for databases; applications talk to them over the
  cluster/NodePort network only.

---

## 3. Supported Engines

| Engine | Image | Default port | Credentials in Secret |
| --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine` | 5432 | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| `mongodb` | `mongo:7.0.14` | 27017 | `MONGO_INITDB_ROOT_USERNAME`, `MONGO_INITDB_ROOT_PASSWORD` |
| `mysql` | `mysql:8.4` | 3306 | `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD` |
| `redis` | `redis:7-alpine` | 6379 | `REDIS_PASSWORD` |

Allowed sizes (GiB): `1`, `5` (default `1`). Allowed to choose from a fixed
whitelist to keep the prototype honest about what it supports.

---

## 4. Connection URLs (No Auto-Injection)

The student connects to the database **manually** using the returned
connection string. There is **no reserved environment variable** and no
automatic injection into app deployments — the earlier "databases exported to
your app as env vars" mechanism was removed because a standalone database is the
user's own concern, not a per-project add-on.

- PostgreSQL: `postgresql://user:pass@host:port/db`
- MySQL:     `mysql+pymysql://user:pass@host:port/db`
- MongoDB:   `mongodb://user:pass@host:port/db?authSource=admin`
- Redis:     `redis://:pass@host:port/0`

`host` and `port` reflect the user's own choices; the external form uses the
NodePort allocated (or requested) on the cluster.

---

## 5. Idempotency & Quotas

- **One database per (user, name).** Identical documents are identified by
  `idem_key = "<user_id>:<db_name>"` (unique index).
- Calling provision again for a database whose status is already `ready` does
  **not** create a duplicate. Instead it rotates the credentials and returns a
  fresh connection URL. This makes "provision" safe to retry.
- A database still in `creating` state conflicts (HTTP `409`) until it is ready
  or failed, so you cannot spin up two pods from the same name.
- Quotas (configurable, requires platform restart to change in the prototype):
  - at most **2** active databases per user (per-user only; this is a standalone
    service so there is no per-project quota),
  - a database may be blocked if the user hits that limit (HTTP `409`).
- Engine, size, storage class, external host, and credit cost are read from
  environment variables (`DATABASE_*`, see `.env.example`).

---

## 6. Deprovisioning vs Deleting (Data Safety)

- **Deprovision** (the `DELETE` endpoint / "Deprovision" button) stops the
  StatefulSet and removes the Service. The PVCs and the data are **retained**
  (`purge_data: false` always in the prototype). The database record is marked
  `deprovisioned` and its connection info is cleared.
- Deleting an application project does **not** touch databases — they are
  standalone and outlive any app.
- There is intentionally **no hard delete / purge** path exposed on the
  platform yet. Clearing a disk is a hostile operation and is left as future
  work (or an admin action directly on the cluster via `kubectl`).

---

## 7. Where the Code Lives

**Deployer (talks to k3s):**
- `deployer/k3s_conf.py` — `DATA_PRIORITY`, `DATABASE_ENGINES` registry
  (postgres/mongodb/mysql), and `DatabaseManifestBuilder` that turns a
  `database_config` into Secret, Service, and StatefulSet manifests. Honors
  user-supplied `port` / `node_port` overrides.
- `deployer/deploy.py` — `provision_database`, `rotate_database_credentials`,
  `deprovision_database`, `check_database_status`, `get_database_logs`.
- `deployer/deploy_service.py` — HTTP endpoints:
  `POST  /api/database/provision | rotate | deprovision | status`,
  `GET   /api/database/engines`, `GET /api/database/logs`.
- `deployer/priority-classes.yaml` — the `data-rank` PriorityClass manifest.
- `service-config/deploy-service-config.yaml` — RBAC grants for
  `statefulsets` (apps) and `persistentvolumeclaims` (core), plus secrets,
  pods, services.
- `deployer/api-usage.md` — worked examples of the standalone database
  endpoints.

**Backend (the platform API):**
- `backend/services/database_service.py` — the whole domain service:
  validation, per-user quota, idempotency, deployer calls, URL building,
  masking, status refresh, and log fetching.
- `backend/db.py` — `user_databases_col()` and its indexes (`database_id`
  unique, `idem_key` unique + partial, per-user lookups).
- `backend/config.py` — `DatabaseProvisionSettings` (no per-project quota).
- `backend/main.py` — standalone endpoints
  `GET /api/v1/databases/engines`,
  `POST/GET /api/v1/databases`,
  `GET/DELETE /api/v1/databases/{id}`,
  `POST /api/v1/databases/{id}/rotate`,
  `GET /api/v1/databases/{id}/status`,
  `GET /api/v1/databases/{id}/logs`.
- `backend/.env.example` — every `DATABASE_*` variable, documented.

**Frontend:**
- `frontend/lib/api.ts` — standalone database types + API client functions.
- `frontend/components/DatabasePanel.tsx` — provision (with creation form:
  engine, name, host, port, size, storage class, credentials, external toggle)
  / list / rotate / deprovision / status-refresh / **logs** UI, rendered on
  the dashboard page (not the project detail page).

**Tests:**
- `backend/tests/test_user_database_service.py` — 34 unit tests covering URL
  building (incl. custom ports, Redis's password-only URL and MySQL root
  password), engine metadata, per-user quota, credits, idempotent re-provision,
  rotate, deprovision, status mapping, log fetching, and masking. Run from
  `backend/` with `python -m pytest tests/test_user_database_service.py -q`.
- Note: the existing `test_github_app_architecture.py` has two failures on
  Windows (`PermissionError` while unlinking a Git askpass temp file) that are
  **pre-existing and unrelated** to this feature.

---

## 8. Configuration (all via environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_PROVISIONING_ENABLED` | (`true` if set) | master switch for the feature |
| `DEPLOYER_URL` | `http://192.168.68.121:5000` | where the deployer HTTP service lives |
| `APP_RUNTIME` | `docker` | `docker` → external NodePort URL; `k3s` → internal cluster DNS URL |
| `DATABASE_DEFAULT_SIZE_GB` | `1` | default size for new databases |
| `DATABASE_ALLOWED_ENGINES` | `postgres,mongodb,mysql,redis` | comma-separated whitelist |
| `DATABASE_ALLOWED_SIZES_GB` | `1,5` | comma-separated whitelist |
| `DATABASE_MAX_PER_USER` | `2` | active-database quota per user |
| `DATABASE_STORAGE_CLASS` | `local-path` | default PVC storage class on the cluster |
| `DATABASE_EXTERNAL_HOST` | — | default host shown in external NodePort URLs |
| `DATABASE_COST_CREDITS` | `0` | credits charged per provision (0 disables charging) |

---

## 9. Security Notes

- Passwords are generated with a `secrets`-backed generator and only ever stored
  in a Kubernetes Secret and in the backend catalog (credentials stored per
  database document). Connection strings embedded in URLs are percent-encoded
  with `quote_plus` so special characters cannot break the URL.
- List and detail responses **mask** connection URLs
  (`postgresql://*****@*****:5432/...`) so the dashboard never leaks
  credentials. The full string is returned only by provision/rotate, displayed
  once on screen ("shown only once").
- Rotating credentials replaces the Secret and the stored URLs; the user
  reconnects with the new value.

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
- Unlike the first attempt, there is **no automatic env-var injection** into
  app deployments, no reserved keys, and no per-project cascade deprovision —
  databases are fully standalone by design.
- The authoritative quota check is server-side; the UI simply disables further
  provisioning when the limit is reached.