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
  jq -r 'map(select(.status=="deployed")) | last | .revision')" = '8'
test "$(helm history monitoring-stack -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')" = '6'
test "$(kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter -o json | jq '.items | length')" = '4'
test "$(metric_value <<< "$(query 'count%28up%29')")" = '35'
test "$(jq '.data.result | length' <<< "$(query 'up%3D%3D0')")" = '0'
for service in frontend backend deployer registry; do
  test "$(metric_value <<< "$(query "probe_success%7Bservice%3D%22${service}%22%7D")")" = '1'
done
test "$(metric_value <<< "$(query 'probe_http_ssl%7Bservice%3D%22registry%22%7D')")" = '1'

sonar_body="$(curl --fail --silent --show-error --max-time 15 \
  http://192.168.128.33:9000/api/system/status)"
grep -q '"status":"UP"' <<< "$sonar_body"

echo 'BLACKBOX_STATUS'
helm status blackbox-exporter -n monitoring
echo 'CURRENT_SERVICEMONITORS'
kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter -o name
echo 'SONARQUBE_HEALTH'
printf '%s\n' "$sonar_body"
echo 'PROMETHEUS_BASELINE'
jq -n --arg total '35' --arg down '0' \
  '{total_up:$total,down:$down,existing_probe_success:"4/4",harbor_ssl:"1"}'
echo 'STEP15D8_PREFLIGHT_SUCCESS'
