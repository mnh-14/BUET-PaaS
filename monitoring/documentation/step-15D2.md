# Step 15D2 - Atomically apply and verify backend Blackbox probe

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15D2 - atomically apply and verify the backend Blackbox probe`
- Result: **complete**
- Final Blackbox Helm revision: 6, deployed
- Live probes: frontend and backend
- Safety rollbacks: two successful automatic verification rollbacks
- kube-prometheus-stack revision: 6, unchanged

## Initial preflight

Before the first upgrade:

```text
Blackbox release:       revision 1, deployed
live ServiceMonitors:   frontend only
frontend probe:         success 1, HTTP 200
Prometheus:             32 UP, zero DOWN
backend /health:        HTTP success
backend body:           status ok, version 0.2.0, MongoDB connected
```

The pinned chart OCI/archive, base values, and cumulative overlay hashes
matched the reviewed repository. Each attempt ran a server-side Helm dry run
before its atomic upgrade.

## First safe attempt and rollback

Revision 2 deployed the cumulative two-target overlay. The backend target did
in fact return `probe_success=1` and HTTP 200. However, the first verifier
evaluated probe samples and Prometheus target discovery in separate moments;
its exact-state assertion raced discovery convergence and failed. The guard
automatically rolled back to the revision-1 configuration, creating deployed
revision 3.

Rollback verification showed exactly one frontend ServiceMonitor, 32 UP, zero
DOWN, and a healthy frontend canary. No application or monitoring outage
occurred.

A manual Kubernetes API service-proxy request to Blackbox returned 502 while
Prometheus scraping continued to work. This is expected evidence that the
Prometheus-only NetworkPolicy blocks non-Prometheus ingress to port 9115.

## Second safe attempt and label diagnosis

The verifier was changed to require all conditions in one bounded convergence
loop. Revision 4 deployed and both frontend/backend active targets were UP,
both probes succeeded, both returned HTTP 200, and no target was DOWN.

The only mismatch was total `count(up)=32`, not the expected 33. The cause was
the chart's separation between metric relabeling and target relabeling:

- probe metrics already had distinct `service` and `target` labels;
- Prometheus-generated `up` series do not pass through metric relabeling;
- both ServiceMonitors therefore produced identical target labels for `up`.

The guard correctly treated this as an incomplete acceptance result and rolled
back revision 4 to the healthy configuration as deployed revision 5.

## Corrective configuration

Every staged target now uses the chart's supported `additionalRelabeling` to
set stable pre-scrape labels:

```text
instance
target
service
environment
deployment_type
```

This makes `up`, scrape metadata, alerts, and probe metrics consistently
distinguishable. Frontend-only, frontend-plus-backend, and future all-target
overlays were all updated to prevent recurrence.

Current overlay hashes:

```text
frontend:         9fe865b0db0dfdb241f7f646b7a8033fc434e5db5f5f3f3c4561a56afdd1b0fe
frontend-backend: 5f412b07a85c01141b622c0467895e8698af296c86105aae2396988d9bf28fad
all-target:       997b626a87edb2d87d9f4ba3ef1a263d9e76486855ea8571920780f43a72644e
```

All three overlays passed Helm lint/render again. The native pinned exporter
accepted the four-module configuration. The corrected cumulative render hash
is:

```text
a705eee23ac8088d8919fd627b2267eeb015ff87c0f6bfe95dd59d360ba319d9
```

## Final atomic upgrade

From healthy revision 5, the corrected configuration passed server dry-run and
was atomically upgraded to revision 6. The bounded verifier converged and the
rollback branch did not run.

```text
release:   blackbox-exporter
revision:  6
status:    deployed
chart:     prometheus-blackbox-exporter-11.18.0
app:       v0.28.0
dry-run SHA256: 3866b6c4720ca31ca1591e21d5fda7664630087154267adb0b7361677a734952
```

## Final probe evidence

Exactly two live ServiceMonitors exist:

| Service | Module | Target | Result |
|---|---|---|---|
| frontend | `http_frontend` | `http://192.168.128.15/` | success 1, HTTP 200 |
| backend | `http_json_ok` | `http://192.168.128.131:8020/health` | success 1, HTTP 200 |

Observed durations at final verification:

```text
frontend: 0.007849828 seconds
backend:  0.006044354 seconds
```

Prometheus active-target evidence:

```text
targets:    exactly 2
health:     both up
lastError:  empty for both
labels:     unique instance/target/service/environment/deployment_type
modules:    one http_frontend, one http_json_ok
```

## Regression and security result

```text
Prometheus count(up):       33
Prometheus DOWN:            zero
standalone VM exporters UP: 6/6
Kubernetes nodes:           4/4 Ready
monitoring Pods:            10 Running, zero restarts
Blackbox Pod:               same Pod, Ready, zero restarts
exporter logs:              INFO only; no error/fatal/panic
kube-prometheus-stack:      revision 6 unchanged
```

Blackbox remains ClusterIP-only with the same Prometheus-only NetworkPolicy,
immutable image digest, non-root/read-only security context, and public Harbor
CA mount. No Ingress, public port, DNS, security-group, or application change
was made.

## Cleanup

The exact `/tmp/buet-paas-step15d2` directory was enumerated, removed, and
confirmed absent. The offline-validator container exited and its newly pulled
Docker cache image was removed; the live Kubernetes worker image was not
touched.

## Next approval

The next one-service gate is offline-only: prepare a cumulative overlay that
retains frontend and backend and adds only the in-cluster deployer health URL.

```text
Approve Step 15D3 - prepare and offline verify the frontend, backend, and deployer Blackbox target overlay
```
