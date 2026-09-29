# Step 9 — Verify UIs and built-in metrics privately

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: explicitly approved by the user with `Approve Step 9`
- Step type: temporary private access and read-only validation
- Result: **passed; browser access and dashboard inventory visually confirmed by the user**
- Kubernetes resource changes: none
- OpenStack changes: none
- Application changes: none
- Grafana password displayed or stored: no
- Step 9-created tunnels remaining: none

## What this step verified

This step verified Grafana, Prometheus, and Alertmanager one at a time through loopback-only paths:

```text
Windows localhost
  -> temporary SSH local tunnel
  -> k3s-user 127.0.0.1 high port
  -> temporary kubectl port-forward
  -> private ClusterIP service
```

No UI or monitoring port was exposed through an OpenStack public ingress rule.

## Services used

```text
Grafana:      service/monitoring-stack-grafana, service port 80
Prometheus:   service/monitoring-stack-kube-prom-prometheus, service port 9090
Alertmanager: service/monitoring-stack-kube-prom-alertmanager, service port 9093
```

## Preflight

The intended Windows listener ports were initially free:

```text
3000 FREE
9090 FREE
9093 FREE
```

## Grafana verification

### Temporary private access

The first remote command attempted the plan's normal port:

```bash
kubectl -n monitoring port-forward \
  svc/monitoring-stack-grafana \
  3000:80 \
  --address 127.0.0.1
```

It failed safely:

```text
Unable to listen on port 3000
bind: address already in use
```

No existing process was stopped. The corrected temporary remote port was `13000`:

```bash
kubectl -n monitoring port-forward \
  svc/monitoring-stack-grafana \
  13000:80 \
  --address 127.0.0.1
```

Windows received the normal URL through this temporary SSH tunnel:

```powershell
ssh -N \
  -L 127.0.0.1:3000:127.0.0.1:13000 \
  -i "C:\Users\USER\Downloads\mykey.pem" \
  ubuntu@192.168.64.242
```

### UI and health result

```text
http://127.0.0.1:3000/login -> HTTP 200
HTML title Grafana present       -> yes
/api/health database             -> ok
Grafana version                  -> 13.2.2
```

### Credential handling

The exact Secret `monitoring-stack-grafana` was used. The username and password were decoded only into transient remote shell variables:

```bash
GU=$(kubectl get secret monitoring-stack-grafana \
  -n monitoring \
  -o jsonpath={.data.admin-user} | base64 -d)

GP=$(kubectl get secret monitoring-stack-grafana \
  -n monitoring \
  -o jsonpath={.data.admin-password} | base64 -d)
```

Authenticated API requests used `GU` and `GP` in memory. The password was never printed, copied into a file, included in a URL, or written to this journal. The verified username was `admin`.

### Datasources

```text
Prometheus datasource:  type=prometheus, default=true, uid=prometheus
Alertmanager datasource: type=alertmanager, default=false, uid=alertmanager
Prometheus datasource health: OK
message: Successfully queried the Prometheus API.
```

### Provisioned dashboard inventory

The authenticated Grafana search API returned exactly 23 dashboards:

```text
Alertmanager / Overview
CoreDNS
Grafana Overview
Kubernetes / API server
Kubernetes / Compute Resources / Multi-Cluster
Kubernetes / Compute Resources / Cluster
Kubernetes / Compute Resources / Namespace (Pods)
Kubernetes / Compute Resources / Namespace (Workloads)
Kubernetes / Compute Resources / Node (Pods)
Kubernetes / Compute Resources / Nodes Overview
Kubernetes / Compute Resources / Pod
Kubernetes / Compute Resources / Workload
Kubernetes / Kubelet
Kubernetes / Networking / Cluster
Kubernetes / Networking / Namespace (Pods)
Kubernetes / Networking / Namespace (Workload)
Kubernetes / Networking / Pod
Kubernetes / Networking / Workload
Kubernetes / Persistent Volumes
Node Exporter / Nodes
Node Exporter / USE Method / Cluster
Node Exporter / USE Method / Node
Prometheus / Overview
```

Five dashboard models requested by the original plan were fetched successfully:

```text
Kubernetes / Compute Resources / Nodes Overview       5 panels
Kubernetes / Compute Resources / Namespace (Pods)    18 panels
Kubernetes / Compute Resources / Namespace (Workloads) 13 panels
Kubernetes / Compute Resources / Pod                 16 panels
Kubernetes / Compute Resources / Workload            13 panels
```

Total across these five models: 65 panels.

### Live data through Grafana

The Grafana Prometheus datasource proxy returned successful live queries:

