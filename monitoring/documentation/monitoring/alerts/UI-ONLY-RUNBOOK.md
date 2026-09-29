# UI-only alert review for the three-day MVP

The team chose Grafana and Alertmanager UI review for the MVP. Alertmanager's
effective route currently uses the `null` receiver. No email or chat message
will be sent when an alert fires; a team operator must open the dashboards.

Use the VPN and the trusted monitoring CA, then open:

- [BUET-PaaS Monitoring Overview](https://grafana.monitoring.192.168.64.121.sslip.io/d/buet-paas-overview/buet-paas-monitoring-overview)
- [Alertmanager Alerts](https://alerts.monitoring.192.168.64.121.sslip.io/#/alerts)
- [Prometheus Targets](https://prometheus.monitoring.192.168.64.121.sslip.io/targets)

At the start and end of each operating shift or demonstration, check the
overview's targets UP/DOWN, nodes, VMs, service probes, firing alerts, and disk
panels. Open Alertmanager to read the alert name, affected namespace/service,
duration, and any inhibition/silence state. Open Prometheus Targets if a scrape
or probe is missing. Record who reviewed an actionable alert and what they did
in the team's incident notes. During active incidents, review more frequently.

`Watchdog` is intentionally firing. `InfoInhibitor` is a control alert used to
inhibit noisy informational alerts. Neither is evidence of a failed workload
by itself. Do not dismiss Pod, Deployment, VM, probe, or disk alerts without
checking the affected target. The pre-existing alerts for the crashing
`to-do-backend-deployment` Pod in namespace `2105062` require the owning
application team's investigation; monitoring has only detected them.

For planned downtime, use the exact-label, time-limited silence procedure in
`MAINTENANCE.md`. Review active silences after maintenance. Silence does not
restore service health, and the Grafana/Prometheus views continue to show the
actual target state.

This manual review process is the MVP choice, not a guaranteed paging system.
If the team later needs unattended incident notification, select a team-owned
destination and approve a separate receiver change. Keep its credentials in a
protected Kubernetes Secret, outside Git.
