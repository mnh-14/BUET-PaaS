# Step 11A1 - Prepare frontend-vm scrape configuration

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: explicitly approved with `Approve Step 11A1 - prepare frontend-vm scrape configuration`
- Scope: repository preparation and offline Helm validation only
- Current state: **completed successfully**
- Live Helm/Kubernetes mutation authorized: none
- VM/OpenStack mutation authorized: none

## Purpose

Prepare one Prometheus scrape job for the node_exporter already running on
`frontend-vm`. The exporter is reachable from `k3s-control-01` at
`192.168.128.15:9100`, but it was intentionally not part of the live Prometheus
configuration at the start of this step.

This substep does not apply the configuration. Applying it is reserved for a
separately approved Step 11A2.

## Design decision

The existing base file `monitoring/prometheus/values.yaml` was left unchanged.
The new configuration is an additive Helm values overlay:

```text
monitoring/external-vms/scrape-values.yaml
```

Future Helm commands must provide the base file first and this overlay second.
This keeps the standalone-VM targets separate and makes rollback explicit.

The job uses a stable `instance: frontend-vm` label instead of exposing the IP
address as the Grafana-facing instance name. The remaining labels distinguish
the service, environment, and deployment type.

## Pinned chart schema verification

The first read-only command used a repository alias:

```bash
helm show values prometheus-community/kube-prometheus-stack --version 91.4.1
```

Output:

```text
Error: repo prometheus-community not found
```

This did not change the cluster. The correction used the same pinned OCI source
used by this project:

```bash
helm show values \
  oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack \
  --version 91.4.1
```

Relevant output:

```text
Pulled: ghcr.io/prometheus-community/charts/kube-prometheus-stack:91.4.1
Digest: sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
additionalScrapeConfigs: []
```

The pinned chart therefore accepts a list at:

```text
prometheus.prometheusSpec.additionalScrapeConfigs
```

The focused template was also located at:

```text
templates/prometheus/additionalScrapeConfigs.yaml
```

## Repository file added

File:

```text
monitoring/external-vms/scrape-values.yaml
```

SHA-256:

```text
a5b4c936232457e957f1c2b2fab3dfc3ec1799c9d21df0490fbc865caeef1a32
```

Content:

```yaml
# Additional Prometheus scrape targets for BUET-PaaS standalone VMs.
#
# Apply this file as an overlay after monitoring/prometheus/values.yaml.
# It contains no credentials.

prometheus:
  prometheusSpec:
    additionalScrapeConfigs:
      - job_name: standalone-node-exporters
        scheme: http
        metrics_path: /metrics
        scrape_interval: 30s
        scrape_timeout: 10s
        static_configs:
          - targets:
              - "192.168.128.15:9100"
            labels:
              instance: frontend-vm
              service: frontend
              environment: buet-paas
              deployment_type: standalone-vm
```

No credentials or private keys are present in this file.

## Validation commands

The base values and overlay were copied to the exact temporary directory
`/tmp/buet-step11a1-chart-20260924` on `k3s-user`. Nothing was copied into the
cluster.

File-integrity output:

```text
c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b  input/values.yaml
a5b4c936232457e957f1c2b2fab3dfc3ec1799c9d21df0490fbc865caeef1a32  input/scrape-values.yaml
```

The remote hashes matched the local files.

Helm lint command:

```bash
helm lint /tmp/buet-step11a1-chart-20260924/kube-prometheus-stack \
  --namespace monitoring \
  --kube-version 1.36.2 \
  -f /tmp/buet-step11a1-chart-20260924/input/values.yaml \
  -f /tmp/buet-step11a1-chart-20260924/input/scrape-values.yaml
```

Output:

```text
1 chart(s) linted, 0 chart(s) failed
```

Focused render command:

```bash
helm template monitoring-stack \
  /tmp/buet-step11a1-chart-20260924/kube-prometheus-stack \
  --namespace monitoring \
  --kube-version 1.36.2 \
  -f /tmp/buet-step11a1-chart-20260924/input/values.yaml \
  -f /tmp/buet-step11a1-chart-20260924/input/scrape-values.yaml \
  --show-only templates/prometheus/additionalScrapeConfigs.yaml
```

Decoded focused render:

```yaml
- job_name: standalone-node-exporters
  metrics_path: /metrics
  scheme: http
  scrape_interval: 30s
  scrape_timeout: 10s
  static_configs:
  - labels:
      deployment_type: standalone-vm
      environment: buet-paas
      instance: frontend-vm
      service: frontend
    targets:
    - 192.168.128.15:9100
```

The first combined lint/render/decode wrapper had a local PowerShell quote
terminator error. It stopped before SSH execution, so no remote command and no
cluster mutation occurred. The corrected workflow rendered first and decoded
the single focused field locally.

## Proof that live monitoring was not changed

Read-only checks after preparation:

```text
Helm release: monitoring-stack
namespace: monitoring
revision: 1
status: deployed
chart: kube-prometheus-stack-91.4.1
app version: v0.94.0
Prometheus additionalScrapeConfigs reference: <none>
additional scrape Secret: absent
```

Therefore `frontend-vm` is prepared in Git working files but is not yet a live
Prometheus target.

## Temporary-file cleanup

The resolved deletion target was checked first:

```text
/tmp/buet-step11a1-chart-20260924
```

Its top-level contents were only:

```text
input
kube-prometheus-stack
rendered-scrape-secret.yaml
```

Then only that directory was removed, and `test ! -e` confirmed deletion. No
rendered Secret or full manifest was retained.

## Rollback

Because nothing was applied to Kubernetes, rollback currently means removing
only this newly added repository file:

```text
monitoring/external-vms/scrape-values.yaml
```

Do not perform that rollback unless separately requested. There is no Helm,
Kubernetes, OpenStack, frontend application, or node_exporter state to undo for
Step 11A1.

## Result and next permission boundary

```text
base values changed: no
new additive overlay: yes
chart version/digest pinned: yes
hashes matched: yes
Helm lint: passed
focused render: passed
credentials recorded: no
live Helm revision changed: no (still revision 1)
live additional scrape config changed: no
Step 11A1: complete
```

The next proposed action is **Step 11A2 - apply and verify the frontend-vm
scrape configuration**. It would be the first live monitoring mutation in this
sequence: run an atomic Helm upgrade with both values files, wait for the
operator reconciliation, and verify the single target is `UP` with the expected
labels. It requires separate explicit approval.