```text
count(kube_node_info)             = 4
count(kube_pod_info)              = 66
count(kube_namespace_created)     = 18
count(kube_deployment_created)    = 34
count(node_uname_info)            = 4
```

This proves that the requested Nodes, Pods, Namespaces, Workloads, and node-exporter dashboard families have a healthy datasource and matching live metric series. No custom dashboard was created.

### Grafana command corrections

Two read-only formatting/query commands failed before correction:

1. Shell quoting stripped the `jq` filter quotes, producing `@tsv: command not found`. Dashboard count had already succeeded; JSON was then parsed locally instead.
2. PromQL parentheses were interpreted by the remote shell, producing a syntax error. The same PromQL was retried with URL encoding and all five queries succeeded.

Neither error changed any resource or exposed a credential.

### Grafana cleanup

Closing the SSH execution session stopped the Windows tunnel but left the remote `kubectl` process listening on port `13000`. The exact process was inspected first:

```text
PID 64172
kubectl -n monitoring port-forward svc/monitoring-stack-grafana 13000:80 --address 127.0.0.1
```

Only verified PID `64172`, which this step created, was terminated. Remote `13000` and Windows `3000` were confirmed closed.

## Prometheus verification

### Temporary private access

```bash
kubectl -n monitoring port-forward \
  svc/monitoring-stack-kube-prom-prometheus \
  19090:9090 \
  --address 127.0.0.1
```

```powershell
ssh -N \
  -L 127.0.0.1:9090:127.0.0.1:19090 \
  -i "C:\Users\USER\Downloads\mykey.pem" \
  ubuntu@192.168.64.242
```

### UI, targets, and metrics

```text
/-/ready                         -> HTTP 200, Prometheus Server is Ready
/query UI                        -> HTTP 200, Prometheus title present
active targets                   -> 25
healthy targets                  -> 25 up
down targets                     -> 0
count(kube_node_info)            -> 4
count(kube_pod_info)             -> 66
count(kube_namespace_created)    -> 18
count(kube_deployment_created)   -> 34
count(node_uname_info)           -> 4
```

### Prometheus alert state

Nine firing or pending alert instances were returned:

```text
Watchdog: firing, expected health alert
InfoInhibitor: firing
CPUThrottlingHigh: two firing and one pending, monitoring/info
KubePodCrashLooping: firing, namespace 2105062
KubePodNotReady: firing, namespace 2105062
KubeDeploymentReplicasMismatch: firing, namespace 2105062
KubeDeploymentRolloutStuck: firing, namespace 2105062
```

The four warning alerts in `2105062` correspond to the known pre-existing `to-do-backend` failure. `TargetDown` was absent.

### Prometheus cleanup

The Windows tunnel stopped. The exact remaining remote process was inspected:

```text
PID 65787
kubectl -n monitoring port-forward svc/monitoring-stack-kube-prom-prometheus 19090:9090 --address 127.0.0.1
```

Only verified PID `65787` was terminated. Remote `19090` and Windows `9090` were confirmed closed.

## Alertmanager verification

### Temporary private access

```bash
kubectl -n monitoring port-forward \
  svc/monitoring-stack-kube-prom-alertmanager \
  19093:9093 \
  --address 127.0.0.1
```

```powershell
ssh -N \
  -L 127.0.0.1:9093:127.0.0.1:19093 \
  -i "C:\Users\USER\Downloads\mykey.pem" \
  ubuntu@192.168.64.242
```

### UI and API result

```text
/-/ready              -> HTTP 200, OK
/ UI                  -> HTTP 200, Alertmanager title present
version               -> 0.34.0
cluster status        -> disabled, expected for one replica
received alerts       -> 8
silences              -> 0
```

Alertmanager states:

```text
Watchdog: active
four 2105062 warning alerts: active
InfoInhibitor: suppressed
two CPUThrottlingHigh info alerts: suppressed
```

The first PowerShell array wrapper reported an incorrect count of one while printing all alert values concatenated. The raw response was reparsed with pipeline measurement, producing the correct count of eight. This was a local read-only parsing error.

### Alertmanager cleanup

One combined cleanup/status command had an unmatched quote and did not execute remotely. The exact remote process was then handled separately:

```text
PID 66063
kubectl -n monitoring port-forward svc/monitoring-stack-kube-prom-alertmanager 19093:9093 --address 127.0.0.1
```

Only verified PID `66063` was terminated. Remote `19093` and Windows `9093` were confirmed closed.

## Browser verification

The Windows computer-use inventory returned no available app or browser surface:

```json
{"apps":[],"browsers":[]}
```

