# Step 13A - Read-only stability, alerts, targets, and capacity audit

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: `Approve Step 13A - run read-only stability, alerts, targets, and capacity audit`
- Result: **complete**
- Kubernetes/OpenStack/VM/application mutation: **none**
- Alerts silenced or edited: **none**
- Services restarted or installed: **none**

## Executive result

The monitoring platform is healthy and correctly detecting a pre-existing
student workload fault:

```text
Helm release monitoring-stack: revision 5, deployed
k3s nodes: 4/4 Ready
monitoring Pods: 9, all Ready, zero restarts
Prometheus targets: 26/26 UP
standalone frontend-vm target: UP
```

The only non-healthy Kubernetes workload is
`2105062/to-do-backend-deployment`. Four actionable warnings all describe that
one failure. The application starts successfully, but its generated readiness
and liveness probes request `/`, which returns HTTP 404. The liveness probe then
restarts the otherwise running Uvicorn process.

## Cluster and workload evidence

```text
non-ready Pod:
2105062/to-do-backend-deployment-6b849bbf9d-xnt9s
0/1, CrashLoopBackOff, 473 restarts at inspection time

deployment desired/available:
2105062/to-do-backend-deployment  1/0

failed Jobs: none
monitoring workload restarts: zero
```

Recent warnings also contain recurring `DNSConfigForming` messages on several
DaemonSet Pods because the node resolver provides more nameservers than
Kubernetes accepts. CoreDNS and all monitoring targets are currently UP, so
this is platform technical debt rather than a current monitoring outage.

## Alert classification

Prometheus reported six firing alerts and one pending alert. Alertmanager held
six entries because the pending alert had not reached its firing duration.

| Alert | State | Classification | Evidence |
|---|---|---|---|
| `Watchdog` | firing/active | expected | Intentionally always fires to prove the alert pipeline is alive |
| `InfoInhibitor` | firing, suppressed | expected helper | Built-in inhibition helper; routed to the null receiver |
| `KubePodCrashLooping` | firing | actionable | Student backend container repeatedly restarted |
| `KubePodNotReady` | firing | actionable | Same Pod was unready for more than 15 minutes |
| `KubeDeploymentReplicasMismatch` | firing | actionable | Deployment wanted 1 replica and had 0 available |
| `KubeDeploymentRolloutStuck` | firing | actionable | Deployment exceeded its progress deadline |
| `CPUThrottlingHigh` | pending, info | observe | node-exporter on worker-01 briefly reported throttling; not active in Alertmanager |

The Alertmanager browser view previously showed five visible alerts because
the suppressed `InfoInhibitor` is hidden unless suppressed alerts are included.

No alert was acknowledged, silenced, removed, or reconfigured.

## Root cause of the four actionable warnings

Selected deployment configuration:

```text
image: 192.168.128.152/buet-paas-student-apps/to-do-backend-2105062-build:latest
container port: 8000
readiness path: /
liveness path: /
```

Selected log and event evidence:

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:8000
GET / HTTP/1.1 -> 404 Not Found
Container failed liveness probe, will be restarted
```

The last terminated process had exit code 0 (`Completed`), which supports the
diagnosis that the probe is killing a running service rather than the process
crashing on its own. The application owner should deploy a real health path or
configure the deployment's `health_path` to an endpoint that returns 2xx. That
application fix is outside this read-only monitoring step.

## Prometheus targets

```text
job                                      total  UP
apiserver                                    1   1
coredns                                      1   1
kube-state-metrics                           1   1
kubelet                                     12  12
monitoring-stack-grafana                     1   1
monitoring-stack-kube-prom-alertmanager      2   2
monitoring-stack-kube-prom-operator          1   1
monitoring-stack-kube-prom-prometheus        2   2
node-exporter                                4   4
standalone-node-exporters                    1   1
TOTAL                                       26  26
```

## Standalone VM readiness matrix

| VM | Read-only SSH/API result | Root disk | node_exporter | Step recommendation |
|---|---|---:|---|---|
| `frontend-vm` | frontend and nginx active | 50% used | active/enabled; k3s source can reach 9100 | complete |
| `database-vm` | MongoDB active on 27017 | 42% used | absent; k3s source 9100 timeout | Step 14A candidate |
| `registry-vm-2` | Docker/Harbor ports 80/443 active | 16% used | absent; k3s source 9100 timeout | Step 14B candidate |
| `k3s-user` | Docker and admin services active | 21% used | inactive/absent; k3s source 9100 timeout | Step 14C candidate |
| `backend-vm` | BUET-PaaS backend active on 8020; app ports 9000-9008 listening | 67% used | absent; k3s source 9100 timeout | active; Step 14D candidate |
| `sonarqube` | HTTP API reports `UP` | not SSH verified | k3s source 9100 timeout | block VM change until SSH host key is verified |

The SonarQube SSH attempt stopped at a host-key mismatch. The observed ED25519
fingerprint was:

```text
SHA256:+FDZkJcqkKQULlQOuWUukqFHZNqWzltyjhwPE5G/AzE
```

The existing `known_hosts` entry was not removed or replaced. Verify this
fingerprint through Horizon console or the VM owner before any future SSH.

Port 9100 from `k3s-user` was filtered even for frontend-vm, while Prometheus
and a k3s control-node source could reach frontend-vm successfully. This is the
intended source-security-group behavior. Control-node checks timed out for port
9100 on all five remaining VMs.

## Confirmed service endpoints for future Blackbox probes

| Service | Confirmed private endpoint | Result | Future note |
|---|---|---|---|
| Frontend | `http://192.168.128.15/` | 200 | good first HTTP probe candidate |
| Frontend app | `http://192.168.128.15:3000/` | 200 | prefer nginx/public path unless app-direct monitoring is explicitly needed |
| Backend | `http://192.168.128.131:8020/health` | 200 | body reports app `ok`, version `0.2.0`, MongoDB connected |
| Deployer | Kubernetes Service proxy `/health` | 200 | body `{"status":"ok"}` |
| Harbor | HTTP `/api/v2.0/health` | 308 to HTTPS | use the HTTPS endpoint with correct trust configuration |
| Harbor | HTTPS `/api/v2.0/health` | 200 diagnostic | the audit used `curl -k` only to prove service response; final probe must validate TLS |
| SonarQube | `http://192.168.128.33:9000/api/system/status` | 200 | body reports status `UP` |

