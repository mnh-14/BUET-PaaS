# Step 3 — Capacity and compatibility decision

## Status

- Permission received: `Approve Step 3`
- Execution date: 2026-09-23 (Asia/Dhaka)
- Step type: analysis and read-only inspection
- Cluster changes: none
- Existing tracked repository files changed: none
- New file produced by this step: `step-3.md`
- Decision: **GO for Step 4**, subject to the safeguards in this document

## What this step means in plain language

Step 2 photographed the cluster before monitoring exists. Step 3 uses that photograph to answer four questions before creating configuration or installing anything:

1. Is there enough CPU and memory for a small monitoring stack?
2. Which exact monitoring chart version should be used?
3. Should the first installation use persistent disks or temporary storage?
4. Which default chart features need adjustment for this k3s cluster?

No monitoring software was installed in this step. No namespace, CRD, Pod, Service, Secret, PVC, Helm release, or VM package was created or modified.

## Inputs carried forward from Step 2

### Cluster capacity

| Node | Role | CPU | Memory | Observed CPU | Observed memory |
|---|---|---:|---:|---:|---:|
| `k3s-control-01` | control plane | 4 cores | about 8 GiB | 103m / 2% | 1723 Mi / 21% |
| `k3s-worker-01` | worker | 4 cores | about 8 GiB | 93m / 2% | 2802 Mi / 35% |
| `k3s-worker-02` | worker | 4 cores | about 8 GiB | 99m / 2% | 1054 Mi / 13% |
| `k3s-worker-03` | worker | 4 cores | about 8 GiB | 89m / 2% | 959 Mi / 12% |

All four nodes were `Ready`. All four reported `MemoryPressure=False`, `DiskPressure=False`, and `PIDPressure=False`.

The cluster therefore has 16 CPU cores and roughly 32 GiB RAM in total. The proposed monitoring requests below consume about 0.88 CPU cores and 1.56 GiB RAM cluster-wide. This is approximately 5.5% of total CPU and 4.9% of total RAM before small sidecars and temporary install Jobs.

This is enough headroom for the MVP. It is not a guarantee for future high-cardinality application metrics; actual Prometheus ingestion and memory must be measured after installation.

### Pre-existing problems that monitoring must not be blamed for

- `2105062/to-do-backend-deployment` already had an unavailable/CrashLooping Pod and a readiness probe returning HTTP 404.
- An older frontend build Pod was already in `Error`; a later Pod for that Job completed.
- CoreDNS and MetalLB speaker Pods already had `DNSConfigForming` warnings caused by the nameserver limit.
- These conditions existed before monitoring and are preserved in `monitoring/baseline/20260923T154047Z/`.

## Read-only commands executed in Step 3

The local private key path is shown so the procedure can be repeated, but no private-key content, kubeconfig, token, password, or Secret value was printed or saved.

### 1. Inspect existing kube-system services and discovery endpoints

Input from Windows PowerShell:

```powershell
ssh -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ubuntu@192.168.64.242 `
  "kubectl get services,endpoints,endpointslices -n kube-system -o wide"
```

Output:

```text
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice

Services present:
- kube-dns       ClusterIP      10.43.0.10      ports 53/UDP, 53/TCP, 9153/TCP
- metrics-server ClusterIP      10.43.249.133   port 443/TCP
- traefik        LoadBalancer   10.43.67.11     external IP 192.168.128.200

EndpointSlices present:
- kube-dns       -> 10.42.2.70
- metrics-server -> 10.42.0.128
- traefik        -> 10.42.0.123
```

Important interpretation: there are no existing Services or EndpointSlices for the embedded k3s scheduler, controller-manager, etcd metrics, or kube-proxy metrics. Enabling the chart's generic targets for those components without additional k3s configuration would create missing or duplicate targets.

The deprecation warning was informational. The command deliberately requested both old Endpoints and current EndpointSlices for discovery evidence; it did not modify anything.

### 2. Check the unified Kubernetes/k3s metrics endpoint

Input from Windows PowerShell:

```powershell
ssh -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ubuntu@192.168.64.242 `
  "kubectl get --raw /metrics | grep -m 5 -E '^(k3s_|scheduler_|etcd_server_|kubeproxy_)'"
```

Output excerpt:

```text
k3s_certificate_expiration_seconds{subject="CN=etcd-client",usages="ClientAuth"} ...
k3s_certificate_expiration_seconds{subject="CN=etcd-peer",usages="ServerAuth,ClientAuth"} ...
k3s_certificate_expiration_seconds{subject="CN=etcd-peer-ca@...",usages="CertSign"} ...
k3s_certificate_expiration_seconds{subject="CN=etcd-server",usages="ServerAuth,ClientAuth"} ...
k3s_certificate_expiration_seconds{subject="CN=etcd-server-ca@...",usages="CertSign"} ...
```

