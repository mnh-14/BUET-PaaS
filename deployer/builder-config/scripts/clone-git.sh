#!/bin/bash
set -e
echo "📥 [TASK 1] Cloning Git Repository: ${GIT_URL} (Branch: ${GIT_BRANCH:-main})..."
git clone --depth 1 -b "${GIT_BRANCH:-main}" "${GIT_URL}" /workspace
echo "✓ Git clone complete."
