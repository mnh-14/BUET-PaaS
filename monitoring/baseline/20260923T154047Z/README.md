# Day-0 Kubernetes Baseline

- Snapshot time: `2026-09-23T15:40:47Z`
- Administration host: `ubuntu@k3s-user` (`192.168.64.242`)
- Kubernetes API: `https://192.168.128.101:6443`
- Context: `default`
- Collection method: read-only `kubectl` and `helm` commands over SSH
- Cluster mutations: none

This directory is the sanitized pre-monitoring baseline. Secrets, kubeconfig contents, private keys, tokens, node machine IDs, and full node annotations are intentionally excluded.

## Baseline conclusions

- All four k3s nodes are `Ready`.
- No node reports `MemoryPressure`, `DiskPressure`, or `PIDPressure`.
- Metrics Server is installed and `kubectl top nodes` works.
- No `monitoring` namespace exists.
- No Prometheus/Grafana/Alertmanager Helm release exists.
- No Prometheus Operator `monitoring.coreos.com` CRDs exist.
- Existing Helm releases are Falco and Traefik only.
- One existing student Deployment is unavailable before monitoring: `2105062/to-do-backend-deployment`.
- Its Pod is in `CrashLoopBackOff` because its readiness endpoint returns HTTP 404.
- One previous build attempt Pod is in `Error`, while the current Job object is complete after a later successful attempt.
- CoreDNS and MetalLB speaker Pods have pre-existing `DNSConfigForming` warnings about too many nameservers.

These conditions must not be attributed to the future monitoring installation. They are comparison points for the post-install regression check.

## Commands represented by this baseline

```bash
kubectl get nodes -o wide
kubectl get namespaces
kubectl get pods -A -o wide
kubectl get deployments -A
kubectl get statefulsets -A
kubectl get daemonsets -A
kubectl get services -A
kubectl get jobs -A
kubectl get pvc -A
kubectl get storageclass
kubectl get ingress -A
kubectl cluster-info
kubectl version -o json
helm version --short
helm list -A
kubectl get events -A --sort-by=.lastTimestamp
kubectl describe node k3s-control-01
kubectl describe node k3s-worker-01
kubectl describe node k3s-worker-02
kubectl describe node k3s-worker-03
kubectl top nodes
```

