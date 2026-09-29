# MVP alert maintenance policy

These rules apply to six standalone VM exporters and five Blackbox service
probes. Deliberately stopping a VM or service will normally produce an alert.

Before planned maintenance, an operator records the service or VM, reason,
owner, start time, and expected end time. Create a time-limited Alertmanager
silence with the exact alert name and the affected labels: `instance` for the
VM root-disk rule, `service` for the built-in VM `TargetDown` rule, and
`service`/`target` for a Blackbox probe. Check the actual labels on the alert
before submitting the silence. Use the shortest practical expiry.
For the two fleet-count alerts, an exact alert-name silence temporarily hides
all missing-target count incidents, so use it only after confirming the count
drop is solely the planned target; keep a separate manual target check during
that window. Review and remove the silence when maintenance ends.

Never silence `Watchdog`, all `severity=critical` alerts, or an entire
namespace to accommodate one maintenance task. A silence changes notification
delivery; it does not make an unhealthy target healthy. The monitoring dashboard
and Prometheus target page must still show the real state.

An unplanned target failure is handled as an incident. Do not make a permanent
silence or disable a rule to clear the page. The existing built-in Kubernetes
and `TargetDown` alerts remain in force for k3s nodes, Pods, Deployments, Jobs,
and scrape failures. The four BUET-PaaS rules cover only the gaps documented in
Step 16C.