The numeric certificate lifetimes and generated CA suffix are intentionally omitted from this repository document because only endpoint availability matters for the decision.

Interpretation: the authenticated API metrics endpoint already includes k3s process metrics. Current k3s documentation explains that embedded Kubernetes components share one metric registry and that scraping every individual embedded endpoint can duplicate metrics.

## Compatibility research and pinned version

Only official project sources were used:

- Kubernetes version-skew policy: <https://kubernetes.io/releases/version-skew-policy/>
- kube-prometheus compatibility table: <https://github.com/prometheus-operator/kube-prometheus>
- kube-prometheus-stack package versions: <https://github.com/prometheus-community/helm-charts/pkgs/container/charts%2Fkube-prometheus-stack/versions>
- Immutable chart metadata: <https://raw.githubusercontent.com/prometheus-community/helm-charts/kube-prometheus-stack-91.4.1/charts/kube-prometheus-stack/Chart.yaml>
- Immutable chart defaults: <https://raw.githubusercontent.com/prometheus-community/helm-charts/kube-prometheus-stack-91.4.1/charts/kube-prometheus-stack/values.yaml>
- K3s metrics behavior: <https://docs.k3s.io/reference/metrics>

### Selected chart

```text
Chart: kube-prometheus-stack
Pinned chart version: 91.4.1
Prometheus Operator appVersion: v0.94.0
Chart Kubernetes constraint: >=1.25.0-0
OCI digest listed by the publisher: sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
Cluster server version: v1.36.2+k3s1
Remote Helm version: v3.22.0
```

Why `91.4.1` instead of the same-day `91.5.0`:

- `91.4.1` was published about one week earlier and had substantially more recorded downloads when checked.
- It declares Kubernetes `>=1.25.0-0` and packages Prometheus Operator `v0.94.0`.
- kube-prometheus release `0.18` supports Kubernetes 1.36.
- Pinning an exact version and verifying the published digest makes later rendering and installation reproducible.

The digest must be rechecked when the chart is pulled in the approved chart-preparation step. No chart was downloaded in Step 3.

### kubectl version-skew blocker before the first cluster write

```text
Administration VM kubectl client: v1.33.13
Kubernetes API server:             v1.36.2+k3s1
Difference:                        3 minor versions
Supported kubectl skew:            within 1 minor version
```

Therefore, the existing `kubectl` on `k3s-user` is outside the supported range. It worked for the read-only inventory, but it must not be the unqualified tool for the first cluster mutation.

Required safeguard before Step 5:

- use a verified `kubectl` 1.35, 1.36, or 1.37 client, preferably 1.36 matching the server; or
- use the matching k3s-provided kubectl through a separately reviewed route.

No binary was replaced and no package was installed in Step 3. Step 4 is local-only, so this does not block Step 4. It does block Step 5 until explicitly resolved and documented.

## Storage decision

Step 2 found:

```text
Default StorageClass: local-path
Binding mode: WaitForFirstConsumer
Reclaim policy: Delete
Volume expansion: false
Existing PVCs: one unrelated 1 GiB Falco Redis claim
Node DiskPressure: false on all four nodes
```

### Decision: start with ephemeral storage

For the first MVP installation:

- Prometheus retention: `2d`
- Prometheus persistence: disabled (`storageSpec: {}`)
- Alertmanager persistence: disabled (`storage: {}`)
- Grafana persistence: disabled
- replica count: one for Prometheus and Alertmanager

Why:

- `local-path` binds data to one node, has reclaim policy `Delete`, and cannot expand volumes in this cluster.
- The actual metric ingestion rate and TSDB disk growth are not yet measured.
- A two-day ephemeral trial minimizes irreversible storage decisions and follows the supplied MVP plan.

Consequence: monitoring history, Alertmanager silences, and UI state can be lost when their Pods are rescheduled or recreated. Dashboards and configuration stored declaratively in Kubernetes objects remain reproducible. This is acceptable only for the initial observation period, not the final production design.

Persistence will be reconsidered after measuring at least 24–48 hours of Prometheus series count, ingestion rate, memory, and disk growth.

## Proposed Step 4 values

These are design decisions only. The YAML will be created and rendered locally only after explicit approval of Step 4.

### Core behavior

```yaml
kubeTargetVersionOverride: "1.36.2"

prometheus:
  service:
    type: ClusterIP
  ingress:
    enabled: false
  prometheusSpec:
    replicas: 1
    retention: 2d
    scrapeInterval: 30s
    evaluationInterval: 30s
    storageSpec: {}

alertmanager:
  service:
    type: ClusterIP
  ingress:
    enabled: false
  alertmanagerSpec:
    replicas: 1
    storage: {}

grafana:
  service:
    type: ClusterIP
  ingress:
    enabled: false
  persistence:
    enabled: false
```

