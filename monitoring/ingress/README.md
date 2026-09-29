# Secure monitoring browser ingress

## Status

These files are prepared and offline-validated only. They are **not applied**.
They reuse the existing public path:

```text
192.168.64.121 -> 192.168.128.200 -> MetalLB -> Traefik
```

## Public hostnames

```text
https://grafana.monitoring.192.168.64.121.sslip.io
https://prometheus.monitoring.192.168.64.121.sslip.io
https://alerts.monitoring.192.168.64.121.sslip.io
```

All backend Services remain `ClusterIP`. No raw monitoring port becomes public.

## Files

- `browser-access-values.yaml`: Helm overlay enabling three HTTPS Ingresses and
  configuring the applications' externally advertised URLs.
- `middlewares.yaml`: Traefik security headers, rate limits, independent Basic
  Auth boundaries for Prometheus and Alertmanager, and middleware chains.
- `http-redirect-ingress.yaml`: redirects the three monitoring hosts from HTTP
  to HTTPS. It does not expose an unauthenticated HTTP UI.
- `kustomization.yaml`: renders the non-Helm resources together.
- `certs/buet-paas-monitoring-ca.crt`: distributable CA public certificate;
  contains no private key.
- `scripts/install-ca-current-user.ps1`: validates the pinned fingerprint and,
  only with explicit `-Install`, adds the CA to the current Windows user's root
  store.
- [`WINDOWS-TRUST.md`](../documentation/monitoring/ingress/WINDOWS-TRUST.md): manual validation, installation, browser, and rollback
  instructions.

## Required Step 12C Secrets

Do not commit Secret manifests or generated credentials. Before any Step 12D
apply, create these exact Secrets in namespace `monitoring` by an approved,
out-of-band process:

| Secret | Type/required keys | Purpose |
|---|---|---|
| `monitoring-internal-ca` | `Opaque`: `ca.crt`, `ca.key` | VPN-only internal CA; private key stays inside the protected Secret |
| `monitoring-public-tls` | `kubernetes.io/tls`: `tls.crt`, `tls.key` | Internal-CA leaf certificate whose SANs contain all three hostnames |
| `monitoring-prometheus-basic-auth` | `kubernetes.io/basic-auth`: `username`, `password` | Random Prometheus team credential |
| `monitoring-alertmanager-basic-auth` | `kubernetes.io/basic-auth`: `username`, `password` | Separate random Alertmanager administrator credential |

The Prometheus and Alertmanager credentials are different. Grafana uses its
native named-user login; anonymous access and self-sign-up remain disabled.

Step 12C1 selected VPN-only internal TLS. The CA is trusted only after its
public `ca.crt` is explicitly installed on an authorized device. Never export
`ca.key`. The current Traefik default certificate, plain-HTTP credentials, and
browser-warning bypass are not acceptable final states.

The leaf certificate expires on 2027-09-24 and requires planned renewal before
that date. The CA expires on 2031-09-23.

## Intended deployment order (not authorized in Step 12B)

1. Reconfirm cluster and student-app health.
2. Create and inspect the three Secrets without printing their values.
3. Apply `middlewares.yaml` and `http-redirect-ingress.yaml`.
4. Run the existing Helm release upgrade with all three values files, using
   `--atomic`, `--wait`, and a 30-minute timeout.
5. Verify TLS identity, authentication boundaries, redirects, dashboards,
   targets, alerts, raw-port isolation, and student-app regression.

## Helm values order

```powershell
helm upgrade monitoring-stack <PINNED_CHART> `
  --namespace monitoring `
  --values monitoring/prometheus/values.yaml `
  --values monitoring/external-vms/scrape-values.yaml `
  --values monitoring/ingress/browser-access-values.yaml `
  --atomic --wait --timeout 30m
```

The command above is documentation only and must not run without explicit Step
12D approval.

## Verification outline

```text
HTTP on each monitoring hostname -> permanent HTTPS redirect
HTTPS certificate -> trusted and SAN matches hostname
Grafana -> native login; anonymous request cannot read dashboards
Prometheus -> 401 without its credentials; works with authorized credentials
Alertmanager -> 401 without its separate credentials
3000/9090/9093/9100 -> not publicly reachable
Prometheus targets -> remain UP
Grafana dashboards -> remain provisioned and query successfully
student application routes -> unchanged and healthy
```

## Rollback outline

1. Atomically roll the Helm release back to its immediately previous successful
   revision.
2. Delete only `monitoring/monitoring-http-redirect` and the ten
   `monitoring-*` Middleware objects defined here.
3. Confirm private port-forward access still works.
4. Delete the three Step 12C Secrets only after confirming no resource refers
   to them.
5. Never disassociate `192.168.64.121`, edit `metallb-vip-port`, remove
   `192.168.128.200`, or change student application routes as part of rollback.

## NetworkPolicy decision

No NetworkPolicy is prepared in this step. Step 12A found no existing policies,
and CNI policy enforcement has not been demonstrated. Introducing a deny policy
without that evidence could interrupt Prometheus, Grafana, Alertmanager, DNS,
or Traefik traffic. It remains a separate evidence-gated hardening step.
