# Step 7R2 — Retry the monitoring-stack installation

## Status

- Local date: 2026-09-24 (Asia/Dhaka)
- Cluster/VM UTC date: 2026-09-23
- Permission: explicitly approved by the user with `Approve Step 7R2`
- Installation result: **successful**
- Helm release: `monitoring-stack`, revision 1, status `deployed`
- Grafana/Prometheus/Alertmanager health endpoints: healthy
- Existing application configuration changed: no
- OpenStack configuration changed: no
- Follow-up required: inter-VM TCP 9100 is blocked, leaving 3 of 25 Prometheus targets down

## What this step was authorized to do

Step 7R2 was the separately approved cluster-changing retry. Its approved sequence was:

1. recheck cluster health and Step 7 residue;
2. prove that the remaining admission certificate Secret was orphaned;
3. delete only that orphan Secret;
4. transfer the corrected Step 7R1 values under a new remote filename;
5. verify hashes, lint, and render remotely;
6. retry the pinned Helm installation with `--atomic --wait --timeout 25m`;
7. monitor startup and verify the resulting stack;
8. avoid any OpenStack or unrelated application change.

## Connection path

```text
Local repository:
E:\BUET\4-1\Sessional\Capstone\monitoring\BUET-PaaS

Administration VM:
ubuntu@192.168.64.242 (k3s-user)

SSH identity:
C:\Users\USER\Downloads\mykey.pem

Remote protected artifact directory:
/tmp/buet-paas-monitoring-step6-20260923
```

The private key content was never displayed or copied into the repository.

## Initial execution-sandbox issue

Four parallel read-only SSH checks were initially attempted inside the restricted local execution environment. All four stopped locally with:

```text
ssh: connect to host 192.168.64.242 port 22: Permission denied
```

They did not reach the VM and did not change anything. The same SSH route was then run with the approved external-network permission.

Connection confirmation:

```text
hostname: k3s-user
user: ubuntu
remote UTC time: 2026-09-23T20:05:47Z
```

## Read-only safety gate

### Helm and namespace residue

Commands:

```bash
helm status monitoring-stack -n monitoring
kubectl get all,pvc -n monitoring -o wide
kubectl describe secret monitoring-stack-kube-prom-admission -n monitoring
```

Output:

```text
Error: release: not found
No resources found in monitoring namespace.

Name: monitoring-stack-kube-prom-admission
Namespace: monitoring
Labels: <none>
Annotations: <none>
Type: Opaque
Data keys and sizes only:
  cert: 660 bytes
  key: 227 bytes
  ca: 566 bytes
```

No Secret value was printed.

### Admission webhooks

Command:

```bash
kubectl get \
  mutatingwebhookconfigurations.admissionregistration.k8s.io,\
  validatingwebhookconfigurations.admissionregistration.k8s.io \
  -o custom-columns=KIND:.kind,NAME:.metadata.name,SERVICE_NAMESPACE:.webhooks[*].clientConfig.service.namespace,SERVICE_NAME:.webhooks[*].clientConfig.service.name \
  --no-headers
```

Output before cleanup:

```text
ValidatingWebhookConfiguration metallb-webhook-configuration metallb-system metallb-webhook-service
```

No webhook referenced the monitoring namespace or orphan Secret. Therefore, deleting only the orphan Secret was safe for the clean retry.

### Retained CRDs and instance emptiness

The same 10 Step 7 CRDs were present:

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

Querying all corresponding custom resources returned:

```text
No resources found
```

The CRDs were retained as planned.

### Nodes and capacity

```text
k3s-control-01 Ready v1.36.2+k3s1
k3s-worker-01  Ready v1.36.4+k3s1
k3s-worker-02  Ready v1.36.2+k3s1
k3s-worker-03  Ready v1.36.2+k3s1

Before retry:
k3s-control-01 96m CPU (2%), 2105Mi memory (26%)
k3s-worker-01  88m CPU (2%), 3216Mi memory (40%)
k3s-worker-02  100m CPU (2%), 1148Mi memory (14%)
k3s-worker-03  76m CPU (1%), 1035Mi memory (13%)
```

All required create permissions and the specific monitoring-namespace Secret delete permission returned `yes`.

### Existing application baseline immediately before retry

The namespace `2105062` had six healthy deployments and the same pre-existing unhealthy deployment:

```text
to-do-backend-deployment: 0/1
pod status: CrashLoopBackOff
restart count: 113
```

