#!/usr/bin/env bash
set -euo pipefail

expected_revision="${EXPECTED_REVISION:?EXPECTED_REVISION is required}"

query() {
  kubectl get --raw \
    "/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=$1"
}

metric_value() {
  jq -r '.data.result[0].value[1] // empty'
}

helm status blackbox-exporter -n monitoring
kubectl rollout status deployment/blackbox-exporter -n monitoring --timeout=3m

frontend=''
backend=''
deployer=''
frontend_status=''
backend_status=''
deployer_status=''
frontend_duration=''
backend_duration=''
deployer_duration=''
total=''
down=''
blackbox_targets='[]'
sm_count=0
converged=false

for _ in $(seq 1 30); do
  frontend="$(query 'probe_success%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22frontend%22%7D')"
  backend="$(query 'probe_success%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22backend%22%7D')"
  deployer="$(query 'probe_success%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22deployer%22%7D')"
  frontend_status="$(query 'probe_http_status_code%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22frontend%22%7D')"
  backend_status="$(query 'probe_http_status_code%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22backend%22%7D')"
  deployer_status="$(query 'probe_http_status_code%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22deployer%22%7D')"
  frontend_duration="$(query 'probe_duration_seconds%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22frontend%22%7D')"
  backend_duration="$(query 'probe_duration_seconds%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22backend%22%7D')"
  deployer_duration="$(query 'probe_duration_seconds%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22deployer%22%7D')"
  total="$(query 'count%28up%29')"
  down="$(query 'up%3D%3D0')"
  targets="$(kubectl get --raw \
    '/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/targets?state=active')"
  blackbox_targets="$(jq '[.data.activeTargets[] | select(.discoveredLabels.__meta_kubernetes_service_name == "blackbox-exporter")]' <<< "$targets")"
  sm_count="$(kubectl get servicemonitor -n monitoring \
    -l app.kubernetes.io/instance=blackbox-exporter -o json | jq -r '.items | length')"

  if test "$(metric_value <<< "$frontend")" = '1' && \
     test "$(metric_value <<< "$backend")" = '1' && \
     test "$(metric_value <<< "$deployer")" = '1' && \
     test "$(metric_value <<< "$frontend_status")" = '200' && \
     test "$(metric_value <<< "$backend_status")" = '200' && \
     test "$(metric_value <<< "$deployer_status")" = '200' && \
     test "$(metric_value <<< "$total")" = '34' && \
     test "$(jq -r '.data.result | length' <<< "$down")" = '0' && \
     test "$sm_count" -eq 3 && \
     test "$(jq 'length' <<< "$blackbox_targets")" -eq 3 && \
     test "$(jq '[.[] | select(.health=="up" and .lastError=="")] | length' <<< "$blackbox_targets")" -eq 3 && \
     test "$(jq '[.[] | select(.scrapeUrl | contains("module=http_frontend"))] | length' <<< "$blackbox_targets")" -eq 1 && \
     test "$(jq '[.[] | select(.scrapeUrl | contains("module=http_json_ok"))] | length' <<< "$blackbox_targets")" -eq 2 && \
     test "$(jq '[.[] | select(.labels.service=="frontend" and .labels.target=="buet-paas-frontend")] | length' <<< "$blackbox_targets")" -eq 1 && \
     test "$(jq '[.[] | select(.labels.service=="backend" and .labels.target=="buet-paas-backend")] | length' <<< "$blackbox_targets")" -eq 1 && \
     test "$(jq '[.[] | select(.labels.service=="deployer" and .labels.target=="paas-deployer")] | length' <<< "$blackbox_targets")" -eq 1; then
    converged=true
    break
  fi
  sleep 10
done

if test "$converged" != true; then
  echo 'Three-target Prometheus state did not converge before timeout.' >&2
  jq -n \
    --arg frontend "$(metric_value <<< "$frontend")" \
    --arg backend "$(metric_value <<< "$backend")" \
    --arg deployer "$(metric_value <<< "$deployer")" \
    --arg total "$(metric_value <<< "$total")" \
    --arg down "$(jq -r '.data.result | length' <<< "$down")" \
    --arg sm_count "$sm_count" \
    --arg active "$(jq -r 'length' <<< "$blackbox_targets")" \
    '{frontend:$frontend,backend:$backend,deployer:$deployer,total:$total,down:$down,serviceMonitors:$sm_count,activeTargets:$active}' >&2
  exit 1
