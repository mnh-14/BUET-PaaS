# BUET-PaaS Monitoring — current overview

**Reviewed:** 2026-09-25 (Asia/Dhaka)  
**Scope:** Cross-check of the [user-supplied 3-day plan](monitoring/BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md) against repository configuration and the recorded implementation/verification notes. This review is read-only with respect to the cluster. **No fresh live cluster query was run for this document**; counts below are the last recorded Step 16B–16E observations, not a guarantee of the present moment.

## Executive result

The plan's five primary MVP outcomes are evidenced as complete for **operator use**: k3s monitoring, six standalone VM metrics, five HTTP/service probes, browser-based Grafana, and visible alerts. The implementation uses authenticated, VPN-only HTTPS browser links rather than the early plan's port-forward examples. The operator-facing three-day MVP is complete, but the exact detailed panel/alert wish list is only **partially** implemented. Persistent storage, automatic alert delivery, student project-scoped monitoring, central logs, and integration into a BUET-PaaS admin page are not complete.

| Plan area | Cross-checked status | Evidence and qualification |
|---|---|---|
| Day-0 baseline, cluster/capacity preflight | Complete as recorded | [Baseline snapshot](../baseline/20260923T154047Z/README.md) and [continuation plan](step-13-plan.md). This is historical evidence, not a fresh capacity reading. |
| Day 1: monitoring namespace, Prometheus, Grafana, Alertmanager, kube-state-metrics, four k3s node exporters | Complete as recorded | [Step 13 status](step-13-plan.md) records kube-prometheus-stack 91.4.1, Helm revision 6, four node exporters, and healthy core services. [Base values](../prometheus/values.yaml) declare the components. |
| Browser access and built-in dashboards | Complete as recorded | User screenshots showed Grafana, Prometheus, and Alertmanager in browsers. [UI runbook](monitoring/alerts/UI-ONLY-RUNBOOK.md) has the VPN HTTPS links. This supersedes port forwarding for normal operator access; the tools remain separately authenticated. |
| Day 2: six standalone VM exporters | Complete as recorded | [Scrape configuration](../external-vms/scrape-values.yaml) lists frontend, database, registry, k3s-user, backend, and SonarQube private-IP targets. [Step 13 status](step-13-plan.md) records six of six live and UP. |
| Day 2: frontend, backend, deployer, Harbor, SonarQube service probes | Complete as recorded | [Final Blackbox targets](../blackbox/targets-all.yaml) list five semantic probes. [Step 13 status](step-13-plan.md) records Blackbox revision 9 and five of five UP. |
| Day 3: BUET-PaaS overview dashboard | Complete, with narrower detailed layout than the original wish list | [Dashboard JSON](../dashboards/buet-paas-overview.json) has 16 panels; [Step 16B](step-16B.md) records live provisioning and successful execution of all 16 queries. The dashboard covers targets, nodes, VMs, probes, alerts, pod phases/restarts, replicas, failed jobs, CPU, memory, and root filesystem free. It does **not** contain every original row/panel separately—for example per-VM network RX/TX, a dedicated registry disk panel, and separate desired/ready replica or successful-job panels. |
| Day 3: useful alerts and safe test | Partially matched | [Four custom MVP rules](../alerts/prometheus-rule.yaml) are live per [Step 16D](step-16D.md): service probe failed, missing service probe targets, missing standalone VM targets, and low standalone VM root disk. Built-in chart rules provide additional Kubernetes alerts. The original suggested 8–12 *named* alerts were not all implemented as custom BUET-PaaS rules. Rule lifecycle was tested with synthetic series, not by intentionally disrupting services. |
| Alertmanager notification/maintenance | UI-only MVP complete; automated delivery absent by choice | [Step 16E](step-16E.md) records `null` as the only receiver. Operators must inspect Grafana/Alertmanager; no email, Discord, or chat paging occurs. [Maintenance policy](monitoring/alerts/MAINTENANCE.md) documents silences. |
| Optional Headlamp | Not evidenced; optional, not an MVP blocker | No Headlamp installation result was found in the reviewed monitoring records. |

