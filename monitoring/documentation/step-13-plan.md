# Step 13 and Revised Continuation Plan after Step 12E

## Planning status

- Date: 2026-09-24 (Asia/Dhaka)
- Scope: documentation only
- Live infrastructure changes: none
- Last completed implementation step: Step 12E
- Step 13A: **complete**
- Step 14A1/14B1/14C1/14D1: **complete locally**
- Step 14A2: **complete** - all five installed exporters reachable from control plane
- Step 14E1: **complete locally** - SonarQube identity verified and exporter installed
- Step 14E2: **complete** - SonarQube restricted control-plane path verified
- Step 14A3: **complete** - five new scrape targets prepared and offline-verified
- Step 14A4: **complete** - six standalone targets live and UP
- Step 15A: **complete** - five endpoints and Harbor TLS trust design confirmed
- Step 15B: **complete** - secure pinned Blackbox configuration offline-verified
- Step 15C: **complete** - exporter live; frontend canary UP
- Step 15D1: **complete** - cumulative frontend plus backend overlay offline-verified
- Step 15D2: **complete** - frontend and backend probes live and UP
- Step 15D3: **complete** - cumulative frontend, backend, deployer overlay offline-verified
- Step 15D4: **complete** - deployer probe live and UP; frontend/backend unchanged
- Step 15D5: **complete** - cumulative strict-TLS Harbor overlay offline-verified
- Step 15D6: **complete** - strict-TLS Harbor probe live and UP; prior probes unchanged
- Step 15D7: **complete** - SonarQube healthy; final five-target overlay offline-verified
- Step 15D8: **complete** - all five Blackbox probes live and UP
- Step 16A: **complete** - overview dashboard prepared and offline-verified
- Step 16B: **complete** - overview dashboard live, 16 queries verified
- Step 16C: **complete** - four focused MVP alert rules offline-verified
- Step 16D: **complete** - four rules live, healthy, inactive
- Step 16E: **complete** - team chose UI-only alert review
- Three-day monitoring MVP: **complete** as operator-facing monitoring

## Current 3-day MVP position

### Day 1 - complete

```text
monitoring namespace                         complete
kube-prometheus-stack 91.4.1                Helm revision 6, deployed
Prometheus / Grafana / Alertmanager          healthy
kube-state-metrics                           healthy
node-exporter on four k3s nodes              4/4 healthy
Grafana provisioned dashboards               23
Prometheus active targets                    36/36 UP
authenticated VPN HTTPS browser access       complete
raw monitoring ports on ingress address      closed
```

### Day 2 - complete

```text
frontend-vm node_exporter                    installed and UP
database/registry/k3s-user/backend exporters installed; network reachable
SonarQube exporter                             installed and network reachable
standalone VM exporters                        6/6 live and UP
Blackbox endpoint/TLS preflight               complete
Blackbox secure configuration                 prepared and offline-verified
Blackbox live exporter                        revision 9 deployed
Blackbox frontend canary                      UP; HTTP 200
Blackbox backend probe                        UP; HTTP 200; Mongo-dependent health
Blackbox deployer probe                       UP; HTTP 200; status ok
Blackbox Harbor probe                         UP; HTTP 200; verified TLS; healthy
Blackbox SonarQube probe                      UP; HTTP 200; status UP
Blackbox probes                               5/5 live and UP
```

### Day 3 - complete

```text
BUET-PaaS overview dashboard as code       prepared and offline-verified
BUET-PaaS overview dashboard live          complete; 16 panels provisioned
small useful alert-rule set                  four rules live and healthy
maintenance policy and UI-only notification decision complete
```

Persistence, project-scoped user monitoring, and Loki/Alloy remain hardening
or post-MVP work. They will not be mixed into Day 2 or Day 3 changes.

## Step 13A - Read-only stability, alerts, targets, and capacity audit

Alertmanager currently displays five active alerts. Their exact names,
severity, duration, and cause have not been reviewed. Prometheus also has only
partial standalone VM coverage, so current storage growth is not yet the final
steady-state ingestion load.

After approval, Step 13A will only read state:

1. record nodes, Pods, Deployments, Jobs, PVCs, StorageClasses, events, Helm
   revision, Prometheus targets, and application health;
