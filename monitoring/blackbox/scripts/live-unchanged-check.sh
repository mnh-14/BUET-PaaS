#!/usr/bin/env bash
set -euo pipefail

echo 'HELM_HISTORY'
helm history monitoring-stack -n monitoring | tail -n 2

echo 'BLACKBOX_LIVE_RESOURCES'
kubectl get \
  all,servicemonitor,networkpolicy,configmap \
  -n monitoring -o name | grep -i blackbox || true

echo 'NODES'
kubectl get nodes --no-headers

echo 'MONITORING_PODS'
kubectl get pods -n monitoring --no-headers

echo 'PROM_COUNT_UP'
kubectl get --raw \
  '/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=count%28up%29'
echo

echo 'PROM_DOWN'
kubectl get --raw \
  '/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=up%3D%3D0'
echo
