#!/usr/bin/env bash
set -euo pipefail

root="${1:-/tmp/buet-paas-step15d6}"
input="$root/input"
output="$root/output"

query() {
  kubectl get --raw \
    "/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=$1"
}

metric_value() {
  jq -r '.data.result[0].value[1] // empty'
}

test "$(helm history blackbox-exporter -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')" = '7'
test "$(helm history monitoring-stack -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')" = '6'
test "$(kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter -o json | jq '.items | length')" = '3'
test "$(metric_value <<< "$(query 'count%28up%29')")" = '34'
test "$(jq '.data.result | length' <<< "$(query 'up%3D%3D0')")" = '0'
test "$(metric_value <<< "$(query 'probe_success%7Bservice%3D%22frontend%22%7D')")" = '1'
test "$(metric_value <<< "$(query 'probe_success%7Bservice%3D%22backend%22%7D')")" = '1'
test "$(metric_value <<< "$(query 'probe_success%7Bservice%3D%22deployer%22%7D')")" = '1'

kubectl get configmap blackbox-harbor-ca -n monitoring \
  -o json | jq -j '.data["harbor-ca.crt"]' > "$output/live-harbor-ca.crt"
test "$(sha256sum "$output/live-harbor-ca.crt" | awk '{print $1}')" = \
  '6fecd502db98d54578c590c385df4a3d590caf495e26ed770e54bdc2f6df6d44'
cmp "$input/harbor-ca.crt" "$output/live-harbor-ca.crt"

harbor_body="$(curl --cacert "$input/harbor-ca.crt" \
  --fail --silent --show-error --max-time 15 \
  https://192.168.128.152/api/v2.0/health)"
grep -q '"status":"healthy"' <<< "$harbor_body"

echo 'BLACKBOX_STATUS'
helm status blackbox-exporter -n monitoring
echo 'CURRENT_SERVICEMONITORS'
kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter -o name
echo 'HARBOR_CA'
sha256sum "$output/live-harbor-ca.crt"
openssl x509 -in "$output/live-harbor-ca.crt" \
  -noout -subject -issuer -dates -fingerprint -sha256
echo 'HARBOR_HEALTH'
printf '%s\n' "$harbor_body"
echo 'PROMETHEUS_BASELINE'
jq -n --arg total '34' --arg down '0' \
  '{total_up:$total,down:$down,frontend_success:"1",backend_success:"1",deployer_success:"1"}'
echo 'STEP15D6_PREFLIGHT_SUCCESS'
