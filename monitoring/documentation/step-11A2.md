# Step 11A2 - Apply and verify frontend-vm scrape configuration

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: explicitly approved with `Approve Step 11A2 - apply and verify frontend-vm scrape configuration`
- Scope: apply the prepared frontend-only Prometheus scrape overlay
- Final state: **completed successfully**
- Final Helm revision: `4`, status `deployed`
- OpenStack mutation: none
- frontend-vm configuration mutation: none
- application configuration mutation: none

## Intended change

Apply these two reviewed values files, in this order:

```text
monitoring/prometheus/values.yaml
monitoring/external-vms/scrape-values.yaml
```

File-integrity evidence:

```text
c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b  values.yaml
a5b4c936232457e957f1c2b2fab3dfc3ec1799c9d21df0490fbc865caeef1a32  scrape-values.yaml
```

The local and remote hashes matched. The pinned chart remained:

```text
kube-prometheus-stack: 91.4.1
application version: v0.94.0
OCI digest: sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
```

## Pre-change baseline

```text
Helm release: monitoring-stack
revision: 1
status: deployed
Prometheus additional scrape reference: none
Prometheus active targets: 25
Prometheus targets UP: 25
standalone-node-exporters targets: 0
Kubernetes nodes Ready: 4/4
monitoring Pods: all Ready
node-exporter DaemonSet: 4/4
Grafana dashboards represented by dashboard ConfigMaps: 23
```

The pre-existing application issue was still present:

```text
2105062/to-do-backend-deployment: 0/1 available
```

All other observed Deployments were available. This issue predates Step 11A2
and was not modified.

The existing K3s-to-frontend path returned 949 metric lines before the upgrade.
The Grafana admin Secret was fingerprinted without printing the credential so
that unintended credential rotation could be detected.

## Preflight and dry-run

The reviewed files were copied to the exact temporary directory:

```text
/tmp/buet-step11a2-20260924
```

A server-side Helm dry-run used `--hide-secret`:

```bash
helm upgrade monitoring-stack \
  oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack \
  --version 91.4.1 \
  --namespace monitoring \
  -f values.yaml \
  -f scrape-values.yaml \
  --dry-run=server \
  --hide-secret
```

Result:

```text
NAME: monitoring-stack
NAMESPACE: monitoring
STATUS: pending-upgrade
REVISION: 2
```

The dry-run rendered the expected additional-scrape Secret resource. A final
`grep` for the job name did not match because `--hide-secret` intentionally
redacted the Secret body. The dry-run itself succeeded, and Step 11A1 had
already decoded and verified the focused Secret render. No live state changed
during the dry-run.

One earlier read-only Prometheus target-count command had a nested jq/PowerShell
quote error. It did not modify Prometheus. A quote-free retry recorded 25/25
targets UP and zero standalone targets.

## First atomic upgrade attempt

Command pattern:

```bash
helm upgrade monitoring-stack \
  oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack \
  --version 91.4.1 \
  --namespace monitoring \
  -f values.yaml \
  -f scrape-values.yaml \
  --atomic \
  --cleanup-on-fail \
  --wait \
  --timeout 15m \
  --history-max 10
```

Prometheus accepted the additional-scrape reference and remained available.
Helm also initiated a Grafana rolling update. The old Grafana Pod stayed 3/3
Ready while the new Pod pulled the approximately 460 MB Grafana image and ran
first-start SQLite migrations on its ephemeral storage.

The migrations logged repeated successful entries with zero container
restarts, but image pull plus migrations exceeded the total 15-minute Helm
timeout:

```text
Error: UPGRADE FAILED: release monitoring-stack failed, and has been rolled
back due to atomic being set: context deadline exceeded
```

This was a timeout sizing error, not an invalid scrape configuration.

## Atomic rollback verification

Helm automatically produced revision 3:

```text
revision 2: failed - context deadline exceeded
revision 3: deployed - Rollback to 1
```

After rollback:

```text
old Grafana Pod: 3/3 Ready
Prometheus: 1/1 available
additional scrape reference: none
additional scrape Secret: absent
Grafana admin credential fingerprint: unchanged
monitoring Pods: healthy
```

No manual recovery was required. This clean rollback was verified before any
retry.

## Corrected atomic upgrade

The same chart and values were retried without configuration changes. Only the
timeout was corrected from 15 minutes to 30 minutes based on the observed
Grafana initialization duration:

