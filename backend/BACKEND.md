# BUET-PaaS Backend — Reference

Detailed structure and API reference for the `backend/` module (FastAPI orchestrator). Generated from the current codebase for use as security-testing / tooling context.

## 1. Tech stack

- **Framework:** FastAPI 0.115 on Uvicorn (ASGI), ASGI app object: `main:app`
- **DB:** MongoDB via PyMongo (`pymongo==4.8.0`)
- **Auth:** Signed cookie sessions (HMAC-SHA256, not JWT) + Argon2id password hashing (`argon2-cffi`)
- **External services:** GitHub App API, SonarQube/SonarScanner, a separate Kubernetes "deployer" HTTP service (Flask app on the k8s VM, out of this repo)
- **Run command:** `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- **Default local port:** `8000`

## 2. Module map

```
backend/
├── main.py                  # FastAPI app, all core routes, deployment pipeline orchestration
├── github_routes.py         # APIRouter for GitHub App OAuth + installation/repo endpoints (mounted at /api/v1/github)
├── auth.py                  # Session cookie signing/verification, password hashing, require_user dependency, CSRF-ish same-origin check
├── config.py                # Env-driven settings: GitHubAppSettings, SonarSettings (python-dotenv loads .env)
├── db.py                    # MongoClient/collection accessors + index setup (users, projects, deployments, github_*)
├── deployment_config.py     # Resource tiers (small/medium/large), kubernetes_name() slugifier, build_deployer_config()
├── deployment_service.py    # queue_deployment(): creates a deployment doc + schedules the background worker
├── kubernetes_service.py    # HTTP client for the external Kubernetes deployer VM (build/deploy/status polling)
├── github_app.py            # GitHub App JWT + installation token issuance, GitHub REST API wrapper
├── services/
│   └── sonarqube_service.py # Local sonar-scanner invocation + SonarQube Web API polling for Quality Gate results
├── static/                  # Static files served at /static, index.html served at /
├── check_backend.py         # Standalone health-check script
└── tests/                   # Pytest suite (auth, kubernetes_service, sonarqube_service, github_app arch, security gate)
```

Only two files register routes: `main.py` (app-level `@app.*`) and `github_routes.py` (`APIRouter`, mounted via `app.include_router(create_github_router())` at the bottom of `main.py`).

## 3. Data model (MongoDB, db name from `MONGO_DB`, default `buetpaas`)

| Collection | Key fields | Notes |
|---|---|---|
| `users` | `user_id` (unique), `namespace`, `name`, `email` (unique), `password_hash`, `credit_balance`, `created_at` | `namespace` = k8s namespace provisioned at signup |
| `projects` | `project_id` (unique), `user_id`, `project_name`, `app_name`, `namespace`, `repo_url`, `env_vars`, `instance_size`, `deploy_branch`, `latest_remote_sha`, `last_deployed_sha`, `current_status`, `github_*` fields | unique on `(namespace, app_name)` when both are strings |
| `deployments` | `deployment_id` (unique), `project_id`, `commit_sha`, `branch`, `trigger`, `status`, `failure`, `public_url`, `security_scan.*`, `deployer.*`, `resources` | one per build/deploy attempt; indexed by `project_id` + `deployed_at` desc |
| `github_installations` | `installation_id` (unique), `account_id`, `account_login`, `account_type`, `status` | GitHub App installations known to the backend |
| `github_connections` | `(user_id, installation_id)` unique, `github_user_id`, `github_login`, `status` | links a BUET-PaaS user to a GitHub App installation |
| `github_oauth_states` | `state_hash` (unique), `user_id`, `expires_at` (TTL index, 10 min) | CSRF state for the GitHub OAuth flow |

## 4. Authentication model

- Login (`POST /api/v1/users/login`) sets an **HttpOnly, SameSite=Lax** cookie `buetpaas_session` containing `base64(json{user_id, exp}).base64(HMAC-SHA256 signature)`, signed with `SESSION_SECRET`. TTL: 8 hours (`SESSION_TTL_SECONDS`).
- `require_user` (FastAPI dependency, `auth.py`) reads/verifies this cookie on every protected route and loads the user from Mongo (excludes `password_hash`).
- `enforce_same_origin(request)` is called on all state-changing routes (POST/PUT/DELETE): if an `Origin` header is present, it must exactly match `FRONTEND_URL`, else `403`. This is the app's only CSRF mitigation — cookie-based auth without this check would be CSRF-able.
- Passwords: Argon2id (`argon2-cffi`). Legacy unsalted SHA-256 hashes are still verified and transparently upgraded to Argon2 on successful login (`verify_password`).
- No RBAC/roles — every user can only ever act on resources where `user_id` matches their own session; ownership is checked per-route via Mongo filters, not by a shared decorator.

## 5. Full API endpoint reference

Base URL in dev: `http://localhost:8000`. All JSON unless noted. Endpoints under `/api/v1/*` unless noted.

