# Step 16A - Prepare and offline verify the BUET-PaaS Monitoring Overview dashboard

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 16A - prepare and offline verify the BUET-PaaS Monitoring Overview dashboard as code`
- Result: **complete**
- Live Kubernetes/Grafana mutation: **none**
- Next permission boundary: Step 16B live apply and verification

## Prepared dashboard

The repository now contains a provisioned Grafana dashboard with stable UID
`buet-paas-overview`, schema version 39, a 30-second refresh, and a one-hour
default time range. All 16 panels use the existing Prometheus datasource UID
`prometheus`:

1. Prometheus Targets UP
2. Prometheus Targets DOWN
3. Kubernetes Nodes Ready
4. Standalone VMs UP
5. Service Probes UP
6. Firing Alerts
7. Service Availability
8. Service Probe Duration
9. Service HTTP Status
10. Kubernetes Pods by Phase
11. Unavailable Deployment Replicas
12. Top Container Restarts (1h)
13. Failed Kubernetes Jobs
14. Host CPU Utilization
15. Host Memory Utilization
16. Root Filesystem Free

The dashboard is intentionally operator/admin focused. It does not expose
project-scoped metrics to normal BUET-PaaS users and contains no credentials.

## Provisioning design

`monitoring/dashboards/kustomization.yaml` deterministically generates one
ConfigMap named `grafana-dashboard-buet-paas-overview` in namespace
`monitoring`. The label `grafana_dashboard: "1"` matches the live Grafana
sidecar selector. Name suffix hashing is disabled so later updates are
auditable and predictable.

## Offline verification

The local JSON parser confirmed:

```text
title:                        BUET-PaaS Monitoring Overview
uid:                          buet-paas-overview
schemaVersion:                39
version:                      1
panels:                       16
unique panel IDs:             16
unique panel titles:          16
Prometheus datasource panels: 16
```

The isolated verifier then confirmed:

```text
JSON structure and required metadata: passed
panel/grid/datasource assertions:      passed
required metric references:           passed
deployable-input secret scan:          passed
kubectl kustomize render:              passed
rendered ConfigMaps:                   1
rendered Secrets:                      0
rendered Ingresses:                    0
promtool check rules:                  SUCCESS, 16 rules found
```

PromQL was parsed by the exact immutable Prometheus image already running in
the cluster:

```text
quay.io/prometheus/prometheus:v3.14.0-distroless
sha256:50c707e96da5ade383cb1707790576480485e93de06aa60ad8802cb5f744bd0a
```

Generated validation artifact hashes:

```text
dashboard-promql-rules.json  665be52b693c440d314c335e5d93a9c5711bf66f76bf9b110380e5b8859652e5
dashboard-configmap.yaml      2ae7a898c6edcebc15801f42c868d5fce79cfe9cf00c083d390d203fc7af4f53
```

Two verifier-only defects were found and corrected before success: malformed
threshold-object closures in the initial JSON, and an assertion that accepted
only Kustomize's `|-` literal style instead of its actual `|` output. A secret
scan was also narrowed to deployable inputs so its own detection pattern could
not self-match. No defective artifact reached the cluster.

## Repository file hashes

```text
buet-paas-overview.json  f16060fa9acc37c326db19371b5b34b47f31bdaf7d5984d1f88f19e6889b9af0
kustomization.yaml       f8ca3de482ca86c1c6401bb2b6e2e548d2273ba518274e27bd1e84eee95d199b
offline-verify.sh        f55336d2a7b460c7326b1684039c0fbe7aed81c819fb86916051e7fde5089fdb
```

## Live unchanged evidence

The final read-only regression check proved:

```text
Blackbox Helm revision:              9
kube-prometheus-stack revision:      6
custom dashboard ConfigMap present:  no
existing provisioned dashboard maps: 23
Prometheus targets UP:               36
Prometheus targets DOWN:             0
monitoring Pods:                     10 Running
monitoring container restarts:       0
```

Therefore Step 16A did not apply the dashboard or modify Grafana, Prometheus,
Alertmanager, ingress, DNS, OpenStack, Secrets, or application workloads.

## Cleanup

The exact `/tmp/buet-paas-step16a` validation tree was enumerated and removed.
The unused Prometheus validator image pulled into the `k3s-user` Docker cache
was removed after confirming that no container used it. Live Kubernetes images
were not touched.

## Next approval

Step 16B will render the reviewed ConfigMap again, apply only that ConfigMap,
wait for Grafana's sidecar to provision the dashboard, validate all 16 queries
against the live Prometheus API, and verify the dashboard through Grafana. It
will not add alert rules or notification receivers.

```text
Approve Step 16B - atomically apply and verify the BUET-PaaS Monitoring Overview dashboard
```