```bash
helm upgrade monitoring-stack \
  oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack \
  --version 91.4.1 \
  --namespace monitoring \
  -f values.yaml \
  -f scrape-values.yaml \
  --atomic \
  --cleanup-on-fail \
  --wait \
  --timeout 30m \
  --history-max 10
```

Result:

```text
Release "monitoring-stack" has been upgraded. Happy Helming!
STATUS: deployed
REVISION: 4
```

The new Grafana Pod completed migrations, became 3/3 Ready with zero restarts,
and only then was the old Pod scaled down. No Grafana outage was observed.

## Live configuration verification

The Prometheus custom resource now references:

```text
Secret: monitoring-stack-kube-prom-prometheus-scrape-confg
Key: additional-scrape-configs.yaml
Prometheus available replicas: 1
Prometheus updated replicas: 1
```

Decoded non-credential scrape configuration:

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

The Grafana admin Secret fingerprint matched the pre-change fingerprint. The
credential was neither printed nor stored in documentation.

Service readiness through the Kubernetes API proxy:

```text
Prometheus: Prometheus Server is Ready.
Alertmanager: OK
Grafana database: ok
Grafana version: 13.2.2
```

## Prometheus target and metric verification

Post-change target summary:

```text
active targets: 26
UP targets: 26
DOWN targets: 0
frontend targets: 1
```

Exact frontend target:

```json
{"health":"up","lastError":"","scrapeUrl":"http://192.168.128.15:9100/metrics","job":"standalone-node-exporters","instance":"frontend-vm","service":"frontend","environment":"buet-paas","deployment_type":"standalone-vm"}
```

PromQL/API verification:

```text
up{job="standalone-node-exporters",instance="frontend-vm"}
status: success
result count: 1
value: 1

node_uname_info{job="standalone-node-exporters",instance="frontend-vm"}
status: success
result count: 1
nodename: frontend-vm
machine: x86_64
sysname: Linux
```

This proves both scrape health and actual node metric ingestion. It is not only
a TCP connectivity test.

## Post-change regression state

```text
Kubernetes nodes: 4/4 Ready
monitoring Pods: all Ready
Prometheus: 2/2 containers Ready
Alertmanager: 2/2 containers Ready
Grafana: 3/3 containers Ready, 0 restarts
kube-state-metrics: 1/1 Ready
node-exporter DaemonSet: 4/4 Ready
dashboard ConfigMaps: 23
all Prometheus targets: 26/26 UP
```

Application Deployments matched the baseline. The only unavailable Deployment
remained the pre-existing `2105062/to-do-backend-deployment` at 0/1.

Frontend VM regression:

```text
node_exporter: enabled, active, 0 restarts
listener: 192.168.128.15:9100 only
local metrics: 949 lines
Nginx: active and local HTTP request successful
Next.js port 3000: local HTTP request successful
failed systemd units: none
```

No OpenStack rule, VM unit, application file, or frontend configuration was
changed in Step 11A2.

The recent Grafana startup-probe warnings in Kubernetes Events occurred while
the new process was running migrations. They are historical events; the final
Pod is 3/3 Ready with zero restarts. Node-exporter `DNSConfigForming` warnings
about excess nameservers were also present independently and did not make any
target unhealthy.

## Temporary-file cleanup

Before deletion, the resolved target was verified as:

```text
/tmp/buet-step11a2-20260924
```

It contained only:

```text
values.yaml
scrape-values.yaml
dry-run.txt
```

Only this exact directory was removed. `test ! -e` confirmed deletion.

## Rollback if later required

The verified pre-scrape state is Helm revision 3. A separately approved rollback
can use:

```bash
helm rollback monitoring-stack 3 \
  --namespace monitoring \
  --wait \
  --timeout 30m
```

Then verify:

```text
release deployed
Prometheus additionalScrapeConfigs reference absent
additional scrape Secret absent
25 original targets UP
monitoring Pods healthy
applications unchanged
```

Do not remove node_exporter or the `monitoring-exporter` OpenStack security group
merely to roll back Prometheus scraping; those are independent changes with
their own rollback procedures.

## Final result

```text
prepared overlay applied: yes
atomic rollback protection tested: yes
final Helm status: deployed
final Helm revision: 4
frontend target: UP
frontend metric ingestion: verified
all targets: 26/26 UP
Grafana dashboards provisioned: 23
credential rotation: no
application regression: none observed
OpenStack/VM/app mutation: none
Step 11A2: complete
```

No Git commit or push was performed.
