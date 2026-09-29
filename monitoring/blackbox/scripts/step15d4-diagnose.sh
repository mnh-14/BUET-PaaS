#!/usr/bin/env bash
set -u

query() {
  kubectl get --raw \
    "/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=$1"
}

echo 'HELM_HISTORY'
helm history blackbox-exporter -n monitoring

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
  jq '[.data.activeTargets[] | select(.discoveredLabels.__meta_kubernetes_service_name == "blackbox-exporter") | {health,lastError,labels,scrapeUrl}]'

echo 'RECENT_DEPLOYER_SUCCESS'
query 'max_over_time%28probe_success%7Bservice%3D%22deployer%22%7D%5B10m%5D%29'
echo

echo 'RECENT_DEPLOYER_STATUS'
query 'max_over_time%28probe_http_status_code%7Bservice%3D%22deployer%22%7D%5B10m%5D%29'
echo

echo 'DEPLOYER_SERVICE_PROXY'
kubectl get --raw \
  '/api/v1/namespaces/buet-paas-system-team23/services/http:paas-deployer:80/proxy/health' || true
echo