Therefore an automated screenshot/click-through of the authenticated Grafana dashboard pages was not possible in this environment. Initial verification used:

- the actual UI HTML endpoints through Windows-local tunnels;
- authenticated Grafana APIs;
- all 23 dashboard definitions;
- panel-model retrieval for the five requested dashboard categories;
- datasource health;
- live metric queries through Grafana;
- Prometheus and Alertmanager UI/API endpoints.

This limitation did not indicate a Grafana failure. It only meant no browser window was exposed to the automation tool during the automated part of this step.

### User-confirmed visual evidence

After the technical verification, the user opened `http://127.0.0.1:3000`, authenticated successfully, and supplied a browser screenshot of the Grafana **Dashboards** page. The screenshot visibly confirms:

```text
Grafana web UI rendered successfully
authenticated Dashboards page accessible
all 23 provisioned dashboard rows visible
Kubernetes compute-resource dashboards visible
Kubernetes networking dashboards visible
Node Exporter dashboards visible
Prometheus and Alertmanager overview dashboards visible
```

No dashboard was manually created or modified. The screenshot verifies the dashboard-list UI; live datasource queries and panel models were already verified through the authenticated API above.

### User-confirmed Prometheus visual evidence

The user then opened Prometheus through the private Windows tunnel and supplied screenshots confirming:

```text
Prometheus Query UI rendered successfully
up query: 25 result series, every displayed value = 1
count(kube_node_info) = 4
count(node_uname_info) = 4
count(kube_pod_info) = 66
Status > Target health page rendered
visible scrape pools/targets show State=UP
```

The screenshots agree with the earlier API result of 25 active targets, 25 up, and zero down.

### User-confirmed Alertmanager visual evidence

The user opened Alertmanager through the private Windows tunnel and supplied screenshots confirming:

```text
Alerts page rendered successfully
one ungrouped alert group visible
namespace 2105062 group: 4 alerts
namespace monitoring group: 1 visible alert
Silences page: No silences found
Status page rendered
version: 0.34.0
cluster status: disabled
```

The Alertmanager UI hides inhibited/suppressed alerts unless the corresponding filters are enabled, explaining why six alerts are visible in the default UI while the API returned eight total alert objects. `cluster status: disabled` is expected for the configured single Alertmanager replica.

The displayed configuration routes notifications to the `null` receiver; generic global integration endpoint defaults do not mean Slack, PagerDuty, or another external notification destination is configured. No receiver or silence was changed.

## Pre-existing port-forward preserved

The remote port `127.0.0.1:3000` that blocked the first attempt belongs to an older process:

```text
PID: 38379
started: Wed Sep 23 20:45:43 2026
command: kubectl -n monitoring port-forward service/monitoring-stack-grafana 3000:80 --address 127.0.0.1
```

It predates Step 9 and was not stopped or modified. It is private to `k3s-user` loopback and is not an OpenStack/public exposure.

## Final regression check

```text
Helm monitoring-stack: deployed, revision 1
Kubernetes nodes: 4/4 Ready
monitoring Pods: 9/9 Ready
Prometheus targets: 25/25 up
new unavailable Deployment: none
pre-existing 2105062/to-do-backend: still 0/1
Step 9-created Windows listeners 3000/9090/9093: closed
Step 9-created remote listeners 13000/19090/19093: closed
```

No Kubernetes object, Helm release, OpenStack rule, application workload, dashboard, alert, or silence was created, edited, or deleted.

## Final result

```text
Grafana login UI reachable: yes
Grafana authenticated API: yes
Grafana dashboards provisioned: 23/23
requested dashboard models retrieved: 5/5
Grafana Prometheus datasource: healthy
live Kubernetes/node metrics through Grafana: yes
Prometheus UI/API: healthy
Prometheus targets: 25/25 up
Alertmanager UI/API: healthy
temporary access cleanup: complete
visual Grafana login/dashboard inventory: confirmed by user screenshot
visual Prometheus queries/targets: confirmed by user screenshots
visual Alertmanager alerts/silences/status: confirmed by user screenshots
automated browser control: unavailable, non-blocking
Step 9: PASS
```

Rollback is not applicable because Step 9 made no persistent change. Temporary-process cleanup is complete.

## Next permission gate

Do not begin Step 10 without explicit permission.

Step 10 is a remote mutation and is split into six independently approved VM substeps. The first proposed substep is `frontend-vm` (`192.168.128.15`): capture its baseline, verify OS/architecture, install a pinned and checksum-verified node_exporter with a least-privilege systemd service, verify private reachability and application health, then stop before touching any other VM.
