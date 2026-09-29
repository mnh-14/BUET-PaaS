#!/usr/bin/env bash
set -euo pipefail

echo 'HELM_HISTORY'
helm history blackbox-exporter -n monitoring

echo 'FRONTEND_ONLY_SERVICEMONITOR'
kubectl get servicemonitor \
  -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter \
  -o json | jq '{count:(.items|length), monitors:[.items[] | {
    name:.metadata.name,
    release:.metadata.labels.release,
    module:.spec.endpoints[0].params.module,
    target:.spec.endpoints[0].params.target
  }]}'

test "$(kubectl get servicemonitor \
  -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter \
  -o json | jq -r '.items | length')" -eq 1
test "$(kubectl get servicemonitor blackbox-exporter-buet-paas-frontend \
  -n monitoring -o json | jq -r '.spec.endpoints[0].params.target[0]')" = \
  'http://192.168.128.15/'

echo 'LIVE_MODULES'
modules="$(kubectl get configmap blackbox-exporter -n monitoring \
  -o json | jq -r '.data["blackbox.yaml"]')"
grep '^  http_[a-z_]*:$' <<< "$modules"
test "$(grep -c '^  http_[a-z_]*:$' <<< "$modules")" -eq 4
if grep -q '^  http_2xx:$' <<< "$modules"; then
  exit 1
fi

echo 'LIVE_CA_HASH'
kubectl get configmap blackbox-harbor-ca -n monitoring \
  -o json | jq -j '.data["harbor-ca.crt"]' | sha256sum

echo 'NETWORK_POLICY_SPEC'
kubectl get networkpolicy blackbox-exporter-prometheus-only \
  -n monitoring -o json | jq '.spec'

echo 'POD_IMAGE_ID_AND_MOUNT'
kubectl get pod -n monitoring \
  -l app.kubernetes.io/instance=blackbox-exporter \
  -o json | jq '{pods:[.items[] | {
    name:.metadata.name,
    ready:.status.containerStatuses[0].ready,
    restarts:.status.containerStatuses[0].restartCount,
    imageID:.status.containerStatuses[0].imageID,
    caMount:[.spec.containers[0].volumeMounts[] | select(.mountPath=="/etc/blackbox/certs")]
  }]}'

echo 'BLACKBOX_LOG_ERRORS'
if kubectl logs deployment/blackbox-exporter -n monitoring --tail=100 | \
  grep -E -i 'level=(error|fatal)|panic'; then
  exit 1
else
  echo none
fi

echo 'CLUSTER_REGRESSION'
kubectl get nodes --no-headers
kubectl get pods -n monitoring --no-headers

echo 'STANDALONE_EXPORTERS_UP'
kubectl get --raw \
  '/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query=count%28up%7Bjob%3D%22standalone-node-exporters%22%7D%29'
echo

echo 'FRONTEND_DIRECT'
curl --fail --silent --show-error --max-time 10 http://192.168.128.15/ | \
  grep -o -m1 'BUET-PaaS'

echo 'STEP15C_POSTCHECK_SUCCESS'
