# Step 16D - Apply and verify BUET-PaaS MVP alert rules

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 16D - atomically apply and verify the BUET-PaaS MVP alert rules`
- Result: **complete**
- Live change: one PrometheusRule, `monitoring/buet-paas-mvp-alerts`
- Rollback: prepared but not triggered
- kube-prometheus-stack revision: 6, unchanged
- Blackbox revision: 9, unchanged

## Preflight and transaction

The reviewed Step 16C rule and Kustomization hashes matched. The live
PrometheusRule was absent, 30 existing rule objects were present, and
Prometheus reported 36 targets UP and zero DOWN. Kustomize regenerated one
PrometheusRule, no Secret or ConfigMap, with the exact reviewed render SHA-256:

```text
13adcdb3ce53b2a116b62e97c3ef4794523cf59bc802b5a24cf70e1cc202ee42
```

The manifest passed `kubectl apply --dry-run=server`. The guarded transaction
then created only `monitoring/buet-paas-mvp-alerts`. The stored object had
`release=monitoring-stack`, two groups, and four expected alerts.

## Live evaluation

The Prometheus rules API showed both groups loaded and all four alerts with
`health=ok`, `state=inactive`, zero attached alerts, and a recent evaluation
timestamp:

```text
BUETPaaSServiceProbeFailed          inactive, healthy
BUETPaaSServiceProbeTargetMissing   inactive, healthy
BUETPaaSStandaloneVMTargetMissing   inactive, healthy
BUETPaaSStandaloneVMRootDiskLow     inactive, healthy
```

No BUET-PaaS alert was pending or firing. The six previously firing built-in
alerts remained: `Watchdog`, `InfoInhibitor`, `KubePodCrashLooping`,
`KubePodNotReady`, `KubeDeploymentReplicasMismatch`, and
`KubeDeploymentRolloutStuck`. A built-in `CPUThrottlingHigh` briefly appeared
as pending; it was unrelated to the new rules.

The PrometheusRule count rose from 30 to 31. Prometheus stayed at 36 UP and
zero DOWN; ten monitoring Pods stayed Running with zero restarts. Both Helm
revisions were unchanged. No notification receiver, application, ingress,
certificate, Secret, OpenStack rule, or public port changed.

## Safe lifecycle test

The pinned Prometheus v3.14.0 `promtool test rules` ran synthetic series against
the exact rule expressions and returned `SUCCESS`. It covered:

- service probe pending before five minutes, firing after five minutes, and
  resolved after recovery;
- both missing-target alerts pending before ten minutes and firing after;
- writable standalone VM root disk pending before fifteen minutes and firing
  after.

No real service was stopped or metric changed for the test. Live behavior was
verified only in the healthy/inactive state; pending, firing, and resolved
transitions were verified offline with synthetic samples.

## Files and cleanup

```text
step16d-apply-verify.sh    23e85389f447a0e002592f832cb3af245674fb3425b8963f9560df97df948a38
step16d-synthetic-test.sh  780fb1c7da1e4475c25974c50270772092547e4c640a9d9fec459e2e8e6df5b5
step16d-rule-test.yaml     a572e8df00a12c2e61162cddb2ada8d377317f7fbb6a5c2fc6c406bd631f58a7
```

The exact `/tmp/buet-paas-step16d` staging directory and unused Docker
validator image cache were enumerated, removed, and confirmed absent. The
live PrometheusRule remained in place.

## Next decision

Step 16E concerns notification delivery. Alertmanager currently displays and
groups alerts, but no team notification receiver has been selected. Choose
whether the three-day MVP stops with authenticated Alertmanager/Grafana UI
review or adds a team-owned email/chat receiver. Receiver credentials require
a separate protected Secret and approval before configuration.
