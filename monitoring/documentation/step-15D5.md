# Step 15D5 - Prepare cumulative strict-TLS Harbor Blackbox overlay

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15D5 - prepare and offline verify the frontend, backend, deployer, and Harbor Blackbox target overlay`
- Result: **complete**
- Live Kubernetes/Helm mutation: **none**
- Next permission boundary: Step 15D6

## Prepared overlay

New cumulative repository file:

```text
monitoring/blackbox/targets-frontend-backend-deployer-harbor.yaml
SHA-256: fa5b89d0ccc74a220996f7faa67f19f19df7a61d700963b83c4b9cab7f711863
```

It contains exactly:

| Service | Target | Module |
|---|---|---|
| frontend | `http://192.168.128.15/` | `http_frontend` |
| backend | `http://192.168.128.131:8020/health` | `http_json_ok` |
| deployer | `http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health` | `http_json_ok` |
| Harbor | `https://192.168.128.152/api/v2.0/health` | `http_harbor_tls` |

All four retain explicit pre-scrape `instance`, `target`, `service`,
`environment`, and `deployment_type` labels. Harbor uses `service=registry`.
SonarQube is deliberately absent.

## Harbor trust and health recheck

The public Harbor CA remained byte-identical to the reviewed file:

```text
SHA-256:    6fecd502db98d54578c590c385df4a3d590caf495e26ed770e54bdc2f6df6d44
subject:    CN=Harbor-CA
issuer:     CN=Harbor-CA
valid:      2026-09-04 through 2036-09-01
fingerprint F2:2D:B8:38:48:10:85:E2:17:CD:50:36:6A:3D:91:48:
            4E:F5:D0:9B:19:8A:B3:4E:BD:9B:FD:B5:6D:67:BD:FB
```

A fresh HTTPS request using only that CA returned TLS verification result 0,
HTTP 200, top-level `status=healthy`, and healthy core, database, jobservice,
portal, Redis, registry, and registry-controller components. No insecure TLS
flag was used.

## Pinned inputs and offline verification

```text
chart:          prometheus-blackbox-exporter 11.18.0
app:            v0.28.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
archive SHA256: 19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
image digest:   sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc
```

The repeatable verifier now covers every staged rollout size:

```text
frontend:                             1 ServiceMonitor
frontend + backend:                   2 ServiceMonitors
+ deployer:                           3 ServiceMonitors
+ Harbor:                             4 ServiceMonitors
+ future SonarQube all-target stage:  5 ServiceMonitors
```

All five overlays passed Helm lint/render for Kubernetes 1.36.2. The four-
target render contains the exact reviewed names and URLs, one
`http_frontend`, two `http_json_ok`, and one `http_harbor_tls` selection.
Negative assertions prove SonarQube did not enter this stage.

The rendered exporter config still contains exactly four allowlisted modules
and no generic `http_2xx`. It mounts the public CA read-only and sets:

```yaml
ca_file: /etc/blackbox/certs/harbor-ca.crt
insecure_skip_verify: false
```

The immutable v0.28.0 image accepted the configuration with
`Config file is ok exiting...`. No private key material was found. ClusterIP-
only exposure, zero Ingresses, the Prometheus-only NetworkPolicy, immutable
image, disabled service-account token, non-root/read-only security context,
dropped capabilities, and resource limits remain unchanged.

Relevant hashes:

```text
four-target render: fef435e4533094192c3af2d88a671201317fd8b3a4298a534224dbebf6754009
Blackbox config:    9e843c719fd059230c51dc2f73ef93e98e12f2cef25d5832ed103c929cdfe52f
platform render:    644ba51e74841e87e6dbb4fe7f5034bf44ace462d112f7b4930dc6c611ba76c8
offline verifier:   417d574092eedc015a18667910575e5817c7d26bce25f165a83e4c604f7aa3c7
```

## Live-state proof

Before and after offline validation:

```text
Blackbox release:          revision 7, deployed
live ServiceMonitors:      frontend, backend, deployer only
Harbor ServiceMonitor:     absent
Prometheus count(up):      34
Prometheus DOWN:           zero
Kubernetes nodes:          4/4 Ready
monitoring Pods:           10 Running, zero restarts
```

No Kubernetes object, Helm release, application, Harbor configuration,
certificate, Secret, DNS, Ingress, OpenStack rule, or public port changed.

## Cleanup

The exact `/tmp/buet-paas-step15d5` tree was enumerated, removed, and confirmed
absent. The exact-digest validator container exited and its newly pulled Docker
cache image was removed. The running Kubernetes image was not touched.

## Next approval

Step 15D6 will server-dry-run and atomically upgrade only the Blackbox Helm
release from three to four targets. It must prove Harbor `probe_success=1`,
HTTP 200, strict TLS success and certificate-expiry metrics, unique labels,
all previous probes healthy, Prometheus `count(up)=35`, and zero DOWN. Any
failed acceptance condition must roll back to the current revision-7 three-
target configuration.

```text
Approve Step 15D6 - atomically apply and verify the Harbor Blackbox probe
```
