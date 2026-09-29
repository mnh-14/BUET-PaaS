# Step 15D6 - Atomically apply and verify Harbor Blackbox probe

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15D6 - atomically apply and verify the Harbor Blackbox probe`
- Result: **complete**
- Final Blackbox Helm revision: 8, deployed
- Live probes: frontend, backend, deployer, and Harbor
- Rollback: prepared but not triggered
- kube-prometheus-stack revision: 6, unchanged

## Preflight

The guarded preflight proved:

```text
Blackbox revision:           7, deployed
live ServiceMonitors:        frontend, backend, deployer
three existing probes:       probe_success=1
Prometheus count(up):        34
Prometheus DOWN:             zero
live Harbor CA SHA-256:      6fecd502db98d54578c590c385df4a3d590caf495e26ed770e54bdc2f6df6d44
Harbor strict HTTPS health:  HTTP 200; all components healthy
```

The live CA ConfigMap was byte-for-byte identical to the reviewed public CA.
Repository values, CA, and four-target overlay hashes matched Step 15D5. The
pinned chart identities also matched:

```text
chart:          prometheus-blackbox-exporter 11.18.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
archive SHA256: 19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
```

## Guarded transaction

The exact chart, base values, and cumulative four-target overlay first passed
`helm upgrade --dry-run=server --hide-secret`. Captured dry-run SHA-256:

```text
5ab460b30870d50ca60e7d474b23bacc21749398f8883a0811fea271729ceb44
```

The same inputs were then applied with `--atomic --wait` and a ten-minute
timeout. Helm deployed revision 8. A bounded verifier required all four probes,
TLS metrics, unique labels, total target count, and regression checks to pass
in one converged observation. Every condition passed; rollback to revision 7
was not triggered.

## Probe results

| Service | Module | Result | Duration |
|---|---|---|---:|
| frontend | `http_frontend` | success 1, HTTP 200 | 0.008587651 s |
| backend | `http_json_ok` | success 1, HTTP 200 | 0.005986331 s |
| deployer | `http_json_ok` | success 1, HTTP 200 | 0.203932288 s |
| Harbor | `http_harbor_tls` | success 1, HTTP 200, SSL 1 | 0.019554746 s |

All four Prometheus active targets reported `health=up`, empty `lastError`,
and exact unique `instance`, `target`, `service`, `environment`, and
`deployment_type` labels.

Harbor TLS evidence:

```text
probe_http_ssl:                 1
probe_ssl_earliest_cert_expiry: 1859799441
certificate expiry UTC:         2028-12-07T10:57:21Z
post-apply curl verification:    result 0, HTTP 200
Harbor API status:               healthy; all listed components healthy
```

The verifier required more than 90 days remaining certificate validity.

## Regression and security result

```text
Prometheus count(up):       35
Prometheus DOWN:            zero
standalone VM exporters UP: 6/6
Kubernetes nodes:           4/4 Ready
monitoring Pods:            10 Running, zero restarts
frontend marker:            present
backend health:             status ok, MongoDB connected
deployer health:            status ok
Harbor health:              healthy
```

Blackbox remains ClusterIP-only on 9115 with no external IP and no Blackbox
Ingress. The Prometheus-only NetworkPolicy, immutable image digest, disabled
service-account-token mount, non-root UID/GID 1000, read-only root filesystem,
dropped capabilities, no privilege escalation, public CA mount, and resource
limits remain unchanged. The final log sample contained no error/fatal/panic.

No application, Harbor setting, certificate, Secret, OpenStack rule, DNS,
public port, or kube-prometheus-stack configuration changed.

## Repeatable scripts

```text
step15d6-preflight.sh    f2600752e399ac4b4fbdd387ab0aae35c54994870b7618dab4d0662d8d34fb57
step15d6-transaction.sh  f1caaf2b46c491cbf00996e2c2c174f5aeb01145dfcdd2786299c326b4fca742
step15d6-verify.sh       f401048178a25e430defd33af0ff7c8aba850eeceeea6274d0bd75c2029294f1
step15d6-diagnose.sh     578342939fd13fc7d9158db69d0058e18ce03847734fe2253143d610b6be43ee
```

## Cleanup

The exact `/tmp/buet-paas-step15d6` staging tree was enumerated, removed, and
confirmed absent. No live object or running image was part of cleanup.

## Next approval

The next gate is non-mutating. It will recheck the SonarQube health endpoint
and offline-verify the already prepared final five-target overlay, proving that
only SonarQube is added to the four live targets. It will not apply anything.

```text
Approve Step 15D7 - revalidate SonarQube and offline verify the final five-target Blackbox overlay
```
