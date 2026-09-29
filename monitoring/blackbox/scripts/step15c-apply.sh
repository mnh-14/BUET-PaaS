#!/usr/bin/env bash
set -euo pipefail

root="${1:-/tmp/buet-paas-step15c}"
input="$root/input"
output="$root/output"
chart="$output/prometheus-blackbox-exporter-11.18.0.tgz"
control_host="ubuntu@192.168.128.101"

kube() {
  ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
    "$control_host" sudo -n k3s kubectl "$@"
}

rollback_platform() {
  kube delete networkpolicy blackbox-exporter-prometheus-only \
    -n monitoring --ignore-not-found
  kube delete configmap blackbox-harbor-ca \
    -n monitoring --ignore-not-found
}

test "$(sha256sum "$chart" | awk '{print $1}')" = \
  "19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8"

kubectl kustomize "$input" > "$output/platform-rendered.yaml"

if helm status blackbox-exporter -n monitoring >/dev/null 2>&1; then
  echo 'blackbox-exporter Helm release already exists; refusing first-install script' >&2
  exit 1
fi

test -z "$(kube get all,servicemonitor,networkpolicy,configmap \
  -n monitoring -o name | grep -i blackbox || true)"

kube apply --server-side --dry-run=server \
  -f - < "$output/platform-rendered.yaml" \
  > "$output/platform-server-dry-run.txt"

helm upgrade --install blackbox-exporter "$chart" \
  --namespace monitoring \
  --values "$input/values.yaml" \
  --values "$input/targets-frontend.yaml" \
  --atomic --wait --timeout 10m --history-max 10 \
  --dry-run=server --hide-secret \
  > "$output/helm-server-dry-run.txt"

kube apply -f - < "$output/platform-rendered.yaml"

if ! helm upgrade --install blackbox-exporter "$chart" \
  --namespace monitoring \
  --values "$input/values.yaml" \
  --values "$input/targets-frontend.yaml" \
  --atomic --wait --timeout 10m --history-max 10; then
  rollback_platform
  exit 1
fi

echo 'STEP15C_APPLY_SUCCESS'
