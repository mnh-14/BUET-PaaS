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

INJECT_HEADER=$(cat << 'EOF'
ARG NODE_OPTIONS="--max-old-space-size=1536 --max-semi-space-size=64"
ARG NODE_ENV=production
ENV NODE_OPTIONS=$NODE_OPTIONS
ENV NODE_ENV=$NODE_ENV
EOF
)

# Insert the entire block at the top of the Dockerfile
sed -i "1i $INJECT_HEADER" /workspace/Dockerfile
echo "✓ Injected NODE_OPTIONS and NODE_ENV into Dockerfile."


/kaniko/executor \
  --context=dir:///workspace \
  --dockerfile="/workspace/${DOCKERFILE_PATH:-Dockerfile}" \
  --destination="${IMAGE_DESTINATION}" \
  --cache=true \
  --cache-copy-layers=true \
  --compressed-caching=false \
  ${EXTRA_FLAGS}
echo "✓ Kaniko build complete."
