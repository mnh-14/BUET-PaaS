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

for encoded_query in \
  'probe_success%7Bservice%3D%22registry%22%7D' \
  'probe_http_status_code%7Bservice%3D%22registry%22%7D' \
  'probe_http_ssl%7Bservice%3D%22registry%22%7D' \
  'probe_ssl_earliest_cert_expiry%7Bservice%3D%22registry%22%7D'; do
  query "$encoded_query"
  echo
done