This condition existed before the retry.

## Intended cleanup mutation

The verified orphan Secret had UID:

```text
71c3a970-0db2-4787-90dc-aac55da68886
```

Command:

```bash
kubectl delete secret monitoring-stack-kube-prom-admission -n monitoring
```

Output:

```text
secret "monitoring-stack-kube-prom-admission" deleted
```

Verification:

```text
Error from server (NotFound): secrets "monitoring-stack-kube-prom-admission" not found
```

The combined command returned exit code 1 only because the final verification intentionally queried the deleted object. The deletion succeeded.

No CRD, namespace, application resource, or unrelated Secret was deleted.

## Corrected values transfer

To preserve the Step 6 values for comparison, the corrected file was uploaded under a new name:

```powershell
scp -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ".\monitoring\prometheus\values.yaml" `
  ubuntu@192.168.64.242:/tmp/buet-paas-monitoring-step6-20260923/values-step7r2.yaml
```

The transfer exited successfully with no output.

Remote permissions and hashes:

```text
600 ubuntu:ubuntu values.yaml
600 ubuntu:ubuntu values-step7r2.yaml
644 ubuntu:ubuntu kube-prometheus-stack-91.4.1.tgz

original Step 6 values:
2d98fe9150c90ae7709864590b3145a94c8e369f6b1e9c06c9cf8d53f79a57b7

corrected Step 7R2 values:
c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b

pinned chart archive:
1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb
```

## Remote lint and render gate

Commands used the pinned archive and corrected values:

```bash
helm lint \
  /tmp/buet-paas-monitoring-step6-20260923/kube-prometheus-stack-91.4.1.tgz \
  --values /tmp/buet-paas-monitoring-step6-20260923/values-step7r2.yaml \
  --kube-version 1.36.2

helm template monitoring-stack \
  /tmp/buet-paas-monitoring-step6-20260923/kube-prometheus-stack-91.4.1.tgz \
  --namespace monitoring \
  --values /tmp/buet-paas-monitoring-step6-20260923/values-step7r2.yaml \
  --kube-version 1.36.2 \
  --include-crds >/dev/null
```

First output:

```text
1 chart(s) linted, 0 chart(s) failed
FULL_RENDER_EXIT=True
```

`True` was not the remote numeric exit code: Windows PowerShell expanded `$?` locally inside the SSH command. No file or cluster resource was affected. The validation was repeated using remote `set -e`, avoiding `$?` entirely:

```text
1 chart(s) linted, 0 chart(s) failed
FULL_RENDER=PASS
```

Focused Grafana render:

```yaml
startupProbe:
  failureThreshold: 90
  httpGet:
    path: /api/health
    port: grafana
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
livenessProbe:
  failureThreshold: 10
  httpGet:
    path: /api/health
    port: grafana
readinessProbe:
  httpGet:
    path: /api/health
    port: grafana
resources:
  limits:
    cpu: 1
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

No full manifest or generated password was retained by this remote validation.

## Helm installation retry

Exact command:

```bash
helm upgrade --install monitoring-stack \
  /tmp/buet-paas-monitoring-step6-20260923/kube-prometheus-stack-91.4.1.tgz \
  --namespace monitoring \
  --values /tmp/buet-paas-monitoring-step6-20260923/values-step7r2.yaml \
  --atomic \
  --wait \
  --timeout 25m \
  --history-max 10
```

Final result:

```text
NAME: monitoring-stack
NAMESPACE: monitoring
STATUS: deployed
REVISION: 1
```

Helm history:

```text
REVISION 1
STATUS deployed
CHART kube-prometheus-stack-91.4.1
APP VERSION v0.94.0
DESCRIPTION Install complete
```

Atomic rollback was enabled throughout but was not needed.

## Grafana startup timeline

All timestamps below are UTC. Repetitive log checks were sanitized for password/secret/token-shaped fields.

