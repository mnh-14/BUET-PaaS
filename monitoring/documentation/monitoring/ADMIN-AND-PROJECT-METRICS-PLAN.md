# Admin and project resource monitoring — implementation plan

**Status:** proposal only, 2026-09-25. No application or cluster changes are authorized by this document. Read alongside [current overview](../CURRENT-OVERVIEW.md) and the [revised monitoring plan](BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md). Each numbered gate needs its own review/approval.

This plan uses **M0–M5** labels deliberately: the earlier admin-page proposal called its first gate “17A,” but Step 17 in the revised monitoring plan is reserved for storage measurement/persistence. The M labels avoid implying that admin integration replaces that persistence work.

## Goal and scope

- **Operators:** an admin-only Monitoring page with two first-class links: **Dashboard** (existing BUET-PaaS Grafana overview) and **Active alerts** (existing Alertmanager UI). Prometheus Targets may be a secondary troubleshooting link. Keep the existing VPN, internal CA, and separate monitoring-tool authentication. Step 16E remains UI-only: an assigned admin must review alerts routinely; no automatic notification is implied.
- **Project owners:** on the existing project-detail page, show **current running application deployment** CPU and RAM usage, optionally short 1-hour trends, replica count, and data freshness. Resource *usage* (observed) must be visually distinct from CPU/memory *request/limit* (configured). No cluster-wide Grafana/Prometheus link or credential for ordinary users.
- Exclude build Jobs, other tenants, platform Pods, host totals, billing, per-container logs, and arbitrary PromQL from the first user-facing endpoint.

## Architecture facts that must be reconciled first

The current frontend project page is `frontend/app/projects/[id]/page.tsx`; the corresponding `GET /api/v1/projects/{project_id}` already checks project ownership. But `backend/main.py` currently creates a `docker run --name <project_id>` container on a VM, while `deployer/k3s_conf.py` creates a Kubernetes Deployment named `<app_name>-deployment` with Pod label `app=<app_name>`. The Kubernetes code does **not** show a stable `project_id` or `deployment_id` Pod label, and the reviewed repository does not prove that the live student UI uses that deployer path. The existing six VM `node_exporter` targets expose *host* metrics, not per-Docker-container usage. The Kubernetes stack can provide container metrics, but their exact available series/labels for student Pods have not yet been checked. Consequently **per-deployment CPU/RAM is feasible, not yet verified end-to-end**.

The `deployment_id` in the application database denotes a deployment attempt/history record; a running workload may span several Pod replicas and redeploys. For MVP, define the displayed metric as **current live workload belonging to a project**, not historical per-attempt resource accounting. Avoid promising old release-specific usage until immutable workload identity and retention are designed.

## Permission-gated sequence

### M0 — read-only identity/metric preflight (first recommended approval)

1. Trace a real dashboard project through frontend request, backend database record, deployment orchestrator, and live runtime. Determine whether the current user workload is Docker on `backend-vm`, Kubernetes in a user namespace, or both. Record the authoritative mapping: authenticated `user_id` → owned `project_id` → namespace/workload or Docker container ID. Do not infer ownership from user-supplied namespace, name, or URL.
2. For one consented test project, inspect runtime labels/IDs and Prometheus metric *names and label sets* without exposing other tenants' values. Check whether `container_cpu_usage_seconds_total` and `container_memory_working_set_bytes` (or a validated equivalent) are present, fresh, and tied to exactly that workload. Confirm kube-state-metrics Pod/owner label availability if Kubernetes; check whether cAdvisor or an equivalent **private** container exporter exists if Docker. `node_exporter` alone is insufficient for this feature.
3. Record scrape interval, data age, restart/Pod churn behavior, replicas, rate-window stability, Prometheus reachability from the backend, and query cost. Validate a two-project isolation case before designing queries. **Stop if workload identity cannot be proven.**

Deliverable: a short evidence sheet with one chosen runtime path, exact metric series/labels, an ownership mapping, and a go/no-go decision. No exporter installation or scrape change in M0.

### M1 — make workload identity reliable (only if M0 finds a gap)

- **Kubernetes path:** persist authoritative `project_id`, namespace, Deployment name, and current workload identity in backend data. Add a stable, Kubernetes-safe project identifier label to generated Deployment and Pods; use a separate rollout/revision identifier only when historical release accounting is explicitly needed. Ensure kube-state-metrics exports only the needed label via a targeted allowlist, or use verified Kubernetes owner relationships. Do not rely on namespace alone or `app` alone: one user may own several apps, labels may collide, and builder Pods may share namespaces.
- **Docker path:** persist the actual running container ID/project mapping. Install a private, least-privilege container-metric source (for example cAdvisor after security review) and scrape it from Prometheus; its target and metric labels must uniquely map to the owned container. Do not expose Docker socket, exporter port, or raw metrics to students/the Internet. Docker container recreation must update the mapping.
- If the active deployment system is being migrated, decide which runtime is supported for the first release; do not silently combine Docker and Kubernetes totals.

