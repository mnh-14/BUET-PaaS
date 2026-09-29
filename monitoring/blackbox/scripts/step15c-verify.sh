#!/usr/bin/env bash
set -euo pipefail

query() {
  kubectl get --raw \
    "/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=$1"
}

helm status blackbox-exporter -n monitoring
kubectl rollout status deployment/blackbox-exporter -n monitoring --timeout=3m

test "$(kubectl get deployment blackbox-exporter -n monitoring \
  -o jsonpath='{.spec.template.spec.containers[0].image}')" = \
  'quay.io/prometheus/blackbox-exporter:v0.28.0@sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc'
test "$(kubectl get service blackbox-exporter -n monitoring \
  -o jsonpath='{.spec.type}')" = 'ClusterIP'
test "$(kubectl get service blackbox-exporter -n monitoring \
  -o jsonpath='{.spec.ports[0].port}')" = '9115'
test "$(kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter --no-headers | wc -l)" -eq 1
test "$(kubectl get ingress -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter --no-headers 2>/dev/null | wc -l)" -eq 0

probe=''
for _ in $(seq 1 24); do
  probe="$(query 'probe_success%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22frontend%22%7D')"
  if test "$(jq -r '.data.result[0].value[1] // empty' <<< "$probe")" = '1'; then
    break
  fi
  sleep 10
done

test "$(jq -r '.data.result[0].value[1] // empty' <<< "$probe")" = '1'

status="$(query 'probe_http_status_code%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22frontend%22%7D')"
duration="$(query 'probe_duration_seconds%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22frontend%22%7D')"
protocol="$(query 'probe_ip_protocol%7Bdeployment_type%3D%22blackbox%22%2Cservice%3D%22frontend%22%7D')"
total="$(query 'count%28up%29')"
down="$(query 'up%3D%3D0')"

test "$(jq -r '.data.result[0].value[1]' <<< "$status")" = '200'
test "$(jq -r '.data.result[0].value[1]' <<< "$protocol")" = '4'
test "$(jq -r '.data.result[0].value[1]' <<< "$total")" = '32'
test "$(jq -r '.data.result | length' <<< "$down")" = '0'
awk -v value="$(jq -r '.data.result[0].value[1]' <<< "$duration")" \
  'BEGIN { exit !(value > 0 && value < 10) }'

targets="$(kubectl get --raw \
  '/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/targets?state=active')"
test "$(jq '[.data.activeTargets[] | select(.discoveredLabels.__meta_kubernetes_service_name == "blackbox-exporter")] | length' <<< "$targets")" -eq 1
test "$(jq -r '[.data.activeTargets[] | select(.discoveredLabels.__meta_kubernetes_service_name == "blackbox-exporter")][0].health' <<< "$targets")" = 'up'
test -z "$(jq -r '[.data.activeTargets[] | select(.discoveredLabels.__meta_kubernetes_service_name == "blackbox-exporter")][0].lastError' <<< "$targets")"

echo 'BLACKBOX_OBJECTS'
kubectl get deployment,service,servicemonitor,networkpolicy,configmap \
  -n monitoring | grep -E 'NAME|blackbox'

echo 'BLACKBOX_POD_SECURITY'
kubectl get deployment blackbox-exporter -n monitoring -o json | jq '{
  replicas: .spec.replicas,
  automountServiceAccountToken: .spec.template.spec.automountServiceAccountToken,
  image: .spec.template.spec.containers[0].image,
  resources: .spec.template.spec.containers[0].resources,
  securityContext: .spec.template.spec.containers[0].securityContext
}'

echo 'PROBE_RESULT'
jq -n \
  --arg success "$(jq -r '.data.result[0].value[1]' <<< "$probe")" \
  --arg status "$(jq -r '.data.result[0].value[1]' <<< "$status")" \
  --arg duration "$(jq -r '.data.result[0].value[1]' <<< "$duration")" \
  --arg protocol "$(jq -r '.data.result[0].value[1]' <<< "$protocol")" \
  --arg total "$(jq -r '.data.result[0].value[1]' <<< "$total")" \
  '{probe_success:$success,http_status:$status,duration_seconds:$duration,ip_protocol:$protocol,total_up:$total,down:0}'

echo 'PROMETHEUS_TARGET'
jq '[.data.activeTargets[] | select(.discoveredLabels.__meta_kubernetes_service_name == "blackbox-exporter") | {
  health,
  lastError,
  labels,
  scrapeUrl
}]' <<< "$targets"

echo 'STEP15C_VERIFY_SUCCESS'
