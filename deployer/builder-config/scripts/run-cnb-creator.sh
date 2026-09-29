#!/bin/bash
set -e
echo "🔨 [TASK 3] Running Cloud Native Buildpacks (creator) Build & Push..."

# Dockerfile-less equivalent of run-kaniko.sh: the CNB `creator` binary
# (baked into a builder image, e.g. paketobuildpacks/builder or
# gcr.io/buildpacks/builder) auto-detects the app and builds+pushes the
# final image directly — no Docker daemon, same daemonless spirit as kaniko.

# -----------------------------------------------------------------------
# 0. DNS PRE-FLIGHT CHECK — mitigates CoreDNS/CNI startup-race SERVFAILs
#
#    Checks hosts commonly involved in pulling buildpack/run-image
#    layers mid-build — NOT the destination registry we push to.
#    Adjust DNS_CHECK_HOSTS below to match your builder's actual
#    run-image registry if it isn't Docker Hub / gcr.io.
# -----------------------------------------------------------------------
DNS_CHECK_HOSTS=(
  "auth.docker.io"          # Docker Hub token auth endpoint
  "registry-1.docker.io"    # Docker Hub blob/manifest pulls
  "gcr.io"                  # common Paketo/GCP builder run-image registry
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
  echo "❌ DNS resolution failed for one or more hosts. Aborting before starting the buildpack creator."
  exit 1
fi
echo "✅ DNS pre-flight checks passed."

# -----------------------------------------------------------------------
# 1. EXPLICITLY SET DOCKER_CONFIG PATH FOR THE LIFECYCLE
#    (the CNB lifecycle reads registry creds from the same
#    ~/.docker/config.json style file kaniko uses)
# -----------------------------------------------------------------------
export DOCKER_CONFIG="/cnb/.docker"
mkdir -p "${DOCKER_CONFIG}"

# -----------------------------------------------------------------------
# 2. GENERATE AUTH CONFIG IF CREDENTIALS EXIST
# -----------------------------------------------------------------------
if [ -n "${HARBOR_USER}" ] && [ -n "${HARBOR_PASS}" ]; then

  REGISTRY_HOST=$(echo "${IMAGE_DESTINATION}" | cut -d'/' -f1)
  AUTH_BASE64=$(printf "%s:%s" "${HARBOR_USER}" "${HARBOR_PASS}" | base64 | tr -d '\r\n')

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
  echo "✓ Buildpack authentication config generated at ${DOCKER_CONFIG}/config.json"
fi

# -----------------------------------------------------------------------
# 3. RUN THE CNB CREATOR (no Dockerfile involved — detect, analyze,
#    restore, build and export all happen in this single step)
# -----------------------------------------------------------------------
/cnb/lifecycle/creator \
  -app="/workspace" \
  -cache-dir="${CACHE_DIR:-/cache}" \
  -uid="${CNB_USER_ID:-1000}" \
  -gid="${CNB_GROUP_ID:-1000}" \
  -process-type="${CNB_PROCESS_TYPE:-web}" \
  ${EXTRA_FLAGS} \
  "${IMAGE_DESTINATION}"

echo "✓ Buildpack build complete."