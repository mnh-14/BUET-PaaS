# Step 6 — Prepare and remotely validate the pinned Helm chart

## Status

- Permission received: `Approve Step 6`
- Execution date: 2026-09-23 (Asia/Dhaka)
- Step type: remote artifact preparation, linting, and local Helm rendering on `k3s-user`
- Helm installation/upgrade: not performed
- Kubernetes resource changes: none
- Result: **completed successfully**

## What this step means in plain language

Step 4 proved that the configuration renders correctly on the Windows workstation. Step 6 repeated that validation on the administration VM that will run Helm during installation.

The flow was:

```text
verify unused protected remote path
    -> copy only reviewed values.yaml
    -> compare local and remote SHA-256
    -> pull exact OCI chart version
    -> verify publisher digest and chart archive hash
    -> inspect chart metadata
    -> Helm lint
    -> Helm template to a protected temporary file
    -> inspect sanitized counts and negative checks
    -> prove namespace/release remained empty
    -> stop before installation
```

No `helm install`, `helm upgrade`, `kubectl apply`, or `kubectl create` command was run in Step 6.

## Why OCI was used instead of adding a Helm repository

The chart is officially distributed as an OCI artifact. Using the immutable reference below avoids a mutable local repository alias and matches the artifact already reviewed in Step 4:

```text
oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack
version: 91.4.1
expected OCI digest: sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
```

No Helm repository was added or updated.

## Remote working location

```text
Host: ubuntu@192.168.64.242 (k3s-user)
Directory: /tmp/buet-paas-monitoring-step6-20260923
Directory mode: 700
Owner: ubuntu:ubuntu
```

The path is temporary and can disappear after a VM reboot or `/tmp` cleanup. It is being retained for the separately approved Step 7 so the already verified archive can be reused.

## Pre-transfer safety check

Local values hash:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\monitoring\prometheus\values.yaml'
```

Output:

```text
2d98fe9150c90ae7709864590b3145a94c8e369f6b1e9c06c9cf8d53f79a57b7
```

Remote path check:

```powershell
ssh -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ubuntu@192.168.64.242 `
  "if test -e /tmp/buet-paas-monitoring-step6-20260923; then echo PATH_EXISTS; else echo PATH_ABSENT; fi"
```

Output:

```text
PATH_ABSENT
```

The absence check prevented accidental overwrite of an earlier operator's artifacts.

## Directory creation and values transfer

Create the dedicated directory:

```powershell
ssh ... ubuntu@192.168.64.242 `
  "install -d -m 700 /tmp/buet-paas-monitoring-step6-20260923"
```

Output: none; exit code `0`.

Transfer only the reviewed values file:

```powershell
scp -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ".\monitoring\prometheus\values.yaml" `
  ubuntu@192.168.64.242:/tmp/buet-paas-monitoring-step6-20260923/values.yaml
```

Output: none; exit code `0`.

Protect and verify the file:

```text
chmod 600 /tmp/buet-paas-monitoring-step6-20260923/values.yaml
stat -c '%A %U:%G %s %n' \
  /tmp/buet-paas-monitoring-step6-20260923 \
  /tmp/buet-paas-monitoring-step6-20260923/values.yaml
sha256sum /tmp/buet-paas-monitoring-step6-20260923/values.yaml
helm version --short
```

Output:

```text
drwx------ ubuntu:ubuntu 4096 /tmp/buet-paas-monitoring-step6-20260923
-rw------- ubuntu:ubuntu 2472 /tmp/buet-paas-monitoring-step6-20260923/values.yaml
2d98fe9150c90ae7709864590b3145a94c8e369f6b1e9c06c9cf8d53f79a57b7  .../values.yaml
v3.22.0+g144ca65
```

The local and remote values hashes match exactly.

## Pinned OCI chart pull

Input:

```text
cd /tmp/buet-paas-monitoring-step6-20260923
helm pull \
  oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack \
  --version 91.4.1
```

Output:

```text
Pulled: ghcr.io/prometheus-community/charts/kube-prometheus-stack:91.4.1
Digest: sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
```

The digest exactly matches the value selected in Step 3 and checked in Step 4.

## Chart metadata and lint

Input:

```text
sha256sum kube-prometheus-stack-91.4.1.tgz
helm show chart kube-prometheus-stack-91.4.1.tgz |
  grep -E '^(name|version|appVersion|kubeVersion):'
helm lint kube-prometheus-stack-91.4.1.tgz \
  --values values.yaml \
  --kube-version 1.36.2
```

