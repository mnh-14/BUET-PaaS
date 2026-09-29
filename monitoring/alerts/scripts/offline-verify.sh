#!/usr/bin/env bash
set -euo pipefail

root="${1:-/tmp/buet-paas-step16c}"
input="$root/input"
output="$root/output"
prom_image='quay.io/prometheus/prometheus@sha256:50c707e96da5ade383cb1707790576480485e93de06aa60ad8802cb5f744bd0a'

kubectl kustomize "$input" > "$output/prometheus-rule-rendered.yaml"
test "$(grep -c '^kind: PrometheusRule$' "$output/prometheus-rule-rendered.yaml")" -eq 1
test "$(grep -c '^kind: Secret$' "$output/prometheus-rule-rendered.yaml")" -eq 0
test "$(grep -c '^kind: ConfigMap$' "$output/prometheus-rule-rendered.yaml")" -eq 0
python3 "$input/offline-verify.py" "$root"

sudo docker run --rm \
  --entrypoint /bin/promtool \
  -v "$output:/work:ro" \
  "$prom_image" \
  check rules /work/prometheus-rules.yaml

echo 'SHA-256'
sha256sum \
  "$input/prometheus-rule.yaml" \
  "$input/kustomization.yaml" \
  "$output/prometheus-rule-rendered.yaml" \
  "$output/prometheus-rules.yaml"
echo 'STEP16C_OFFLINE_VERIFY_SUCCESS'
