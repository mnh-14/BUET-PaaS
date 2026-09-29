# Final revised one-day monitoring integration plan

> Superseded for future planning by [the full revised plan](../FINAL-REVISED-MONITORING-PLAN.md). Retained as the earlier time-boxed proposal; it was not executed.

**Status:** proposed, not executed. **Target:** one focused engineering day (approximately 8 working hours), subject to access and approval gates. This is a *platform integration* sprint after the completed operator-facing three-day monitoring MVP, not a reinstallation of Prometheus/Grafana/Alertmanager. See the [cross-checked current state](../CURRENT-OVERVIEW.md) and the [detailed integration design](ADMIN-AND-PROJECT-METRICS-PLAN.md).

## One-day definition of done

1. A verified admin can open an **admin-only Monitoring page** containing two working links: **Dashboard** and **Active alerts**. The existing monitoring login, OpenConnect VPN, and trusted CA remain required. A normal user cannot obtain the page's monitoring links or an admin API response.
2. An owner can open their existing project-detail page and see the **current running workload's CPU and memory usage**, with units, measurement time, and a clear unavailable/stopped state. The owner cannot retrieve another project's metrics. This is current usage, not historical usage per deployment attempt, a billing measure, or a VM-wide total.
3. Existing student deployment behavior and the 36 monitoring targets/5 probes are not degraded. Exact live counts must be rechecked at the end rather than assumed from the previous report.

**Conditional rule:** item 2 is deliverable in this sprint only if the read-only preflight proves an unambiguous live project→workload mapping and an available per-container metric source. If it does not, ship only the separately approved admin links and a documented metric blocker; never substitute host CPU/RAM or cross-tenant namespace totals. “One day” is a scope target, not a reason to bypass this rule.

## Existing facts and decisions

- The original 20-step monitoring list is mostly complete; Step 17's 8–12 proposed custom alerts is only partially matched (four new custom rules plus built-ins), and optional Headlamp was not installed. Neither is on this day's critical path.
- The current frontend project-detail page and backend project APIs already use signed sessions and owner-scoped project lookup. There is **no server-enforced admin role** in the reviewed app.
- Repository code contains both `backend/main.py`'s Docker `run --name <project_id>` path and a separate Kubernetes deployer that names a Deployment `<app_name>-deployment` with Pod label `app=<app_name>`. The live app path is **not established** by repository reading alone. Existing VM `node_exporter` cannot provide per-deployment usage.
- Step 16E chose manual alert review and Alertmanager's receiver is `null`. This sprint will not add automatic paging.
- Use new integration gates **D0–D6**, not “Step 17A”: Step 17 in the revised monitoring plan denotes persistence work.

## Timed sequence and approval boundaries

