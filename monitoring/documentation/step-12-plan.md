# Step 12 Planning - Floating-IP browser access, APIs, persistence, and logs

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Authorization: revise the existing monitoring plan only
- Infrastructure execution: none
- Kubernetes/OpenStack/VM mutation: none
- Current state: **plan prepared; waiting at the next permission boundary**

## Source preservation

The source document supplied in Downloads was copied unchanged into the
repository before revision:

```text
source:
C:\Users\USER\Downloads\BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md

repository copy:
monitoring/BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md

pre-revision SHA-256 for both copies:
0f9c7496c5b121a9c9757c41c6846252b0e0ba5d2d93515fc28de4787e10fecc
```

The Downloads source remains unchanged. Only the repository copy was revised.

## Revision result

Current revised repository plan SHA-256 after the Step 12C TLS constraint:

```text
3dae8ee165a7a4d7f6c9c7678f8f900887908f37c1e63a6b37baa5cc76f23f8c
```

The original 3-day MVP content was retained. New authoritative Sections
22A-22E add:

- the existing proven OpenStack ingress floating IP `192.168.64.121`;
- existing Traefik ingress as the preferred Kubernetes entry point;
- HTTPS-only public edge on TCP 443;
- no new OpenStack security-group rule for the shared ingress path;
- DNS host routing, with an IP/path fallback;
- authentication and least-privilege access for each monitoring UI;
- explicit prohibition on public raw ports 3000/9090/9093/9100/9115;
- staged OpenStack and Kubernetes implementation with separate approvals;
- browser, security, and application-regression tests;
- protected Prometheus/Grafana/Alertmanager API access;
- an explicit statement that metrics are not logs;
- Loki + Grafana Alloy as the later centralized logging phase;
- current ephemeral-storage limitations and a measured persistence plan;
- exact rollback principles;
- a revised order from the current implementation state.

## Architectural recommendation recorded

```text
Team browser
    -> HTTPS 443
    -> existing OpenStack floating IP 192.168.64.121
    -> metallb-vip-port / MetalLB VIP 192.168.128.200
    -> existing k3s Traefik
    -> Grafana/Prometheus/Alertmanager ClusterIP services
```

Step 12A evidence superseded the initial dedicated-FIP assumption. Horizon and
live tests proved that `192.168.64.121` is already mapped to fixed IP
`192.168.128.200` through `metallb-vip-port`, and that HTTP/HTTPS reach the
existing Traefik path. The team explicitly selected this FIP with sslip.io
hostnames. Do not reuse the `frontend-vm` floating IP, allocate a new FIP, or
attach a FIP directly to a K3s VM for this MVP.

Step 12C added an important TLS constraint: `192.168.64.121` is RFC1918 private
space. Public ACME HTTP-01 validators cannot route to it, and DNS-01 is not
available without control of the sslip.io zone. The immediate campus-MVP option
is a private/team CA installed into authorized device trust stores. The
preferred production option is a BUET/team-controlled subdomain with public
ACME DNS-01. Neither option is assumed or executed without a separate explicit
trust-model approval.

## Security boundary

The phrase "browser accessible" does not authorize exposing raw monitoring
ports. The intended public/private split is:

```text
TCP 443 through authenticated HTTPS ingress: complete
TCP 80 for redirect/ACME only: conditional
TCP 3000/9090/9093/9100/9115 public: prohibited
```

Grafana is team-facing with Viewer by default. Prometheus is operations/team
only. Alertmanager is administrator-only. Exporters remain private.

## API and log decisions

Prometheus `/api/v1/*`, Alertmanager `/api/v2/*`, and authenticated Grafana APIs
can be consumed through the same protected HTTPS gateway. Per-client identities,
rate limits, source restrictions, and secrets outside Git are required.

The current stack has component stdout/stderr logs available through
`kubectl logs`, but no centralized durable application-log store. Loki +
Grafana Alloy is planned only after metrics, browser ingress, storage capacity,
privacy/redaction, and retention are reviewed.

## Current durability warning

The plan now clearly records:

```text
Prometheus: 2-day retention, no PVC
Grafana: persistence disabled
Alertmanager: no persistent storage
```

Persistence is a later separately approved step based on measured bytes/day,
active series, StorageClass behavior, and quota. A public URL does not by itself
authorize a PVC or retention increase.

## Revised next steps

```text
11A2  COMPLETE - frontend-vm scrape target UP
12A-E COMPLETE - VPN HTTPS access and browser verification
13A   Read-only stability, alerts, targets, endpoints, and capacity audit
14    Remaining exporters, one VM per approved substep
15    Blackbox endpoint confirmation and probes
16    Provisioned dashboard and small alert set
17    Persistence after representative 48-hour measurement
18    Project-scoped protected monitoring API/UI
19    Loki + Alloy pilot after metrics MVP hardening
```

Steps 11A2 and 12A-12E are complete. The private/team CA was selected for the
VPN-only campus MVP, routes were applied, and trusted-browser verification
passed. The immediate permission boundary is Step 13A, a read-only stability,
alert, target, endpoint, and capacity audit. Detailed sequencing is recorded in
`step-13-plan.md`.

## Tooling correction

The first patch request contained two update operations for the same file, and
the patch tool rejected it before writing. The revision was then applied as two
small patches and verified. This had no infrastructure effect and did not alter
the Downloads source.

## QA

```text
original source hash unchanged: yes
original MVP content retained: yes
revision headings present: yes
Markdown fence-marker count: 428 (even)
new trailing whitespace introduced: none
credentials/secrets added: none
infrastructure commands executed: none
```

## Rollback

Because this is documentation-only, rollback is to remove the repository copy
or revert only the added revision sections. The original Downloads document is
still available with its unchanged hash. Do not roll back unless explicitly
requested.
