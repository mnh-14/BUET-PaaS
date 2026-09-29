# Step 16E - UI-only alert review decision

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Team decision: use Grafana and Alertmanager UI for MVP alert review
- Result: **complete**
- Infrastructure mutation: **none**

The team explicitly chose UI review instead of an email/chat notification
receiver for the three-day MVP. No receiver Secret or Alertmanager route was
created or changed.

Read-only verification of Alertmanager v0.34.0 found the effective route
receiver `null` and only one configured receiver named `null`. The
Alertmanager API returned five active visible alerts at the check: `Watchdog`
and four alerts concerning the existing crash looping student Pod/Deployment
in namespace `2105062`. `InfoInhibitor` may be present in Prometheus but
inhibited in Alertmanager's default view. Prometheus had 36 targets UP, and
the four BUET-PaaS MVP alert rules remained live.

The team review procedure is documented in
`monitoring/alerts/UI-ONLY-RUNBOOK.md`. It covers VPN browser links, routine
target and alert checks, triage, planned-maintenance silences, and the limit
of manual review. No automated page or email should be expected.

## Three-day MVP state

- Day 1: core Prometheus, Grafana, Alertmanager, Kubernetes monitoring, and
  authenticated VPN browser access complete.
- Day 2: six standalone VM exporters and five semantic Blackbox probes live;
  36 total targets UP and zero DOWN at this check.
- Day 3: 16-panel provisioned overview dashboard and four focused custom
  alert rules live; UI-only alert review chosen and documented.

The three-day monitoring MVP is complete as an operator-facing demonstration.
The four existing alerts for the student workload remain actionable. Separate
follow-up work includes a 48-hour representative storage measurement before
persistence, Grafana sidecar automatic reload correction, project-scoped
monitoring for ordinary users, and a later Loki/Alloy logging pilot. None of
those follow-ups was performed in Step 16E.