MongoDB TCP 27017 was filtered from `k3s-user`, consistent with a restricted
database path. It is not selected as an HTTP Blackbox probe. Database health is
already included in the backend `/health` response.

## Capacity and persistence evidence

Current storage configuration:

```text
Prometheus retention: 2d
Prometheus replicas: 1
Prometheus storage: emptyDir, no PVC, no sizeLimit
Grafana /var/lib/grafana: emptyDir
Alertmanager replicas: 1
Alertmanager storage: no PVC
StorageClass: local-path (default)
reclaim policy: Delete
volume binding: WaitForFirstConsumer
volume expansion: false
resource quotas: none
existing PVCs: one unrelated 1Gi Falco Redis PVC
```

Prometheus measurement at the audit time:

```text
current data age after revision-5 Pod recreation: about 4.28 hours
active head series: 142,221
head chunks: 438,528
block bytes: 48,085,742
WAL bytes: 426,917,129
approximate current block + WAL footprint: 475,002,871 bytes (~453 MiB)
sample append rate observed: about 4,886 samples/second for one returned series
Prometheus CPU: 53m
Prometheus memory: 556Mi
Prometheus limit: 1500m CPU / 2Gi memory
```

Prometheus currently runs on `k3s-worker-03`:

```text
root filesystem size: 49,753,808,896 bytes (~46.3 GiB)
root filesystem available: 33,001,971,712 bytes (~30.7 GiB)
allocatable ephemeral storage: 47,266,118,415 bytes (~44.0 GiB)
```

All nodes were lightly loaded at the snapshot: CPU 3-4%, memory 22-40%.

### Persistence decision

**No-go now.** Four hours of data and one standalone VM are not representative
of the final Day 2 target/probe set. WAL size also cannot be linearly treated as
daily retained-block growth. `local-path` is node-local, deletes released
volumes, and cannot expand them in place. Step 17 must wait for at least 48
hours of representative ingestion and include backup/recovery design.

## Go/no-go recommendations

```text
Step 14A database-vm exporter:       GO after explicit VM-change approval
Step 14B registry-vm-2 exporter:     GO after 14A evidence
Step 14C k3s-user exporter:          GO after 14B evidence
Step 14D backend-vm exporter:        GO; VM confirmed active, disk already 67%
Step 14E sonarqube exporter:         NO-GO until SSH fingerprint verified
Step 15 Blackbox preparation:        GO using confirmed endpoints above
Step 16 dashboard/alerts:            GO after target labels and probes stabilize
Step 17 persistence:                 NO-GO until representative 48-hour data
Step 18 user monitoring API/UI:      defer until admin metrics MVP is stable
Step 19 Loki/Alloy:                  post-MVP only
```

The four student-workload alerts do not block monitoring expansion; they prove
that monitoring is detecting a real application configuration fault. Fixing
that deployment belongs to a separately authorized application workflow.

## Errors and corrections

1. `kubectl exec ... sh` failed because the Prometheus image is distroless and
   contains no shell. No command ran in the container. Storage was measured
   through Prometheus APIs and Pod volume metadata instead.
2. The first VM listener filter lost the remote awk `$4` through nested shell
   quoting. Hostname, service state, and disk results were valid; listeners
   were repeated without awk.
3. Direct SSH to the control-node floating IP rejected `mykey.pem`. The known
   `k3s-user -> k3s-control-01` internal SSH path was verified and used.
4. Two loop-based nested SSH wrappers failed locally/remotely because of
   PowerShell and shell quoting. Neither reached the port checks. Six explicit
   `nc` checks were then run independently and produced unambiguous results.
5. SonarQube SSH reported a changed host key. The warning was honored; strict
   checking was not bypassed and `known_hosts` was not edited.

## Next permission boundary

The next implementation change is split so the VM and Kubernetes mutations do
not happen together:

```text
Step 14A1 - install and locally verify pinned node_exporter on database-vm
Step 14A2 - attach/verify the monitoring-exporter security group manually
Step 14A3 - add database-vm to the scrape overlay and verify target UP
```

Immediate approval phrase:

```text
Approve Step 14A1 - install and locally verify node_exporter on database-vm
```

Step 14A1 will not change Prometheus or OpenStack.
