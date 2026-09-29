# Step 7 — First kube-prometheus-stack installation attempt

## Status

- Permission received: `Approve Step 7`
- Execution date: 2026-09-23 (Asia/Dhaka)
- Step type: substantial Kubernetes mutation with Helm atomic rollback
- Installation result: **failed readiness timeout**
- Atomic rollback result: **Helm release and workloads uninstalled**
- Root cause: Grafana first-run migrations repeatedly exceeded its liveness window
- Existing application changes: none
- Automatic retry: not performed

## Outcome in plain language

The monitoring components were created and most became healthy. Grafana downloaded successfully and began its first database migrations, but those migrations took longer than Grafana's default liveness-probe window while constrained to a 500m CPU limit.

Kubernetes repeatedly restarted only the Grafana container before it could finish. Helm waited for 15 minutes, reached the approved timeout, and automatically uninstalled the release because `--atomic` was enabled.

The existing BUET-PaaS applications were not edited. The monitoring namespace still exists. Helm's rollback left the chart's 10 CRDs and one webhook-certificate Secret, which are explicitly inventoried below.

## Final pre-install safety gate

### Artifact hashes

```text
values.yaml
2d98fe9150c90ae7709864590b3145a94c8e369f6b1e9c06c9cf8d53f79a57b7

kube-prometheus-stack-91.4.1.tgz
1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb
```

Both hashes matched Steps 4 and 6.

### Helm and authorization state

```text
Helm releases in monitoring: none
Can create CRDs: yes
Can create ClusterRoles: yes
Can create ClusterRoleBindings: yes
Can create mutating webhooks: yes
Can create Deployments in monitoring: yes
Can create Services in monitoring: yes
Can create Secrets in monitoring: yes
```

The cluster-scoped authorization queries printed expected informational warnings that those resources are not namespace-scoped.

### Cluster state immediately before installation

```text
k3s-control-01   Ready   v1.36.2+k3s1   CPU 105m/2%   memory 1866Mi/23%
k3s-worker-01    Ready   v1.36.4+k3s1   CPU 78m/1%    memory 2558Mi/32%
k3s-worker-02    Ready   v1.36.2+k3s1   CPU 153m/3%   memory 1083Mi/13%
k3s-worker-03    Ready   v1.36.2+k3s1   CPU 74m/1%    memory 957Mi/12%
```

`k3s-worker-01` had been updated externally from patch version 1.36.2 to 1.36.4 since Step 2. This was not caused by the monitoring work. All nodes remained on Kubernetes minor version 1.36 and were Ready.

Namespace `monitoring` contained no workloads and no Prometheus Operator CRDs before the command.

The pre-existing application problem was recaptured:

```text
namespace: 2105062
deployment: to-do-backend-deployment
ready: 0/1
available: 0
restarts before monitoring install: 66
```

## The single installation command

Input from Windows through SSH to `k3s-user`:

```text
helm upgrade --install monitoring-stack \
  /tmp/buet-paas-monitoring-step6-20260923/kube-prometheus-stack-91.4.1.tgz \
  --namespace monitoring \
  --values /tmp/buet-paas-monitoring-step6-20260923/values.yaml \
  --atomic \
  --wait \
  --timeout 15m \
  --history-max 10
```

Initial output:

```text
Release "monitoring-stack" does not exist. Installing it now.
```

No second mutation or manual patch was run while Helm owned the transaction.

## Installation progress

### Components that became healthy

At approximately four minutes:

```text
alertmanager-monitoring-stack-kube-prom-alertmanager-0   2/2 Running
monitoring-stack-kube-prom-operator                      1/1 Running
monitoring-stack-kube-state-metrics                      1/1 Running
monitoring-stack-prometheus-node-exporter                4/4 Ready across all four nodes
prometheus-monitoring-stack-kube-prom-prometheus-0       2/2 Running
```

The operator-created StatefulSets both reached `1/1` Ready. All four node-exporter Pods reached Ready, one on each Linux node.

Images successfully pulled included:

```text
prometheus-operator:v0.94.0
prometheus:v3.14.0-distroless
alertmanager:v0.34.0
node-exporter:v1.12.1-distroless
kube-state-metrics:v2.20.0
k8s-sidecar:2.11.2
grafana:13.2.2-distroless
kube-webhook-certgen:1.8.8
```

