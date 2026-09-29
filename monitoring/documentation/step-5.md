# Step 5 — Create the monitoring namespace

## Status

- Permission received: `Approve Step 5`
- Execution date: 2026-09-23 (Asia/Dhaka)
- Step type: first Kubernetes cluster mutation
- Intended durable change: create namespace `monitoring`
- Result: **completed successfully**
- Helm/chart installation: not performed
- Standalone VM changes: none
- Existing application changes: none

## What this step means in plain language

The Kubernetes namespace is an empty administrative boundary where monitoring resources can be installed later. Creating it does not install Prometheus, Grafana, Alertmanager, exporters, CRDs, or a Helm release.

Step 5 followed this sequence:

```text
read-only tool and permission check
    -> confirm namespace does not exist
    -> create only namespace monitoring
    -> read namespace back
    -> confirm no workload, PVC, Secret, chart, or monitoring CRD was installed
    -> stop
```

## Connection route

The command route was:

```text
Windows workstation
  -> SSH using mykey.pem
k3s-user (ubuntu@192.168.64.242)
  -> nested SSH using its existing key and trusted host entry
k3s-control-01 (ubuntu@192.168.128.101)
  -> sudo -n k3s kubectl
Kubernetes API
```

No private-key content, kubeconfig, token, password, or Secret value was printed or written to the repository.

## Safety gate before mutation

Input from Windows PowerShell:

```powershell
ssh -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ubuntu@192.168.64.242 `
  "ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes ubuntu@192.168.128.101 'hostname; id; sudo -n k3s kubectl version; sudo -n k3s kubectl config current-context; sudo -n k3s kubectl auth can-i create namespaces; sudo -n k3s kubectl auth can-i get namespaces; sudo -n k3s kubectl get namespace monitoring --ignore-not-found -o name'"
```

Output:

```text
k3s-control-01
uid=1000(ubuntu) gid=1000(ubuntu) groups=...,27(sudo),...
Client Version: v1.36.2+k3s1
Kustomize Version: v5.8.1
Server Version: v1.36.2+k3s1
default
Warning: resource 'namespaces' is not namespace scoped
yes
Warning: resource 'namespaces' is not namespace scoped
yes
```

There was no final `namespace/monitoring` line. With `--ignore-not-found -o name`, empty output means the object did not exist.

Interpretation:

- the command reached the intended control node;
- non-interactive sudo worked;
- the server-bundled client exactly matched the API server at `v1.36.2+k3s1`;
- the active context was `default`;
- authorization allowed namespace create/read;
- namespace `monitoring` was absent.

The two warnings are expected because namespaces are cluster-scoped, not namespaced. Both authorization queries returned `yes` and the overall command exited successfully.

## The only explicit mutating command

Input:

```powershell
ssh -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ubuntu@192.168.64.242 `
  "ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes ubuntu@192.168.128.101 'sudo -n k3s kubectl create namespace monitoring'"
```

Output:

```text
namespace/monitoring created
```

Exit code: `0`.

No label, annotation, ResourceQuota, LimitRange, NetworkPolicy, ServiceAccount, Role, RoleBinding, Deployment, Service, Secret, ConfigMap, CRD, PVC, or Helm release was explicitly submitted by this command.

## Post-create verification

### Namespace and object inventory

Input:

```powershell
ssh -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ubuntu@192.168.64.242 `
  "ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes ubuntu@192.168.128.101 'sudo -n k3s kubectl get namespace monitoring -o wide --show-labels; sudo -n k3s kubectl get all -n monitoring; sudo -n k3s kubectl get configmap,secret,pvc,serviceaccount -n monitoring; sudo -n k3s kubectl get crd alertmanagers.monitoring.coreos.com --ignore-not-found -o name; sudo -n k3s kubectl get crd servicemonitors.monitoring.coreos.com --ignore-not-found -o name'"
```

Output:

```text
NAME         STATUS   AGE   LABELS
monitoring   Active   51s   kubernetes.io/metadata.name=monitoring

No resources found in monitoring namespace.

NAME                         DATA   AGE
configmap/kube-root-ca.crt   1      51s

