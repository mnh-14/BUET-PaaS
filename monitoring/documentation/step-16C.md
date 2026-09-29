# Step 16C - Prepare and offline verify MVP alert rules

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 16C - prepare and offline verify the BUET-PaaS MVP alert rules`
- Result: **complete**
- Live PrometheusRule apply: **none**
- Next permission boundary: Step 16D live apply and verification

## Read-only alert audit

The live Prometheus selects PrometheusRules labeled `release=monitoring-stack`.
Built-in rules already cover `TargetDown`, `KubeNodeNotReady`,
`KubePodCrashLooping`, `KubeDeploymentReplicasMismatch`, `KubeJobFailed`, and
k3s node filesystem space. The node filesystem rule selects
`job="node-exporter"`, so it does not cover the six standalone VMs under
`job="standalone-node-exporters"`.

At audit time, six alerts were firing. `Watchdog` and `InfoInhibitor` are
expected control alerts. The four actionable warnings concerned a crash
looping `to-do-backend-deployment` Pod and its Deployment in namespace
`2105062`: `KubePodCrashLooping`, `KubePodNotReady`,
`KubeDeploymentReplicasMismatch`, and `KubeDeploymentRolloutStuck`. The
one-hour restart query showed about 17 restarts for that Pod; the other top
sampled Pods showed zero. This is an existing application incident, not a
failure created by the proposed rules.

All six standalone VM scrape targets and all five Blackbox probes were UP.
Each VM root filesystem was writable, with available space ranging from about
32.7% to 84.7%. Prometheus had 36 UP and zero DOWN targets.

## Prepared rule set

The repository contains one labeled PrometheusRule with two groups and four
alerts:

| Alert | Trigger | Hold | Severity |
|---|---|---:|---|
| `BUETPaaSServiceProbeFailed` | Blackbox `probe_success=0` | 5m | critical |
| `BUETPaaSServiceProbeTargetMissing` | Fewer than five probe series | 10m | warning |
| `BUETPaaSStandaloneVMTargetMissing` | Fewer than six VM `up` series | 10m | warning |
| `BUETPaaSStandaloneVMRootDiskLow` | Writable VM root disk below 15% available | 15m | warning |

The built-in `TargetDown` remains responsible for exporter scrape failures;
the Kubernetes node, Pod, Deployment, and Job rules remain responsible for
their existing conditions. This avoids duplicate incident alerts for the
current student workload. A separate maintenance policy documents exact,
time-limited silences and the special care needed for fleet-count alerts.

## Offline and read-only validation

Kustomize rendered exactly one PrometheusRule, no Secret, and no ConfigMap.
The rendered object was semantically identical to the reviewed source. The
Prometheus selector label, four alert names, hold times, severity/team labels,
annotations, and key query constraints passed structural checks. The pinned
Prometheus v3.14.0 image ran `promtool check rules` successfully:

```text
SUCCESS: 4 rules found
```

Each exact proposed expression was then evaluated through the live Prometheus
API read-only. All four returned a successful vector response with zero
current matches. The new PrometheusRule object remained absent from the
cluster. Overall target state remained 36 UP, zero DOWN.

## Hashes

```text
prometheus-rule.yaml           1418ab588cce202a66b808d7634d355e2313b5e6ab4b2bf99fa99c37f10c6d5b
kustomization.yaml             7ac4439140f27f9a3de938bf29e553bbb6d3a7118f57ebbac7d99339c2fb90a6
MAINTENANCE.md                 04fabeb0789cb81349714d1658b479705a72f3fb51234fc2d9f475957d2743ed
offline-verify.py              3c77cd021c986a3b84a9c46d66f8f6307ae3ab1006371a22359ee8b08c6c1a98
offline-verify.sh              aaec5f0f609bcc5dba1466da67bdd94a0be0c1014f9b872dac679847f7355727
step16c-live-query-check.sh    a08f56ae78bb93c61f106bd94091eb1928d3187f8f87d03886215ea4b372ddbf
step16c-readonly-audit.sh      e4aa377c8db04bc2cc240f79bd68854720c640e3a5ade156385dc8bd028bcb78
rendered PrometheusRule        13adcdb3ce53b2a116b62e97c3ef4794523cf59bc802b5a24cf70e1cc202ee42
native promtool rule file      a57563146295777abeb609edc95042b90e40261112153a8d51f395cd503afa62
```

The exact `/tmp/buet-paas-step16c` validation directory and unused Docker
validator image cache were enumerated, removed, and confirmed absent.

## Next approval

Step 16D will server-dry-run and apply only this PrometheusRule, verify that
the operator selects it, all four rules evaluate healthy, and existing alerts
and targets remain stable. It will remove the new rule if verification fails.
It will not configure a notification receiver.

```text
Approve Step 16D - atomically apply and verify the BUET-PaaS MVP alert rules
```
