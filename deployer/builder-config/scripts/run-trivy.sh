#!/bin/bash
set -e
echo "🔍 [TASK 2] Running Trivy Vulnerability & Secret Scan..."
trivy fs --security-checks vuln,secret --severity "${SEVERITY:-CRITICAL,HIGH}" --exit-code "${EXIT_CODE:-1}" /workspace
echo "✓ Trivy security scan passed."
