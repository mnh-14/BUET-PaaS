# Step 15D4 - Atomically apply and verify deployer Blackbox probe

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15D4 - atomically apply and verify the deployer Blackbox probe`
- Result: **complete**
- Final Blackbox Helm revision: 7, deployed
- Live probes: frontend, backend, and deployer
- Rollback: prepared but not triggered
- kube-prometheus-stack revision: 6, unchanged

## Preflight

The guarded preflight confirmed:

```text
Blackbox revision:             6, deployed
live ServiceMonitors:          frontend and backend only
frontend probe_success:        1
backend probe_success:         1
Prometheus count(up):          33
Prometheus DOWN:               zero
deployer Service /health:      {"status":"ok"}
```

Repository hashes matched the Step 15D3-reviewed inputs. The chart pull also
matched both pinned identities:

```text
chart:          prometheus-blackbox-exporter 11.18.0
OCI digest:     sha256:92342bff9fb25767c18d6d1a12f075502061f2dc495e9f66339664fd1a40a4eb
archive SHA256: 19322b26614c62d6277a1471e26c0b5379ce9ebf43897e01ab85d3e164594ab8
overlay SHA256: 4d15271085e1ca674fde6d366a9fbc507a9d6b406093bc090beb21dafdeec3a5
```

## Guarded transaction

The transaction first ran `helm upgrade --dry-run=server --hide-secret` with
the exact chart, base values, and cumulative three-target overlay. Its captured
output SHA-256 was:

```text
4f9f1241a59ded65fb7ff754cbac9f4eba35af15a4487051cf032260a2528096
```

After dry-run success, the same inputs were applied with `--atomic --wait` and
a ten-minute timeout. Helm deployed revision 7. A bounded convergence loop then
required all probe, target, label, count, and regression checks to pass in the
same observation window. Every condition passed, so the prepared rollback to
revision 6 was not invoked.

## Final probes

Exactly three ServiceMonitors and three active Blackbox targets exist:

| Service | Module | Target | Result |
|---|---|---|---|
| frontend | `http_frontend` | `http://192.168.128.15/` | success 1, HTTP 200 |
| backend | `http_json_ok` | `http://192.168.128.131:8020/health` | success 1, HTTP 200 |
| deployer | `http_json_ok` | `http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health` | success 1, HTTP 200 |

Observed final durations:

```text
frontend: 0.007273573 seconds
backend:  0.006389404 seconds
deployer: 0.189194437 seconds
```

All active targets reported `health=up` and an empty `lastError`. Their
`instance`, `target`, `service`, `environment`, and `deployment_type` labels
were unique and correct. The deployer probe's success proves both HTTP 200 and
the configured `"status":"ok"` body requirement. A separate Kubernetes
Service proxy request returned the same healthy JSON body.

## Regression and security result

```text
Prometheus count(up):       34
Prometheus DOWN:            zero
standalone VM exporters UP: 6/6
Kubernetes nodes:           4/4 Ready
monitoring Pods:            10 Running, zero restarts
frontend marker:            BUET-PaaS present
backend dependency health:  status ok, MongoDB connected
deployer health:            status ok
```

The kube-prometheus-stack remained revision 6. The Blackbox Pod did not roll
or restart. The Service remains ClusterIP-only on 9115 with no external IP and
no Blackbox Ingress. The Prometheus-only NetworkPolicy, immutable image digest,
disabled service-account-token mount, non-root UID/GID 1000, read-only root
filesystem, dropped capabilities, no privilege escalation, and resource
limits remain intact. The final exporter log sample contained no
error/fatal/panic entries.

No application, OpenStack, DNS, ingress, public port, credential, TLS secret,
or kube-prometheus-stack configuration was changed.

## Repeatable scripts

```text
step15d4-preflight.sh    93d27dc6367dc525334e890d000ac4edbc9d1e8fe35dd5745d380fe5373df674
step15d4-transaction.sh  11619a2b1c18d95bc08788b53cc6714d37c1b0b4e6716bb95a94233c71a1a603
step15d4-verify.sh       c96934edf305521a00b0c4c647ee62a038a9a24cc246d34d7a3e5a89412b9725
step15d4-diagnose.sh     c52dc0559aed041db81c6a4a55afc3ef82a187ce27a332f500e2057351ff4ed3
```

## Cleanup

The exact `/tmp/buet-paas-step15d4` staging tree was enumerated, removed, and
confirmed absent after evidence capture. No live resource was part of cleanup.

## Next approval

The next gate is offline-only. It will prepare a cumulative four-target overlay
that retains frontend, backend, and deployer and adds only Harbor through the
already reviewed strict-TLS module and mounted public Harbor CA. It will not
apply anything live.

```text
Approve Step 15D5 - prepare and offline verify the frontend, backend, deployer, and Harbor Blackbox target overlay
```