Grafana's administrator password will remain in a Kubernetes Secret generated or managed at deployment time. It will not be committed to Git. Initial access will use `kubectl port-forward`; no public Ingress, NodePort, or LoadBalancer will be created.

### k3s-specific scrape adjustments

Keep enabled:

- Kubernetes API server
- kubelet and cAdvisor
- CoreDNS
- kube-state-metrics
- node-exporter on all four Kubernetes nodes
- Prometheus, Alertmanager, Grafana, and Prometheus Operator self-monitoring

Disable for the initial MVP:

```yaml
kubeControllerManager:
  enabled: false
kubeScheduler:
  enabled: false
kubeEtcd:
  enabled: false
kubeProxy:
  enabled: false

defaultRules:
  rules:
    etcd: false
    kubeControllerManager: false
    kubeProxy: false
    kubeSchedulerAlerting: false
    kubeSchedulerRecording: false
```

Reason: those generic targets have no discoverable Service/EndpointSlice in the current k3s cluster, while the authenticated K3s/API metrics endpoint is available. Disabling their associated rules avoids false `TargetDown`-style noise and duplicate embedded-component metrics. Step 4's rendered manifests must confirm that the disabled Services, ServiceMonitors, and rules are absent.

### Proposed resource requests and limits

| Component | Replicas | CPU request | CPU limit | Memory request | Memory limit |
|---|---:|---:|---:|---:|---:|
| Prometheus | 1 | 500m | 1500m | 1 GiB | 2 GiB |
| Alertmanager | 1 | 50m | 200m | 128 MiB | 256 MiB |
| Grafana | 1 | 100m | 500m | 128 MiB | 512 MiB |
| Prometheus Operator | 1 | 100m | 300m | 128 MiB | 256 MiB |
| kube-state-metrics | 1 | 50m | 200m | 64 MiB | 256 MiB |
| node-exporter | 4, one per node | 20m each | 100m each | 32 MiB each | 128 MiB each |

Approximate sum for the listed long-running containers:

```text
CPU requests:    880m
CPU limits:      3100m
Memory requests: 1600 MiB
Memory limits:   3840 MiB
```

This estimate excludes small sidecars and short-lived Helm/admission Jobs. Step 4 must render the chart and calculate the complete Pod-level resource picture before any cluster installation.

Exact value paths already verified against the pinned chart and its pinned dependencies:

```text
prometheus.prometheusSpec.resources
alertmanager.alertmanagerSpec.resources
grafana.resources
prometheusOperator.resources
kube-state-metrics.resources
prometheus-node-exporter.resources
```

## Risk and rollback analysis

### Step 3 impact

- Remote impact: none; all SSH/kubectl operations were reads.
- Local impact: this new documentation file and a new master-journal entry only.
- Rollback required: none.
- Secret exposure: none known; outputs were sanitized.

### Main risks carried into later steps

1. The current administrative `kubectl` client is unsupported against this API-server version. Resolve before Step 5.
2. Ephemeral storage intentionally permits metric-history loss. Reassess after measuring real usage.
3. Node-exporter uses host networking, host PID visibility, and read-only host filesystem mounts by design. Step 4 must review the rendered DaemonSet and security context before approval.
4. Prometheus memory is sensitive to time-series cardinality. The initial limits are for a small cluster and must be observed after installation.
5. The pre-existing CrashLoop and DNS warnings will produce alerts; they are not monitoring regressions.

## Step 3 conclusion

```text
Capacity:       GO
Compatibility: GO with kube-prometheus-stack 91.4.1
Storage:       ephemeral for the two-day MVP trial
Exposure:      ClusterIP only; private port-forward access
k3s targets:   disable generic controller-manager, scheduler, etcd, and kube-proxy targets/rules initially
Tooling gate:   fix or bypass unsupported kubectl 1.33 before Step 5
Cluster writes: none performed
```

## Next step — not yet executed

Step 4 is **local configuration only**. After approval, it will:

1. create the monitoring directory layout inside this repository;
2. create the pinned, resource-bounded values file described above;
3. add local validation/rendering support without credentials;
4. render chart `91.4.1` locally and inspect RBAC, CRDs, Services, DaemonSets, host mounts, selectors, and all resource settings;
5. record exact commands, outputs, errors, corrections, hashes, and Git diff in `step-4.md`;
6. make no Kubernetes cluster or standalone-VM change.

Do not execute Step 4 until the user explicitly says `Approve Step 4`.
