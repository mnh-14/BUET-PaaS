#!/usr/bin/env bash
set -euo pipefail

root="${1:-/tmp/buet-paas-step15b}"
input="$root/input"
output="$root/output"
chart="$output/prometheus-blackbox-exporter"

helm lint "$chart" \
  -f "$input/values.yaml" \
  -f "$input/targets-frontend.yaml" \
  --kube-version 1.36.2
helm template blackbox-exporter "$chart" \
  --namespace monitoring \
  -f "$input/values.yaml" \
  -f "$input/targets-frontend.yaml" \
  --kube-version 1.36.2 > "$output/frontend-rendered.yaml"

helm lint "$chart" \
  -f "$input/values.yaml" \
  -f "$input/targets-frontend-backend.yaml" \
  --kube-version 1.36.2
helm template blackbox-exporter "$chart" \
  --namespace monitoring \
  -f "$input/values.yaml" \
  -f "$input/targets-frontend-backend.yaml" \
  --kube-version 1.36.2 > "$output/frontend-backend-rendered.yaml"

helm lint "$chart" \
  -f "$input/values.yaml" \
  -f "$input/targets-frontend-backend-deployer.yaml" \
  --kube-version 1.36.2
helm template blackbox-exporter "$chart" \
  --namespace monitoring \
  -f "$input/values.yaml" \
  -f "$input/targets-frontend-backend-deployer.yaml" \
  --kube-version 1.36.2 > "$output/frontend-backend-deployer-rendered.yaml"

helm lint "$chart" \
  -f "$input/values.yaml" \
  -f "$input/targets-frontend-backend-deployer-harbor.yaml" \
  --kube-version 1.36.2
helm template blackbox-exporter "$chart" \
  --namespace monitoring \
  -f "$input/values.yaml" \
  -f "$input/targets-frontend-backend-deployer-harbor.yaml" \
  --kube-version 1.36.2 > "$output/frontend-backend-deployer-harbor-rendered.yaml"

helm lint "$chart" \
  -f "$input/values.yaml" \
  -f "$input/targets-all.yaml" \
  --kube-version 1.36.2
helm template blackbox-exporter "$chart" \
  --namespace monitoring \
  -f "$input/values.yaml" \
  -f "$input/targets-all.yaml" \
  --kube-version 1.36.2 > "$output/all-rendered.yaml"

kubectl kustomize "$input" > "$output/platform-rendered.yaml"

awk '
  found {
    if ($0 == "---") exit
    sub(/^    /, "")
    print
  }
  /^  blackbox.yaml: \|$/ { found=1 }
' "$output/all-rendered.yaml" > "$output/blackbox.yaml"

test "$(grep -c '^kind: ServiceMonitor$' "$output/frontend-rendered.yaml")" -eq 1
test "$(grep -c '^kind: ServiceMonitor$' "$output/frontend-backend-rendered.yaml")" -eq 2
test "$(grep -c '^kind: ServiceMonitor$' "$output/frontend-backend-deployer-rendered.yaml")" -eq 3
test "$(grep -c '^kind: ServiceMonitor$' "$output/frontend-backend-deployer-harbor-rendered.yaml")" -eq 4
test "$(grep -c '^kind: ServiceMonitor$' "$output/all-rendered.yaml")" -eq 5
test "$(grep -c '^    relabelings:$' "$output/frontend-rendered.yaml")" -eq 1
test "$(grep -c '^    relabelings:$' "$output/frontend-backend-rendered.yaml")" -eq 2
test "$(grep -c '^    relabelings:$' "$output/frontend-backend-deployer-rendered.yaml")" -eq 3
test "$(grep -c '^    relabelings:$' "$output/frontend-backend-deployer-harbor-rendered.yaml")" -eq 4
test "$(grep -c '^    relabelings:$' "$output/all-rendered.yaml")" -eq 5
test "$(grep -c '^kind: Ingress$' "$output/all-rendered.yaml")" -eq 0
test "$(grep -c '^kind: NetworkPolicy$' "$output/platform-rendered.yaml")" -eq 1
test "$(grep -c '^kind: ConfigMap$' "$output/platform-rendered.yaml")" -eq 1

grep -q '^  type: ClusterIP$' "$output/all-rendered.yaml"
grep -q '^      automountServiceAccountToken: false$' "$output/all-rendered.yaml"
grep -q '^          allowPrivilegeEscalation: false$' "$output/all-rendered.yaml"
grep -q '^          readOnlyRootFilesystem: true$' "$output/all-rendered.yaml"
grep -q '^          runAsNonRoot: true$' "$output/all-rendered.yaml"
grep -q '^            - ALL$' "$output/all-rendered.yaml"
grep -q '^        image: quay.io/prometheus/blackbox-exporter:v0.28.0@sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc$' "$output/all-rendered.yaml"
grep -q '^        ca_file: /etc/blackbox/certs/harbor-ca.crt$' "$output/blackbox.yaml"
grep -q '^        insecure_skip_verify: false$' "$output/blackbox.yaml"

