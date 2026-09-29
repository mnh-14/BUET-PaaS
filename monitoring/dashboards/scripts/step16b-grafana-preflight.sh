#!/usr/bin/env bash
set -euo pipefail

root="${1:?temporary workspace required}"
output="$root/output"
host='grafana.monitoring.192.168.64.121.sslip.io'
admin_user="$(kubectl get secret monitoring-stack-grafana -n monitoring -o jsonpath='{.data.admin-user}' | base64 -d)"
admin_password="$(kubectl get secret monitoring-stack-grafana -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d)"
test -n "$admin_user"
test -n "$admin_password"
kubectl port-forward -n monitoring service/monitoring-stack-grafana 13081:80 > "$output/grafana-preflight-port-forward.log" 2>&1 &
pid=$!
trap 'kill "$pid" >/dev/null 2>&1 || true; wait "$pid" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  if curl --silent --fail --max-time 2 --header "Host: $host" http://127.0.0.1:13081/api/health > "$output/grafana-preflight-health.json"; then
    break
  fi
  sleep 1
done
test "$(jq -r '.database' "$output/grafana-preflight-health.json")" = 'ok'
code="$(curl --silent --show-error --max-time 10 --output "$output/grafana-preflight-search.json" --write-out '%{http_code}' --header "Host: $host" --user "$admin_user:$admin_password" 'http://127.0.0.1:13081/api/search?query=Prometheus')"
printf 'HOST_HEADER_API_STATUS=%s\n' "$code"
if test "$code" = '200' && jq -e 'type == "array"' "$output/grafana-preflight-search.json" >/dev/null; then
  echo HOST_HEADER_API_VERIFIED
else
  head -c 200 "$output/grafana-preflight-search.json"
  echo
  exit 1
fi
