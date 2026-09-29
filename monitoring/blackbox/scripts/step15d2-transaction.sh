#!/usr/bin/env bash
set -euo pipefail

root="${1:-/tmp/buet-paas-step15d2}"
input="$root/input"
output="$root/output"
chart="$output/prometheus-blackbox-exporter-11.18.0.tgz"

test "$(sha256sum "$chart" | awk '{print $1}')" = \
  '19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8'
test "$(sha256sum "$input/targets-frontend-backend.yaml" | awk '{print $1}')" = \
  '5f412b07a85c01141b622c0467895e8698af296c86105aae2396988d9bf28fad'

baseline_revision="$(helm history blackbox-exporter -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')"
expected_revision="$((baseline_revision + 1))"

helm upgrade blackbox-exporter "$chart" \
  --namespace monitoring \
  --values "$input/values.yaml" \
  --values "$input/targets-frontend-backend.yaml" \
  --atomic --wait --timeout 10m --history-max 10 \
  --dry-run=server --hide-secret \
  > "$output/helm-server-dry-run.txt"

helm upgrade blackbox-exporter "$chart" \
  --namespace monitoring \
  --values "$input/values.yaml" \
  --values "$input/targets-frontend-backend.yaml" \
  --atomic --wait --timeout 10m --history-max 10

if ! EXPECTED_REVISION="$expected_revision" bash "$root/step15d2-verify.sh"; then
  echo "Post-upgrade verification failed; rolling back to revision $baseline_revision." >&2
  helm rollback blackbox-exporter "$baseline_revision" \
    --namespace monitoring \
    --wait --cleanup-on-fail --timeout 10m
  exit 1
fi

echo 'STEP15D2_TRANSACTION_SUCCESS'
