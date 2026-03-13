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

## Health-check script

A small portable checker has been added at `backend/check_backend.py` to verify the API root and `/health` endpoints.

Usage (run from the `backend/` folder):

```bash
python check_backend.py
python check_backend.py --host 127.0.0.1 --port 8000 --retries 5
```

Exit codes: `0` = success, `2` = failure.
