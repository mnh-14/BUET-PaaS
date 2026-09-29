#!/usr/bin/env bash
set -euo pipefail

root="${1:-/tmp/buet-paas-step15d8}"
input="$root/input"
output="$root/output"
chart="$output/prometheus-blackbox-exporter-11.18.0.tgz"

test "$(sha256sum "$chart" | awk '{print $1}')" = \
  '19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8'
test "$(sha256sum "$input/values.yaml" | awk '{print $1}')" = \
  'f1823607d2090c3370635cd037671af3d1b539ea41f03dce6de008a2de5b6bb4'
test "$(sha256sum "$input/harbor-ca.crt" | awk '{print $1}')" = \
  '6fecd502db98d54578c590c385df4a3d590caf495e26ed770e54bdc2f6df6d44'
test "$(sha256sum "$input/targets-all.yaml" | awk '{print $1}')" = \
  '997b626a87edb2d87d9f4ba3ef1a263d9e76486855ea8571920780f43a72644e'

baseline_revision="$(helm history blackbox-exporter -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')"
expected_revision="$((baseline_revision + 1))"

helm upgrade blackbox-exporter "$chart" \
  --namespace monitoring \
  --values "$input/values.yaml" \
  --values "$input/targets-all.yaml" \
  --atomic --wait --timeout 10m --history-max 10 \
  --dry-run=server --hide-secret \
  > "$output/helm-server-dry-run.txt"

helm upgrade blackbox-exporter "$chart" \
  --namespace monitoring \
  --values "$input/values.yaml" \
  --values "$input/targets-all.yaml" \
  --atomic --wait --timeout 10m --history-max 10

if ! EXPECTED_REVISION="$expected_revision" STEP_ROOT="$root" \
  bash "$root/step15d8-verify.sh"; then
  echo "Post-upgrade verification failed; rolling back to revision $baseline_revision." >&2
  helm rollback blackbox-exporter "$baseline_revision" \
    --namespace monitoring \
    --wait --cleanup-on-fail --timeout 10m
  exit 1
fi

echo 'STEP15D8_TRANSACTION_SUCCESS'
