#!/usr/bin/env bash
set -u

query() {
  kubectl get --raw \
    "/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=$1"
}

echo 'SERVICEMONITORS'
kubectl get servicemonitor -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter -o wide

echo 'TOTAL_UP'
query 'count%28up%29'
echo

echo 'DOWN'
query 'up%3D%3D0'
echo

echo 'BLACKBOX_ACTIVE'
kubectl get --raw \
  '/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/targets?state=active' | \
  jq '[.data.activeTargets[] | select(.discoveredLabels.__meta_kubernetes_service_name == "blackbox-exporter") | {health,lastError,scrapeUrl}]'

echo 'RECENT_BACKEND_SUCCESS'
query 'max_over_time%28probe_success%7Bservice%3D%22backend%22%7D%5B10m%5D%29'
echo

echo 'RECENT_BACKEND_STATUS'
query 'max_over_time%28probe_http_status_code%7Bservice%3D%22backend%22%7D%5B10m%5D%29'
echo

echo 'MANUAL_BACKEND_PROBE'
timeout 20 kubectl get --raw \
  '/api/v1/namespaces/monitoring/services/http:blackbox-exporter:9115/proxy/probe?module=http_json_ok&target=http%3A%2F%2F192.168.128.131%3A8020%2Fhealth&debug=true' || true
echo
