# Step 16B - Apply and verify the BUET-PaaS Monitoring Overview dashboard

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 16B - atomically apply and verify the BUET-PaaS Monitoring Overview dashboard`
- Result: **complete**
- Live change: one Grafana dashboard ConfigMap
- Rollback: triggered on first failed verification, then not triggered on successful retry

## Preflight

The approved Step 16A dashboard JSON and Kustomization SHA-256 values matched
exactly. Blackbox Helm revision 9 and kube-prometheus-stack revision 6 were
unchanged; the dashboard ConfigMap was absent, 23 provisioned dashboard
ConfigMaps existed, Prometheus had 36 UP and zero DOWN targets, and all ten
monitoring Pods were Running with zero restarts.

Kustomize rendered exactly one ConfigMap. Its SHA-256 matched the Step 16A
reviewed render:

```text
2ae7a898c6edcebc15801f42c868d5fce79cfe9cf00c083d390d203fc7af4f53
```

The exact manifest passed `kubectl apply --dry-run=server` before the live
apply.

## Transaction and verification

The ConfigMap `monitoring/grafana-dashboard-buet-paas-overview` was created
with `grafana_dashboard: "1"`. Its stored JSON matched the repository JSON.
Grafana's sidecar wrote `/tmp/dashboards/buet-paas-overview.json`. Grafana's
provisioning reload API returned `Dashboards config reloaded`. Grafana API then
reported:

```text
uid:         buet-paas-overview
title:       BUET-PaaS Monitoring Overview
panels:      16
provisioned: true
```

All 16 dashboard expressions executed successfully against the live Prometheus
API. Key values were 36 Prometheus targets UP, zero DOWN, four Kubernetes
nodes Ready, six standalone VMs UP, and five service probes UP. Availability,
probe duration, HTTP status, and host CPU/memory/root-filesystem panels all
returned nonempty series. Workload and alert queries also executed without
Prometheus errors; their series count is data dependent.

After applying, 24 Grafana dashboard ConfigMaps existed. Prometheus remained
at 36 UP and zero DOWN. All ten monitoring Pods were Running with zero
restarts. Blackbox stayed at revision 9; kube-prometheus-stack stayed at
revision 6.

The HTTPS dashboard link passed certificate validation (`tls_verify=0`). An
unauthenticated request redirected to Grafana's login page, as expected:

```text
https://grafana.monitoring.192.168.64.121.sslip.io/d/buet-paas-overview/buet-paas-monitoring-overview
```

## First attempt and operational follow-up

The first guarded apply rolled back the new ConfigMap when Grafana API
verification failed. Grafana has `enforce_domain=true`; requests to the
sidecar's `http://localhost:3000` reload URL were redirected to the HTTPS
hostname, whose private CA the sidecar does not trust. The local API probe
also received a redirect. The ConfigMap was removed and confirmed absent.

A read-only test proved that sending Grafana's configured `Host` header to the
local service returns HTTP 200 with valid API data. The guarded transaction
then used that header to call the reload API and verify the dashboard. No
Helm, ingress, certificate, Secret, application, or alert-rule settings were
changed. Future dashboard ConfigMap changes may require this manual reload
until the sidecar reload URL/domain configuration is corrected in a separate
approved step. The current dashboard is live and provisioned.

## Cleanup and files

The exact `/tmp/buet-paas-step16b` staging tree was enumerated, removed, and
confirmed absent. No live object was part of cleanup.

```text
step16b-apply-verify.sh       4caf4608b24e9ed5f15e5a302f7f021136f45742cf379a5e26d502e420a36d7d
step16b-grafana-preflight.sh  4257cfacac80822d24020cd50fa1aefcc398a145aeaa37e7f74d4d3ca5d21233
```

## Next permission boundary

Step 16C will prepare a small actionable PrometheusRule set, maintenance
policy, and offline verification. It will not apply alert rules.

```text
Approve Step 16C - prepare and offline verify the BUET-PaaS MVP alert rules
```