### Existing DNS warning observed on new Pods

Each node-exporter Pod eventually received:

```text
DNSConfigForming: Nameserver limits were exceeded, some nameservers have been omitted
```

This is the same node-level DNS configuration issue recorded on CoreDNS and MetalLB Pods in Step 2. Monitoring did not create the underlying nameserver configuration, but host-networked node-exporter Pods inherit and expose the existing warning.

## Grafana failure sequence

Grafana's two sidecars became Ready. The main Grafana container downloaded a 460 MB image and started first-run SQLite migrations.

Rendered resource bounds were confirmed on the live container:

```text
CPU request: 100m
CPU limit: 500m
Memory request: 128Mi
Memory limit: 512Mi
```

Probe configuration from the packaged Grafana chart:

```yaml
startupProbe: {}

readinessProbe:
  httpGet:
    path: /api/health
    port: grafana

livenessProbe:
  httpGet:
    path: /api/health
    port: grafana
  initialDelaySeconds: 60
  timeoutSeconds: 30
  failureThreshold: 10
```

Because `startupProbe` was empty, liveness checks began after 60 seconds. The liveness probe then allowed roughly another 100 seconds of failed checks before restarting Grafana.

Observed sequence:

```text
Grafana image pulled successfully.
Container began SQLite migrations.
Port 3000 remained closed while migrations ran.
Readiness probe: connection refused.
Liveness probe: connection refused.
Grafana container restarted.
EmptyDir database persisted across container restarts.
Next run continued completing additional migrations.
```

Grafana restarted four times before Helm's 15-minute timeout. Each cycle logged successful migrations; no invalid configuration, permission denial, out-of-memory event, or image-pull failure appeared.

The third cycle progressed beyond migrations into alerting and query-service initialization:

```text
template definitions loaded
Applying new configuration to Alertmanager
Setting up remote write using data sources
Query Service initialization
registering usage stat providers
```

However, the liveness window expired again before `/api/health` became reachable.

The Grafana log masked the administrator password as `*********`; no password or Secret value was copied into this document.

## Helm result

Final output:

```text
Error: release monitoring-stack failed, and has been uninstalled due to atomic being set: context deadline exceeded
```

Exit code: `1`.

This is a failed installation attempt, not a successful deployment.

## Polling and diagnostic command issues

One local JavaScript polling wrapper returned:

```text
SyntaxError: Invalid or unexpected token
```

It failed before polling the SSH session and did not interrupt Helm. Polling immediately resumed against the same process session.

The first attempt to inspect the packaged Grafana probe defaults assumed the dependency was stored as a nested `.tgz`:

```text
tar: kube-prometheus-stack/charts/grafana-13.2.5.tgz: Not found in archive
gzip: stdin: unexpected end of file
```

A filename search confirmed the dependency was expanded inside the parent archive. The corrected read-only path was:

```text
kube-prometheus-stack/charts/grafana/values.yaml
```

The corrected extraction succeeded and produced the probe configuration shown above. Neither diagnostic error changed any resource or file.

## Atomic rollback audit

### Removed successfully

```text
Helm release monitoring-stack: absent
Pods: none
Services: none
Deployments: none
StatefulSets: none
DaemonSets: none
Jobs: none
PVCs: none
release-generated application Secrets: none
release-labelled ClusterRoles/ClusterRoleBindings: none
release-labelled mutating/validating webhooks: none
```

`helm status monitoring-stack --namespace monitoring` returned:

```text
Error: release: not found
```

### Retained CRDs

Helm does not automatically delete chart CRDs during uninstall/atomic rollback. These 10 CRDs remain:

```text
alertmanagerconfigs.monitoring.coreos.com
alertmanagers.monitoring.coreos.com
podmonitors.monitoring.coreos.com
probes.monitoring.coreos.com
prometheusagents.monitoring.coreos.com
prometheuses.monitoring.coreos.com
prometheusrules.monitoring.coreos.com
scrapeconfigs.monitoring.coreos.com
servicemonitors.monitoring.coreos.com
thanosrulers.monitoring.coreos.com
```

Queries across Alertmanager, Prometheus, ServiceMonitor, PodMonitor, and PrometheusRule kinds returned:

```text
No resources found
```

The CRDs are therefore present but currently contain no monitoring custom-resource instances.

### Retained webhook certificate Secret

One hook-generated Secret remains:

```text
Name: monitoring-stack-kube-prom-admission
Namespace: monitoring
Type: Opaque
Labels: none
Annotations: none
Data keys and sizes:
  ca:   566 bytes
  cert: 660 bytes
  key:  227 bytes
```

The certificate/key values were not displayed. This Secret was generated by the admission certificate Job and was not removed with the Helm release.

The namespace otherwise contains only the Step 5 bootstrap objects:

```text
configmap/kube-root-ca.crt
serviceaccount/default
```

## Existing-cluster regression check after rollback

All four nodes remained Ready:

```text
k3s-control-01   Ready   CPU 95m/2%    memory 2177Mi/27%
k3s-worker-01    Ready   CPU 182m/4%   memory 3203Mi/40%
k3s-worker-02    Ready   CPU 95m/2%    memory 1104Mi/13%
k3s-worker-03    Ready   CPU 120m/3%   memory 1011Mi/12%
```

The temporary memory increase on worker 01 followed the large Grafana image pull/startup and remained below pressure levels. No node became NotReady.

The known application issue remained unchanged in availability:

```text
to-do-backend-deployment   0/1 ready   0 available
```

No existing application Deployment, Service, Ingress, namespace, PVC, or Helm release was intentionally changed by Step 7.

## Rollback/cleanup decision

No manual deletion was performed.

Current monitoring-related cluster state is:

```text
namespace monitoring: retained from Step 5
10 empty monitoring CRDs: retained from failed Step 7
webhook certificate Secret: retained from failed Step 7
Helm release: absent
monitoring workloads: absent
```

Deleting CRDs or the certificate Secret is destructive and requires explicit permission. Retaining the CRDs is useful for a retry because they are the exact CRDs from the verified chart and contain no instances.

Before a retry, the orphan certificate Secret should be reassessed. A clean retry can delete only that Secret after confirming no webhook configuration exists, allowing the Helm hook to regenerate it.

## Local repository impact

No values file was changed during this attempt. New documentation only:

```text
step-7.md
implementation of monitoring.md journal entry 008
```

Existing tracked source files remain unchanged. No commit was created.

## Step 7 conclusion

```text
Installation:                   FAILED
Failure mode:                   Grafana startup/liveness timeout
Helm atomic uninstall:          COMPLETED
Helm release remaining:         NO
Monitoring workloads remaining: NO
CRDs remaining:                 10, empty
Hook Secret remaining:          1
Existing nodes Ready:           4/4
Existing application changes:   NONE
Automatic retry:                NOT PERFORMED
```

## Recommended next phase — not yet executed

Do not proceed to Step 8 because there is no installed release to compare.

The recommended next phase is **Step 7R1 — prepare and validate retry settings**, with no Kubernetes mutation:

1. update only the local Grafana overrides:

   ```yaml
   grafana:
     resources:
       requests:
         cpu: 100m
         memory: 128Mi
       limits:
         cpu: 1
         memory: 512Mi
     startupProbe:
       httpGet:
         path: /api/health
         port: grafana
       initialDelaySeconds: 10
       periodSeconds: 10
       timeoutSeconds: 5
       failureThreshold: 90
   ```

2. retain the existing liveness/readiness probes; Kubernetes will defer them until the startup probe succeeds;
3. increase a future Helm retry timeout to 25 minutes;
4. render and lint locally and remotely again;
5. verify the startup probe and 1-core Grafana limit in the rendered Deployment;
6. write the result into a separate retry-preparation record;
7. make no cluster change during retry preparation.

This gives Grafana up to roughly 15 minutes to complete first-run migrations before liveness checks begin. The 1-core limit uses available cluster headroom and should materially shorten migration time.

After retry preparation passes, request separate permission for **Step 7R2 — retry installation**. That future approval must explicitly cover:

- deleting only the orphan `monitoring-stack-kube-prom-admission` Secret after re-verifying no monitoring webhook exists;
- retaining the 10 empty CRDs;
- retrying the pinned Helm installation with `--atomic --wait --timeout 25m`.

Do not edit values, delete residue, or retry installation until the user explicitly approves Step 7R1.