2. inspect the five firing alerts through Prometheus and Alertmanager APIs;
3. classify expected versus actionable alerts without silencing or editing;
4. inventory active standalone VMs and existing TCP 9100 listeners;
5. inventory real service URLs, ports, and health paths for Blackbox probes;
6. measure current Prometheus active series and available storage growth;
7. decide whether enough representative data exists for persistence sizing.

Output:

```text
current-health matrix
alert-cause matrix
VM exporter readiness matrix
service endpoint/probe candidate matrix
storage and retention evidence
go/no-go recommendation for each later step
```

Mutation: none.

## Step 14 - Complete Day 2 VM monitoring, one VM at a time

Completed local-install order:

```text
14A1 database-vm                 complete locally
14B1 registry-vm-2               complete locally
14C1 k3s-user                    complete locally
14D1 backend-vm                  complete locally
14E1-E2 sonarqube                local install and restricted network complete
```

The user approved Step 14A1 and explicitly granted sequential automatic
approval for the remaining eligible VM-local installs. Those local operations
followed the proven frontend-vm sequence. Network and Prometheus changes remain
separate:

1. capture VM and application before-state;
2. verify architecture, OS, listener, disk, and firewall;
3. install the pinned official node_exporter with a restricted systemd user;
4. verify the private-IP `:9100/metrics` endpoint locally;
5. manually attach the existing restricted `monitoring-exporter` group while
   retaining each VM's existing groups; **complete**
6. verify control-plane reachability; **complete: HTTP 200 for all five exporters**
7. prepare all four additions to the declarative scrape overlay;
8. run an atomic Helm upgrade and verify every new target UP;
9. verify each VM application and all previous monitoring targets.

Exporter port 9100 must never be opened to `0.0.0.0/0`.

## Step 15 - Add Day 2 service reachability monitoring

```text
15A read-only endpoint and health-path confirmation
15B prepare and offline-render pinned Blackbox Exporter configuration
15C install Blackbox Exporter as ClusterIP and add the first probe
15D add remaining confirmed probes one service at a time
```

Candidate services are frontend, backend, deployer, registry/Harbor, and
SonarQube. Only endpoints proven by direct requests in Step 15A will be added.
Every probe must expose `probe_success`; raw port 9115 remains private.

## Step 16 - Complete Day 3 dashboard and alerting

```text
16A prepare BUET-PaaS Monitoring Overview dashboard as provisioned code - complete
16B verify dashboard queries against real labels and current data - complete
16C prepare a small useful PrometheusRule set as code - complete
16D apply rules; verify live inactive state and offline lifecycle - complete
16E notification decision - complete; UI-only review selected, no receiver
```

The dashboard covers platform status, cluster resources, standalone VM
resources, Kubernetes workloads, and confirmed service probes. Initial alerts
are limited to actionable node/VM down, probe down, disk low, Pod crash loop,
deployment unavailable, failed build Job, and target-down conditions.
Maintenance labels or time-limited silences handle intentionally stopped
services.

Dashboard and alert files are provisioned from Git. Notification credentials,
if selected, remain in Kubernetes Secrets and never enter Git or Markdown.

## Step 17 - Persistence after representative 48-hour measurement

Persistence sizing occurs after the intended exporters and probes have run long
enough to represent steady-state ingestion:

```text
17A measure at least 48 hours of TSDB growth, active series, and disk pressure
17B prepare PVC sizes, retention, backup, and rollback locally
17C apply Prometheus persistence first and test controlled recovery
17D decide Grafana PVC versus fully provisioned state
17E decide whether Alertmanager silence persistence is required
```

Each component is a separate approval. No PVC or retention increase will use a
partial-load measurement.

## Step 18 - Project-scoped monitoring for normal BUET-PaaS users

Raw Grafana, Prometheus, and Alertmanager remain admin/operator interfaces.
Normal users should receive only information for projects they own:

1. map BUET-PaaS identity to the user's project, namespace, and workloads;
2. define allowlisted PromQL queries and bounded time ranges;
3. implement a backend monitoring API that injects authorized labels;
4. return CPU, memory, replicas, restarts, deployment, and availability data;
5. add monitoring panels to the existing project detail page;
6. test cross-project denial before enabling the feature.

Prometheus Basic Auth and Grafana admin credentials must never enter the
frontend.

## Step 19 - Loki and Grafana Alloy pilot

