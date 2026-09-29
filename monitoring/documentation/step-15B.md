# Step 15B - Prepare and offline verify secure Blackbox configuration

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15B - prepare and offline verify secure Blackbox configuration`
- Result: **complete**
- Live Kubernetes/Helm mutation: **none**
- Next permission boundary: Step 15C

## Prepared artifacts

```text
monitoring/blackbox/
  harbor-ca.crt
  kustomization.yaml
  network-policy.yaml
  values.yaml
  targets-frontend.yaml
  targets-all.yaml
  scripts/offline-verify.sh
  scripts/live-unchanged-check.sh
```

`values.yaml` defines the exporter, reviewed modules, resource bounds, CA
mount, and ServiceMonitor defaults, but no live target. The frontend overlay is
the Step 15C one-target canary. The all-target overlay is reserved for Step
15D, preventing all probes from entering the first live change.

## Pinned supply chain

```text
chart:          prometheus-community/prometheus-blackbox-exporter
chart version:  11.18.0
app/image tag:  v0.28.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
chart archive:  19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
image digest:   sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc
```

The rendered Deployment uses immutable
`quay.io/prometheus/blackbox-exporter:v0.28.0@sha256:e753...c2fc`, not a
tag-only reference. The image was also used by an ephemeral Docker config-check
container. That container exited and the newly pulled cache image was removed.

## Probe modules

| Module | Requirement |
|---|---|
| `http_frontend` | HTTP 200, no redirect, body contains `BUET-PaaS` |
| `http_json_ok` | HTTP 200, no redirect, body contains `"status":"ok"` |
| `http_harbor_tls` | HTTP 200, no redirect, verified Harbor CA/SAN, body contains `"status":"healthy"` |
| `http_sonarqube_up` | HTTP 200, no redirect, body contains `"status":"UP"` |

All modules use GET, IPv4 preference, and a 5-second probe timeout under the
10-second scrape timeout. The first render revealed that Helm deep-merged the
chart's generic `http_2xx` module. The final overlay explicitly deletes it, so
only these four reviewed modules render. Blackbox v0.28.0 reported
`Config file is ok exiting...`.

## Secure design

- Service is `ClusterIP` on 9115; no Ingress, NodePort, or LoadBalancer renders.
- Ingress NetworkPolicy allows TCP 9115 only from the live Prometheus Pod
  identity in the `monitoring` namespace.
- The exporter runs non-root, drops all capabilities, disables privilege
  escalation, uses a read-only root filesystem, and does not mount a service
  account token.
- Requests are 20m CPU/32Mi; limits are 100m CPU/128Mi.
- Harbor mounts only the public CA. `insecure_skip_verify: false` is explicit.
- No credential, kubeconfig, private key, or user-controlled target is present.
- Every ServiceMonitor has `release: monitoring-stack`, matching the live
  Prometheus selector, and stable service/environment/deployment labels.

Rendered NetworkPolicy identities:

```text
destination Pod:
  app.kubernetes.io/name=prometheus-blackbox-exporter
  app.kubernetes.io/instance=blackbox-exporter

allowed source Pod:
  app.kubernetes.io/name=prometheus
  operator.prometheus.io/name=monitoring-stack-kube-prom-prometheus

allowed source namespace:
  kubernetes.io/metadata.name=monitoring
```

## Staged targets

Step 15C renders only:

```text
http://192.168.128.15/ -> http_frontend
```

The later overlay renders exactly five ServiceMonitors:

```text
frontend:  http://192.168.128.15/
backend:   http://192.168.128.131:8020/health
deployer:  http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health
Harbor:    https://192.168.128.152/api/v2.0/health
SonarQube: http://192.168.128.33:9000/api/system/status
```

## Offline verification

Both staged combinations passed Helm lint with zero failures for Kubernetes
1.36.2. Rendering and the native binary check returned:

```text
frontend stage: 1 ServiceMonitor
all stage:      5 ServiceMonitors
Ingress:        0
NetworkPolicy:  1
CA ConfigMap:   1
private keys:   none
native parser:  PASS
```

Rendered SHA-256 values:

```text
blackbox config:   9e843c719fd059230c51dc2f73ef93e98e12f2cef25d5832ed103c929cdfe52f
frontend render:   0b4e778c76ac6835b26e5220683c056f8c0f2d799492e11e64f8b4f96dd7e015
all-target render: 45d2d35cd6bca6778d8866645d3ec62a83a736cabeab2dd7cfd379235b175e0e
platform render:   644ba51e74841e87e6dbb4fe7f5034bf44ace462d112f7b4930dc6c611ba76c8
```

Repository input SHA-256 values:

```text
harbor-ca.crt:         6fecd502db98d54578c590c385df4a3d590caf495e26ed770e54bdc2f6df6d44
kustomization.yaml:    da889bd2011277101fab524ca4c356b63bf0974d03a5e244908645b6526aef81
network-policy.yaml:   a17389aba2f4f6e9f92d956dd7c376d6a007ffaba5735ed37598e88d1a0facf7
values.yaml:           f1823607d2090c3370635cd037671af3d1b539ea41f03dce6de008a2de5b6bb4
targets-frontend.yaml: dda9a00f8dfc059d8d9d15b56e65c7d5dd9bd6bfd0ff36aed6f8fecf94208cde
targets-all.yaml:      23bb94b52121a6c1c69f6bca9e9b436ff119330250169dfeb114198fdd35f238
```

## Live-state regression

```text
Helm release:       monitoring-stack revision 6, deployed
Kubernetes nodes:   4/4 Ready
monitoring Pods:    9 Running, zero restarts
Prometheus count:   31 UP
Prometheus DOWN:    zero
Blackbox resources: none
```

The isolated `/tmp/buet-paas-step15b` directory and validation image cache were
removed. No live Kubernetes object, Helm release, application, security group,
firewall rule, DNS record, or browser route changed.

## Non-mutating corrections

One assertion initially expected pre-extraction YAML indentation and stopped
after lint; it was corrected before the parser passed. Two inline remote checks
failed from shell quoting before they ran, so they were moved into auditable
scripts. A cleanup `find -printf` display expression was misquoted, but the
target was already resolved and checked as exactly `/tmp/buet-paas-step15b`;
the image and directory cleanup completed and absence was verified.

## Next approval

Step 15C will server-dry-run, apply the public CA ConfigMap and Prometheus-only
NetworkPolicy, install the pinned exporter as ClusterIP, and activate only the
frontend canary. It must verify Pod security/readiness, policy, `up`,
`probe_success`, HTTP status, duration, all existing targets, and rollback
readiness before any remaining target is added.

```text
Approve Step 15C - install Blackbox Exporter and activate only the frontend canary probe
```