test "$(grep -c '^  http_[a-z_]*:$' "$output/blackbox.yaml")" -eq 4
if grep -q '^  http_2xx:$' "$output/blackbox.yaml"; then
  echo 'unexpected generic http_2xx module' >&2
  exit 1
fi
if grep -R -E 'BEGIN ([A-Z]+ )?PRIVATE KEY' "$input" "$output/blackbox.yaml"; then
  echo 'private key material found' >&2
  exit 1
fi

grep -q '^  name: blackbox-exporter-buet-paas-frontend$' "$output/frontend-backend-rendered.yaml"
grep -q '^  name: blackbox-exporter-buet-paas-backend$' "$output/frontend-backend-rendered.yaml"
grep -q '^      - http://192.168.128.15/$' "$output/frontend-backend-rendered.yaml"
grep -q '^      - http://192.168.128.131:8020/health$' "$output/frontend-backend-rendered.yaml"
if grep -q -E '^  name: blackbox-exporter-(paas-deployer|harbor|sonarqube)$' \
  "$output/frontend-backend-rendered.yaml"; then
  echo 'unexpected later-stage target in frontend-backend render' >&2
  exit 1
fi

grep -q '^  name: blackbox-exporter-buet-paas-frontend$' "$output/frontend-backend-deployer-rendered.yaml"
grep -q '^  name: blackbox-exporter-buet-paas-backend$' "$output/frontend-backend-deployer-rendered.yaml"
grep -q '^  name: blackbox-exporter-paas-deployer$' "$output/frontend-backend-deployer-rendered.yaml"
grep -q '^      - http://192.168.128.15/$' "$output/frontend-backend-deployer-rendered.yaml"
grep -q '^      - http://192.168.128.131:8020/health$' "$output/frontend-backend-deployer-rendered.yaml"
grep -q '^      - http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health$' \
  "$output/frontend-backend-deployer-rendered.yaml"
test "$(grep -c '^      - http_json_ok$' "$output/frontend-backend-deployer-rendered.yaml")" -eq 2
if grep -q -E '^  name: blackbox-exporter-(harbor|sonarqube)$' \
  "$output/frontend-backend-deployer-rendered.yaml"; then
  echo 'unexpected later-stage target in frontend-backend-deployer render' >&2
  exit 1
fi

grep -q '^  name: blackbox-exporter-buet-paas-frontend$' "$output/frontend-backend-deployer-harbor-rendered.yaml"
grep -q '^  name: blackbox-exporter-buet-paas-backend$' "$output/frontend-backend-deployer-harbor-rendered.yaml"
grep -q '^  name: blackbox-exporter-paas-deployer$' "$output/frontend-backend-deployer-harbor-rendered.yaml"
grep -q '^  name: blackbox-exporter-harbor$' "$output/frontend-backend-deployer-harbor-rendered.yaml"
grep -q '^      - http://192.168.128.15/$' "$output/frontend-backend-deployer-harbor-rendered.yaml"
grep -q '^      - http://192.168.128.131:8020/health$' "$output/frontend-backend-deployer-harbor-rendered.yaml"
grep -q '^      - http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health$' \
  "$output/frontend-backend-deployer-harbor-rendered.yaml"
grep -q '^      - https://192.168.128.152/api/v2.0/health$' \
  "$output/frontend-backend-deployer-harbor-rendered.yaml"
test "$(grep -c '^      - http_frontend$' "$output/frontend-backend-deployer-harbor-rendered.yaml")" -eq 1
test "$(grep -c '^      - http_json_ok$' "$output/frontend-backend-deployer-harbor-rendered.yaml")" -eq 2
test "$(grep -c '^      - http_harbor_tls$' "$output/frontend-backend-deployer-harbor-rendered.yaml")" -eq 1
if grep -q '^  name: blackbox-exporter-sonarqube$' \
  "$output/frontend-backend-deployer-harbor-rendered.yaml"; then
  echo 'unexpected SonarQube target in frontend-backend-deployer-harbor render' >&2
  exit 1
fi

