# Admin monitoring integration plan (proposal; not applied)

## Current boundary

The three-day operator monitoring MVP is live: the Grafana overview, Prometheus targets, and Alertmanager alerts are available through VPN-only authenticated HTTPS. The application repository currently has a student-facing `/dashboard`, not a protected admin panel: registration creates users without an admin role; `require_user` validates a signed session but does not authorize administrators; the frontend `User` type has no role. The projects API returns the signed-in user's projects. Do not place cluster-wide links or credentials in the shared student dashboard or navbar.

## Recommended sequence, with a separate approval for each step

1. **17A — establish admin identity and authorization.** Confirm which existing account(s) are operators. Add a server-owned admin role/allowlist and `require_admin` authorization; default all current and newly registered users to non-admin. Provision admins through a controlled operator action, never through public registration or a client-provided role. Test unauthenticated = 401 and student = 403. If another admin identity service exists outside this repository, integrate with it instead of inventing a second source of truth.
2. **17B — attach a small admin Monitoring page.** Add an admin-only navigation entry and `/admin/monitoring` page. Link to the existing Grafana BUET-PaaS overview, Alertmanager Alerts, and Prometheus Targets. Open links in separate tabs; explain OpenConnect VPN, trusted internal CA, and the monitoring tools' separate login. Do not iframe the tools, expose Basic Auth passwords, or link from student project pages. Add a backend admin-only check used by the page; client-side hiding alone is not authorization.
3. **17C — verify the full access path.** With an admin account on VPN, confirm all three links and the 16-panel overview load; with a student account, confirm no navigation entry and 403 on admin API routes; with no session, confirm 401. Check browser trust and that the monitoring URLs remain unreachable off VPN. Confirm deployment/project functionality is unchanged. Record results and rollback instructions.
4. **17D — optional admin summary cards.** Only if a one-page operational summary is needed, add a backend `require_admin` read-only endpoint with fixed, allowlisted Prometheus queries for targets UP/DOWN, nodes Ready, standalone VMs, service probes, and firing alerts. Fetch from the backend, not the browser; keep any monitoring API credential server-side and set timeouts/caching. Link to Grafana/Alertmanager for detail. This is not required to attach monitoring links.
5. **Later — student project monitoring.** After defining project-to-namespace ownership and enforcing it on every backend query, expose limited project-scoped metrics in each user's project view. Never give ordinary users the cluster-wide Grafana, Prometheus, or Alertmanager interface as a substitute for project authorization.

## First implementation gate

Approve only Step 17A after identifying the authoritative admin account/identity source. No application code, role assignment, Kubernetes resource, or monitoring ingress should change merely by approving this plan. The UI-only Alertmanager policy remains in force; this plan does not add email/chat notifications.
