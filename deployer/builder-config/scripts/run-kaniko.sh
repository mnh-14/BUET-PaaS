#!/bin/bash
set -e
echo "🔨 [TASK 3] Running Kaniko Image Build & Push..."

# -----------------------------------------------------------------------
# 0. DNS PRE-FLIGHT CHECK — mitigates CoreDNS/CNI startup-race SERVFAILs
#    (see: "server misbehaving" on auth.docker.io lookups)
#
#    Checks the hosts kaniko commonly talks to while PULLING a base
#    image — NOT the destination registry we push the built image to.
#    Adjust DNS_CHECK_HOSTS below if your Dockerfiles pull from a
#    different/private base registry.
# -----------------------------------------------------------------------
DNS_CHECK_HOSTS=(
  "auth.docker.io"          # Docker Hub token auth endpoint
  "registry-1.docker.io"    # Docker Hub blob/manifest pulls
)
DNS_MAX_ATTEMPTS="${DNS_MAX_ATTEMPTS:-5}"
DNS_RETRY_DELAY="${DNS_RETRY_DELAY:-3}"
 
resolve_host() {
  local host="$1"
  if command -v nslookup >/dev/null 2>&1; then
    nslookup "$host" >/dev/null 2>&1 && return 0
  fi
  if command -v getent >/dev/null 2>&1; then
    getent hosts "$host" >/dev/null 2>&1 && return 0
  fi
  return 1
}
 
wait_for_dns() {
  local host="$1"
  local attempt=1
  while [ "$attempt" -le "$DNS_MAX_ATTEMPTS" ]; do
    if resolve_host "$host"; then
      echo "  ✓ DNS OK: ${host} (attempt ${attempt}/${DNS_MAX_ATTEMPTS})"
      return 0
    fi
    echo "  ✗ DNS not ready: ${host} (attempt ${attempt}/${DNS_MAX_ATTEMPTS})"
    attempt=$((attempt + 1))
    [ "$attempt" -le "$DNS_MAX_ATTEMPTS" ] && sleep "$DNS_RETRY_DELAY"
  done
  return 1
}
 
echo "🌐 DNS pre-flight check: ${DNS_CHECK_HOSTS[*]}"
DNS_FAILED=0
for host in "${DNS_CHECK_HOSTS[@]}"; do
  echo "→ Checking ${host} (up to ${DNS_MAX_ATTEMPTS} attempts)..."
  wait_for_dns "$host" || DNS_FAILED=1
done
 
if [ "$DNS_FAILED" -eq 1 ]; then
  echo "❌ DNS resolution failed for one or more base-image pull hosts. Aborting before starting kaniko."
  exit 1
fi
echo "✅ DNS pre-flight checks passed."



# 1. EXPLICITLY SET DOCKER_CONFIG PATH FOR KANIKO
export DOCKER_CONFIG="/kaniko/.docker"
mkdir -p "${DOCKER_CONFIG}"

# 2. GENERATE AUTH CONFIG IF CREDENTIALS EXIST
if [ -n "${HARBOR_USER}" ] && [ -n "${HARBOR_PASS}" ]; then

  # Extract host (e.g. 192.168.128.4)
  REGISTRY_HOST=$(echo "${IMAGE_DESTINATION}" | cut -d'/' -f1)

  # Generate base64 token safely using printf
  AUTH_BASE64=$(printf "%s:%s" "${HARBOR_USER}" "${HARBOR_PASS}" | base64 | tr -d '\r\n')

  # Write config with all 3 URL variations
  cat <<EOF > "${DOCKER_CONFIG}/config.json"
{
  "auths": {
    "${REGISTRY_HOST}": {
      "auth": "${AUTH_BASE64}"
    },
    "https://${REGISTRY_HOST}": {
      "auth": "${AUTH_BASE64}"
    },
    "https://${REGISTRY_HOST}/v2/": {
      "auth": "${AUTH_BASE64}"
    }
  }
}
EOF
  echo "✓ Kaniko authentication config generated at ${DOCKER_CONFIG}/config.json"
fi


/kaniko/executor \
  --context=dir:///workspace \
  --dockerfile="/workspace/${DOCKERFILE_PATH:-Dockerfile}" \
  --destination="${IMAGE_DESTINATION}" \
  --cache=true \
  --cache-copy-layers=true \
  --compressed-caching=false \
  --snapshot-mode=redo \
  --use-new-run \
  ${EXTRA_FLAGS}
echo "✓ Kaniko build complete."
