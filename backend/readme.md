# BUET-PaaS — Backend

**Module B** (Build & Transformation) + **Module D** (Serverless Execution)

---

## Setup — Run Once After Cloning

**Linux / macOS:**
```bash
bash backend/setup.sh
```

**Windows:**
```bat
backend\setup.bat
```

Both scripts do the same thing: check Python 3.11+, Docker, Git, create the `venv`, and install all packages.

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

## Database setup (db.py)

This project expects a MongoDB connection described by environment variables. Create a `.env` file inside the `backend/` folder with these values (example):

```dotenv
MONGO_URI=mongodb+srv://<username>:<password>@cluster.example.mongodb.net/?retryWrites=true&w=majority
MONGO_DB=buetpaas
```