fi

test "$(helm history blackbox-exporter -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')" = "$expected_revision"
test "$(helm history monitoring-stack -n monitoring -o json | \
  jq -r 'map(select(.status=="deployed")) | last | .revision')" = '6'
kubectl get servicemonitor blackbox-exporter-buet-paas-frontend \
  -n monitoring >/dev/null
kubectl get servicemonitor blackbox-exporter-buet-paas-backend \
  -n monitoring >/dev/null
kubectl get servicemonitor blackbox-exporter-paas-deployer \
  -n monitoring >/dev/null
awk -v value="$(metric_value <<< "$frontend_duration")" \
  'BEGIN { exit !(value > 0 && value < 10) }'
awk -v value="$(metric_value <<< "$backend_duration")" \
  'BEGIN { exit !(value > 0 && value < 10) }'
awk -v value="$(metric_value <<< "$deployer_duration")" \
  'BEGIN { exit !(value > 0 && value < 10) }'

test "$(kubectl get deployment blackbox-exporter -n monitoring \
  -o jsonpath='{.spec.template.spec.containers[0].image}')" = \
  'quay.io/prometheus/blackbox-exporter:v0.28.0@sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc'
test "$(kubectl get pod -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter \
  -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')" = '0'
test "$(kubectl get nodes --no-headers | awk '$2=="Ready" {count++} END {print count+0}')" -eq 4
test "$(kubectl get pods -n monitoring --no-headers | awk '$3=="Running" {count++} END {print count+0}')" -eq 10
test "$(kubectl get pods -n monitoring -o json | jq '[.items[].status.containerStatuses[]?.restartCount] | add')" = '0'
test "$(metric_value <<< "$(query 'count%28up%7Bjob%3D%22standalone-node-exporters%22%7D%29')")" = '6'

frontend_body="$(curl --fail --silent --show-error --max-time 10 http://192.168.128.15/)"
grep -q 'BUET-PaaS' <<< "$frontend_body"
backend_body="$(curl --fail --silent --show-error --max-time 10 http://192.168.128.131:8020/health)"
grep -q '"status":"ok"' <<< "$backend_body"
deployer_body="$(kubectl get --raw \
  '/api/v1/namespaces/buet-paas-system-team23/services/http:paas-deployer:80/proxy/health')"
grep -q '"status":"ok"' <<< "$deployer_body"

echo 'SERVICEMONITORS'
kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter -o json | jq '[.items[] | {
  name:.metadata.name,
  module:.spec.endpoints[0].params.module[0],
  target:.spec.endpoints[0].params.target[0]
}] | sort_by(.name)'

echo 'PROBE_RESULTS'
jq -n \
  --arg frontend_success "$(metric_value <<< "$frontend")" \
  --arg frontend_status "$(metric_value <<< "$frontend_status")" \
  --arg frontend_duration "$(metric_value <<< "$frontend_duration")" \
  --arg backend_success "$(metric_value <<< "$backend")" \
  --arg backend_status "$(metric_value <<< "$backend_status")" \
  --arg backend_duration "$(metric_value <<< "$backend_duration")" \
  --arg deployer_success "$(metric_value <<< "$deployer")" \
  --arg deployer_status "$(metric_value <<< "$deployer_status")" \
  --arg deployer_duration "$(metric_value <<< "$deployer_duration")" \
  --arg total "$(metric_value <<< "$total")" \
  '{frontend:{success:$frontend_success,status:$frontend_status,duration:$frontend_duration},backend:{success:$backend_success,status:$backend_status,duration:$backend_duration},deployer:{success:$deployer_success,status:$deployer_status,duration:$deployer_duration},total_up:$total,down:0}'

echo 'PROMETHEUS_TARGETS'
jq '[.[] | {health,lastError,labels,scrapeUrl}]' <<< "$blackbox_targets"

echo 'REGRESSION'
kubectl get nodes --no-headers
kubectl get pods -n monitoring --no-headers
printf 'frontend_marker=BUET-PaaS backend_body=%s deployer_body=%s\n' \
  "$backend_body" "$deployer_body"

echo 'STEP15D4_VERIFY_SUCCESS'