M1 needs its own rollout, security review, regression checks, and rollback. A backend API must not launch before identity is validated.

### M2 — owner-authorized resource API

Proposed contract: `GET /api/v1/projects/{project_id}/metrics?window=1h` (or a shorter fixed-window `/resources` endpoint for MVP). Follow the existing signed-session `require_user` dependency, look up `project_id` with `user_id` from that session, and return 404 for unowned/nonexistent projects. Resolve workload identity from server-owned data. Query **only fixed, reviewed Prometheus expressions**; never accept arbitrary PromQL, namespace, Pod selector, or Prometheus URL from the client. Monitoring credentials and internal endpoint stay server-side; use network policy/firewall controls, narrow service identity, request timeouts, a small TTL cache, and bounded query range/step/series count.

Recommended first response fields: `status` (`ok`, `no_running_workload`, `no_data`, `stale`, `monitoring_unavailable`), `cpu_millicores`, `memory_bytes`, `sampled_at`, `window`, `replicas_observed`; optionally `cpu_request_millicores`, `cpu_limit_millicores`, `memory_request_bytes`, `memory_limit_bytes` **only when verified from the owned workload**. Current CPU is a five-minute rate of container CPU seconds, summed across current app replicas; memory is current working-set bytes summed across the same replicas. Exclude empty/POD infrastructure containers, init/build containers, and old rollout Pods as appropriate. If a query is empty or old, return null/status—not zero. Present units and timestamps clearly. Add 1-hour charts only after the instant values are accurate.

Test: unauthenticated 401; owner 200; other user 404 without existence leakage; request-tampering cannot change workload; missing/stopped/redeploying app has explicit status; Prometheus timeout does not break project details; multi-replica sums are correct; Pod/container restart does not double count; no secrets or raw PromQL appear in browser responses/logs. Add query-cost and request-rate tests.

### M3 — project dashboard UI

Add a **Resource usage** section to the existing project detail page. Show CPU (mCPU or cores), RAM (MiB/GiB), sample freshness, replica count, and a clear “metrics unavailable/not running” state. If request/limit values are available, show them separately from observed use; never call a request or limit “used.” Refresh conservatively (for example 30–60 seconds while visible) and avoid polling every project card on the main dashboard. Keep deployment history separate: first release shows the *current project workload*, not CPU/RAM for each past `deployment_id`. Test responsive layout and failed API states.

### M4 — admin Monitoring page

The reviewed app has a student dashboard but no server-enforced admin role. First establish admin identity and `require_admin` with non-admin default, controlled operator assignment, and 401/403 tests, as detailed in [admin integration plan](ADMIN-MONITORING-INTEGRATION-PLAN.md). Then add `/admin/monitoring` and admin-only navigation with the existing [Grafana overview](https://grafana.monitoring.192.168.64.121.sslip.io/d/buet-paas-overview/buet-paas-monitoring-overview) and [Alertmanager active alerts](https://alerts.monitoring.192.168.64.121.sslip.io/#/alerts) links; optionally include Prometheus Targets as troubleshooting. Open in new tabs. Link visibility is convenience, **not** authorization for the external tools; retain VPN, internal TLS trust, and each tool's own login. Do not embed admin credentials or expose this page to students.

### M5 — acceptance and operations

Verify an admin and a normal project owner in separate browser sessions; verify a second owner's data is inaccessible by API even if IDs are guessed. Confirm Grafana/Alertmanager still work over VPN, all existing probes/targets stay healthy, and no application deployment is disturbed. Document the operator alert-review rota because the receiver remains `null`. Record rollback for each application/metric change. Keep the persistence decision separate: the current two-day ephemeral Prometheus retention limits historical charts and may erase history on recreation.

## Suggested order and stop/go criteria

`M0 read-only evidence → choose Kubernetes or Docker path → M1 only if necessary → M2 owner API → M3 user UI`; in parallel *after admin identity is settled*, `M4 admin page → M5 access/operations checks`. Do not conflate the admin's cluster overview with a student's own workload metrics. The next approval should be **M0 only**. A concrete M1/M2 query and endpoint implementation should be approved after M0 resolves the runtime and labels; guessed selectors could leak another student's metrics or report host usage as deployment usage.