```text
20:09:34  Pod 0/3, ContainerCreating
20:09:56  Pod 2/3; main Grafana running; 0 restarts
20:10:51  migrations advancing; 0 restarts
20:11:45  migrations advancing; Prometheus/Alertmanager becoming ready
20:12:39  all other monitoring Pods ready; Grafana 2/3, 0 restarts
20:13:30  migrations advancing; 0 restarts
20:14:20  migrations advancing; 0 restarts
20:15:10  migrations advancing; 0 restarts
20:16:01  migrations advancing; 0 restarts
20:16:50  migrations advancing; 0 restarts
20:17:39  migrations advancing; 0 restarts
20:18:29  migrations advancing; 0 restarts
20:19:20  migrations advancing; 0 restarts
20:20:09  migrations advancing; 0 restarts
20:20:59  migrations advancing; 0 restarts
20:21:49  migrations advancing; 0 restarts
20:22:43  migrations advancing; 0 restarts
20:23:39  secret-storage migrations; 0 restarts
20:24:31  resource migrations; 0 restarts
approximately 20:24:44 startup threshold reached; main container restarted once
20:25:20  resumed persisted migrations; 1 restart
20:25:52  unified storage migrations completed successfully
20:29:00  background plugins installing successfully
approximately 20:30:08 Grafana became 3/3 Ready
20:34:50  final check: Grafana 3/3 Ready, still exactly 1 restart
```

The restart did not discard progress because Grafana's SQLite data is in an `emptyDir` shared for the Pod lifetime. The restarted container skipped completed migrations, finished the remaining migrations and plugins, then became healthy before Helm's 25-minute timeout.

Observed transient Grafana messages:

```text
database is locked (SQLITE_BUSY)
failed to prune history
```

These occurred during concurrent initial provisioning. Grafana subsequently became Ready, its database health endpoint returned `ok`, and alert scheduling started. They are recorded for traceability but did not prevent successful installation.

## Installed resource health

Final Pods:

```text
Alertmanager:             2/2 Running, 0 restarts
Grafana:                  3/3 Running, 1 startup restart
Prometheus Operator:      1/1 Running, 0 restarts
kube-state-metrics:       1/1 Running, 0 restarts
node-exporter control:    1/1 Running, 0 restarts
node-exporter worker 01:  1/1 Running, 0 restarts
node-exporter worker 02:  1/1 Running, 0 restarts
node-exporter worker 03:  1/1 Running, 0 restarts
Prometheus:               2/2 Running, 0 restarts
```

Controllers:

```text
Grafana Deployment: 1/1
Prometheus Operator Deployment: 1/1
kube-state-metrics Deployment: 1/1
Prometheus StatefulSet: 1/1
Alertmanager StatefulSet: 1/1
node-exporter DaemonSet: 4 desired, 4 ready
```

The MVP intentionally has no PVC; Prometheus, Alertmanager, and Grafana storage remain ephemeral as defined in the reviewed values.

Prometheus and Alertmanager custom resources both reported:

```text
READY: 1
RECONCILED: True
AVAILABLE: True
```

Admission resources now correctly reference the operator service in `monitoring`:

```text
MutatingWebhookConfiguration monitoring-stack-kube-prom-admission
ValidatingWebhookConfiguration monitoring-stack-kube-prom-admission
```

The unrelated MetalLB validating webhook remained unchanged.

## Functional endpoint checks

The services remain private `ClusterIP` services.

Grafana API health:

```json
{
  "database": "ok",
  "version": "13.2.2",
  "commit": "1bea008f7e4e858b6824c9e364d608bd4d10b13a"
}
```

Prometheus readiness:

```text
Prometheus Server is Ready.
```

Alertmanager readiness:

```text
OK
```

The Grafana Secret was inspected with `kubectl describe` only:

```text
admin-password: 40 bytes
admin-user: 5 bytes
ldap-toml: 0 bytes
```

No credential value was displayed or written to documentation.

## Grafana dashboards

The Grafana sidecar discovered 23 dashboard ConfigMaps. The inventory includes:

```text
Alertmanager / Overview
API server
Cluster total
Grafana overview
CoreDNS
Kubernetes resources: cluster, namespace, node, pod, and workload
Kubernetes nodes and node resource usage
Namespaces by pod and workload
Persistent volume usage
Prometheus overview
Workload networking and totals
```

An initial inventory command selected `.data`, which printed the full non-secret dashboard JSON and produced excessive output. It made no change and exposed no credential. The corrected command used `-o name` and `wc -l`, returning exactly 23 names.

## Prometheus scrape-target verification

Prometheus target API summary:

```json
{
  "status": "success",
  "activeTargets": 25,
  "healthCounts": {
    "up": 22,
    "down": 3
  },
  "droppedTargets": 0
}
```

Down targets:

```text
node-exporter 192.168.128.101:9100 context deadline exceeded
node-exporter 192.168.128.121:9100 context deadline exceeded
node-exporter 192.168.128.122:9100 context deadline exceeded
```

