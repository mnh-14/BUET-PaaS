#!/bin/bash
set -e

echo "Cloning Git repository (Branch: ${GIT_BRANCH:-main})..."

clone_url="${GIT_URL}"
if [[ -n "${GIT_TOKEN:-}" ]]; then
	clone_url="https://x-access-token:${GIT_TOKEN}@${GIT_URL#https://}"
fi

git clone --depth 1 --branch "${GIT_BRANCH:-main}" "${clone_url}" /workspace
echo "Git clone complete."
