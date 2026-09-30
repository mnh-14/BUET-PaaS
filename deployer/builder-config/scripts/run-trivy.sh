#!/bin/bash
set -e

IMAGE_TO_SCAN="${IMAGE_DESTINATION:?IMAGE_DESTINATION is required}"

echo "Scanning image: ${IMAGE_TO_SCAN}"

/kaniko/trivy image \
  --scanners vuln,secret \
  --severity "${SEVERITY:-CRITICAL,HIGH}" \
  --exit-code "${EXIT_CODE:-1}" \
  --insecure \
  ${HARBOR_USER:+--username "$HARBOR_USER"} \
  ${HARBOR_PASS:+--password "$HARBOR_PASS"} \
  "${IMAGE_TO_SCAN}"

echo "Trivy image scan passed."