Output:

```text
1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb  kube-prometheus-stack-91.4.1.tgz
appVersion: v0.94.0
kubeVersion: '>=1.25.0-0'
name: kube-prometheus-stack
version: 91.4.1

==> Linting kube-prometheus-stack-91.4.1.tgz

1 chart(s) linted, 0 chart(s) failed
```

The chart archive hash exactly matches the Step 4 archive hash.

## Remote local rendering

Input:

```text
cd /tmp/buet-paas-monitoring-step6-20260923
umask 077
helm template monitoring-stack kube-prometheus-stack-91.4.1.tgz \
  --namespace monitoring \
  --values values.yaml \
  --kube-version 1.36.2 \
  --include-crds > rendered.yaml
sha256sum rendered.yaml
stat -c '%A %U:%G %s %n' rendered.yaml
```

Output:

```text
3d5189de873ddcdadffa9dbe72e49bde7b9eefb0cd4cbb46dd7e9b084afe74e5  rendered.yaml
-rw------- ubuntu:ubuntu 5219214 rendered.yaml
```

`helm template` is a local rendering operation. It did not contact the cluster to create resources.

The rendered hash differs from Step 4 because the chart generates random render-time data for Secret objects. This does not mean the chart or values changed:

- chart archive hash matches Step 4;
- values hash matches Step 4;
- chart metadata matches Step 4;
- object kinds/counts match Step 4;
- configured resource markers match Step 4.

The temporary rendered Secret values were never printed, copied to the repository, or installed. The manifest is protected by file mode `600` inside a mode-`700` directory. Step 7 must use Helm with the verified chart and values; it must not apply `rendered.yaml`.

## Sanitized rendered-object inventory

Command:

```text
grep '^kind:' rendered.yaml | sort | uniq -c
```

Result:

| Kind | Count |
|---|---:|
| Alertmanager | 1 |
| ClusterRole | 5 |
| ClusterRoleBinding | 5 |
| ConfigMap | 26 |
| CustomResourceDefinition | 10 |
| DaemonSet | 1 |
| Deployment | 3 |
| Job | 2 |
| MutatingWebhookConfiguration | 1 |
| Prometheus | 1 |
| PrometheusRule | 30 |
| Role | 1 |
| RoleBinding | 1 |
| Secret | 3 |
| Service | 7 |
| ServiceAccount | 7 |
| ServiceMonitor | 9 |
| ValidatingWebhookConfiguration | 1 |

Total objects: `114`, exactly matching Step 4.

No Secret body was included in the count output.

## Exposure, storage, and k3s checks

### Forbidden exposure/storage pattern check

Pattern:

```text
^kind: (Ingress|PersistentVolumeClaim)$|type: (NodePort|LoadBalancer)
```

Match count:

```text
0
```

### Disabled generic k3s targets

Pattern:

```text
kube-controller-manager|kube-scheduler|kube-etcd|kube-proxy
```

Match count:

```text
0
```

### Service types

Sanitized checks:

```text
lines containing both type: and ClusterIP: 6
lines containing type: and NodePort/LoadBalancer: 0
Service objects: 7
```

Six Services explicitly declare `ClusterIP`. The CoreDNS monitoring Service omits `type`, which Kubernetes defaults to `ClusterIP`. This matches the detailed Step 4 object-level inspection.

### Resource and retention markers

The remote render reproduced the Step 4 counts:

```text
cpu: 1500m       1
memory: 2Gi      1
cpu: 500m        2
memory: 512Mi    1
cpu: 300m        1
cpu: 200m        2
cpu: 100m        3
cpu: 50m         2
cpu: 20m         1
memory: 256Mi    3
memory: 128Mi    4
memory: 64Mi     1
memory: 32Mi     1
retention: 2d    1
scrapeInterval: 30s  1
```

## Inspection-command mistakes and corrections

These were read-only text-filter issues. They did not alter the remote files, chart, rendered manifest, namespace, or cluster.

### 1. Service type undercount from indentation assumption

Initial filter:

```text
grep -E '^  type: (ClusterIP|NodePort|LoadBalancer)'
```

Output: `2` explicit ClusterIP lines.

Cause: the filter assumed exactly two leading spaces. It did not match every YAML nesting level.

### 2. Retention grep quoting error

Initial result:

```text
grep: Trailing backslash
```

Cause: quote escaping did not survive the Windows PowerShell → SSH → Bash command chain.

Correction:

```text
grep -Ec 'retention:.*2d' rendered.yaml
```