| Gate | Target time | Work and pass condition |
|---|---:|---|
| **D0 — read-only preflight** | 45–60 min | Identify one existing, verified operator account for admin status; trace one consented project from DB to its actual running Docker container **or** Kubernetes Deployment/Pods. Check exact CPU/memory metric source, identity labels, age, replicas, and backend reachability. Record no-go conditions. No mutation. |
| **D1 — admin authorization** | 60–75 min | Add server-side `require_admin` based on a controlled, pre-existing operator identity/role. New registrations remain non-admin; neither request body nor frontend can self-assign admin. Expose a small admin-only link/config API. Tests: no session 401; normal user 403; admin 200. Do not treat hiding a nav item as authorization. |
| **D2 — admin Monitoring page** | 45–60 min | Add `/admin/monitoring` and a conditional admin navigation entry. Fetch links only after the D1 check. Link to existing Grafana overview and Alertmanager Alerts; optionally show Prometheus Targets as a troubleshooting link. Open in a new tab; show VPN, trusted CA, separate-login, and UI-only alert-review notes. No iframe, monitoring secret, or PromQL in frontend. |
| **D3 — owner-scoped resource API** | 90–120 min | Only after D0 passes, add `GET /api/v1/projects/{project_id}/resources`. First resolve the project with `user_id` from the signed session; resolve the runtime identity from server-owned records. Docker path: read the **specific owned running container's** stats using the backend's existing local Docker access, with bounded calls and no shell interpolation. Kubernetes path: use verified Prometheus container CPU/memory series scoped to the exact owned workload/Pods; fixed backend queries only. Do not add an exporter or rollout just to meet the clock. Return CPU millicores, RAM bytes, timestamp and explicit `ok/stopped/no_data/stale/unavailable` state; null rather than fabricated zero. Cache briefly and bound timeouts/query costs. |
| **D4 — user project UI** | 45–60 min | Add a compact **Resource usage** card on the existing project-detail page, not the global dashboard. Show CPU, RAM, freshness, and optional replica count. Distinguish observed usage from configured request/limit. Poll conservatively only while the page is visible. Handle failed/stopped/new deployments without breaking the project page. Defer charts/history. |
| **D5 — tests and staged verification** | 90–120 min | Automated owner-vs-other-user API tests, admin-vs-student tests, absent/stale metric tests, multiple-replica and redeploy checks as applicable. Validate API response is free of credentials/raw queries. Stage or canary-check actual admin and student browser sessions on VPN. Recheck app deployment flow, monitoring targets/probes and alerts. Keep rollback ready. |
| **D6 — handoff** | 20–30 min | Document URLs, admin account assignment procedure, API contract, operator alert-review responsibility, limitations, test evidence, and rollback. Mark only tested outcomes complete. |

Total target: roughly **7–9 hours**. D0 can shorten or block D3–D4. Approval is per gate; planning approval does not authorize account-role changes, application deployment, exporter installation, Prometheus changes, or cluster writes.

## Resource API contract (MVP)

Example shape, not an assertion that live measurements are already available:

```json
{
  "project_id": "proj-example",
  "scope": "current_running_workload",
  "status": "ok",
  "cpu_millicores": 85,
  "memory_bytes": 134217728,
  "sampled_at": "2026-09-25T10:00:00Z",
  "replicas_observed": 1
}
```

CPU is a recent usage rate; memory is current used/working-set memory. Explain the measurement window for the chosen source and never present a configured CPU/memory limit as actual usage. For non-running workloads return null numeric fields and a meaningful status. The backend takes `project_id` only, not a namespace, container ID, metric query, or arbitrary monitoring URL from the browser. A guessed project ID belonging to someone else returns 404 without revealing its existence.

## Explicitly out of scope for this one day

- 48-hour storage sizing, Prometheus/Grafana/Alertmanager PVCs, or retention changes.
- Repairing Grafana sidecar automatic reload.
- Adding the remaining candidate alerts or any email/chat receiver.
- Headlamp, Loki/Alloy, logs, traces, historical per-deployment resource accounting, build-job usage, billing/quotas, or full admin health cards.
- Public monitoring links or removal of VPN/CA/tool authentication.

## Risk controls and rollback

- **Tenant isolation:** owner authorization precedes any metric lookup; test two distinct users/projects. Kubernetes namespace alone and Docker host totals are not sufficient identity.
- **Admin identity:** D0 must verify that the proposed admin account already belongs to the operator. An unclaimed student `user_id` in an allowlist would be unsafe because public registration accepts user IDs. Role assignment must be controlled out-of-band and never writable by users.
- **Reliability:** monitoring timeouts return an unavailable state rather than taking down project details. Keep the current monitoring stack untouched unless a later approval explicitly scopes a change.
- **Rollback:** deploy API/UI changes in separable units. If authorization or data matching fails, disable/remove the new route/cards/links and verify ordinary deployment paths; do not roll back the monitoring stack. If D0 fails, stop before D3 and report the exact missing identity/metric evidence.

## Immediate next approval

**Approve D0 — read-only live runtime, workload identity, per-container metric, and operator-account preflight.** Its result determines whether the user CPU/RAM card can safely ship within the same day and which source it will use. No later gate is auto-approved by D0.
