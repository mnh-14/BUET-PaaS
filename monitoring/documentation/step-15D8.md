# Step 15D8 - Atomically apply and verify SonarQube Blackbox probe

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15D8 - atomically apply and verify the SonarQube Blackbox probe`
- Result: **complete**
- Final Blackbox Helm revision: 9, deployed
- Live probes: all five planned service probes
- Rollback: prepared but not triggered
- kube-prometheus-stack revision: 6, unchanged

## Preflight

The guarded preflight proved:

```text
Blackbox revision:          8, deployed
live ServiceMonitors:       frontend, backend, deployer, Harbor
existing probe_success:     4/4
Harbor probe_http_ssl:      1
Prometheus count(up):       35
Prometheus DOWN:            zero
SonarQube direct health:    HTTP 200, version 26.8.0.126808, status UP
```

Repository values, public Harbor CA, and final overlay hashes matched the
reviewed Step 15D7 evidence. The pinned chart identity matched:

```text
chart:          prometheus-blackbox-exporter 11.18.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
archive SHA256: 19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
```

## Guarded transaction

The exact pinned chart, base values, and final five-target overlay first passed
`helm upgrade --dry-run=server --hide-secret`. Captured dry-run SHA-256:

```text
db887b2bfe2f4f1050a371ecfb0d14a598f2d1f76ed2d1c49e9ba72dbd2744ae
```

The same inputs were applied with `--atomic --wait` and a ten-minute timeout.
Helm deployed revision 9. A bounded verifier required all five semantic probes,
module distribution, exact labels, Harbor TLS, target count, and regression
checks to pass in a single converged observation. All checks passed, so the
prepared rollback to revision 8 was not invoked.

## Final service-probe result

| Service | Module | Result | Duration |
|---|---|---|---:|
| frontend | `http_frontend` | success 1, HTTP 200 | 0.006974360 s |
| backend | `http_json_ok` | success 1, HTTP 200 | 0.006388225 s |
| deployer | `http_json_ok` | success 1, HTTP 200 | 0.008583715 s |
| Harbor | `http_harbor_tls` | success 1, HTTP 200, SSL 1 | 0.015523949 s |
| SonarQube | `http_sonarqube_up` | success 1, HTTP 200 | 0.007759462 s |

All five Prometheus active targets reported `health=up`, empty `lastError`,
and exact unique `instance`, `target`, `service`, `environment`, and
`deployment_type` labels. SonarQube is labeled `service=code-quality` and
`target=sonarqube`; its success also proves the configured `"status":"UP"`
body requirement.

## Regression and security result

```text
Prometheus count(up):       36
Prometheus DOWN:            zero
standalone VM exporters UP: 6/6
Kubernetes nodes:           4/4 Ready
monitoring Pods:            10 Running, zero restarts
frontend:                   BUET-PaaS marker present
backend:                    status ok, MongoDB connected
deployer:                   status ok
Harbor:                     healthy, verified TLS
SonarQube:                  status UP
```

Blackbox remains ClusterIP-only on 9115 with no external IP and no Blackbox
Ingress. The Prometheus-only NetworkPolicy, immutable image digest, disabled
service-account-token mount, non-root UID/GID 1000, read-only root filesystem,
dropped capabilities, no privilege escalation, public Harbor CA mount, and
resource limits remain unchanged. The final exporter log sample contained no
error/fatal/panic entries.

No application, SonarQube or Harbor setting, certificate, Secret, OpenStack
rule, DNS, public port, or kube-prometheus-stack configuration changed.

## Repeatable scripts

```text
step15d8-preflight.sh    90aa2112e993ceab064b753bf49649299fa4706d7c87184c9cad9f0dbe2745e5
step15d8-transaction.sh  0007d640dbc33e514a55b565bf905ab8c7f208761f78cddf2bece3d44743facd
step15d8-verify.sh       f667e93844c29746d925a47b2d40e59f08abd1b9eeab7d06702a234b1b4cd743
step15d8-diagnose.sh     a2f338803f272b24b74a6b14d04e8becc7533ce00c8add6676d83eac9162fa4f
```

## Cleanup

The exact `/tmp/buet-paas-step15d8` staging tree was enumerated, removed, and
confirmed absent. No live object or running image was part of cleanup.

## Day 2 completion

Day 2 monitoring scope is now complete:

```text
standalone VM node_exporters: 6/6 live and UP
service Blackbox probes:      5/5 live and UP
Prometheus overall targets:   36 UP, zero DOWN
```

## Next approval

The next gate starts Day 3 and is repository/offline-only. It will prepare the
BUET-PaaS Monitoring Overview dashboard as provisioned JSON, using queries
validated against the real labels now available. It will not apply a Grafana
dashboard or alert rules.

```text
Approve Step 16A - prepare and offline verify the BUET-PaaS Monitoring Overview dashboard as code
```
