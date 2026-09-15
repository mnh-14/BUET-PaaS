@echo off
cd /d "%~dp0"

set "DOCKER_NETWORK=BUET-PaaS-network-v1.0"


REM ── Check Python ─────────────────────────────────────────────────
echo [1/6] Checking Python...
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo   ERROR: Python not found.
    echo   Install Python 3.11+ from https://python.org
    echo   IMPORTANT: Check "Add Python to PATH" during install.
    pause
    exit /b 1
)

FOR /F "tokens=2" %%V IN ('python --version 2^>^&1') DO SET PY_VER=%%V
FOR /F "tokens=1,2 delims=." %%A IN ("%PY_VER%") DO (
    SET PY_MAJOR=%%A
    SET PY_MINOR=%%B
)

IF %PY_MAJOR% LSS 3 (
    echo   ERROR: Python 3.11+ required. You have %PY_VER%
    pause
    exit /b 1
)
IF %PY_MAJOR% EQU 3 IF %PY_MINOR% LSS 11 (
    echo   ERROR: Python 3.11+ required. You have %PY_VER%
    pause
    exit /b 1
)
echo   OK: Python %PY_VER%

REM ── Check Docker ─────────────────────────────────────────────────
echo [2/6] Checking Docker...
docker --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo   ERROR: Docker not found.
    echo   Install Docker Desktop from https://www.docker.com/products/docker-desktop/
    echo   After installing, start Docker Desktop and wait for it to be "Running".
    pause
    exit /b 1
)
echo   OK: Docker found

REM ── Ensure required Docker network exists ────────────────────────
echo [3/6] Checking Docker network: %DOCKER_NETWORK%...
docker network inspect "%DOCKER_NETWORK%" >nul 2>&1
IF ERRORLEVEL 1 (
    echo   INFO: Docker network not found. Creating %DOCKER_NETWORK%...
    docker network create "%DOCKER_NETWORK%" >nul 2>&1
    IF ERRORLEVEL 1 (
        echo   ERROR: Failed to create Docker network %DOCKER_NETWORK%.
        echo   Ensure Docker Desktop is running and try again.
        pause
        exit /b 1
    )
    echo   OK: Docker network created
) ELSE (
    echo   OK: Docker network exists
)

REM ── Check Git ────────────────────────────────────────────────────
echo [4/6] Checking Git...
git --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo   ERROR: Git not found.
    echo   Install from https://git-scm.com/download/win
    pause
    exit /b 1
)
echo   OK: Git found

REM ── Create virtual environment ───────────────────────────────────
echo [5/6] Setting up virtual environment...
IF EXIST "venv\" (
    echo   INFO: venv already exists, skipping creation
) ELSE (
    python -m venv venv
    echo   OK: venv created
)

REM ── Install dependencies ─────────────────────────────────────────
echo [6/6] Installing Python dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo   OK: All packages installed

REM ── Create static\ if missing ────────────────────────────────────
IF NOT EXIST "static\" (
    mkdir static
    echo   OK: static\ folder created
)

REM ── Check pack CLI (optional) ────────────────────────────────────
pack --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo.
    echo   NOTE: pack CLI not found - docker build will be used instead.
    echo   To install pack on Windows, download from:
    echo   https://github.com/buildpacks/pack/releases/latest
    echo   (get the -windows.zip, extract pack.exe, add to PATH)
) ELSE (
    echo   OK: pack CLI found - CNB builds enabled
)

echo.
echo ================================================
echo          Setup Complete!
echo ================================================
echo.
echo   Start the API server:
echo     cd backend\
echo     venv\Scripts\activate
echo     uvicorn main:app --reload --host 0.0.0.0 --port 8000
echo.
echo   Dashboard  -^>  http://localhost:8000
echo   API Docs   -^>  http://localhost:8000/docs
echo   Health     -^>  http://localhost:8000/health
echo.
pause
