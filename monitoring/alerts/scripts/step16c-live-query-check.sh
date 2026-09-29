#!/usr/bin/env bash
set -euo pipefail

root="${1:?temporary workspace required}"
prom_path='/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query='

python3 - "$root/input/prometheus-rule.yaml" <<'PY' |
import sys
import yaml
rule = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
for group in rule["spec"]["groups"]:
    for item in group["rules"]:
        print(item["alert"] + "\t" + item["expr"].replace("\n", " "))
PY
while IFS=$'\t' read -r name expression; do
  encoded="$(jq -nr --arg expr "$expression" '$expr | @uri')"
  response="$(kubectl get --raw "${prom_path}${encoded}")"
  jq -e '.status == "success" and .data.resultType == "vector"' <<< "$response" >/dev/null
  count="$(jq '.data.result | length' <<< "$response")"
  printf '%s current_matches=%s\n' "$name" "$count"
  test "$count" -eq 0
done

test "$(kubectl get --raw "${prom_path}count%28up%29" | jq -r '.data.result[0].value[1]')" = '36'
test "$(kubectl get --raw "${prom_path}up%3D%3D0" | jq '.data.result | length')" -eq 0
if kubectl get prometheusrule buet-paas-mvp-alerts -n monitoring >/dev/null 2>&1; then
  echo 'Step 16C alert rule unexpectedly exists live.' >&2
  exit 1
fi
echo 'STEP16C_LIVE_QUERY_READONLY_SUCCESS'
