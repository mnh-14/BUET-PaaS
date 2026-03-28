# BUET-PaaS — Backend

**Module B** (Build & Transformation) + **Module D** (Serverless Execution)

---

## Prerequisites

- Python 3.11+
- Docker Desktop (or Docker Engine + Compose)
- Git
- Cloudflared binary (for public tunnel URLs via `tunnel.py`)

### Required Docker network

The backend runs deployed containers on a fixed Docker network:

- `BUET-PaaS-network-v1.0`

You can create it manually once before running backend deployment flows:

```bash
docker network create BUET-PaaS-network-v1.0
```

If it already exists, Docker will report that and you can continue.

Suggestion: you usually do not need to create this network manually because `backend/setup.sh` and `backend/setup.bat` now check for it and create it automatically.

## Setup — Run Once After Cloning

**Linux / macOS:**
```bash
bash backend/setup.sh
```

**Windows:**
```bat
backend\setup.bat
```

Both scripts do the same thing: check Python 3.11+, Docker, required Docker network, and Git; create the `venv`; install all packages; and ensure `static/` exists.

Brief command-level summary:

- `backend/setup.sh`:
	- Checks tools: `python3 --version`, `docker info`, `git --version`
	- Ensures network: `docker network inspect BUET-PaaS-network-v1.0` then `docker network create BUET-PaaS-network-v1.0` if missing
	- Creates venv: `python3 -m venv venv`
	- Installs deps: `pip install --upgrade pip` and `pip install -r requirements.txt`

- `backend/setup.bat`:
	- Checks tools: `python --version`, `docker --version`, `git --version`
	- Ensures network: `docker network inspect BUET-PaaS-network-v1.0` then `docker network create BUET-PaaS-network-v1.0` if missing
	- Creates venv: `python -m venv venv`
	- Installs deps: `python -m pip install --upgrade pip` and `pip install -r requirements.txt`

### Activating the virtual environment

| OS | Command |
|----|---------|
| Linux / macOS | `source venv/bin/activate` |
| Windows (CMD) | `venv\Scripts\activate.bat` |
| Windows (PowerShell) | `venv\Scripts\Activate.ps1` |

> **Windows PowerShell note:** if you get a script execution error, run this once:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

---

## Running the Server

Note: `main.py` integrates with `tunnel.py` automatically. During deployment, the backend may create/reuse Cloudflare quick tunnels for deployed project ports.

**Linux / macOS:**
```bash
# Terminal 1 — API server
cd backend/
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Commit poller (Himel's file)
cd backend/
source venv/bin/activate
python poller.py
```

**Windows:**
```bat
REM Terminal 1 — API server
cd backend\
venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

REM Terminal 2 — Commit poller
cd backend\
venv\Scripts\activate
python poller.py
```

| URL | What it is |
|-----|-----------|
| http://localhost:8000 |
| http://localhost:8000/health | Liveness check |

## Tunnel utility (tunnel.py)

The `tunnel.py` script can be used directly to manage Cloudflare quick tunnels.

Examples:

```bash
# Open tunnel for a local port
python tunnel.py --port 9000

# Open tunnel for a full URL
python tunnel.py --url http://localhost:9000

# Stop all running cloudflared processes
python tunnel.py --stop
```

Environment variable used by `tunnel.py`:

- `CLOUDFLARED_EXECUTABLE`: absolute path to cloudflared executable.

Example `.env` value on Windows:

```dotenv
CLOUDFLARED_EXECUTABLE=D:\\Softwares\\Cloudflared\\cloudflared-windows-amd64.exe
```

## API Endpoints (quick reference)

Below are the primary API endpoints implemented in `main.py`. Replace `:8000` with your host/port as needed.

- **GET /**: Serves the frontend `static/index.html`.
- **GET /openapi.json**: OpenAPI specification (JSON).
- **GET /health**: Liveness and MongoDB connectivity. Response example:

```json
{ "status": "ok", "version": "0.2.0", "mongodb": "connected" }
```

- **POST /api/v1/users**: Register a new student. Body (JSON):

```json
{ "user_id": "2105085", "name": "Test User", "email": "2105085@cse.buet.ac.bd", "password": "secret" }
```

- **POST /api/v1/users/login**: Login. Body:

```json
{ "user_id": "2105085", "password": "secret" }
```

- **GET /api/v1/users/{user_id}**: Get student profile (no password_hash returned).
- **GET /api/v1/users/{user_id}/projects**: List projects for the student with latest deployment info.

- **GET /api/v1/projects**: List all projects (admin view).
- **POST /api/v1/projects**: Create a project and queue a build. Body:

```json
{ "repo_url": "https://github.com/example/repo.git", "user_id": "2105085", "project_name": "my-project" }
```

- **GET /api/v1/projects/{project_id}**: Get project with deployment history.
- **DELETE /api/v1/projects/{project_id}**: Stop/remove running container and mark project stopped.

- **GET /api/v1/deployments/{deployment_id}**: Poll deployment status (queued → building → running/failed).
- **POST /api/v1/deployments/redeploy/{project_id}**: Trigger a redeploy for a project (queues a new build).

Use the `check_backend.py` script to exercise these endpoints automatically (it can seed a test user/project with `--seed`).

## Health-check script

A small portable checker has been added at `backend/check_backend.py` to verify the API root and `/health` endpoints.

Usage (run from the `backend/` folder):

```bash
python check_backend.py
python check_backend.py --host 127.0.0.1 --port 8000 --retries 5
```

Exit codes: `0` = success, `2` = failure.

## Environment variables (.env)

Create a `.env` file inside the `backend/` folder with the following values (example):

```dotenv
MONGO_URI=mongodb+srv://<username>:<password>@cluster.example.mongodb.net/?retryWrites=true&w=majority
MONGO_DB=buetpaas
CLOUDFLARED_EXECUTABLE=D:\Softwares\Cloudflared\cloudflared-windows-amd64.exe
GITHUB_PAT=<Your github personal access token>
```

Notes:

- `MONGO_URI` and `MONGO_DB` are used by `db.py`. You can skip these if you used the docker frontend and database setup
- `CLOUDFLARED_EXECUTABLE` is used by `tunnel.py` and tunnel integration inside `main.py`.

