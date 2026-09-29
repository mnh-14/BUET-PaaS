#!/usr/bin/env bash
set -euo pipefail

root="${1:?temporary workspace required}"
input="$root/input"
output="$root/output"
dashboard="$input/buet-paas-overview.json"
rendered="$output/dashboard-configmap.yaml"
configmap='grafana-dashboard-buet-paas-overview'
grafana_uid='buet-paas-overview'
grafana_host='grafana.monitoring.192.168.64.121.sslip.io'
prom_path='/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query='
applied=false
port_forward_pid=''

rollback() {
  result=$?
  if test -n "$port_forward_pid"; then
    kill "$port_forward_pid" >/dev/null 2>&1 || true
    wait "$port_forward_pid" 2>/dev/null || true
  fi
  if test "$result" -ne 0 && test "$applied" = true; then
    echo 'Verification failed; removing only the new dashboard ConfigMap.' >&2
    kubectl delete configmap "$configmap" -n monitoring --wait=true >&2 || true
  fi
  exit "$result"
}
trap rollback EXIT

test "$(sha256sum "$dashboard" | cut -d' ' -f1)" = 'f16060fa9acc37c326db19371b5b34b47f31bdaf7d5984d1f88f19e6889b9af0'
test "$(sha256sum "$input/kustomization.yaml" | cut -d' ' -f1)" = 'f8ca3de482ca86c1c6401bb2b6e2e548d2273ba518274e27bd1e84eee95d199b'
test "$(helm status blackbox-exporter -n monitoring | awk '/^REVISION:/ {print $2}')" = '9'
test "$(helm status monitoring-stack -n monitoring | awk '/^REVISION:/ {print $2}')" = '6'
if kubectl get configmap "$configmap" -n monitoring >/dev/null 2>&1; then
  echo 'Dashboard ConfigMap already exists; stopping before mutation.' >&2
  exit 1
fi
test "$(kubectl get configmap -n monitoring -l grafana_dashboard=1 --no-headers | wc -l)" -eq 23
test "$(kubectl get --raw "${prom_path}count%28up%29" | jq -r '.data.result[0].value[1]')" = '36'
test "$(kubectl get --raw "${prom_path}up%3D%3D0" | jq '.data.result | length')" -eq 0

kubectl kustomize "$input" > "$rendered"
test "$(sha256sum "$rendered" | cut -d' ' -f1)" = '2ae7a898c6edcebc15801f42c868d5fce79cfe9cf00c083d390d203fc7af4f53'
test "$(grep -c '^kind: ConfigMap$' "$rendered")" -eq 1
test "$(grep -c '^kind: Secret$' "$rendered")" -eq 0
test "$(grep -c '^kind: Ingress$' "$rendered")" -eq 0
kubectl apply --dry-run=server -f "$rendered" >/dev/null

kubectl apply -f "$rendered"
applied=true
test "$(kubectl get configmap "$configmap" -n monitoring -o json | jq -r '.metadata.labels.grafana_dashboard')" = '1'
kubectl get configmap "$configmap" -n monitoring -o json | jq -e --argjson dashboard "$(cat "$dashboard")" '.data["buet-paas-overview.json"] | fromjson == $dashboard' >/dev/null

grafana_pod="$(kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana,app.kubernetes.io/instance=monitoring-stack -o jsonpath='{.items[0].metadata.name}')"
test -n "$grafana_pod"
for _ in $(seq 1 30); do
  if kubectl exec -n monitoring "$grafana_pod" -c grafana-sc-dashboard -- test -s '/tmp/dashboards/buet-paas-overview.json' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
kubectl exec -n monitoring "$grafana_pod" -c grafana-sc-dashboard -- test -s '/tmp/dashboards/buet-paas-overview.json'

