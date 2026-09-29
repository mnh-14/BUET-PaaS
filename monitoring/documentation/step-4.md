# Step 4 — Create and validate local monitoring configuration

## Status

- Permission received: `Approve Step 4`
- Execution date: 2026-09-23 (Asia/Dhaka)
- Step type: local repository additions and local rendering only
- Kubernetes cluster changes: none
- Standalone VM changes: none
- Existing tracked repository files changed: none
- Decision: **local configuration passed; eligible for Step 5 after approval**

## What this step means in plain language

Step 3 decided what should be installed. Step 4 converted that decision into a values file and tested what Helm would generate, without installing it.

The flow was:

```text
Step 3 decisions
    -> write local values.yaml
    -> pull exact chart into a temporary directory
    -> verify chart digest/version
    -> Helm lint
    -> Helm template (local render)
    -> inspect generated object types, exposure, storage, resources, RBAC, and host access
    -> stop before any Kubernetes API write
```

No `helm install`, `helm upgrade`, `kubectl apply`, `kubectl create`, package installation, SSH command, or Kubernetes API mutation was performed.

## Files added

```text
monitoring/README.md
monitoring/prometheus/values.yaml
monitoring/scripts/render-kube-prometheus-stack.ps1
step-4.md
```

The existing `monitoring/baseline/20260923T154047Z/` files were not edited.

### Purpose of each file

#### `monitoring/README.md`

Explains scope, layout, reproduction command, security rules, generated-artifact policy, and the fact that cluster installation has not happened.

#### `monitoring/prometheus/values.yaml`

Contains only non-secret Helm overrides:

- chart target Kubernetes version `1.36.2`;
- two-day Prometheus retention;
- ephemeral initial storage;
- resource requests and limits;
- private `ClusterIP` services;
- disabled Ingresses;
- k3s-specific disabled embedded-component targets/rules;
- enabled API server, kubelet/cAdvisor, CoreDNS, kube-state-metrics, and node-exporter monitoring.

It contains no password, token, private key, kubeconfig, notification credential, or standalone-VM address.

#### `monitoring/scripts/render-kube-prometheus-stack.ps1`

A reproducible local validator that:

1. pulls exactly `kube-prometheus-stack:91.4.1` from the official OCI registry;
2. requires the expected publisher digest;
3. checks chart version `91.4.1` and appVersion `v0.94.0`;
4. captures chart metadata/default values;
5. runs Helm lint;
6. runs Helm template with Kubernetes version `1.36.2` and CRDs included;
7. writes SHA-256 hashes;
8. never runs an install/upgrade command and never invokes kubectl.

Generated chart archives and manifests are written to a caller-specified output directory. The verified run used a Windows temporary directory outside the repository.

## Initial local tool discovery

Commands:

```powershell
Get-Command helm,kubectl,yq,docker,podman -ErrorAction SilentlyContinue
kubectl version --client -o yaml
```

Result:

```text
helm:    NOT FOUND
kubectl: C:\Program Files\Docker\Docker\resources\bin\kubectl.exe
kubectl client: v1.34.1
yq:      NOT FOUND
docker:  C:\Program Files\Docker\Docker\resources\bin\docker.exe
podman:  NOT FOUND
```

Local kubectl 1.34.1 is also outside the supported one-minor range of the 1.36 API server, although it is closer than the administration VM's 1.33 client. It was not used against the cluster or for rendering.

## Helm acquisition and verification

Helm was not installed system-wide. The official Windows archive and checksum were downloaded to:

```text
C:\Users\USER\AppData\Local\Temp\buet-paas-monitoring-step4\
```

Input:

```powershell
$d='C:\Users\USER\AppData\Local\Temp\buet-paas-monitoring-step4'
New-Item -ItemType Directory -Force -Path $d
Invoke-WebRequest `
  -Uri 'https://get.helm.sh/helm-v3.22.0-windows-amd64.zip' `
  -OutFile "$d\helm-v3.22.0-windows-amd64.zip"
Invoke-WebRequest `
  -Uri 'https://get.helm.sh/helm-v3.22.0-windows-amd64.zip.sha256sum' `
  -OutFile "$d\helm-v3.22.0-windows-amd64.zip.sha256sum"
Get-FileHash -Algorithm SHA256 "$d\helm-v3.22.0-windows-amd64.zip"
Expand-Archive -LiteralPath "$d\helm-v3.22.0-windows-amd64.zip" -DestinationPath $d -Force
& "$d\windows-amd64\helm.exe" version --short
```

Output:

```text
publisher checksum: 899615865726d39f9b245e71e848c5bf4adc7ed33a8c43ede660facb48151b43
actual checksum:    899615865726d39f9b245e71e848c5bf4adc7ed33a8c43ede660facb48151b43
Helm version:       v3.22.0+g144ca65
Checksum result:    MATCH
```

