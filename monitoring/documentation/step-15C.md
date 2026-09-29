# Step 15C - Install Blackbox Exporter and activate frontend canary

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15C - install Blackbox Exporter and activate only the frontend canary probe`
- Result: **complete**
- Blackbox Helm release: revision 1, deployed
- Rollback triggered: no
- Active Blackbox probes: frontend only

## Before-state

```text
Blackbox live resources: absent
kube-prometheus-stack:   revision 6, deployed
Prometheus count(up):    31
Prometheus DOWN:         zero
Kubernetes nodes:        4/4 Ready
monitoring Pods:         9 Running, zero restarts
```

The copied repository inputs matched the reviewed SHA-256 values. The exact
chart was pulled from the official OCI registry:

```text
chart:          prometheus-blackbox-exporter 11.18.0
app:            v0.28.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
archive SHA256: 19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
image digest:   sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc
```

## Dry runs

The public Harbor CA ConfigMap and NetworkPolicy passed a server-side dry run
using the server-bundled k3s kubectl through the established private control
node route. The pinned Helm release with base values plus only
`targets-frontend.yaml` also passed `--dry-run=server --hide-secret`.

```text
platform render SHA256: 644ba51e74841e87e6dbb4fe7f5034bf44ace462d112f7b4930dc6c611ba76c8
platform dry-run SHA256:69da16c5c81f15cb8a361803db617c5a39a15c1c2c1566b4b6f76f3c510eff34
Helm dry-run SHA256:    2a6ca53ba90ae891879541a015b2ec401b4307498fc3f801989c4d6a05c5fe05
```

## Applied change

Standalone objects:

```text
ConfigMap/blackbox-harbor-ca
NetworkPolicy/blackbox-exporter-prometheus-only
```

The ConfigMap contains only the public Harbor CA. The NetworkPolicy selects
only the Blackbox Pod and permits ingress on TCP 9115 only from the confirmed
Prometheus Pod identity in namespace `monitoring`.

Helm installed a separate release:

```text
release:        blackbox-exporter
namespace:      monitoring
chart:          prometheus-blackbox-exporter-11.18.0
app:            v0.28.0
revision:       1
status:         deployed
safety:         --atomic --wait --timeout 10m
target overlay: targets-frontend.yaml only
```

The kube-prometheus-stack release was not upgraded and remains revision 6.

## Workload and security verification

```text
Deployment:      blackbox-exporter 1/1 Available
Pod:             1/1 Ready, zero restarts
Service:         ClusterIP 10.43.40.33:9115
Ingress:         none
ServiceMonitors: exactly one
```

The running container uses the immutable image digest. It runs as UID/GID
1000, requires non-root, drops all capabilities, disables privilege
escalation, uses a read-only root filesystem, and has no service-account token
mount. Requests are 20m CPU/32Mi and limits are 100m CPU/128Mi.

The live Harbor CA ConfigMap byte hash is exactly:

```text
6fecd502db98d54578c590c385df4a3d590caf495e26ed770e54bdc2f6df6d44
```

The CA is mounted read-only at `/etc/blackbox/certs`. The live Blackbox config
contains exactly the four reviewed modules and no generic `http_2xx` module.
The last 100 exporter log lines contained no error, fatal, or panic entry.

## Frontend-only proof

The single ServiceMonitor is:

```text
name:    blackbox-exporter-buet-paas-frontend
release: monitoring-stack
module:  http_frontend
target:  http://192.168.128.15/
```

No backend, deployer, Harbor, or SonarQube ServiceMonitor was created.
Prometheus reports exactly one Blackbox active target:

```text
health:     up
lastError:  empty
job:        blackbox-exporter
module:     http_frontend
target:     http://192.168.128.15/
```

Canary metrics:

```text
probe_success:           1
probe_http_status_code:  200
probe_duration_seconds:  0.006289445
probe_ip_protocol:       4
```

The frontend also returned its `BUET-PaaS` marker through a direct independent
request.

## Regression result

```text
Prometheus count(up):       31 -> 32
Prometheus DOWN:            zero
standalone VM exporters UP: 6/6
Kubernetes nodes:           4/4 Ready
monitoring Pods:            10 Running, zero restarts
kube-prometheus-stack:      revision 6 unchanged
```

## Corrections during verification

The first live CA hash used `jq -r`, which appended a display newline and
therefore produced a different hash. Byte-exact `jq -j` returned the expected
repository hash; the ConfigMap was not changed. One inline jq check was then
misquoted by the Windows-to-SSH shell boundary and parsed no data; the audited
script supplied the correct byte-exact result.

The first active-target assertion searched the scrape URL for the Service
name, but Prometheus correctly uses the selected Pod IP in `scrapeUrl`. The
assertion was changed to the Kubernetes-discovered Service label
`blackbox-exporter`; it then confirmed exactly one UP target with no error.
Neither correction mutated the cluster.

## Rollback procedure (not executed)

If this canary later requires removal, use this order after explicit approval:

```bash
helm uninstall blackbox-exporter -n monitoring --wait
kubectl delete networkpolicy blackbox-exporter-prometheus-only -n monitoring
kubectl delete configmap blackbox-harbor-ca -n monitoring
```

This removes only Step 15C resources and does not alter monitoring-stack.

## Cleanup and next boundary

The exact `/tmp/buet-paas-step15c` staging directory was enumerated, removed,
and confirmed absent. Live approved resources remain installed.

The next safe action is repository/offline only: prepare a cumulative overlay
containing the already healthy frontend plus backend health endpoint. It will
not add deployer, Harbor, or SonarQube yet.

```text
Approve Step 15D1 - prepare and offline verify the frontend plus backend Blackbox target overlay
```
