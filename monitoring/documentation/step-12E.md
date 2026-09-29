# Step 12E - Manual trusted-browser monitoring verification

## Status

- Date started: 2026-09-24 (Asia/Dhaka)
- Permission: `Approve Step 12E - manually verify trusted-browser monitoring access`
- Infrastructure mutation: **none**
- Current result: **complete; all three monitoring UIs verified in the browser**

Step 12D already proved routing, TLS identity, authentication boundaries,
dashboard provisioning, target health, closed raw ports, and application
regression with read-only network/API checks. Step 12E adds the human browser
view: trusted certificate behavior, login screens, and usable rendered UIs.

## Browser automation attempt

The Windows browser-control surface was inspected before interaction:

```text
apps: []
browsers: []
```

Two non-mutating attempts were made to open the Grafana URL:

```text
Chrome: Browser is not available: chrome
Visible built-in browser: Browser is not available: iab
Browser lookup by URL: No browser is available
```

No browser, credential, certificate setting, Kubernetes object, or application
resource was changed. Authentication dialogs were not automated and no TLS
warning was bypassed.

## Manual verification procedure

Prerequisites:

1. Connect OpenConnect VPN.
2. Confirm the Step 12C2 CA is installed for the current Windows user.
3. Fully close and reopen the browser after CA installation.
4. Keep credentials out of screenshots.

### Grafana

Open:

```text
https://grafana.monitoring.192.168.64.121.sslip.io
```

Verify:

- no certificate warning;
- Grafana login page opens;
- native Grafana login succeeds;
- Dashboards page lists 23 provisioned dashboards;
- open `Kubernetes / Compute Resources / Nodes Overview`;
- panels render data and show four k3s nodes.

Evidence requested:

- dashboard-list screenshot with no credentials;
- Nodes Overview screenshot with the time range and node panels visible.

#### Evidence received - Grafana dashboard list

The user supplied a browser screenshot after logging in through the approved
access path. It shows:

```text
Grafana application rendered normally
Dashboards page open
provisioned Alertmanager, CoreDNS, Grafana, Kubernetes, Node Exporter,
and Prometheus dashboards visible
no certificate warning or browser interstitial
no credential visible in the screenshot
```

This satisfies the Grafana trusted-browser, login, and dashboard-list portion
of Step 12E. The Step 12D authenticated API result remains the authoritative
exact count: 23 dashboards.

#### Evidence received - Grafana Nodes Overview

The user supplied the next sequential browser screenshot. It shows:

```text
dashboard: Kubernetes / Compute Resources / Nodes Overview
time range: Last 1 hour (UTC)
node count: 4
pod count: 62
CPU Usage panel: populated
Memory Usage panel: populated
CPU Utilization per Node: four node series
Memory Utilization per Node: four node series
```

Visible node series:

```text
k3s-control-01
k3s-worker-01
k3s-worker-02
k3s-worker-03
```

No `No data` state or panel error is visible. This completes the Grafana UI
portion of Step 12E.

### Prometheus

Open:

```text
https://prometheus.monitoring.192.168.64.121.sslip.io
```

Use the credentials from Secret `monitoring-prometheus-basic-auth`. Verify:

- Basic Auth prompt appears;
- login succeeds without a certificate warning;
- `Status -> Target health` opens;
- targets show 26/26 UP;
- querying `count(kube_node_info)` returns `4`.

Evidence requested:

- Target health screenshot showing UP state;
- query screenshot showing result `4`.

#### Evidence received - Prometheus Target health

The user supplied the authenticated browser screenshot for `/targets`. It
shows the Prometheus `Status > Target health` page with visible green `UP`
states for Grafana, Alertmanager, API server, CoreDNS, and kubelet scrape pools.
The kubelet pools show `4 / 4 up`, covering all four k3s nodes. No `DOWN` state
is visible in the supplied view. This agrees with the Step 12D API result of
26 active targets and 26 UP targets.

#### Evidence received - Prometheus node-count query

The user supplied a screenshot of this PromQL query:

```promql
count(kube_node_info)
```

The Table result contains one result series with value `4` and a 6 ms load
time. This matches the four Ready nodes and completes the Prometheus browser
portion of Step 12E.

### Alertmanager

Open:

```text
https://alerts.monitoring.192.168.64.121.sslip.io
```

Use the credentials from Secret `monitoring-alertmanager-basic-auth`. Verify:

- Basic Auth prompt appears;
- login succeeds without a certificate warning;
- Alerts page renders;
- Status page renders configuration/version information;
- do not create a silence or change configuration.

Evidence requested:

- Alerts page screenshot;
- Status page screenshot without credentials.

#### Evidence received - Alertmanager Alerts and Silences

The user supplied two authenticated UI screenshots:

```text
Alerts page rendered normally
Not grouped: 1 alert
namespace="2105062": 4 alerts
total alerts visible: 5

Silences page rendered normally
Active/Pending/Expired tabs available
No silences found
```

No credential is visible and no silence was created. This verifies the
Alertmanager trusted-browser login and read-only Alerts/Silences UI behavior.
The existing alerts are operational state to review separately; merely viewing
them did not modify routing, alerts, or silences.

#### Evidence received - Alertmanager Status

The user provided a text excerpt from the authenticated Status page rather
than a screenshot. It shows `Cluster Status: disabled`, no peers, version
metadata (branch `HEAD`, build date `20260816-16:36:04`, Go `1.26.6`), and the
start of the configuration section. This confirms that the read-only Status
page renders. The full configuration was not shared or recorded.

`Cluster Status: disabled` is expected for the current single Alertmanager
replica; it does not mean Alertmanager or alert evaluation is disabled. The
Alerts page already showed active alert groups, and the Step 12D API check
returned HTTP 200.

## Already verified automatically

```text
TLS chain and hostname: valid (ssl_verify_result=0)
Grafana health: 200
Grafana anonymous dashboard API: 401
Prometheus unauthenticated: 401
Prometheus authenticated API: 200
Alertmanager unauthenticated: 401
Alertmanager authenticated API: 200
Grafana dashboards through authenticated API: 23
Prometheus targets: 26/26 UP
frontend-vm exporter: UP
ports 3000/9090/9093/9100 on ingress IP: closed
existing student routes: HTTP 200
```

## Completion boundary

Step 12E is complete based on the user supplied browser screenshots/results
and the Step 12D automated evidence. Grafana dashboards and node panels,
Prometheus Target health and node query, and Alertmanager Alerts, Silences,
and Status all rendered. No certificate warning, failed login, empty panel, or
DOWN target was reported. Student route regression checks returned HTTP 200.

The Alertmanager Status evidence is a user supplied excerpt, so its page
layout and full configuration were not independently inspected. The five
visible active alerts remain operational items for a separate review; this
verification step did not diagnose, silence, or change them.
