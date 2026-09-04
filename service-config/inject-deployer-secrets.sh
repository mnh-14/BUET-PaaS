#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
NAMESPACE="BUET-PaaS-System-Team23"
SECRET_NAME="paas-deployer-env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing local env file: $ENV_FILE" >& exit 1
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
  --from-literal=HARBOR_USER="${HARBOR_USER}" \
  --from-literal=HARBOR_PASS="${HARBOR_PASS}" \
  --from-literal=BUILDER_IMAGE_SOURCE="${BUILDER_IMAGE_SOURCE}" \
  --from-literal=DEFAULT_PRIVATE_IP="${DEFAULT_PRIVATE_IP}" \
  --from-literal=DEFAULT_FLOATING_IP="${DEFAULT_FLOATING_IP}" \
  --from-literal=DEFAULT_HARBOR_IP="${DEFAULT_HARBOR_IP}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secret '$SECRET_NAME' created/updated in namespace '$NAMESPACE'."
