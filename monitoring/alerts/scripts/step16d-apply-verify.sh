#!/usr/bin/env bash
set -euo pipefail

root="${1:?temporary workspace required}"
input="$root/input"
output="$root/output"
manifest="$output/prometheus-rule-rendered.yaml"
rule_name='buet-paas-mvp-alerts'
rules_path='/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/rules?type=alert'
query_path='/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query='
applied=false

rollback() {
  result=$?
  if test "$result" -ne 0 && test "$applied" = true; then
    echo 'Step 16D verification failed; deleting only the new PrometheusRule.' >&2
    kubectl delete prometheusrule "$rule_name" -n monitoring --wait=true >&2 || true
  fi
  exit "$result"
}
trap rollback EXIT

test "$(sha256sum "$input/prometheus-rule.yaml" | cut -d' ' -f1)" = '1418ab588cce202a66b808d7634d355e2313b5e6ab4b2bf99fa99c37f10c6d5b'
test "$(sha256sum "$input/kustomization.yaml" | cut -d' ' -f1)" = '7ac4439140f27f9a3de938bf29e553bbb6d3a7118f57ebbac7d99339c2fb90a6'
test "$(helm status monitoring-stack -n monitoring | awk '/^REVISION:/ {print $2}')" = '6'
test "$(helm status blackbox-exporter -n monitoring | awk '/^REVISION:/ {print $2}')" = '9'
if kubectl get prometheusrule "$rule_name" -n monitoring >/dev/null 2>&1; then
  echo 'New PrometheusRule already exists; stopping before mutation.' >&2
  exit 1
fi
test "$(kubectl get prometheusrule -n monitoring --no-headers | wc -l)" -eq 30
test "$(kubectl get --raw "${query_path}count%28up%29" | jq -r '.data.result[0].value[1]')" = '36'
test "$(kubectl get --raw "${query_path}up%3D%3D0" | jq '.data.result | length')" -eq 0

kubectl kustomize "$input" > "$manifest"
test "$(sha256sum "$manifest" | cut -d' ' -f1)" = '13adcdb3ce53b2a116b62e97c3ef4794523cf59bc802b5a24cf70e1cc202ee42'
test "$(grep -c '^kind: PrometheusRule$' "$manifest")" -eq 1
test "$(grep -c '^kind: Secret$' "$manifest")" -eq 0
test "$(grep -c '^kind: ConfigMap$' "$manifest")" -eq 0
kubectl apply --dry-run=server -f "$manifest" >/dev/null

kubectl apply -f "$manifest"
applied=true
test "$(kubectl get prometheusrule "$rule_name" -n monitoring -o json | jq -r '.metadata.labels.release')" = 'monitoring-stack'
test "$(kubectl get prometheusrule "$rule_name" -n monitoring -o json | jq '[.spec.groups[].rules[]] | length')" -eq 4

converged=false
for _ in $(seq 1 30); do
  rules="$(kubectl get --raw "$rules_path")"
  group_count="$(jq '[.data.groups[] | select(.name | startswith("buet-paas.mvp."))] | length' <<< "$rules")"
  alert_count="$(jq '[.data.groups[] | select(.name | startswith("buet-paas.mvp.")) | .rules[]] | length' <<< "$rules")"
  healthy_count="$(jq '[.data.groups[] | select(.name | startswith("buet-paas.mvp.")) | .rules[] | select(.health == "ok" and .state == "inactive" and ((.alerts | length) == 0) and (.lastEvaluation != null))] | length' <<< "$rules")"
  if test "$group_count" -eq 2 && test "$alert_count" -eq 4 && test "$healthy_count" -eq 4; then
    converged=true
    break
  fi
  sleep 5
done
if test "$converged" != true; then
  printf 'Rule convergence failed: groups=%s alerts=%s healthy=%s\n' "$group_count" "$alert_count" "$healthy_count" >&2
  exit 1
fi

jq '[.data.groups[] | select(.name | startswith("buet-paas.mvp.")) | {group:.name,rules:[.rules[] | {name,state,health,lastEvaluation,alerts:(.alerts|length)}]}]' <<< "$rules"
for name in \
  BUETPaaSServiceProbeFailed \
  BUETPaaSServiceProbeTargetMissing \
  BUETPaaSStandaloneVMTargetMissing \
  BUETPaaSStandaloneVMRootDiskLow; do
  test "$(jq --arg name "$name" '[.data.groups[] | select(.name | startswith("buet-paas.mvp.")) | .rules[] | select(.name == $name)] | length' <<< "$rules")" -eq 1
done

alerts="$(kubectl get --raw '/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/alerts')"
test "$(jq '[.data.alerts[] | select(.labels.alertname | startswith("BUETPaaS"))] | length' <<< "$alerts")" -eq 0
test "$(kubectl get prometheusrule -n monitoring --no-headers | wc -l)" -eq 31
test "$(kubectl get --raw "${query_path}count%28up%29" | jq -r '.data.result[0].value[1]')" = '36'
test "$(kubectl get --raw "${query_path}up%3D%3D0" | jq '.data.result | length')" -eq 0
test "$(kubectl get pods -n monitoring --no-headers | awk '$3=="Running" {count++} END {print count+0}')" -eq 10
test "$(kubectl get pods -n monitoring -o json | jq '[.items[].status.containerStatuses[]?.restartCount] | add')" = '0'
test "$(helm status monitoring-stack -n monitoring | awk '/^REVISION:/ {print $2}')" = '6'
test "$(helm status blackbox-exporter -n monitoring | awk '/^REVISION:/ {print $2}')" = '9'
echo 'STEP16D_APPLY_VERIFY_SUCCESS'