admin_user="$(kubectl get secret monitoring-stack-grafana -n monitoring -o jsonpath='{.data.admin-user}' | base64 -d)"
admin_password="$(kubectl get secret monitoring-stack-grafana -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d)"
test -n "$admin_user"
test -n "$admin_password"
kubectl port-forward -n monitoring service/monitoring-stack-grafana 13080:80 > "$output/grafana-port-forward.log" 2>&1 &
port_forward_pid=$!
for _ in $(seq 1 30); do
  if curl --silent --fail --max-time 2 --header "Host: $grafana_host" http://127.0.0.1:13080/api/health > "$output/grafana-health.json"; then
    break
  fi
  sleep 1
done
test "$(jq -r '.database' "$output/grafana-health.json")" = 'ok'
reload_code="$(curl --silent --show-error --max-time 15 --output "$output/grafana-reload-response.json" --write-out '%{http_code}' --header "Host: $grafana_host" --user "$admin_user:$admin_password" --request POST 'http://127.0.0.1:13080/api/admin/provisioning/dashboards/reload')"
test "$reload_code" = '200'
provisioned=false
for _ in $(seq 1 30); do
  http_code="$(curl --silent --show-error --max-time 10 --output "$output/grafana-dashboard-response.json" --write-out '%{http_code}' --header "Host: $grafana_host" --user "$admin_user:$admin_password" "http://127.0.0.1:13080/api/dashboards/uid/$grafana_uid")"
  if test "$http_code" = '200' && jq -e '.dashboard.uid == "buet-paas-overview" and .dashboard.title == "BUET-PaaS Monitoring Overview" and (.dashboard.panels | length) == 16' "$output/grafana-dashboard-response.json" >/dev/null; then
    provisioned=true
    break
  fi
  sleep 2
done
test "$provisioned" = true
test "$(jq -r '.meta.provisioned' "$output/grafana-dashboard-response.json")" = 'true'
test "$(jq -r '.dashboard.panels | map(select(.datasource.uid == "prometheus")) | length' "$output/grafana-dashboard-response.json")" -eq 16

for index in $(seq 0 15); do
  title="$(jq -r ".panels[$index].title" "$dashboard")"
  expression="$(jq -r ".panels[$index].targets[0].expr" "$dashboard")"
  encoded="$(jq -nr --arg expr "$expression" '$expr | @uri')"
  response="$(kubectl get --raw "${prom_path}${encoded}")"
  if ! jq -e '.status == "success" and .data.resultType == "vector"' <<< "$response" >/dev/null; then
    echo "PromQL execution failed: panel $((index+1)) $title" >&2
    exit 1
  fi
  result_count="$(jq '.data.result | length' <<< "$response")"
  printf '%02d | %s | series=%s\n' "$((index+1))" "$title" "$result_count"
  case "$index" in
    0) test "$(jq -r '.data.result[0].value[1]' <<< "$response")" = '36' ;;
    1) test "$(jq -r '.data.result[0].value[1]' <<< "$response")" = '0' ;;
    2) test "$(jq -r '.data.result[0].value[1]' <<< "$response")" = '4' ;;
    3) test "$(jq -r '.data.result[0].value[1]' <<< "$response")" = '6' ;;
    4) test "$(jq -r '.data.result[0].value[1]' <<< "$response")" = '5' ;;
    6|7|8|13|14|15) test "$result_count" -gt 0 ;;
  esac
done

test "$(kubectl get configmap -n monitoring -l grafana_dashboard=1 --no-headers | wc -l)" -eq 24
test "$(kubectl get --raw "${prom_path}count%28up%29" | jq -r '.data.result[0].value[1]')" = '36'
test "$(kubectl get --raw "${prom_path}up%3D%3D0" | jq '.data.result | length')" -eq 0
test "$(kubectl get pods -n monitoring --no-headers | awk '$3=="Running" {count++} END {print count+0}')" -eq 10
test "$(kubectl get pods -n monitoring -o json | jq '[.items[].status.containerStatuses[]?.restartCount] | add')" = '0'
test "$(helm status blackbox-exporter -n monitoring | awk '/^REVISION:/ {print $2}')" = '9'
test "$(helm status monitoring-stack -n monitoring | awk '/^REVISION:/ {print $2}')" = '6'
echo 'STEP16B_APPLY_VERIFY_SUCCESS'
