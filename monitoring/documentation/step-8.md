# Step 8 — Mandatory post-install regression comparison

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: authorized by the user's instruction to proceed to the next stage
- Step type: read-only Kubernetes and Helm validation
- Result: **passed**
- Kubernetes resources changed: none
- OpenStack resources changed: none
- Existing application files or workloads changed: none

## Purpose

This step compares the live cluster after installation with the Day-0 baseline in `monitoring/baseline/20260923T154047Z/`. It separates resources created by `monitoring-stack` from unrelated changes made by other cluster users after the baseline.

## Baseline used

The relevant Day-0 evidence was read from:

```text
monitoring/baseline/20260923T154047Z/nodes.txt
monitoring/baseline/20260923T154047Z/resource-counts-before.txt
monitoring/baseline/20260923T154047Z/workload-problems-before.txt
monitoring/baseline/20260923T154047Z/warning-events-before.txt
monitoring/baseline/20260923T154047Z/helm-before.txt
```

Important baseline conditions:

```text
nodes Ready: 4/4
known unavailable deployment: 2105062/to-do-backend-deployment, 0/1
known pod state: CrashLoopBackOff
known warnings: to-do-backend BackOff/readiness failures and DNSConfigForming
monitoring namespace/release: absent
```

## Commands executed

All remote commands used SSH to the existing admin VM and were read-only:

```powershell
ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ubuntu@192.168.64.242 '<read-only command>'
```

The command groups run remotely were:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
kubectl get nodes -o wide
kubectl top nodes

kubectl get namespaces,pods,deployments,statefulsets,daemonsets,services,jobs,persistentvolumeclaims,storageclasses,ingresses -A
kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp

helm list -A
helm status monitoring-stack -n monitoring
kubectl get deploy,statefulset,daemonset,pod,svc -n monitoring -o wide
kubectl get svc -n monitoring -o custom-columns=NAME:.metadata.name,TYPE:.spec.type,EXTERNAL-IP:.status.loadBalancer.ingress[*].ip
kubectl get pvc -n monitoring

kubectl get pods -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.containerStatuses[*].ready,PHASE:.status.phase,WAITING:.status.containerStatuses[*].state.waiting.reason
kubectl get deployments -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.readyReplicas,DESIRED:.spec.replicas,AVAILABLE:.status.availableReplicas

kubectl get clusterrole,clusterrolebinding,mutatingwebhookconfiguration,validatingwebhookconfiguration -o name
kubectl get deploy,statefulset,daemonset,svc,serviceaccount,role,rolebinding,prometheus,alertmanager,servicemonitor,prometheusrule -n monitoring -l app.kubernetes.io/instance=monitoring-stack -o name
kubectl get all -n monitoring -o custom-columns=KIND:.kind,NAME:.metadata.name,CREATED:.metadata.creationTimestamp
kubectl get prometheus,alertmanager,servicemonitor,prometheusrule -n monitoring --no-headers
```

No `apply`, `create`, `delete`, `edit`, `patch`, `rollout`, `scale`, `helm upgrade`, or OpenStack mutation command was run.

## Command error and correction

The first combined capture command had an unmatched nested quote:

```text
bash: -c: line 1: unexpected EOF while looking for matching `"'
bash: -c: line 2: syntax error: unexpected end of file
```

The remote shell rejected the command before any `kubectl` operation ran. The capture was repeated as smaller read-only commands.

A later display filter also lost the quotes around its alternation expression:

```text
bash: line 1: Completed: command not found
```

That filter produced no reliable result and changed nothing. It was replaced with an unfiltered `kubectl get pods ... -o custom-columns=...` view, which directly exposed every Pod's phase, readiness, and waiting reason.

## Node comparison

Capture timestamp:

```text
2026-09-24T07:30:44Z
```

All nodes remain Ready:

```text
k3s-control-01   Ready   v1.36.2+k3s1   CPU 3%   memory 28%
k3s-worker-01    Ready   v1.36.4+k3s1   CPU 4%   memory 37%
k3s-worker-02    Ready   v1.36.2+k3s1   CPU 3%   memory 20%
k3s-worker-03    Ready   v1.36.2+k3s1   CPU 7%   memory 24%
```

The worker-01 patch-version difference had already been observed before the successful monitoring installation and was not caused by monitoring.

## Resource-count comparison

The `outside monitoring` column excludes objects in the `monitoring` namespace. The last column is a net change caused by concurrent cluster activity, not by this monitoring work.

