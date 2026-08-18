# BUET-PaaS Prototype v2

BUET-PaaS is a prototype Platform-as-a-Service environment with:

- A Next.js frontend
- A Python/FastAPI backend
- A MongoDB database
- A GitHub App supporting authorized public and private repositories
- SonarQube quality-gate enforcement
- Kubernetes build and deployment orchestration

This README covers running the frontend and MongoDB using Docker. For backend setup and execution, follow the backend documentation in `backend/readme.md`.

## Deployment flow

Students authenticate to BUET-PaaS, install the shared GitHub App, and create a project from an authorized repository and branch. The project page checks the branch head on demand and enables the manual deploy button when it differs from the last successfully deployed commit.

The backend clones the selected source for SonarQube analysis, then calls the private deployment service on the Kubernetes VM. It polls that service every five seconds for build/deploy status, persists state changes and the final URL in MongoDB, and streams changes to the frontend with SSE. Private build requests use short-lived GitHub App installation tokens. There is no native Kubernetes Watch connection, webhook auto-deployment, continuous commit poller, local application Docker execution, or Cloudflare application tunnel.

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