The node-exporter target on `192.168.128.123`, the node currently hosting Prometheus, is up.

## Alert verification

Prometheus returned six firing alerts:

```text
KubePodCrashLooping                 namespace 2105062
KubePodNotReady                    namespace 2105062
KubeDeploymentReplicasMismatch     namespace 2105062
KubeDeploymentRolloutStuck         namespace 2105062
TargetDown                         namespace monitoring
Watchdog                           expected always-firing health alert
```

The first four correctly detect the pre-existing `to-do-backend` problem. `TargetDown` corresponds to the three unreachable node-exporter targets.

## TCP 9100 diagnosis

Read-only TCP checks were run from the already trusted control-plane VM:

```text
k3s-control-01 -> 192.168.128.101:9100 succeeded (itself)
k3s-control-01 -> 192.168.128.121:9100 timed out
k3s-control-01 -> 192.168.128.122:9100 timed out
k3s-control-01 -> 192.168.128.123:9100 timed out
```

The same checks from worker 01 returned:

```text
k3s-worker-01 -> 192.168.128.101:9100 timed out
k3s-worker-01 -> 192.168.128.121:9100 succeeded (itself)
k3s-worker-01 -> 192.168.128.122:9100 timed out
k3s-worker-01 -> 192.168.128.123:9100 timed out
```

This proves:

- every tested exporter listens successfully on its local VM;
- TCP 9100 traffic between VMs is blocked;
- the problem is not a crashed node-exporter Pod;
- the likely control point is the OpenStack security group and/or VM firewall policy.

No OpenStack rule or VM firewall was changed in Step 7R2.

## Node health after installation

```text
k3s-control-01 Ready, CPU 2%, memory 26%
k3s-worker-01  Ready, CPU 4%, memory 42%
k3s-worker-02  Ready, CPU 3%, memory 15%
k3s-worker-03  Ready, CPU 3%, memory 19%
```

The monitoring stack did not exhaust cluster capacity.

The same pre-existing application remained unhealthy after installation:

```text
to-do-backend-deployment: 0/1
restart count after verification: 121
```

All six other listed deployments in namespace `2105062` remained `1/1`. Monitoring did not edit or restart those application deployments.

## Other warnings

node-exporter Pods continue to report the pre-existing K3s/node resolver warning:

```text
DNSConfigForming: Nameserver limits were exceeded; some nameservers were omitted.
```

This warning existed in Step 7 and does not prevent the exporters from running. It was not changed in this step.

## Read-only diagnostic errors and corrections

1. Four initial SSH checks were blocked by the local sandbox and never reached the VM. They were rerun with approved network permission.
2. PowerShell expanded a remote `$?` to `True`; validation was rerun with remote `set -e` and returned `FULL_RENDER=PASS`.
3. Two JSONPath condition-format commands were altered by cross-shell quoting and returned `unterminated quoted string`. They were replaced with `kubectl get`, `describe`, and `top` checks.
4. The first dashboard inventory printed complete dashboard JSON because `.data` was selected. It contained no credential. The corrected names-only inventory returned 23 ConfigMaps.

None of these diagnostic issues changed Kubernetes, OpenStack, or application state.

## Step 7R2 result

```text
orphan Secret cleanup: successful
corrected values transfer/hash verification: successful
remote lint: successful
remote full render: successful
atomic Helm installation: successful
Helm status: deployed, revision 1
monitoring Pods/controllers: ready
Grafana API/database: healthy
Prometheus: ready
Alertmanager: ready
Grafana dashboards provisioned: 23 ConfigMaps
Prometheus targets: 22/25 up
remaining limitation: inter-VM TCP 9100 blocked for three node-exporter targets
existing application modifications: none
OpenStack modifications: none
```

## Proposed next phase — not authorized

Before claiming complete four-node host monitoring, perform **Step 7R3A: read-only OpenStack/security inspection**:

1. identify the security group(s) attached to all four K3s VM ports;
2. list their ingress rules without modifying them;
3. check whether VM-local firewall rules also filter TCP 9100;
4. determine the narrowest safe source (prefer the K3s node security group rather than public CIDRs);
5. document the exact proposed rule and rollback command.

Only after separate approval should **Step 7R3B** add a least-privilege TCP 9100 rule and verify that all 25 targets are up. Do not expose TCP 9100 to `0.0.0.0/0`.

Grafana is already running privately. A later access step can use SSH tunneling/port-forwarding without exposing Grafana publicly.