| Resource | Day 0 | Current total | Outside `monitoring` | Monitoring contribution | Concurrent net delta |
|---|---:|---:|---:|---:|---:|
| Namespaces | 16 | 18 | 17 | 1 | +1 |
| Pods | 48 | 66 | 57 | 9 | +9 |
| Deployments | 25 | 34 | 31 | 3 | +6 |
| StatefulSets | 1 | 3 | 1 | 2 | 0 |
| DaemonSets | 2 | 4 | 3 | 1 | +1 |
| Services | 26 | 44 | 36 | 8 | +10 |
| Jobs | 4 | 2 | 2 | 0 | -2 |
| PVCs | 1 | 1 | 1 | 0 | 0 |
| StorageClasses | 1 | 1 | 1 | 0 | 0 |
| Ingresses | 18 | 24 | 24 | 0 | +6 |

This shows why the raw Day-0/current difference cannot be attributed entirely to monitoring. For example, namespaces `2106090` and `test-user-002` were created after the baseline by unrelated activity:

```text
monitoring      2026-09-23T16:46:29Z
2106090         2026-09-23T19:09:04Z
test-user-002   2026-09-23T22:13:14Z
```

Resources may also have been removed or replaced by their owners, so the final column records only the net difference.

## Existing workload regression result

Every non-monitoring Deployment except the known fault reports its desired replicas available. The only unavailable Deployment remains:

```text
namespace: 2105062
deployment: to-do-backend-deployment
ready: 0/1
available: 0
pod waiting reason: CrashLoopBackOff
```

This exact failure was recorded before installation. Its restart count has continued to rise because the application is still failing, but monitoring did not create or restart it.

All other inspected application, platform, Falco, Traefik, MetalLB, CoreDNS, metrics-server, and local-path-provisioner Pods were Running and ready. Completed debug/Helm Pods were in the expected `Succeeded` phase.

No new non-monitoring unavailable Deployment was found.

## Event comparison

Current warnings fall into these groups:

```text
2105062/to-do-backend: BackOff and HTTP readiness 404
kube-system/MetalLB: DNSConfigForming nameserver-limit warnings
monitoring/node-exporter: the same DNSConfigForming nameserver-limit warning
```

The application failure and nameserver-limit condition existed at baseline. The monitoring node-exporter Pods inherit the same node DNS warning, but all four are Ready and their metrics were verified in Step 7R3B. No warning indicates that monitoring regressed an existing application.

## Monitoring resource attribution

Helm reports:

```text
release: monitoring-stack
namespace: monitoring
revision: 1
status: deployed
chart: kube-prometheus-stack-91.4.1
app version: v0.94.0
```

Expected live workload contribution:

```text
Deployments: 3
StatefulSets: 2
DaemonSets: 1
Pods: 9
Services: 8
PVCs: 0
Ingresses: 0
```

All 9 Pods are Ready. The node-exporter DaemonSet is 4 desired, 4 current, and 4 ready.

All eight monitoring Services are `ClusterIP`, including the two operator-created headless Services. There is no monitoring `NodePort`, `LoadBalancer`, external IP, Ingress, or PVC.

The queried release selector matched 57 namespaced Helm-labelled objects across the workload, service, RBAC, service-account, and monitoring custom-resource kinds. The operator resources comprise 41 Prometheus, Alertmanager, ServiceMonitor, and PrometheusRule objects. Their workload creation timestamps cluster at `2026-09-23T20:09:14Z` through `20:09:38Z`, matching the Helm release installation.

Expected release-named cluster-scoped objects were present:

```text
4 ClusterRoles
4 ClusterRoleBindings
1 MutatingWebhookConfiguration
1 ValidatingWebhookConfiguration
```

The 10 Prometheus Operator CRDs retained from the earlier atomic attempt are the reviewed chart CRDs and now back these release resources. No unrelated application resource carries a claimed monitoring modification.

## Final result

```text
nodes Ready: 4/4
monitoring Pods Ready: 9/9
node-exporter coverage: 4/4 nodes
monitoring release: deployed, revision 1
monitoring public services/ingresses: none
new non-monitoring workload regression: none
pre-existing 2105062 backend fault: unchanged in classification
cluster/OpenStack mutations in Step 8: none
Step 8: PASS
```

Rollback is not applicable because Step 8 was read-only.

## Next permission gate

Do not begin Step 9 without explicit permission.

Step 9 will temporarily establish private local access to Grafana, Prometheus, and Alertmanager one at a time; verify the 23 provisioned Grafana dashboards, Prometheus targets/metrics, and alert state; avoid recording credentials; and terminate every port-forward/tunnel after verification.
