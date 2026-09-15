# BUET-PaaS Prototype v2

BUET-PaaS is a prototype Platform-as-a-Service environment with:

- A Next.js frontend
- A Python/FastAPI backend
- A MongoDB database
- One central GitHub App webhook supporting authorized public and private repositories

This README covers running the frontend and MongoDB using Docker. For backend setup and execution, follow the backend documentation in `backend/readme.md`.

## GitHub App deployment flow

Students authenticate to BUET-PaaS, install the shared GitHub App, select an authorized repository and branch, and deploy an exact commit. Future pushes arrive through one signed endpoint, `/api/v1/github/webhook`. The backend generates short-lived installation tokens only when calling GitHub or cloning a private repository; tokens never reach the frontend or MongoDB.

The former 30-second GitHub poller is deprecated and is not part of normal startup. See `backend/readme.md` for GitHub App settings, Cloudflare Quick/Named Tunnel ingress, environment variables, secret rules, testing, and troubleshooting.

## Prerequisites

Install the following on your machine:

- Docker Desktop (with Docker Compose support)
- Git (for source management)

Recommended:

- Keep Docker Desktop running before executing any compose command.

## Services Defined in Docker Compose

The root `docker-compose.yaml` defines:

- `buet-paas-frontend` (container name: `BUET-PaaS-frontend`)
- `buet-paas-database` (container name: `BUET-PaaS-mongodb`)

Exposed ports:

- Frontend: `3000`
- MongoDB: `27017`

Data persistence:

- MongoDB data is bind-mounted to `./database` on the host.

## Run Frontend and MongoDB with Docker

From the project root directory, run:

```bash
docker compose up --build -d
```

This command:

- Builds the frontend image from `frontend/Dockerfile`
- Starts the frontend container on port `3000`
- Starts MongoDB on port `27017`
- Runs both containers in detached mode

## Verify Running Services

Check container status:

```bash
docker compose ps
```

Open the frontend:

- http://localhost:3000

Optional MongoDB connectivity check:

```bash
docker exec -it BUET-PaaS-mongodb mongosh --eval "db.adminCommand({ ping: 1 })"
```

## Logs and Operations

View logs (all services):

```bash
docker compose logs -f
```

View logs for frontend only:

```bash
docker compose logs -f buet-paas-frontend
```

Stop services:

```bash
docker compose down
```

Reset local database state (optional):

1. Stop services with `docker compose down`.
2. Delete the contents of the `database/` directory.
3. Start services again with `docker compose up --build -d`.

## Backend Instructions

Backend setup and runtime are documented separately.

- See `backend/readme.md` for:
  - Environment setup
  - Virtual environment activation
  - API and poller execution
  - Health check and endpoint usage

## Troubleshooting

If frontend cannot call backend from inside Docker:

- The compose file uses `host.docker.internal:8000` for backend access.
- Ensure the backend is running on your host machine at port `8000`.

If port conflicts occur:

- Free ports `3000` or `27017`, or adjust mappings in `docker-compose.yaml`.

If Docker build fails:

- Re-run with fresh build output:

```bash
docker compose build --no-cache
docker compose up -d
```
