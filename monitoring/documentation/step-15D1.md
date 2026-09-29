# Step 15D1 - Prepare frontend plus backend Blackbox overlay

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15D1 - prepare and offline verify the frontend plus backend Blackbox target overlay`
- Result: **complete**
- Live Kubernetes/Helm mutation: **none**
- Next permission boundary: Step 15D2

## Prepared overlay

New repository file:

```text
monitoring/blackbox/targets-frontend-backend.yaml
SHA-256: 777086c84563526c901dcc89b493ae8c47009a09e4f58a3160c95824d1337466
```

This was the Step 15D1 preparation hash. Step 15D2 later added required
pre-scrape target relabeling so generated `up` series are unique. The current
overlay hash is `5f412b07a85c01141b622c0467895e8698af296c86105aae2396988d9bf28fad`;
the change and revalidation are recorded in `step-15D2.md`.

It is cumulative and contains exactly:

| Service | Target | Module |
|---|---|---|
| frontend | `http://192.168.128.15/` | `http_frontend` |
| backend | `http://192.168.128.131:8020/health` | `http_json_ok` |

Both targets retain `environment=buet-paas` and
`deployment_type=blackbox`. Their service labels are `frontend` and `backend`.
Deployer, Harbor, and SonarQube are deliberately absent.

## Pinned inputs

```text
chart:          prometheus-blackbox-exporter 11.18.0
app:            v0.28.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
archive SHA256: 19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
image digest:   sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc
```

The previously reviewed values, public Harbor CA, Kustomize file, and
NetworkPolicy hashes also matched the repository.

## Offline validation

The repeatable verifier now covers three rollout stages:

```text
frontend-only render:          1 ServiceMonitor
frontend-plus-backend render:  2 ServiceMonitors
all-target render:             5 ServiceMonitors
```

All three combinations passed Helm lint with zero failures for Kubernetes
1.36.2. The cumulative render contains exactly the frontend and backend names,
URLs, modules, and labels. A negative assertion confirmed that no deployer,
Harbor, or SonarQube ServiceMonitor entered this stage.

The full rendered Blackbox configuration still contains exactly four reviewed
modules and no generic `http_2xx` module. The exact immutable exporter image
loaded it successfully and returned `Config file is ok exiting...`. No Ingress
rendered; the ClusterIP, non-root security controls, public CA mount, and
Prometheus-only NetworkPolicy remain unchanged.

Relevant hashes:

```text
cumulative render: 98ca3931c87757c045aa5205274c3f6061ac32d2e24a9c13db4104def4caa18d
Blackbox config:   9e843c719fd059230c51dc2f73ef93e98e12f2cef25d5832ed103c929cdfe52f
platform render:   644ba51e74841e87e6dbb4fe7f5034bf44ace462d112f7b4930dc6c611ba76c8
```

## Live-state proof

Read-only checks before and after offline validation confirmed:

```text
Blackbox Helm release: revision 1, deployed
live ServiceMonitors:  exactly 1, frontend only
frontend probe:        success 1, HTTP 200, target UP
Prometheus count(up):  32
Prometheus DOWN:       zero
Blackbox Pod:          Ready, zero restarts
```

Therefore the backend probe is prepared but not live. No Kubernetes object,
Helm release, application, network rule, or browser route changed.

## Cleanup

The exact `/tmp/buet-paas-step15d1` validation directory was enumerated,
removed, and confirmed absent. The ephemeral exact-digest validator container
exited, and its newly pulled Docker image cache was removed. This did not touch
the running Kubernetes image on the worker node.

## Next approval

Step 15D2 will server-dry-run and atomically upgrade only the Blackbox Helm
release from the frontend-only overlay to this cumulative two-target overlay.
It must prove both probes UP, backend `probe_success=1` and HTTP 200, total
Prometheus targets 33 with zero DOWN, frontend regression safety, and rollback
to release revision 1 if verification fails.

```text
Approve Step 15D2 - atomically apply and verify the backend Blackbox probe
```