## Renderer command

Final successful input:

```powershell
.\monitoring\scripts\render-kube-prometheus-stack.ps1 `
  -HelmPath 'C:\Users\USER\AppData\Local\Temp\buet-paas-monitoring-step4\windows-amd64\helm.exe' `
  -OutputDirectory 'C:\Users\USER\AppData\Local\Temp\buet-paas-monitoring-step4\render-final'
```

Final output:

```text
v3.22.0+g144ca65
Pulled: ghcr.io/prometheus-community/charts/kube-prometheus-stack:91.4.1
Digest: sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
==> Linting ...\kube-prometheus-stack-91.4.1.tgz

1 chart(s) linted, 0 chart(s) failed
Rendered manifest: ...\render-final\rendered.yaml
Chart metadata:    ...\render-final\chart-metadata.yaml
Chart defaults:    ...\render-final\chart-default-values.yaml
Hashes:            ...\render-final\sha256.txt
```

Chart metadata checked from the downloaded archive:

```text
name: kube-prometheus-stack
version: 91.4.1
appVersion: v0.94.0
kubeVersion: >=1.25.0-0
```

## Errors, corrections, and traceability

### Attempt 1 — stopped by PowerShell stderr handling

Observed output:

```text
v3.22.0+g144ca65
Pulled: ghcr.io/prometheus-community/charts/kube-prometheus-stack:91.4.1
NativeCommandError
```

What happened:

- Helm writes successful OCI pull messages and the digest to stderr.
- The first script version used `$ErrorActionPreference = 'Stop'` with `2>&1`.
- Windows PowerShell converted Helm's successful stderr status into a terminating `NativeCommandError` before the script could evaluate Helm's exit code.

Impact:

- The chart download completed in the temporary directory.
- Lint and template did not run in this attempt.
- No repository configuration, VM, or cluster resource was changed by the failure.

### Attempt 2 — functionally successful but output was too noisy

The script was changed to evaluate the native exit code. Lint and template both succeeded, but PowerShell still printed its verbose error-record wrapper around Helm's successful stderr output.

This was not accepted as the final implementation because another operator could mistake the wrapper for a real Helm failure.

### Final correction

The script now uses `System.Diagnostics.ProcessStartInfo` for the pull and lint commands. It captures stdout and stderr directly and treats the Helm process exit code as authoritative.

The final retest produced clean output, verified the expected digest, passed lint, and rendered successfully.

## Rendered object inventory

The final manifest contains 114 Kubernetes objects:

| Kind | Count |
|---|---:|
| CustomResourceDefinition | 10 |
| PrometheusRule | 30 |
| ConfigMap | 26 |
| ServiceMonitor | 9 |
| ServiceAccount | 7 |
| Service | 7 |
| ClusterRole | 5 |
| ClusterRoleBinding | 5 |
| Deployment | 3 |
| Secret | 3 |
| Job | 2 |
| Role | 1 |
| RoleBinding | 1 |
| DaemonSet | 1 |
| Prometheus | 1 |
| Alertmanager | 1 |
| MutatingWebhookConfiguration | 1 |
| ValidatingWebhookConfiguration | 1 |

The three rendered Secrets were kept only in the temporary manifest. Their values were not printed, copied into documentation, or written inside the repository.

### Core workload objects

```text
Alertmanager  monitoring-stack-kube-prom-alertmanager
Prometheus    monitoring-stack-kube-prom-prometheus
Deployment    monitoring-stack-grafana
Deployment    monitoring-stack-kube-prom-operator
Deployment    monitoring-stack-kube-state-metrics
DaemonSet     monitoring-stack-prometheus-node-exporter
```

Prometheus Operator will create the actual Prometheus and Alertmanager StatefulSets after the corresponding custom resources exist. The local template correctly contains the operator-managed custom resources rather than directly templating those StatefulSets.

## Exposure validation

Rendered Services:

```text
monitoring-stack-grafana                    ClusterIP
monitoring-stack-kube-state-metrics         ClusterIP
monitoring-stack-prometheus-node-exporter   ClusterIP
monitoring-stack-kube-prom-alertmanager     ClusterIP
monitoring-stack-kube-prom-coredns          ClusterIP (default type)
monitoring-stack-kube-prom-operator         ClusterIP
monitoring-stack-kube-prom-prometheus       ClusterIP
```

Negative checks:

```text
Ingress objects:          0
NodePort services:        0
LoadBalancer services:    0
PersistentVolumeClaims:   0
runtime volume claims:    0
```

Therefore the rendered MVP does not publicly expose its UIs and does not allocate persistent storage.

## k3s-specific validation

Rendered runtime matches:

```text
kube-controller-manager: 0
kube-scheduler:          0
kube-etcd:               0
kube-proxy:              0
```

Runtime standalone/external target checks:

```text
additionalScrapeConfigs: 0
static_configs:          0
```