Pilot one namespace only after storage, privacy, redaction, retention, and log
access are approved. Measure bytes/day and query performance before expanding.
This remains outside the first 3-day MVP.

## Deferred item

Headlamp remains optional. It adds another administrative interface and is not
required for the monitoring MVP.

## Step 14 local-install result and immediate next boundary

Database, registry, k3s-user, and backend now run the pinned exporter with a
restricted user and private-IP-only listener. The user attached the existing
restricted `monitoring-exporter` group while retaining prior groups. The
control node receives HTTP 200 and valid build metrics from frontend plus all
four new exporters. The user verified the previously changed SonarQube SSH key
against the recorded fingerprint, and its exporter is now locally healthy.
The SonarQube restricted security-group attachment is also complete and the
control plane receives HTTP 200 from its exporter. Helm revision 6 now scrapes
all six standalone exporters; Prometheus reports 31/31 targets UP.

```text
Three-day MVP complete; follow-up work proceeds only by separate approval
```

Step 15D2 ultimately deployed revision 6 with uniquely labeled frontend and
backend targets. Both are UP with `probe_success=1`, HTTP 200, and empty target
errors; Prometheus reports 33 UP and zero DOWN. Two verifier-driven attempts
rolled back safely before the missing pre-scrape target-label distinction was
corrected and offline-revalidated. Deployer, Harbor, and SonarQube remain
absent. Step 15D3 prepared and offline-verified the cumulative three-target
overlay without changing live state. Step 15D4 then deployed Blackbox revision
7 atomically. Frontend, backend, and deployer are all UP with successful HTTP
200 semantic probes; Prometheus reports 34 UP and zero DOWN. The rollback guard
was not triggered. Step 15D5 prepared and offline-verified the cumulative
strict-TLS Harbor overlay without changing live state; Harbor and SonarQube
remain absent from Prometheus. Step 15D6 then atomically deployed revision 8:
Harbor and all three prior probes are UP, Harbor reports SSL 1 with a valid
2028 certificate expiry, and Prometheus reports 35 UP with zero DOWN. Rollback
was not triggered. Step 15D7 revalidated SonarQube HTTP 200/status UP and
offline-verified the exact final five-target overlay; live revision 8 and four
probes remained unchanged. Step 15D8 then atomically deployed revision 9. All
five probes are UP with successful semantic checks; Prometheus reports 36 UP
and zero DOWN, and rollback was not triggered. Day 2 is complete. Step 16A then
prepared the 16-panel overview dashboard, deterministic ConfigMap, and offline
validator. JSON, Kustomize, secret-scan, and 16-expression promtool checks
passed without changing the cluster. Step 16B was the next permission boundary.
Step 16B then applied the dashboard ConfigMap. Grafana reports the dashboard
as provisioned with 16 panels, and all 16 expressions executed against live
Prometheus. The first guarded attempt rolled back because Grafana's domain
enforcement redirected the sidecar reload API; the corrected hostname-aware
reload succeeded. The dashboard is live, with 36 targets UP and zero DOWN.
The sidecar reload configuration remains an operational follow-up for future
dashboard updates. Step 16C was the next permission boundary.
Step 16C prepared four focused rules for service probe failure, missing probe
or VM targets, and low standalone VM root disk. Built-in rules already cover
scrape failure and Kubernetes node, Pod, Deployment, and Job incidents. The
new rule set passed Kustomize, structural, and promtool checks; all four
expressions executed successfully with zero current matches. No rule was
applied. Step 16D was the next permission boundary.
Step 16D server-dry-ran and applied only the reviewed PrometheusRule. All four
rules loaded in Prometheus, evaluated healthy and inactive, and generated no
new alerts. Synthetic promtool tests verified pending, firing, and resolution
without disrupting real workloads. Target health remained 36 UP, zero DOWN;
Helm revisions were unchanged. Step 16E is the team notification decision.
Step 16E recorded the team's UI-only decision. Alertmanager's effective route
and only configured receiver are `null`; the UI shows current active alerts.
The operator review procedure is in `monitoring/alerts/UI-ONLY-RUNBOOK.md`.
The three-day operator-facing monitoring MVP is complete. Existing student
workload alerts and the post-MVP persistence, user-scoped monitoring, logging,
and Grafana sidecar reload follow-ups remain separate.
