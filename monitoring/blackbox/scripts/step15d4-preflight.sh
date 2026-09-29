#!/usr/bin/env bash
set -euo pipefail

query() {
  kubectl get --raw \
    "/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=$1"
}

metric_value() {
  jq -r '.data.result[0].value[1] // empty'
}

test "$(helm history blackbox-exporter -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')" = '6'
test "$(helm history monitoring-stack -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')" = '6'
test "$(kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter -o json | jq '.items | length')" = '2'
test "$(metric_value <<< "$(query 'count%28up%29')")" = '33'
test "$(jq '.data.result | length' <<< "$(query 'up%3D%3D0')")" = '0'
test "$(metric_value <<< "$(query 'probe_success%7Bservice%3D%22frontend%22%7D')")" = '1'
test "$(metric_value <<< "$(query 'probe_success%7Bservice%3D%22backend%22%7D')")" = '1'

deployer_body="$(kubectl get --raw \
  '/api/v1/namespaces/buet-paas-system-team23/services/http:paas-deployer:80/proxy/health')"
grep -q '"status":"ok"' <<< "$deployer_body"

echo 'BLACKBOX_STATUS'
helm status blackbox-exporter -n monitoring
echo 'CURRENT_SERVICEMONITORS'
kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter -o name
echo 'DEPLOYER_HEALTH'
printf '%s\n' "$deployer_body"
echo 'PROMETHEUS_BASELINE'
jq -n --arg total '33' --arg down '0' \
  '{total_up:$total,down:$down,frontend_success:"1",backend_success:"1"}'
echo 'STEP15D4_PREFLIGHT_SUCCESS'
