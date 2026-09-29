# BUET-PaaS monitoring — final revised implementation plan

**Prepared:** 2026-09-25. **Status:** proposal; no live change in this planning step. This supersedes the earlier [one-day integration proposal](monitoring/FINAL-ONE-DAY-INTEGRATION-PLAN.md), not the completed operator-facing monitoring MVP. The [cross-checked overview](CURRENT-OVERVIEW.md) is the baseline. Each phase below is a separate approval and verification boundary.

## What is already done, and what the new work must deliver

The existing operator stack has Prometheus, Grafana, Alertmanager, four monitored k3s nodes, six standalone VM exporters, five Blackbox service probes, a 16-panel overview, and four custom MVP rules. The last documented check showed 36/36 targets UP. Those are **last recorded** values, not a fresh live check. Alerts are reviewed manually in the UI; the Alertmanager receiver is `null`. The original plan's optional Headlamp and full 8–12 custom alert wish list were not completed, and they are not prerequisites for the user card.

The next release should deliver two distinct experiences:

1. **Project owner:** on their existing project page, a small card such as `Running · CPU 0.05 cores · RAM 100 MiB · updated 25 s ago`. The numbers must belong to **that project's current running application workload**, not the whole VM, namespace, build Job, or another student. Also show `Stopped`, `Deploying`, `Metrics unavailable`, or `Stale` honestly. A compact replica/Pod count and configured CPU/memory limit are useful *if reliably known*, but limits must be labeled as limits, not usage. Start with current values; defer historical graphs and billing.
2. **Platform admin:** a protected Monitoring page with links to the existing [Grafana dashboard](https://grafana.monitoring.192.168.64.121.sslip.io/d/buet-paas-overview/buet-paas-monitoring-overview) and [Alertmanager active alerts](https://alerts.monitoring.192.168.64.121.sslip.io/#/alerts); Prometheus Targets may be a third troubleshooting link. Existing VPN, trusted CA, Grafana login, and Prometheus/Alertmanager authentication remain intact. No raw monitoring credentials reach the browser.

**GPU clarification:** “100gpu” could mean **100 MB/MiB RAM**. This plan treats it as RAM for the required card. If actual GPU utilization or GPU memory is intended, that is a separate optional phase: first prove the project is scheduled on a GPU-equipped node and that a per-workload GPU metric exists. The current evidence establishes neither. NVIDIA's [DCGM exporter](https://docs.nvidia.com/datacenter/dcgm/latest/reference/command-line-reference/dcgm-exporter.html) can expose GPU metrics, but installing it would not by itself prove safe per-project attribution.

## Why a preflight is mandatory

The checked repository has **two deployment paths**. `backend/main.py` runs Docker containers named after `project_id`; separate `deployer/k3s_conf.py` builds Kubernetes Deployments using `app` labels. The screenshots show Kubernetes student workloads, but the repository alone does not prove that the current web UI's specific project uses that path. Six VM `node_exporter` targets report host resources, not per-container CPU/RAM. Kubernetes kubelet can expose container metrics, while Docker provides per-container live stats; the actual source and labels must be verified on the deployed system. See the official [Kubernetes metrics endpoints](https://kubernetes.io/docs/concepts/cluster-administration/system-metrics/) and [Docker container stats](https://docs.docker.com/reference/cli/docker/container/stats/) descriptions.

An application database `deployment_id` is an attempt/history identifier. The first UI release should therefore mean **current running project workload**, aggregated across its current replicas. It must not claim past per-attempt resource usage after a redeploy unless immutable release identity and retention are designed later.

## Implementation phases and acceptance gates

### Phase 0 — read-only reality and identity audit

- Trace one consented live project: authenticated user → owned database `project_id` → runtime (Docker container ID or Kubernetes namespace, Deployment, Pods) → available per-container metric series. Repeat with a second owner's project to prove selectors cannot overlap. Check CPU, memory, sample age, stopped/redeploying behavior, and number of replicas.
- Confirm the authoritative admin identity. The reviewed app has signed sessions but **no enforced admin role**; public registration must never be able to claim an allowlisted admin identifier. Confirm existing operator account ownership before any role/allowlist assignment.
- Check backend-to-metrics connectivity and whether a Docker-only project can be measured locally. Record the exact monitoring data source and whether adding labels/exporters is required. Take a fresh read-only monitoring/app baseline (nodes, targets, probes, Pods, existing student app health).
- **Exit:** written mapping, exact source/labels, two-project isolation evidence, admin identity decision, and a chosen Docker/Kubernetes/both implementation branch. If mapping cannot be proved, stop user-metric work rather than showing host or namespace totals.

### Phase 1 — secure identity and metric source, only where missing

- For Kubernetes apps, persist a server-owned mapping to the current Deployment. Prefer a stable project label on Deployment **and Pod template**, with an explicit controlled rollout and test, or verify an equally reliable ownership join using existing Kubernetes metadata. Namespace or `app` label alone is insufficient if multiple apps can share it. Ensure required labels are actually available to Prometheus before writing queries. Keep build Jobs and previous rollout Pods out of current usage.
- For Docker apps, persist the current container ID. The backend already has Docker access; a bounded local stats call for the **verified owned container** may support current CPU/RAM without adding a Prometheus exporter. If history is later required, plan a private container-metrics exporter separately. Do not expose Docker socket or exporter to students.
- If both runtimes actively serve projects, use a small internal runtime adapter with the same response schema; do not silently mix their CPU/memory semantics. Record how cache and container/Pod replacement invalidate identity.
- **Exit:** one project maps to exactly its own live workload across a redeploy; one user cannot select another workload; no new public port. Any workload-label rollout is independently approved, staged, and reversible.

### Phase 2 — owner-authorized resource API

- Add a backend endpoint such as `GET /api/v1/projects/{project_id}/resource-usage`. Authenticate with the existing signed session and look up the project by **both** `project_id` and current `user_id` before resolving runtime identity. Return 404 for another user's ID without revealing its existence. No client-supplied namespace, container ID, PromQL, or monitoring URL.
- For Kubernetes, use fixed, reviewed Prometheus expressions over validated container metrics: a recent CPU-seconds rate converted to cores/millicores, and a current container working-set memory value, summed over exactly the current application's containers/replicas. The backend queries Prometheus through a private path, with server-side credentials if required. The [Prometheus HTTP API](https://prometheus.io/docs/prometheus/3.9/querying/api/) supports this query pattern; exact expressions are finalized only after Phase 0 verifies labels. For Docker, normalize the verified live container stats into the same schema, documenting CPU/memory semantics. Do not pretend Docker CLI percentages are automatically equivalent to a Prometheus five-minute CPU rate.
- Return a typed state (`ok`, `deploying`, `stopped`, `no_data`, `stale`, `monitoring_unavailable`), `cpu_cores` or `cpu_millicores`, `memory_bytes`, `sampled_at`, `source`, and optional `replicas_observed`/verified limits. Unknown numeric values are `null`, never fabricated zero. Add a short backend cache (for example 30–60 seconds), per-request timeout, bounded series/query range, and safe errors. Never log credentials or expose raw query responses.
- **Exit:** owner 200; unauthenticated 401; other owner 404; multi-replica sum correct; redeploy/stopped/old-data cases correct; monitoring outage degrades only the card, not project operations. Unit and integration tests cover these cases.

### Phase 3 — small user-facing resource card

- Add the card to `frontend/app/projects/[id]/page.tsx`. Show project/deployment status already known by the app plus measured CPU/RAM and sample age. For example `CPU 0.05 cores` and `RAM 100 MiB`; label the unit and that this is **current usage**. If known, add `2 Pods` or `CPU limit 0.5 cores / RAM limit 512 MiB` in smaller text. Do not confuse `request`, `limit`, `quota`, and `usage`.
- Refresh only while visible and at a conservative interval; do not poll every dashboard project simultaneously. Show `—` and an explanatory state when there is no data. Avoid arbitrary queries or Grafana/Prometheus links in normal user pages.
- **Exit:** real owner sees correct metrics; stopped/new deployments display honest states; second user cannot see the card's underlying data by changing a URL; mobile layout and loading/error states work.

### Phase 4 — admin authorization and Monitoring page

- Add a server-controlled admin assignment mechanism and `require_admin`; all existing/new accounts default non-admin. Assignment must be out-of-band by an operator and bound to a verified existing identity, not editable through public registration or profile fields. Add 401/403/200 tests and an audit note for assignments.
- Add `/admin/monitoring` and an admin-only navigation entry. Return link configuration only after backend admin authorization. The page's primary actions are **Dashboard** and **Active alerts**; include an operator reminder that Step 16E requires manual alert review. Keep links in separate tabs and do not iframe tools or copy monitoring credentials into frontend code. The external tools retain their own access controls; hiding links alone is not security.
- **Exit:** admin sees/opens links on VPN; ordinary student cannot obtain admin link API data; unauthenticated visitor is denied; off-VPN and missing-CA behavior is documented rather than bypassed.

### Phase 5 — end-to-end pilot, safety, and handoff

- Pilot with at least two users/projects, one admin, a stopped or redeploying app, and (if applicable) a multi-replica Kubernetes app. Cross-check displayed CPU/RAM against the authoritative runtime or validated Prometheus query within the documented sampling window. Check target/probe health and existing deployment workflows before/after.
- Record response latency and query load; set an appropriate polling/cache limit. Verify role denial by direct API request, not only UI inspection. Keep rollback as separate API/UI and runtime-label units; a metrics feature failure must not require uninstalling the monitoring stack.
- Update user/admin runbooks, document what the metric does **not** represent, and assign who will inspect Alertmanager regularly. The `2105062` crashing workload alerts remain a separate application issue for its owner.
- **Exit:** evidence-based sign-off; no cross-tenant data exposure; no deployment regression; no claim of “live” target counts unless freshly checked.

## Realistic effort and calendar estimate

| Scope | Engineering effort | Calendar expectation / caveat |
|---|---:|---|
| Phases 0–5, **if the active runtime already exposes uniquely attributable container CPU/RAM** | **4–6 working days** | About one working week including backend/frontend tests and pilot. |
| If Kubernetes labels/ownership or a private Docker metric source must be added and rolled out | **6–9 working days total** | Rollout and security review add time; exact duration follows Phase 0. |
| Actual GPU metrics, **only if GPU workloads exist and per-project attribution is feasible** | **+2–4 working days** | Additional exporter, labels, access, and verification; hardware/provisioning delays are not included. |
| Historical charts, Prometheus PVCs/retention, sidecar reload fix, more custom alerts | **separate 3–6 working days** | Persistence sizing additionally needs the already-planned representative **48-hour measurement window**; do not squeeze it into the owner-card rollout. |
| Centralized logs (Loki/Alloy) | **separate later pilot** | Requires storage, privacy/redaction, retention, and tenant-access design; not included in the core estimate. |

These are planning ranges, not guarantees. External approvals, missing runtime identity, unavailable metrics, or failed pilots extend the schedule. The fastest safe path is to keep the user display minimal and reuse the existing operator tools, while preserving each approval gate.

## Recommended immediate sequence

Approve **Phase 0 only**: read-only runtime/metric/admin-identity preflight. Review its findings, choose the actual runtime branch, then approve Phases 1–5 one at a time. In parallel, operators can continue using the existing Grafana and Alertmanager URLs; no new admin UI is required to keep monitoring operational.