grep -q '^  name: blackbox-exporter-buet-paas-frontend$' "$output/all-rendered.yaml"
grep -q '^  name: blackbox-exporter-buet-paas-backend$' "$output/all-rendered.yaml"
grep -q '^  name: blackbox-exporter-paas-deployer$' "$output/all-rendered.yaml"
grep -q '^  name: blackbox-exporter-harbor$' "$output/all-rendered.yaml"
grep -q '^  name: blackbox-exporter-sonarqube$' "$output/all-rendered.yaml"
grep -q '^      - http://192.168.128.15/$' "$output/all-rendered.yaml"
grep -q '^      - http://192.168.128.131:8020/health$' "$output/all-rendered.yaml"
grep -q '^      - http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health$' \
  "$output/all-rendered.yaml"
grep -q '^      - https://192.168.128.152/api/v2.0/health$' "$output/all-rendered.yaml"
grep -q '^      - http://192.168.128.33:9000/api/system/status$' "$output/all-rendered.yaml"
test "$(grep -c '^      - http_frontend$' "$output/all-rendered.yaml")" -eq 1
test "$(grep -c '^      - http_json_ok$' "$output/all-rendered.yaml")" -eq 2
test "$(grep -c '^      - http_harbor_tls$' "$output/all-rendered.yaml")" -eq 1
test "$(grep -c '^      - http_sonarqube_up$' "$output/all-rendered.yaml")" -eq 1
test "$(grep -c '^        replacement: "code-quality"$' "$output/all-rendered.yaml")" -eq 1
test "$(grep -c '^      - replacement: code-quality$' "$output/all-rendered.yaml")" -eq 1
test "$(grep -c '^        replacement: sonarqube$' "$output/all-rendered.yaml")" -eq 1
test "$(grep -c '^      - replacement: sonarqube$' "$output/all-rendered.yaml")" -eq 1
test "$(grep -c '^        replacement: http://192.168.128.33:9000/api/system/status$' \
  "$output/all-rendered.yaml")" -eq 1
test "$(grep -c '^      - replacement: http://192.168.128.33:9000/api/system/status$' \
  "$output/all-rendered.yaml")" -eq 1

sudo docker run --rm \
  -v "$output/blackbox.yaml:/config/blackbox.yaml:ro" \
  -v "$input/harbor-ca.crt:/etc/blackbox/certs/harbor-ca.crt:ro" \
  quay.io/prometheus/blackbox-exporter@sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc \
  --config.file=/config/blackbox.yaml \
  --config.check

echo 'Rendered object counts:'
printf 'frontend ServiceMonitors=%s\n' "$(grep -c '^kind: ServiceMonitor$' "$output/frontend-rendered.yaml")"
printf 'frontend-backend ServiceMonitors=%s\n' "$(grep -c '^kind: ServiceMonitor$' "$output/frontend-backend-rendered.yaml")"
printf 'frontend-backend-deployer ServiceMonitors=%s\n' \
  "$(grep -c '^kind: ServiceMonitor$' "$output/frontend-backend-deployer-rendered.yaml")"
printf 'frontend-backend-deployer-harbor ServiceMonitors=%s\n' \
  "$(grep -c '^kind: ServiceMonitor$' "$output/frontend-backend-deployer-harbor-rendered.yaml")"
printf 'all-target ServiceMonitors=%s\n' "$(grep -c '^kind: ServiceMonitor$' "$output/all-rendered.yaml")"
printf 'Ingresses=%s NetworkPolicies=%s CA ConfigMaps=%s\n' \
  "$(grep -c '^kind: Ingress$' "$output/all-rendered.yaml")" \
  "$(grep -c '^kind: NetworkPolicy$' "$output/platform-rendered.yaml")" \
  "$(grep -c '^kind: ConfigMap$' "$output/platform-rendered.yaml")"

echo 'Rendered module names:'
grep '^  http_[a-z_]*:$' "$output/blackbox.yaml"

echo 'SHA-256:'
sha256sum \
  "$input/harbor-ca.crt" \
  "$input/kustomization.yaml" \
  "$input/network-policy.yaml" \
  "$input/values.yaml" \
  "$input/targets-frontend.yaml" \
  "$input/targets-frontend-backend.yaml" \
  "$input/targets-frontend-backend-deployer.yaml" \
  "$input/targets-frontend-backend-deployer-harbor.yaml" \
  "$input/targets-all.yaml" \
  "$output/blackbox.yaml" \
  "$output/frontend-rendered.yaml" \
  "$output/frontend-backend-rendered.yaml" \
  "$output/frontend-backend-deployer-rendered.yaml" \
  "$output/frontend-backend-deployer-harbor-rendered.yaml" \
  "$output/all-rendered.yaml" \
  "$output/platform-rendered.yaml"