Text occurrences inside CRD schemas were excluded from these runtime checks. No backend, frontend, registry, or other standalone VM was added in Step 4.

## Resource validation

Rendered core object values:

| Object | CPU request | CPU limit | Memory request | Memory limit |
|---|---:|---:|---:|---:|
| Prometheus | 500m | 1500m | 1 GiB | 2 GiB |
| Alertmanager | 50m | 200m | 128 MiB | 256 MiB |
| Grafana | 100m | 500m | 128 MiB | 512 MiB |
| Prometheus Operator | 100m | 300m | 128 MiB | 256 MiB |
| kube-state-metrics | 50m | 200m | 64 MiB | 256 MiB |
| node-exporter, per node | 20m | 100m | 32 MiB | 128 MiB |

Prometheus settings found in the rendered custom resource:

```text
scrapeInterval: 30s
evaluationInterval: 30s
retention: 2d
volumeClaimTemplate: absent
```

Alertmanager settings:

```text
replicas: 1
retention: 48h
volumeClaimTemplate: absent
```

## Node-exporter security review

The rendered node-exporter DaemonSet intentionally contains:

```text
hostNetwork: true
hostPID: true
hostIPC: false
readOnlyRootFilesystem: true
host mount readOnly: true
mountPropagation: HostToContainer
privileged: true: absent
```

This host visibility is required for node-level CPU, memory, filesystem, and operating-system metrics. It is a meaningful permission boundary and is recorded for future review. There is exactly one DaemonSet, so Kubernetes will schedule one exporter Pod per eligible Linux node.

## Hashes

Repository source files:

```text
f1fb0310e4a78899ee5148b2e7b01898b4b9d6b93cf2ebe4cad11f9067f99a22  monitoring/README.md
2d98fe9150c90ae7709864590b3145a94c8e369f6b1e9c06c9cf8d53f79a57b7  monitoring/prometheus/values.yaml
b953cc5f15ccfda24f0a494c8fdc714d080aab868e38f33a5b90bcb9204420f0  monitoring/scripts/render-kube-prometheus-stack.ps1
```

Temporary verification artifacts:

```text
1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb  kube-prometheus-stack-91.4.1.tgz
933c3347ffabbd52720ec1119964e8fedf14ff0fc62593a100d6eed64fe94117  rendered.yaml
```

The chart archive hash is the downloaded `.tgz` file hash. The separately verified OCI manifest digest is:

```text
sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
```

These are different artifact layers and are not expected to have the same digest.

## Repository integrity checks

```text
PowerShell syntax: PASS
Helm archive checksum: PASS
Expected OCI digest: PASS
Chart metadata version/appVersion: PASS
Helm lint: PASS
Helm template: PASS
Trailing whitespace in new source files: NONE
Tab characters in YAML: NONE
Generated chart/render artifacts inside repository: NONE
Existing tracked files modified: NONE
```

Current untracked work remains limited to the monitoring documentation/configuration created during Steps 0–4:

```text
implementation of monitoring.md
monitoring/
step-3.md
step-4.md
```

No commit was created because the user did not authorize a commit.

## Rollback for Step 4

No cluster rollback exists because the cluster was not changed.

If the user later authorizes a local rollback, remove only these Step 4 additions:

```text
monitoring/README.md
monitoring/prometheus/values.yaml
monitoring/scripts/render-kube-prometheus-stack.ps1
step-4.md
```

Do not remove `monitoring/baseline/`, `step-3.md`, or the master journal as part of a Step 4-only rollback.

The temporary directory can be removed separately if the user requests cleanup. It currently preserves the exact chart and render used for traceability.

## Step 4 conclusion

```text
Local configuration: PASS
Pinned chart:        kube-prometheus-stack 91.4.1
OCI digest:          MATCH
Helm lint:           PASS
Helm template:       PASS
Public exposure:     NONE
Persistent storage:  NONE
External VM targets: NONE
Cluster writes:      NONE
```

## Next step — not yet executed

Step 5 is the first cluster-changing step. Its only intended durable change is creating the empty `monitoring` namespace.

Because both currently observed standalone kubectl clients are outside the supported version range, Step 5 must begin with a read-only check for the server-matched k3s kubectl on `k3s-control-01`. Recommended flow:

1. use the already verified SSH path through `k3s-user`;
2. run a read-only `sudo -n k3s kubectl version` and context/authorization check on `k3s-control-01`;
3. stop without changes if the matching client or non-interactive authorization is unavailable;
4. if checks pass, capture the current absence of namespace `monitoring`;
5. create only namespace `monitoring`;
6. read it back and record its exact metadata/status;
7. create `step-5.md` with commands, outputs, errors, and rollback command;
8. install no chart and create no other Kubernetes object.

Do not execute Step 5 until the user explicitly says `Approve Step 5`.
