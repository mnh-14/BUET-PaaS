#!/usr/bin/env bash
set -euo pipefail

root="${1:?temporary workspace required}"
input="$root/input"
output="$root/output"
prom_image='quay.io/prometheus/prometheus@sha256:50c707e96da5ade383cb1707790576480485e93de06aa60ad8802cb5f744bd0a'

python3 - "$input/prometheus-rule.yaml" "$output/prometheus-rules.yaml" <<'PY'
import sys
import yaml
source = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
with open(sys.argv[2], "w", encoding="utf-8") as target:
    yaml.safe_dump({"groups": source["spec"]["groups"]}, target, sort_keys=False)
PY
cp "$input/step16d-rule-test.yaml" "$output/step16d-rule-test.yaml"
sudo docker run --rm \
  --entrypoint /bin/promtool \
  -v "$output:/work:ro" \
  "$prom_image" \
  test rules /work/step16d-rule-test.yaml
echo STEP16D_SYNTHETIC_TEST_SUCCESS