Corrected output: `1`.

### 3. Quoted ClusterIP values still undercounted

The indentation-flexible filter still produced `2` because four Service templates emit `type: "ClusterIP"` while two emit the value without quotes.

### 4. Quote-tolerant regex was parsed locally

One attempted combined regex was interpreted by Windows PowerShell as a local pipeline. It failed before SSH and therefore performed no remote action.

Final simple checks avoided nested regex quoting:

```text
grep 'type:' rendered.yaml | grep 'ClusterIP' | wc -l
=> 6

grep 'type:' rendered.yaml | grep -E 'NodePort|LoadBalancer' | wc -l
=> 0
```

These results, together with seven Service objects and the Step 4 object-level parser, confirm all Services are internal.

## Final remote artifact inventory

```text
drwx------ ubuntu:ubuntu    4096 /tmp/buet-paas-monitoring-step6-20260923
-rw------- ubuntu:ubuntu    2472 .../values.yaml
-rw-r--r-- ubuntu:ubuntu  933672 .../kube-prometheus-stack-91.4.1.tgz
-rw------- ubuntu:ubuntu 5219214 .../rendered.yaml
```

Hashes:

```text
2d98fe9150c90ae7709864590b3145a94c8e369f6b1e9c06c9cf8d53f79a57b7  values.yaml
1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb  kube-prometheus-stack-91.4.1.tgz
3d5189de873ddcdadffa9dbe72e49bde7b9eefb0cd4cbb46dd7e9b084afe74e5  rendered.yaml
```

The chart archive is readable only through the mode-`700` parent directory, even though the file itself is mode `644`.

## Proof that nothing was installed

Post-render cluster output:

```text
NAME         STATUS   AGE   LABELS
monitoring   Active   14m   kubernetes.io/metadata.name=monitoring

No resources found in monitoring namespace.

NAME                         DATA   AGE
configmap/kube-root-ca.crt   1      14m

NAME                     AGE
serviceaccount/default   14m
```

Representative Prometheus Operator CRD lookups returned empty output.

Helm output:

```text
NAME  NAMESPACE  REVISION  UPDATED  STATUS  CHART  APP VERSION
```

Therefore:

```text
Helm releases in monitoring: 0
Monitoring workloads:        0
Monitoring Services:         0
PVCs:                        0
Secrets:                     0
Prometheus Operator CRDs:    0
```

Only the Step 5 namespace and its automatic bootstrap objects remain in the cluster.

## Rollback and cleanup

No cluster rollback is required because Step 6 did not change Kubernetes.

The only remote Step 6 changes are files inside:

```text
/tmp/buet-paas-monitoring-step6-20260923
```

They are intentionally retained for exact Step 7 reuse. Do not remove them until Step 7 either succeeds, is abandoned, or the user explicitly authorizes cleanup.

The cluster namespace rollback from Step 5 remains a separate destructive action and was not performed.

## Local repository impact

New documentation:

```text
step-6.md
implementation of monitoring.md journal entry 007
```

No existing tracked repository file was modified, and no commit was created.

## Step 6 conclusion

```text
Remote values hash:       MATCH
Pinned OCI digest:        MATCH
Chart archive hash:       MATCH STEP 4
Chart metadata:           MATCH
Helm lint:                PASS
Remote Helm template:     PASS
Rendered object counts:   MATCH STEP 4
Public exposure/PVCs:     NONE
Disabled k3s targets:     ABSENT
Helm releases:            0
Cluster writes in Step 6: NONE
```

## Next step — not yet executed

Step 7 installs `kube-prometheus-stack` and is a substantial cluster mutation.

Proposed safe flow:

1. recheck namespace emptiness, cluster node readiness, pre-existing unhealthy workloads, artifact hashes, chart digest, and Helm release absence;
2. use the verified chart archive and verified values file from the protected Step 6 directory;
3. run one pinned command equivalent to:

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

4. do not use `--create-namespace` because the reviewed namespace already exists;
5. monitor the command and stop if prerequisites changed;
6. verify Helm status, CRDs, Pods, Deployments, DaemonSet, operator-created StatefulSets, Services, PVC absence, events, and cluster regressions;
7. record everything in `step-7.md`.

Important limitation: Helm's `--atomic` can remove a failed release, but CRDs installed from a chart's `crds/` directory are not normally removed automatically. A failed Step 7 may therefore leave Prometheus Operator CRDs that require a separately reviewed cleanup decision.

Do not execute Step 7 until the user explicitly says `Approve Step 7`.
