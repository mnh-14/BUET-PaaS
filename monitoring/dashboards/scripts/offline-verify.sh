#!/usr/bin/env bash
set -euo pipefail

root="${1:-/tmp/buet-paas-step16a}"
input="$root/input"
output="$root/output"
dashboard="$input/buet-paas-overview.json"
rendered="$output/dashboard-configmap.yaml"
prom_image='quay.io/prometheus/prometheus@sha256:50c707e96da5ade383cb1707790576480485e93de06aa60ad8802cb5f744bd0a'

jq empty "$dashboard"
test "$(jq -r '.title' "$dashboard")" = 'BUET-PaaS Monitoring Overview'
test "$(jq -r '.uid' "$dashboard")" = 'buet-paas-overview'
test "$(jq -r '.schemaVersion' "$dashboard")" = '39'
test "$(jq -r '.version' "$dashboard")" = '1'
test "$(jq -r '.editable' "$dashboard")" = 'false'
test "$(jq -r '.refresh' "$dashboard")" = '30s'
test "$(jq -r '.time.from' "$dashboard")" = 'now-1h'
test "$(jq -r '.panels | length' "$dashboard")" -eq 16
test "$(jq '[.panels[].id] | unique | length' "$dashboard")" -eq 16
test "$(jq '[.panels[].title] | unique | length' "$dashboard")" -eq 16
test "$(jq '[.panels[] | select(.datasource.uid == "prometheus")] | length' "$dashboard")" -eq 16
test "$(jq '[.panels[].targets[] | select(.expr != null and .expr != "")] | length' "$dashboard")" -eq 16
test "$(jq '[.panels[].gridPos | select(.x >= 0 and .y >= 0 and .w > 0 and .h > 0 and (.x + .w) <= 24)] | length' "$dashboard")" -eq 16

for title in \
  'Prometheus Targets UP' \
  'Prometheus Targets DOWN' \
  'Kubernetes Nodes Ready' \
  'Standalone VMs UP' \
  'Service Probes UP' \
  'Firing Alerts' \
  'Service Availability' \
  'Service Probe Duration' \
  'Service HTTP Status' \
  'Kubernetes Pods by Phase' \
  'Unavailable Deployment Replicas' \
  'Top Container Restarts (1h)' \
  'Failed Kubernetes Jobs' \
  'Host CPU Utilization' \
  'Host Memory Utilization' \
  'Root Filesystem Free'; do
  test "$(jq --arg title "$title" '[.panels[] | select(.title == $title)] | length' "$dashboard")" -eq 1
done

for metric in \
  up ALERTS probe_success probe_duration_seconds probe_http_status_code \
  kube_node_status_condition kube_pod_status_phase \
  kube_deployment_status_replicas_unavailable \
  kube_pod_container_status_restarts_total kube_job_status_failed \
  node_cpu_seconds_total node_memory_MemAvailable_bytes \
  node_memory_MemTotal_bytes node_filesystem_avail_bytes \
  node_filesystem_size_bytes; do
  grep -q "$metric" "$dashboard"
done

if grep -R -E -i \
  'BEGIN ([A-Z]+ )?PRIVATE KEY|admin-password|bearer[[:space:]]+|authorization:|password[[:space:]]*[:=]|token[[:space:]]*[:=]' \
  "$dashboard" "$input/kustomization.yaml"; then
  echo 'secret-like material found in dashboard inputs' >&2
  exit 1
fi

kubectl kustomize "$input" > "$rendered"
test "$(grep -c '^kind: ConfigMap$' "$rendered")" -eq 1
test "$(grep -c '^kind: Secret$' "$rendered")" -eq 0
test "$(grep -c '^kind: Ingress$' "$rendered")" -eq 0
grep -q '^  name: grafana-dashboard-buet-paas-overview$' "$rendered"
grep -q '^  namespace: monitoring$' "$rendered"
grep -q '^    grafana_dashboard: "1"$' "$rendered"
grep -Eq '^  buet-paas-overview.json: \|(-)?$' "$rendered"

jq '{
  groups: [{
    name: "buet-paas-dashboard-offline-validation",
    rules: ([.panels[].targets[] | select(.expr != null and .expr != "") | .expr]
      | to_entries
      | map({record: ("buet_paas_dashboard_expr_" + (.key | tostring)), expr: .value}))
  }]
}' "$dashboard" > "$output/dashboard-promql-rules.json"

sudo docker run --rm \
  --entrypoint /bin/promtool \
  -v "$output:/work:ro" \
  "$prom_image" \
  check rules /work/dashboard-promql-rules.json

echo 'DASHBOARD_SUMMARY'
jq '{title,uid,schemaVersion,version,editable,refresh,panelCount:(.panels|length),panelTitles:[.panels[].title],expressions:[.panels[].targets[].expr]}' "$dashboard"
echo 'RENDERED_OBJECTS'
printf 'ConfigMaps=%s Secrets=%s Ingresses=%s\n' \
  "$(grep -c '^kind: ConfigMap$' "$rendered")" \
  "$(grep -c '^kind: Secret$' "$rendered")" \
  "$(grep -c '^kind: Ingress$' "$rendered")"
echo 'SHA-256'
sha256sum \
  "$dashboard" \
  "$input/kustomization.yaml" \
  "$output/dashboard-promql-rules.json" \
  "$rendered"
echo 'STEP16A_OFFLINE_VERIFY_SUCCESS'
