# Step 14A4 - Atomically apply and verify all standalone VM scrape targets

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 14A4 - atomically apply and verify all standalone VM scrape targets`
- Result: **complete**
- Helm release: `monitoring-stack`
- Revision: 5 -> 6
- Rollback triggered: no

## Before-state

```text
Helm:                         revision 5, deployed
chart/app:                    kube-prometheus-stack 91.4.1 / v0.94.0
Kubernetes nodes:             4/4 Ready
monitoring Pods:              9 Running, zero restarts
Prometheus:                   Ready
total count(up):              26
standalone exporter count:    1
six exporter endpoints:       HTTP 200 from k3s-control-01
```

The three input files were copied into isolated directory
`/tmp/buet-paas-step14a4` and their remote hashes matched the reviewed local
files:

```text
base values:       c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b
scrape overlay:    24c43588815d1b390036e2ec0ab53fab66cc7fd5e4b18b486233893ac9d40248
browser overlay:   0ad5a65f13efb7b4c3356ebe5ba748adf847cb11e62b9af3ccdddf3983696bf7
```

Values order was base, scrape, then browser access so the existing VPN TLS and
authentication settings remained part of the complete desired release.

## Preflight and atomic upgrade

The first server-side dry-run included `--kube-version 1.36.2`. Helm's
`upgrade` subcommand does not accept that lint/template-only flag and stopped
with `unknown flag: --kube-version`; the live release remained revision 5.

The corrected command used the exact OCI chart version, server-side dry-run,
and `--hide-secret`. It completed with planned revision 6 and
`STATUS: pending-upgrade`; live revision still remained 5. The hidden-secret
dry-run output SHA-256 was
`8ab19e741576ab21b45f4585978e181d9640777024c21c85a2ee7ab48b51c91c`.

The approved live operation then used:

```text
chart:        oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack
version:      91.4.1
OCI digest:   sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
namespace:    monitoring
safety:       --atomic --timeout 15m
```

Helm returned `STATUS: deployed`, `REVISION: 6`, and `Upgrade complete`.
Atomic rollback was not required.

## Prometheus result

The query `up{job="standalone-node-exporters"}` returned six series, each value
`1`, with the intended labels:

```text
frontend-vm    service=frontend
database-vm    service=database
registry-vm-2  service=registry
k3s-user       service=platform-admin
backend-vm     service=backend
sonarqube      service=code-quality
```

All six also retained `environment=buet-paas` and
`deployment_type=standalone-vm`.

```text
standalone exporters UP: 6/6
total count(up):         31
count(up == 0):          no series
Prometheus readiness:    ready
```

The increase from 26 to 31 is exactly the five newly applied targets.

## Cluster, ingress, and application regression

```text
Helm revision 6:         deployed
Kubernetes nodes:        4/4 Ready
monitoring Pods:         9 Running, zero restarts
Grafana HTTPS health:    200, trusted TLS result 0
Prometheus without auth: 401, trusted TLS result 0
Alertmanager no auth:    401, trusted TLS result 0
Grafana HTTP route:      301 to HTTPS
```

The first Windows HTTPS checks failed because Schannel could not query a CRL
for the private CA. The established `--ssl-no-revoke` method disabled only the
unavailable CRL lookup; CA-chain and hostname verification remained enabled
and returned verification result 0. `--insecure` was not used.

Application checks:

```text
all six VM exporters: active, NRestarts=0
frontend:             HTTP 200
MongoDB:              active, expected listeners retained
Docker/Harbor:        active, Harbor health HTTP 200
k3s-user:             4 Ready nodes
BUET backend:          active, /health HTTP 200, MongoDB connected
SonarQube:             Docker active, API UP and HTTP 200
```

Harbor's local diagnostic retained its existing self-managed HTTPS behavior and
used the same audit-only `curl -k` check; no Harbor trust or configuration was
changed.

## Cleanup, security, and rollback

No credential or private key was printed or stored in documentation. The
server dry-run used `--hide-secret`. The resolved temporary directory contained
only three input values files and the hidden-secret dry-run output. It was
enumerated, removed exactly, and confirmed absent.

If a later regression requires rollback, use a separately approved:

```bash
helm rollback monitoring-stack 5 -n monitoring --wait --timeout 15m
```

That would remove the five new live scrape targets while preserving the Step
12 browser-access state represented by revision 5. No rollback is currently
indicated.

## Next permission boundary

Standalone VM metrics for the intended MVP set are complete. The next planned
stage is Step 15A: read-only Blackbox endpoint, redirect, TLS, and health-path
preflight before any Blackbox Exporter configuration is prepared.

