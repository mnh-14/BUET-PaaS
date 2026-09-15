# BUET-PaaS backend

FastAPI orchestrates authenticated project creation, GitHub App access, signed webhooks, exact-commit checkout, SonarQube gating, image builds, Docker execution, and per-project tunnels. MongoDB stores users, projects, deployment history, GitHub installation associations, OAuth state, and webhook delivery idempotency records.

## Architecture

There is exactly one App-level webhook for every user, installation, repository, and project:

```text
POST /api/v1/github/webhook
```

GitHub pushes are matched by immutable installation ID, immutable repository ID, and configured branch. The signed event's exact `after` SHA is queued; the webhook neither calls the public redeploy endpoint nor polls GitHub.

```text
Student
  -> BUET-PaaS session
  -> GitHub App installation and OAuth verification
  -> authorized repository and branch selection
  -> initial exact-SHA deployment
  -> GitHub push
  -> central signed webhook
  -> idempotent deployment queue
  -> short-lived installation token
  -> exact commit checkout
  -> SonarQube Quality Gate
  -> Pack/Docker build and run
```

Installation tokens are generated only for GitHub API operations and checkout. They are passed through an ephemeral `GIT_ASKPASS` environment, never Git arguments, MongoDB, repository URLs, logs, or browser responses.

## GitHub App configuration

Create the GitHub App manually. Recommended settings:

- Public app if students outside the owner account must install it.
- Request user authorization during installation: enabled.
- Repository permission `Contents: Read-only` plus metadata access.
- Subscribe to `Push`, `Installation`, and `Installation repositories`.
- Webhook URL: `https://hooks.example.com/api/v1/github/webhook`.
- Callback/setup URL: `https://hooks.example.com/api/v1/github/callback`.
- Use a high-entropy webhook secret matching the backend environment.

Organization installations may require owner approval. Pending requests do not create an active connection. Installation suspension/deletion and repository removal disable auto-deployment without deleting history.

## Environment and secret storage

Copy `.env.example` to `.env`. Required GitHub values are:

```dotenv
GITHUB_APP_ID=
GITHUB_APP_CLIENT_ID=
GITHUB_APP_CLIENT_SECRET=
GITHUB_APP_SLUG=
GITHUB_APP_PRIVATE_KEY_PATH=/secure/outside/repository/buet-paas-app.pem
GITHUB_WEBHOOK_SECRET=
GITHUB_CALLBACK_URL=https://hooks.example.com/api/v1/github/callback
GITHUB_INSTALL_URL=https://github.com/apps/<app-slug>/installations/new
FRONTEND_URL=http://localhost:3000
SESSION_SECRET=
```

Keep the private key outside this repository and restrict it:

```bash
chmod 600 /secure/outside/repository/buet-paas-app.pem
```

SonarQube values remain in `.env.example`. Startup validates required GitHub settings and the key path without printing secret values.

## Authentication

Login creates a signed HTTP-only SameSite cookie. The frontend restores identity from `/api/v1/session` and stores no authentication token in localStorage. Protected endpoints derive `user_id` from the cookie. State changes enforce the configured frontend Origin. New passwords use Argon2id; legacy SHA-256 hashes are transparently migrated after successful login.

## Cloudflare ingress

GitHub needs one backend ingress, separate from per-project application tunnels.

Development Quick Tunnel:

```bash
cloudflared tunnel --url http://localhost:8000
```

Its random hostname changes when restarted, so update GitHub webhook and callback URLs each time.

Stable development/production uses a named tunnel:

```text
https://hooks.example.com/api/v1/github/webhook
    -> named Cloudflare Tunnel
    -> http://localhost:8000/api/v1/github/webhook
```

Do not put interactive Cloudflare Access login in front of the webhook. `X-Hub-Signature-256` HMAC validation authenticates it before JSON parsing.

## Run

```bash
docker compose up -d buet-paas-database
cd backend
bash setup.sh
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

`poller.py` is deprecated and must not run during normal webhook operation. `GITHUB_PAT` is no longer required. URL-only public projects remain readable and manually redeployable, but are `legacy_public`, have webhook auto-deploy disabled, and receive no unverified installation ID.

## Main API flow

- `POST /api/v1/users/login`: set backend session.
- `GET /api/v1/session`: restore frontend identity.
- `GET /api/v1/github/connect`: start one-time state-protected installation/OAuth.
- `GET /api/v1/github/callback`: verify user access; persist only associations.
- `GET /api/v1/github/installations`: list the user's connections.
- `GET /api/v1/github/repositories`: list authorized public/private repositories.
- `GET /api/v1/github/repositories/{id}/branches`: list branches.
- `POST /api/v1/projects`: verify IDs/branch, resolve exact SHA, queue deployment.
- `POST /api/v1/github/webhook`: the only App webhook.

## Test

```bash
cd backend
source venv/bin/activate
python -m pytest -q
```

Manual signed ping:

```bash
payload='{"zen":"test"}'
signature="sha256=$(printf %s "$payload" | openssl dgst -sha256 -hmac "$GITHUB_WEBHOOK_SECRET" -hex | awk '{print $2}')"
curl -i -X POST http://localhost:8000/api/v1/github/webhook \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $signature" \
  -H "X-GitHub-Event: ping" \
  -H "X-GitHub-Delivery: manual-test-1" \
  --data "$payload"
```

## Troubleshooting and operations

- Missing configuration: fill all required variables and restart.
- Private key unavailable: use an absolute external path and check permissions.
- Pending organization approval: an owner must approve, then the student reconnects.
- Revoked access: reinstall or update selected repository access.
- Valid push ignored: check installation ID, repository ID, branch, `auto_deploy`, and access status.
- Duplicate delivery/commit: expected automatic idempotency.
- Checkout failure: confirm Contents read permission and repository selection.

A future low-frequency reconciliation job may compare branch heads after webhook outages. It must never replace webhooks as the primary trigger.