## Last recorded operating snapshot

At the Step 16B–16E checks, Prometheus had **36 targets UP, zero DOWN**; all **4 k3s nodes** were Ready, all **6 standalone VM exporters** and **5 Blackbox probes** were UP, and the dashboard showed those values. Step 16D recorded **10 monitoring Pods Running with zero restarts**. Step 16E recorded **five visible Alertmanager alerts**: Watchdog and four alerts for an existing crashing student workload in namespace `2105062`. Those alerts are not proof of a monitoring-stack failure, but the affected workload needs its owner's investigation. These are point-in-time observations only.

## Important gaps and deviations from the plan

1. **Persistence is pending.** [Base values](../prometheus/values.yaml) set Prometheus retention to `2d` with empty `storageSpec`, Grafana persistence disabled, and Alertmanager ephemeral storage. The revised [repo plan](monitoring/BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md) calls for a representative 48-hour load/storage measurement before sizing PVCs. No completed measurement-and-PVC step is evidenced. A Pod/storage recreation may lose history, non-provisioned Grafana state, or silences.
2. **The first dashboard is an overview, not every requested panel.** Its 16 actual titles are authoritative in the [dashboard JSON](../dashboards/buet-paas-overview.json). The original plan's per-VM network, registry-specific storage, and several job/replica breakdowns should be treated as follow-up dashboard work, not claimed complete.
3. **Alert coverage is focused, not the entire candidate list.** Built-in Kubernetes rules exist, but the repository adds only four custom rules; do not claim a dedicated custom alert for every originally listed service, Pod, job, or disk case. The dashboard's firing-alert count can include workload alerts outside the custom set.
4. **No unattended notifications.** The team's approved Step 16E decision is manual UI review. The `null` receiver means an alert can fire without a message being sent.
5. **No BUET-PaaS admin-panel integration yet.** The existing application `/dashboard` is student-facing, and the reviewed backend lacks server-enforced admin RBAC. [Admin monitoring integration proposal](monitoring/ADMIN-MONITORING-INTEGRATION-PLAN.md) is a proposal only. Cluster-wide links should not be added to shared student navigation without admin authorization.
6. **Project-scoped monitoring and centralized logs are later phases.** The revised plan places project API/UI after persistence planning and Loki/Alloy after storage/privacy review. Neither is evidenced as deployed.
7. **Grafana automatic dashboard reload needs correction.** [Step 16B](step-16B.md) records a successful manual Host-header reload after the sidecar's localhost reload encountered `enforce_domain` redirection. The dashboard is live, but later ConfigMap changes may not appear automatically until that configuration is fixed.

## Plan-version note and next boundary

The supplied top-level plan preserves the original 3-day teaching sequence. The [repository's revised plan](monitoring/BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md) adds the VPN-only ingress and a permission-gated continuation; it should be consulted for the *actual* deployment order. Some preparatory README text (notably [ingress/README.md](../ingress/README.md)) still says “not applied,” while later [Step 16E](step-16E.md), browser screenshots, and the UI runbook record live ingress. Treat dated implementation notes as later state; refresh stale preparatory docs before using them as an operations checklist.

**Recommended next gate:** Run a fresh read-only health and representative storage-growth check before persistence changes; then separately approve the admin-identity/access-control design before attaching cluster-wide monitoring links to BUET-PaaS. Do not infer fresh health from this document alone.

For the newly requested user-facing per-project CPU/RAM feature and admin links, see the separate [admin and project metrics plan](monitoring/ADMIN-AND-PROJECT-METRICS-PLAN.md). Its first gate is read-only runtime/metric identity verification, because the reviewed application contains both Docker and Kubernetes deployment paths.

The later [final revised implementation plan](FINAL-REVISED-MONITORING-PLAN.md) supersedes the one-day time-boxed proposal and adds the full phased scope and effort estimate.
