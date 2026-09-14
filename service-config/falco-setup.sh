#!/usr/bin/env bash
#
# service-config/falco-setup.sh
#
# Installs (or upgrades in place) Falco + Falcosidekick into the k3s cluster.
# Run this from k3s-user (or any box with a working kubectl context against
# the cluster) — no worker VM access needed; the k3s API server schedules
# the Falco DaemonSet onto every worker automatically.
#
# Safe to re-run: uses `helm upgrade --install`, so editing
# falco-values.yaml (e.g. changing minimumpriority or the webhook address)
# and re-running this script applies the change without a full reinstall.
#
# See falco-integration-plan.md for the full architecture decisions and
# rollback instructions.

set -euo pipefail

NAMESPACE="falco"
RELEASE_NAME="falco"
SCRIPT_DIR="$(dirname "$0")"
VALUES_FILE="${SCRIPT_DIR}/falco-values.yaml"
LOCAL_VALUES_FILE="${SCRIPT_DIR}/falco-values.local.yaml"

HELM_VALUE_ARGS=(--values "${VALUES_FILE}")
if [[ -f "${LOCAL_VALUES_FILE}" ]]; then
  echo "Found ${LOCAL_VALUES_FILE} — layering it on top (holds the real shared-secret token, gitignored)."
  HELM_VALUE_ARGS+=(--values "${LOCAL_VALUES_FILE}")
else
  echo "WARNING: ${LOCAL_VALUES_FILE} not found — Falcosidekick's webhook will have no"
  echo "X-Falco-Token header set. Copy falco-values.local.yaml.example to"
  echo "falco-values.local.yaml and fill in the real token before relying on this in production."
fi

echo "[1/4] Checking helm is installed..."
if ! command -v helm &> /dev/null; then
  echo "ERROR: helm not found. Install it first:"
  echo '  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash'
  exit 1
fi

echo "[2/4] Ensuring namespace '${NAMESPACE}' exists..."
kubectl get namespace "${NAMESPACE}" &> /dev/null || kubectl create namespace "${NAMESPACE}"

echo "[3/4] Adding/updating the falcosecurity Helm repo..."
helm repo add falcosecurity https://falcosecurity.github.io/charts &> /dev/null || true
helm repo update falcosecurity

echo "[4/4] Installing/upgrading Falco + Falcosidekick..."
helm upgrade --install "${RELEASE_NAME}" falcosecurity/falco \
  --namespace "${NAMESPACE}" \
  "${HELM_VALUE_ARGS[@]}"

echo ""
echo "Done. Verify with:"
echo "  kubectl get pods -n ${NAMESPACE} -o wide"
echo ""
echo "Expect 1 Falco pod per worker VM (k3s-worker-01/02/03) plus 1 falcosidekick pod."