### 5.1 Unauthenticated

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serves `static/index.html` |
| GET | `/static/*` | Static file mount |
| GET | `/health` | Liveness probe; reports Mongo connectivity |
| GET | `/api/v1/sonarqube/health` | SonarQube reachability (503 if unavailable/misconfigured) |
| POST | `/api/v1/users` | Register a new user (201). Body: `{user_id, name, email, password}`. Also provisions a Kubernetes namespace synchronously — can return 503 on k8s failure. |
| POST | `/api/v1/users/login` | Login. Body: `{user_id, password}`. Sets session cookie. |
| GET | `/api/v1/github/callback` | GitHub App OAuth callback (redirect target; validates `state`, exchanges `code`) |

### 5.2 Session-authenticated (`require_user` cookie)

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/api/v1/session` | Return current user from session | |
| POST | `/api/v1/users/logout` | Clear session cookie | same-origin enforced |
| GET | `/api/v1/users/{user_id}` | Get a user's own profile | 403 if `user_id` ≠ caller |
| GET | `/api/v1/users/{user_id}/projects` | List a user's own projects + latest deployment | 403 if `user_id` ≠ caller |
| POST | `/api/v1/projects` | Create a project (202). Body: `ProjectCreate` (GitHub App repo or legacy public `repo_url`, branch, instance size, env vars) | same-origin enforced; resolves branch HEAD via GitHub App or public `git ls-remote` |
| GET | `/api/v1/projects` | List caller's projects joined with latest deployment (aggregation) | |
| GET | `/api/v1/projects/{project_id}` | Get one project + all its deployments | scoped to caller |
| DELETE | `/api/v1/projects/{project_id}` | "Stop" a project (marks deployments/project stopped; no real teardown yet) | same-origin enforced |
| GET | `/api/v1/deployments/{deployment_id}` | Get one deployment (scoped to caller's projects) | |
| GET | `/api/v1/deployments/{deployment_id}/events` | **SSE stream** of deployment status until terminal state | `text/event-stream`, polls Mongo every 1s |
| GET | `/api/v1/deployments/{deployment_id}/logs` | **SSE stream** of real-time build/deploy pod logs until terminal state | `text/event-stream`; polls the deployer's `/api/build/logs` + `/api/deploy/logs` every `KUBERNETES_LOG_POLL_INTERVAL` (default 2s) and emits only newly appended text per pod/container |
| POST | `/api/v1/projects/{project_id}/check-update` | Resolve latest remote commit SHA vs. last deployed | same-origin enforced |
| POST | `/api/v1/deployments/redeploy/{project_id}` | Trigger a new deployment for latest commit (409 if one's already running or nothing changed) | same-origin enforced; enqueues `build_and_deploy` background task |
| PUT | `/api/v1/projects/{project_id}/env` | Replace a project's env vars | same-origin enforced |
| GET | `/api/v1/projects/{project_id}/env` | Read a project's env vars | |

### 5.3 GitHub App integration (`/api/v1/github/*`, `github_routes.py`)

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/api/v1/github/connect` | Start GitHub App install/OAuth flow | requires session; issues `state`, 302 redirect to GitHub |
| GET | `/api/v1/github/callback` | OAuth callback | public (GitHub redirects here); validates one-time `state` (10-min TTL, hashed at rest) |
| GET | `/api/v1/github/installations` | List caller's connected installations | requires session |
| GET | `/api/v1/github/repositories?installation_id=` | List repos accessible via installation(s) | requires session; auto-marks installation `revoked` on GitHub 401/403/404 |
| GET | `/api/v1/github/repositories/{repository_id}/branches?installation_id=` | List branches for a repo | requires session |
| DELETE | `/api/v1/github/connections/{installation_id}` | Disconnect a GitHub App installation | requires session; same-origin enforced |

### 5.4 Background pipeline (not HTTP-exposed)

`build_and_deploy()` in `main.py` runs as a `BackgroundTasks` job (triggered by project creation's first deploy path is actually only via `redeploy` — note: `POST /api/v1/projects` does **not** itself queue a deployment, it only creates the project record) and on backend restart via `resume_incomplete_deployments()` in the `lifespan` startup hook. Stages, in order:

1. `cloning` — clone via `git`, either public HTTPS or GitHub App installation token (short-lived, injected through a temp `GIT_ASKPASS` script, never placed in argv/env logs)
2. `security_scan_running` → `security_scan_passed` / `security_scan_failed` / `security_scan_error` — SonarScanner run + Quality Gate check (skippable via `SONAR_ENABLED=false`)
3. Dockerfile discovery (`find_dockerfile`) + `EXPOSE` port parsing
4. `build_queued` → `build_started` → `build_done` — delegated to the external Kubernetes deployer service (`kubernetes_service.py`, `POST /api/build` + polling `POST /api/build/status`)
5. `deploy_queued` → `deploy_started` → `running` — `POST /api/deploy` + polling `POST /api/deploy/status`
6. `failed` on any exception, with a redacted, bounded `failure` object written to the deployment doc (see `pipeline_failure()` / `deployment_failure()` — no tracebacks or secrets are ever persisted/returned)

## 6. External integrations

### 6.1 Kubernetes deployer service (`kubernetes_service.py`)

A separate Flask API on the k8s VM, not part of this repo. Base URL: `KUBERNETES_DEPLOYER_URL` (ingress on port 80 — do **not** point at the internal Flask port 5000). Bearer-token authenticated (`KUBERNETES_DEPLOYER_TOKEN`).

| Method | Path | Called by |
|---|---|---|
| POST | `/api/namespace` | `create_namespace()` — at user signup |
| POST | `/api/build` | `start_build()` — image build from cloned repo |
| POST | `/api/build/status` | `get_status(..., "build")` — polled |
| POST | `/api/deploy` | `start_deploy()` — rollout |
| POST | `/api/deploy/status` | `get_status(..., "deploy")` — polled |
| GET | `/api/build/logs` | `get_build_logs()` — polled by `GET /api/v1/deployments/{id}/logs` |
| GET | `/api/deploy/logs` | `get_deploy_logs()` — polled by `GET /api/v1/deployments/{id}/logs` |

All request/response bodies are logged with credential-bearing keys (`token`, `secret`, `password`, `authorization`, `api_key`, `credential`, `env_vars`, `github_auth`) redacted (`_safe_log_value`).

### 6.2 GitHub App (`github_app.py`)

REST calls to `https://api.github.com`. App-level auth via a short-lived RS256 JWT (`generate_app_jwt`, 9-min expiry) signed with the private key at `GITHUB_APP_PRIVATE_KEY_PATH`; installation-scoped tokens minted per-repository via `create_installation_token`. User-level OAuth (`exchange_oauth_code`) is used only to verify the human actually has access to the installation during `/connect` → `/callback`.

### 6.3 SonarQube (`services/sonarqube_service.py`)

Runs `sonar-scanner` (path from `SONAR_SCANNER_BIN`) as a subprocess against the cloned working directory, then polls the SonarQube Web API (`SONAR_HOST_URL`, token `SONAR_TOKEN`) for the Quality Gate result. Output is scrubbed of ANSI codes, bearer tokens, `sonar.login`/`sonar.token` values, and basic-auth URL credentials before being stored as `diagnostics`.

## 7. Environment variables

Loaded via `python-dotenv` (`backend/.env`); see `backend/.env.example`.

| Variable | Default | Used by |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | `db.py` |
| `MONGO_DB` | `buetpaas` | `db.py` |
| `SONAR_ENABLED` | `true` | `config.py` (skips scan stage if false) |
| `SONAR_HOST_URL` | `http://192.168.67.252:9000` | `config.py` |
| `SONAR_TOKEN` | *(empty)* | `config.py` |
| `SONAR_SCANNER_BIN` | `sonar-scanner` | `config.py` |
| `SONAR_SCAN_TIMEOUT` | `300` | `config.py` (must be > 0) |
| `SONAR_VERBOSE` | `true` | `config.py` |
| `GITHUB_APP_ID` | — | `config.py` (required) |
| `GITHUB_APP_CLIENT_ID` | — | `config.py` (required) |
| `GITHUB_APP_CLIENT_SECRET` | — | `config.py` (required) |
| `GITHUB_APP_SLUG` | — | `config.py` (required) |
| `GITHUB_APP_PRIVATE_KEY_PATH` | — | `config.py` (required, must be a readable file) |
| `GITHUB_CALLBACK_URL` | — | `config.py` (required) |
| `GITHUB_INSTALL_URL` | — | `config.py` (falls back to `https://github.com/apps/{slug}/installations/new`) |
| `FRONTEND_URL` | `http://localhost:3000` | `config.py` — also drives same-origin check and cookie `secure` flag |
| `SESSION_SECRET` | — | `config.py` (required; HMAC key for session cookies) |
| `KUBERNETES_DEPLOYER_URL` | `http://127.0.0.1:5000` | `kubernetes_service.py` |
| `KUBERNETES_DEPLOYER_TOKEN` | *(empty)* | `kubernetes_service.py` |
| `KUBERNETES_STATUS_POLL_INTERVAL` | `5` (sec) | `kubernetes_service.py` |
| `KUBERNETES_LOG_POLL_INTERVAL` | `2` (sec) | `main.py` (`/deployments/{id}/logs` SSE poll cadence) |
| `KUBERNETES_REQUEST_TIMEOUT` | `15` (sec) | `kubernetes_service.py` |
| `KUBERNETES_BUILD_TIMEOUT` | `1800` (sec) | `main.py` |
| `KUBERNETES_DEPLOY_TIMEOUT` | `600` (sec) | `main.py` |
| `GIT_CLONE_TIMEOUT_SECONDS` | `300` | `main.py` |
| `GIT_CHECKOUT_TIMEOUT_SECONDS` | `300` | `main.py` |

`GitHubAppSettings.from_env(require_complete=True)` is called at app startup (`lifespan`), so the app **will not start** unless all "required" GitHub App vars above are set and the private key file is readable.

## 8. Security-relevant implementation notes

- **CORS**: `CORSMiddleware` is imported in `main.py` but not currently added to the `app` — confirm whether cross-origin requests are actually restricted before relying on it as a boundary.
- **Same-origin check** (`enforce_same_origin`) only fires when an `Origin` header is present; requests without one (some non-browser/native clients, some same-site navigations) skip it — it is not a substitute for a CSRF token if that matters for the threat model.
- **Commit pinning**: all deployments checkout an exact 40-hex-char commit SHA (`COMMIT_SHA_PATTERN`), verified post-checkout (`checkout_and_verify_commit` / the checkout in `clone_repository`), preventing TOCTOU branch-head swaps mid-deploy.
- **Secret hygiene**: GitHub installation tokens are never written to argv (delivered via a temp `GIT_ASKPASS` helper script + short-lived env var, cleaned up in a `finally`), and are redacted from all logs (`_safe_git_log_text`, `_safe_log_value`, SonarQube diagnostics scrubbing).
- **Kubernetes namespace naming** (`kubernetes_name`) sanitizes arbitrary user input (`user_id`, `project_name`) into DNS-label-safe strings — relevant if testing for namespace/resource-name injection.
- **Ownership checks** are per-route (`{"project_id": ..., "user_id": user["user_id"]}` filters); there's no separate authorization layer, so a missing filter on a new route would be an IDOR — worth auditing any new endpoint against this pattern.
- **Rate limiting**: none observed in this module for login, signup, or any endpoint.
