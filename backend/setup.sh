#!/usr/bin/env bash
set -e

# Always run from inside backend/ regardless of where the script is called from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"



# ── Check Python 3.11+ ───────────────────────────────────────────
echo "▶ Checking Python..."
PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
MAJOR=$(echo "$PY_VER" | cut -d. -f1)
MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]); then
    echo "  ✗ Python 3.11+ required. You have $PY_VER"
    echo "    sudo apt install python3.11  OR  https://python.org"
    exit 1
fi
echo "   Python $PY_VER"

# ── Check Docker ─────────────────────────────────────────────────
echo "▶ Checking Docker..."
if ! command -v docker &>/dev/null; then
    echo "  ✗ Docker not found. Install: https://docs.docker.com/engine/install/"
    exit 1
fi
if ! docker info &>/dev/null; then
    echo "  ✗ Docker installed but can't run without sudo."
    echo "    Fix: sudo usermod -aG docker \$USER  → then log out & back in"
    exit 1
fi
echo "   Docker OK ($(docker --version | awk '{print $3}' | tr -d ','))"

# ── Check Git ────────────────────────────────────────────────────
echo "▶ Checking Git..."
if ! command -v git &>/dev/null; then
    echo "  ✗ Git not found. Run: sudo apt install git"
    exit 1
fi
echo "   Git OK"

# ── Create venv ──────────────────────────────────────────────────
echo "▶ Setting up Python virtual environment..."
if [ -d "venv" ]; then
    echo "  ℹ  venv already exists — skipping creation"
else
    python3 -m venv venv
    echo "   venv created"
fi

# ── Install deps ─────────────────────────────────────────────────
echo " Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✓ Installed:"
pip show fastapi uvicorn requests 2>/dev/null \
    | grep -E "^(Name|Version):" \
    | paste - - \
    | awk '{printf "    %-20s %s\n", $2, $4}'

# ── Check static/ ────────────────────────────────────────────────
if [ ! -d "static" ]; then
    mkdir -p static
    echo "  ✓ static/ folder created"
fi

# ── Optional: check pack CLI ────────────────────────────────────
echo "▶ Checking pack CLI (optional)..."
if command -v pack &>/dev/null; then
    echo "  ✓ pack found — CNB builds enabled (no Dockerfile needed)"
else
    echo "    pack not found — docker build (needs Dockerfile in repo) will be used"
    echo "    To install pack:"
    echo "       curl -sSL https://github.com/buildpacks/pack/releases/download/v0.35.1/pack-v0.35.1-linux.tgz | tar -xz"
    echo "       sudo mv pack /usr/local/bin/"
fi

echo ""
echo "╔════════════════════════════════════════╗"
echo "║          Setup Complete ✓              ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "  Start the API server:"
echo "    cd backend/"
echo "    source venv/bin/activate"
echo "    uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "  Start the poller (second terminal):"
echo "    cd backend/"
echo "    source venv/bin/activate"
echo "    python poller.py"
echo ""
echo "  Dashboard  →  http://localhost:8000"
echo "  API Docs   →  http://localhost:8000/docs"
echo "  Health     →  http://localhost:8000/health"
echo ""