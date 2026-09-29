# Step 15D7 - Revalidate SonarQube and final five-target overlay

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15D7 - revalidate SonarQube and offline verify the final five-target Blackbox overlay`
- Result: **complete**
- Live Kubernetes/Helm mutation: **none**
- Next permission boundary: Step 15D8

## SonarQube revalidation

Fresh read-only request:

```text
target:  http://192.168.128.33:9000/api/system/status
HTTP:    200
version: 26.8.0.126808
status:  UP
```

The endpoint therefore still satisfies the reviewed `http_sonarqube_up`
module: GET, HTTP 200, no redirect, IPv4, and body marker `"status":"UP"`.

## Final overlay

The existing final overlay was retained without content changes:

```text
monitoring/blackbox/targets-all.yaml
SHA-256: 997b626a87edb2d87d9f4ba3ef1a263d9e76486855ea8571920780f43a72644e
```

It contains exactly the four live targets plus SonarQube:

| Service | Target | Module |
|---|---|---|
| frontend | `http://192.168.128.15/` | `http_frontend` |
| backend | `http://192.168.128.131:8020/health` | `http_json_ok` |
| deployer | `http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health` | `http_json_ok` |
| Harbor | `https://192.168.128.152/api/v2.0/health` | `http_harbor_tls` |
| SonarQube | `http://192.168.128.33:9000/api/system/status` | `http_sonarqube_up` |

SonarQube has stable pre-scrape labels `target=sonarqube`,
`service=code-quality`, `environment=buet-paas`, and
`deployment_type=blackbox`, plus its exact URL as `instance`.

## Pinned offline verification

```text
chart:          prometheus-blackbox-exporter 11.18.0
app:            v0.28.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
archive SHA256: 19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
image digest:   sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc
```

All cumulative stages passed Helm lint/render for Kubernetes 1.36.2:

```text
frontend:                             1 ServiceMonitor
frontend + backend:                   2 ServiceMonitors
+ deployer:                           3 ServiceMonitors
+ Harbor:                             4 ServiceMonitors
+ SonarQube final stage:              5 ServiceMonitors
```

The final render contains each exact name and URL, one `http_frontend`, two
`http_json_ok`, one `http_harbor_tls`, and one `http_sonarqube_up` selection.
Exact SonarQube target, instance, and service relabeling assertions passed.

The rendered exporter configuration still has exactly four allowlisted
modules, no generic `http_2xx`, strict Harbor CA verification, and no private
key. The immutable v0.28.0 binary accepted it with
`Config file is ok exiting...`. The render retained ClusterIP-only exposure,
zero Ingresses, the Prometheus-only NetworkPolicy, immutable image, disabled
service-account token, non-root/read-only container controls, dropped
capabilities, and resource limits.

Relevant hashes:

```text
final five-target render: 0df39788aafe2ab9ae73a221547c1d78f41573dffb87d34c91beb445b9bc88a6
Blackbox config:          9e843c719fd059230c51dc2f73ef93e98e12f2cef25d5832ed103c929cdfe52f
platform render:          644ba51e74841e87e6dbb4fe7f5034bf44ace462d112f7b4930dc6c611ba76c8
offline verifier:         2626b6123827e57efcb4879feea3f5150bfa8f194784725e264fda5103ed3fbc
```

Two initial verifier runs exposed only test serialization assumptions. Helm
quotes metric-relabel map values but not target-relabel list values, and list
items include a leading dash. Assertions were corrected to match the exact
render. No overlay or module behavior changed, and the complete suite then
passed with exit 0.

## Live-state proof

Before and after validation:

```text
Blackbox release:          revision 8, deployed
live ServiceMonitors:      frontend, backend, deployer, Harbor
SonarQube ServiceMonitor:  absent
Prometheus count(up):      35
Prometheus DOWN:           zero
Kubernetes nodes:          4/4 Ready
monitoring Pods:           10 Running, zero restarts
```

No Kubernetes object, Helm release, application, SonarQube setting, network
rule, Ingress, DNS, Secret, or public port changed.

## Cleanup

The exact `/tmp/buet-paas-step15d7` tree was enumerated, removed, and confirmed
absent. The exact-digest validator exited and its newly pulled Docker cache
image was removed without touching the running Kubernetes image.

## Next approval

Step 15D8 will server-dry-run and atomically upgrade only the Blackbox Helm
release from four to five targets. It must prove SonarQube success 1, HTTP 200,
the UP body requirement, unique labels, all four prior probes healthy,
Prometheus `count(up)=36`, zero DOWN, and full regression safety. Any failed
condition must roll back to the current revision-8 four-target configuration.

```text
Approve Step 15D8 - atomically apply and verify the SonarQube Blackbox probe
```