NAME                     AGE
serviceaccount/default   51s
```

The two CRD queries returned empty output, confirming that representative Prometheus Operator CRDs remained absent.

Important explanation: Kubernetes controllers automatically created `serviceaccount/default` and `configmap/kube-root-ca.crt` when the namespace appeared. We did not submit those objects. They are normal namespace bootstrap objects and have the same age as the namespace.

`kubectl get all` reported no resources, so there were no Pods, Services, Deployments, StatefulSets, DaemonSets, ReplicaSets, Jobs, or other objects included by the `all` category.

There were also no Secrets or PVCs.

### Helm verification

Input:

```powershell
ssh -o BatchMode=yes `
  -o IdentitiesOnly=yes `
  -o ConnectTimeout=15 `
  -o StrictHostKeyChecking=yes `
  -i "C:\Users\USER\Downloads\mykey.pem" `
  ubuntu@192.168.64.242 `
  "helm list --namespace monitoring"
```

Output:

```text
NAME  NAMESPACE  REVISION  UPDATED  STATUS  CHART  APP VERSION
```

The header-only result confirms that no Helm release exists in `monitoring`.

### Immutable namespace audit identifiers

Input:

```text
sudo -n k3s kubectl get namespace monitoring \
  -o custom-columns=NAME:.metadata.name,UID:.metadata.uid,CREATED:.metadata.creationTimestamp,STATUS:.status.phase
```

Output:

```text
NAME         UID                                    CREATED                STATUS
monitoring   aefef0b6-83cc-4700-815a-7592fed5225b   2026-09-23T16:46:29Z   Active
```

Namespace count after creation: `17`. Step 2 recorded `16`, so the expected net change is exactly one namespace.

## Before-and-after comparison

| Item | Before Step 5 | After Step 5 |
|---|---:|---:|
| Namespaces | 16 | 17 |
| Namespace `monitoring` | absent | Active |
| Monitoring Helm releases | 0 | 0 |
| Monitoring workloads | 0 | 0 |
| Monitoring Services | 0 | 0 |
| Monitoring PVCs | 0 | 0 |
| Prometheus Operator CRDs | 0 | 0 |
| Existing application workloads changed | no | no |

The only intentional durable change is namespace `monitoring`. The default ServiceAccount and root CA ConfigMap are automatic consequences of namespace creation.

## Errors and unexpected behavior

No command failed.

Expected informational messages:

```text
Warning: resource 'namespaces' is not namespace scoped
```

Cause: `kubectl auth can-i` was asked about a cluster-scoped resource. The result was still `yes` for both create and get.

No correction or retry was required.

## Rollback

Rollback was **not executed**.

If the user explicitly authorizes rollback before anything else is installed, the exact rollback command is:

```text
sudo -n k3s kubectl delete namespace monitoring
```

Expected effect:

- namespace `monitoring` would be deleted;
- its automatically generated default ServiceAccount and root CA ConfigMap would be deleted with it.

This command becomes materially more destructive after monitoring workloads are installed because namespace deletion removes all namespaced resources inside it. Therefore it must never be run later without a fresh inventory and explicit permission.

## Local repository impact

New documentation:

```text
step-5.md
implementation of monitoring.md journal entry 006
```

No existing tracked repository file was modified. No commit was created.

## Step 5 conclusion

```text
Matching kubectl safety gate: PASS
Namespace created:             monitoring
Namespace status:              Active
Namespace count delta:         +1
Monitoring workloads:          0
Helm releases:                 0
PVCs:                          0
Prometheus Operator CRDs:      0
Command failures:              0
```

## Next step — not yet executed

Step 6 prepares the pinned chart on the administration VM but installs no workload.

Because Step 4 already validated the official OCI artifact locally, Step 6 should use the same OCI source instead of adding a mutable Helm repository alias. Proposed flow:

1. copy only `monitoring/prometheus/values.yaml` to a dedicated temporary/work directory on `k3s-user`;
2. verify its SHA-256 equals `2d98fe9150c90ae7709864590b3145a94c8e369f6b1e9c06c9cf8d53f79a57b7`;
3. pull `oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack` version `91.4.1` using remote Helm `v3.22.0`;
4. verify OCI digest `sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9`;
5. run remote `helm lint` and `helm template` with Kubernetes version `1.36.2` and namespace `monitoring`;
6. inspect and compare sanitized object counts with Step 4;
7. create `step-6.md`;
8. run no `helm install`, `helm upgrade`, or kubectl mutation.

Do not execute Step 6 until the user explicitly says `Approve Step 6`.
