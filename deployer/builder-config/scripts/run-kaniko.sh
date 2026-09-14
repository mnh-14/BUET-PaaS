#!/bin/bash
set -e
echo "🔨 [TASK 3] Running Kaniko Image Build & Push..."



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
