#!/usr/bin/env python3
"""Check one staged PrometheusRule and extract the exact rules for promtool."""

import json
import re
import sys
from pathlib import Path

import yaml


def require(condition, message):
    if not condition:
        raise SystemExit(message)


root = Path(sys.argv[1])
source = root / "input" / "prometheus-rule.yaml"
rendered = root / "output" / "prometheus-rule-rendered.yaml"
native = root / "output" / "prometheus-rules.yaml"
source_text = source.read_text(encoding="utf-8")
require(
    not re.search(
        r"BEGIN (?:[A-Z]+ )?PRIVATE KEY|admin-password|"
        r"bearer\s+|authorization:|password\s*[:=]|token\s*[:=]",
        source_text,
        re.IGNORECASE,
    ),
    "secret-like material found in PrometheusRule",
)
rule = yaml.safe_load(source_text)
rendered_rule = yaml.safe_load(rendered.read_text(encoding="utf-8"))
require(rule == rendered_rule, "Kustomize render changed the reviewed PrometheusRule")
require(rule["apiVersion"] == "monitoring.coreos.com/v1", "unexpected API version")
require(rule["kind"] == "PrometheusRule", "unexpected object kind")
metadata = rule["metadata"]
require(metadata["name"] == "buet-paas-mvp-alerts", "unexpected rule name")
require(metadata["namespace"] == "monitoring", "unexpected namespace")
require(metadata["labels"]["release"] == "monitoring-stack", "Prometheus selector label missing")
groups = rule["spec"]["groups"]
require(len(groups) == 2, "expected two rule groups")
rules = [item for group in groups for item in group["rules"]]
expected = {
    "BUETPaaSServiceProbeFailed": "5m",
    "BUETPaaSServiceProbeTargetMissing": "10m",
    "BUETPaaSStandaloneVMTargetMissing": "10m",
    "BUETPaaSStandaloneVMRootDiskLow": "15m",
}
require(len(rules) == len(expected), "unexpected alert count")
require({item["alert"] for item in rules} == set(expected), "unexpected alert names")
for item in rules:
    require(item["for"] == expected[item["alert"]], "unexpected alert duration")
    require(item["labels"]["team"] == "buet-paas-operators", "team label missing")
    require(item["labels"]["severity"] in ("warning", "critical"), "severity missing")
    require(item["annotations"].get("summary"), "alert summary missing")
    require(item["annotations"].get("description"), "alert description missing")

expressions = {item["alert"]: item["expr"] for item in rules}
require('probe_success{deployment_type="blackbox"} == 0' == expressions["BUETPaaSServiceProbeFailed"], "probe failure query changed")
require('count(probe_success{deployment_type="blackbox"}) < 5' == expressions["BUETPaaSServiceProbeTargetMissing"], "probe count changed")
require('count(up{job="standalone-node-exporters"}) < 6' == expressions["BUETPaaSStandaloneVMTargetMissing"], "VM count changed")
require("node_filesystem_avail_bytes" in expressions["BUETPaaSStandaloneVMRootDiskLow"], "disk metric missing")
require("node_filesystem_readonly" in expressions["BUETPaaSStandaloneVMRootDiskLow"], "read-only guard missing")

native.write_text(yaml.safe_dump({"groups": groups}, sort_keys=False), encoding="utf-8")
print(json.dumps({"object": metadata["name"], "groups": len(groups), "alerts": [item["alert"] for item in rules], "selector": metadata["labels"]["release"]}, indent=2))
