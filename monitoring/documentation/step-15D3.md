# Step 15D3 - Prepare frontend, backend, and deployer Blackbox overlay

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15D3 - prepare and offline verify the frontend, backend, and deployer Blackbox target overlay`
- Result: **complete**
- Live Kubernetes/Helm mutation: **none**
- Next permission boundary: Step 15D4

## Prepared overlay

New cumulative repository file:

```text
monitoring/blackbox/targets-frontend-backend-deployer.yaml
SHA-256: 4d15271085e1ca674fde6d366a9fbc507a9d6b406093bc090beb21dafdeec3a5
```

It contains exactly:

| Service | Target | Module |
|---|---|---|
| frontend | `http://192.168.128.15/` | `http_frontend` |
| backend | `http://192.168.128.131:8020/health` | `http_json_ok` |
| deployer | `http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health` | `http_json_ok` |

The deployer target uses stable in-cluster Service DNS, not a Pod IP or
ClusterIP. All targets have explicit pre-scrape `instance`, `target`,
`service`, `environment`, and `deployment_type` labels so Prometheus-generated
`up` series cannot collide. Harbor and SonarQube are deliberately absent.

## Pinned inputs

```text
chart:          prometheus-blackbox-exporter 11.18.0
app:            v0.28.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
archive SHA256: 19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
image digest:   sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc
```

## Offline verification

The repeatable verifier now covers four rollout stages:

```text
frontend-only:                    1 ServiceMonitor
frontend plus backend:            2 ServiceMonitors
frontend plus backend plus deployer: 3 ServiceMonitors
all-target future stage:          5 ServiceMonitors
```

All four combinations passed Helm lint and render for Kubernetes 1.36.2. The
three-target render contains the exact three reviewed names and URLs, exactly
one frontend module and two `http_json_ok` module uses. Negative assertions
confirmed that Harbor and SonarQube did not enter this stage.

The complete rendered exporter configuration still has exactly four reviewed
modules, no generic `http_2xx`, and no private key material. The immutable
v0.28.0 exporter accepted it with `Config file is ok exiting...`. The render
also retained ClusterIP-only service exposure, zero Ingresses, the
Prometheus-only NetworkPolicy, immutable image, disabled service-account-token
mount, non-root/read-only filesystem controls, dropped capabilities, and the
strict Harbor CA configuration.

Relevant hashes:

```text
three-target render: 2032b7c50ff75a786965d692efa135c0303fc1a848c9dcef790b8215c4aa621e
Blackbox config:     9e843c719fd059230c51dc2f73ef93e98e12f2cef25d5832ed103c929cdfe52f
platform render:     644ba51e74841e87e6dbb4fe7f5034bf44ace462d112f7b4930dc6c611ba76c8
offline verifier:    b144733cdb474ed6782a92e1a12881658a3db1b3c7312ebd531e91577679e834
```

The first verifier run exposed only an incorrect whitespace expectation in a
new module-count assertion: Helm rendered the list item with six spaces, while
the assertion expected eight. The generated modules were correct. The test was
fixed to match the rendered YAML, then the complete suite passed with exit 0.

## Live-state proof

Read-only checks before and after offline verification showed no live change:

```text
Blackbox Helm release:      revision 6, deployed
live ServiceMonitors:       exactly frontend and backend
Prometheus count(up):       33
Prometheus DOWN:            zero
Kubernetes nodes:           4/4 Ready
monitoring Pods:            10 Running, zero restarts
```

No deployer ServiceMonitor was applied. No Kubernetes object, Helm release,
application, DNS, Ingress, security group, or network policy changed.

## Cleanup

The exact `/tmp/buet-paas-step15d3` tree and copied live-check script were
enumerated and removed. The exact-digest validator container exited, and its
new Docker cache image was removed. This did not touch the image used by the
running Kubernetes Pod.

## Next approval

Step 15D4 will server-dry-run and atomically upgrade only the Blackbox Helm
release from two to three targets. It must verify the deployer target is UP,
`probe_success=1`, HTTP 200, the expected JSON marker, unique labels, total
Prometheus `count(up)=34`, zero DOWN, and frontend/backend regression safety.
On failure it must roll back to the current healthy two-target configuration.

```text
Approve Step 15D4 - atomically apply and verify the deployer Blackbox probe
```
