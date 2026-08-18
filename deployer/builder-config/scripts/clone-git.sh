#!/bin/bash
set -e
echo "📥 [TASK 1] Cloning Git Repository: ${GIT_URL} (Branch: ${GIT_BRANCH:-main})..."
rm -rf /workspace
mkdir -p /workspace

if [ -n "${GITHUB_TOKEN:-}" ]; then
  ASKPASS_FILE="$(mktemp)"
  cleanup() { rm -f "${ASKPASS_FILE}"; }
  trap cleanup EXIT
  cat > "${ASKPASS_FILE}" <<'EOF'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' 'x-access-token' ;;
  *Password*) printf '%s\n' "${GITHUB_TOKEN}" ;;
esac
EOF
  chmod 700 "${ASKPASS_FILE}"
  GIT_ASKPASS="${ASKPASS_FILE}" GIT_TERMINAL_PROMPT=0 \
    git clone --depth 1 -b "${GIT_BRANCH:-main}" "${GIT_URL}" /workspace
else
  git clone --depth 1 -b "${GIT_BRANCH:-main}" "${GIT_URL}" /workspace
fi
echo "✓ Git clone complete."
