# Step 12B - Prepare secure monitoring ingress locally

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: `Approve Step 12B - prepare secure monitoring ingress configuration locally`
- Repository changes: authorized and completed
- Kubernetes/OpenStack/DNS/browser mutation: **none**
- Live apply: **not performed**
- Result: **local configuration prepared and offline validation passed**

## Purpose

Prepare the reviewed configuration for normal browser access through:

```text
192.168.64.121 -> 192.168.128.200 -> MetalLB -> Traefik
```

Selected hosts:

```text
grafana.monitoring.192.168.64.121.sslip.io
prometheus.monitoring.192.168.64.121.sslip.io
alerts.monitoring.192.168.64.121.sslip.io
```

This step was deliberately local-only. It did not create routes, Secrets,
certificates, users, credentials, DNS records, floating IPs, ports, security
groups, or other live resources.

## Files added

```text
monitoring/ingress/browser-access-values.yaml
monitoring/ingress/middlewares.yaml
monitoring/ingress/http-redirect-ingress.yaml
monitoring/ingress/kustomization.yaml
monitoring/ingress/README.md
```

Application source files were not touched.
`monitoring/README.md` was updated only to reflect the already-completed stack
installation, active frontend VM target, and local-only ingress status.

## Prepared behavior

### HTTPS routes

The Helm overlay enables one host-based HTTPS Ingress for each tool. All three
reference the not-yet-created `monitoring-public-tls` Secret and the existing
Traefik `websecure` entrypoint.

### Authentication

- Grafana keeps its native login. Anonymous access and self-sign-up are
  disabled; new users default to Viewer.
- Prometheus uses a dedicated Traefik Basic Auth Secret named
  `monitoring-prometheus-basic-auth`.
- Alertmanager uses a different administrator-only Secret named
  `monitoring-alertmanager-basic-auth`.
- Basic Auth removes the Authorization header before proxying upstream.

No usernames, password hashes, passwords, certificate values, or private keys
are present in the repository.

### Browser/security behavior

- HTTP requests to only the three monitoring hosts are permanently redirected
  to HTTPS.
- HSTS, `nosniff`, `SAMEORIGIN`, same-origin referrer policy, and a restrictive
  browser feature policy are added at Traefik.
- Separate rate limits are prepared for Grafana, Prometheus, and Alertmanager.
- Prometheus and Alertmanager get correct public external URLs; Grafana gets
  its public domain/root URL and secure cookies.
- Backend services remain `ClusterIP`.

## Secret contract for Step 12C

These exact resources must exist in namespace `monitoring` before any Ingress
apply:

| Secret | Required format |
|---|---|
| `monitoring-public-tls` | `kubernetes.io/tls` with `tls.crt`/`tls.key`; certificate SANs cover all three hosts |
| `monitoring-prometheus-basic-auth` | `Opaque` with key `users` containing strong `htpasswd` entries |
| `monitoring-alertmanager-basic-auth` | `Opaque` with key `users`; credentials differ from Prometheus |

Their values must be created outside Git and must never be printed here.

## Commands executed and outputs

### Inspect existing state and pinned inputs

```powershell
Get-Content -Raw monitoring\prometheus\values.yaml
Get-Content -Raw monitoring\external-vms\scrape-values.yaml
Get-Content -Raw step-12-plan.md
Get-Content -Raw step-12A.md
```

Relevant evidence:

```text
chart: kube-prometheus-stack 91.4.1
Kubernetes target: 1.36.2
selected public FIP: 192.168.64.121
selected MetalLB VIP: 192.168.128.200
IngressClass: traefik
existing raw monitoring services: ClusterIP
```

The pinned chart archive and Helm executable from the earlier offline render
were reused:

```text
chart: C:\Users\USER\AppData\Local\Temp\buet-paas-monitoring-step4\render-final\kube-prometheus-stack-91.4.1.tgz
Helm:  C:\Users\USER\AppData\Local\Temp\buet-paas-monitoring-step4\windows-amd64\helm.exe
```

`helm show chart` confirmed:

```text
name: kube-prometheus-stack
version: 91.4.1
appVersion: v0.94.0
Grafana dependency: 13.2.5
```

### Offline Helm lint

```powershell
helm.exe lint kube-prometheus-stack-91.4.1.tgz `
  --values monitoring\prometheus\values.yaml `
  --values monitoring\external-vms\scrape-values.yaml `
  --values monitoring\ingress\browser-access-values.yaml `
  --kube-version 1.36.2
```

Output:

```text
==> Linting ...\kube-prometheus-stack-91.4.1.tgz
1 chart(s) linted, 0 chart(s) failed
```

### Offline Helm and Kustomize render

```powershell
helm.exe template monitoring-stack kube-prometheus-stack-91.4.1.tgz `
  --namespace monitoring `
  --values monitoring\prometheus\values.yaml `
  --values monitoring\external-vms\scrape-values.yaml `
  --values monitoring\ingress\browser-access-values.yaml `
  --kube-version 1.36.2 --include-crds

kubectl kustomize monitoring\ingress
```

Outputs were written only under:

```text
%TEMP%\buet-paas-step12b-validation\
```

Relevant render results:

```text
Grafana Ingress -> correct host, websecure, TLS Secret, Grafana chain
Prometheus Ingress -> correct host, websecure, TLS Secret, Prometheus chain
Alertmanager Ingress -> correct host, websecure, TLS Secret, Alertmanager chain
Prometheus externalUrl -> exact selected HTTPS URL (1 occurrence)
Alertmanager externalUrl -> exact selected HTTPS URL (1 occurrence)
Grafana root_url -> exact selected HTTPS URL

monitoring-stack-grafana                     ClusterIP
monitoring-stack-kube-prom-alertmanager      ClusterIP
monitoring-stack-kube-prom-prometheus        ClusterIP
public NodePort/LoadBalancer markers: 0

standalone Middleware objects: 10
standalone HTTP redirect Ingress objects: 1
```

### Secret-material guard

```powershell
rg -n 'tls\.crt:|tls\.key:|password:|admin-password:|stringData:|^data:' monitoring\ingress
```

Output:

```text
PASS: no credential or certificate payload keys found in monitoring/ingress
```

### Input preservation

```text
monitoring/prometheus/values.yaml
c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b

monitoring/external-vms/scrape-values.yaml
a5b4c936232457e957f1c2b2fab3dfc3ec1799c9d21df0490fbc865caeef1a32

monitoring/BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md
2ca9582df9a7b20f63c8fd447fc6da3b7f155b51a26ccf7b60b99de163b46fe8
```

These match their pre-Step-12B values.

## Prepared file hashes

```text
0ad5a65f13efb7b4c3356ebe5ba748adf847cb11e62b9af3ccdddf3983696bf7  browser-access-values.yaml
8a181cc14d0a576513b9f38b6f09aa8d6934fa5963e4cf953fe27052a17ff157  middlewares.yaml
8d2d11cc845ad84d86787f5310f7ff009fa5d84c6f1c27890532f3249c20ea5c  http-redirect-ingress.yaml
5bbdb5b1d39b2a4e21b71c8c4087e72ec28112e4ca47696211f3eceb58e91ec6  kustomization.yaml
7a40b2bbec47ffdadf7ed3cbcc5bcfb08fa933e783309799c63eea147130b2cb  ingress/README.md
```

## Errors and corrections

1. The first documentation patch tried to match mojibake tree characters in
   the old `monitoring/README.md`. The patch tool rejected the whole patch
   before writing anything. Documentation was then split into smaller patches.
2. The first PowerShell object-count regex assumed LF line endings and reported
   zero objects. `rg` still showed every rendered object. The regex was changed
   to accept Windows CRLF (`\r?$`), producing the accurate 10 Middleware and 1
   Ingress counts.

Neither error affected live infrastructure or application files.

## NetworkPolicy decision

No NetworkPolicy was prepared. Step 12A found no current policies, and CNI
policy enforcement has not been demonstrated. Applying a deny policy without
that evidence could break monitoring, DNS, or Traefik flows. This is deferred
to a separate evidence-gated hardening step.

## Trusted TLS decision boundary

The configuration requires a valid trusted certificate and does not accept the
current self-signed Traefik default certificate. Step 12C must select and
provision the certificate and auth Secrets. It must not use plain HTTP or rely
on browser certificate-warning bypass.

## Rollback

There is no live rollback because nothing was applied. Repository-only rollback
is deletion/reversion of only the five new `monitoring/ingress` files and the
Step 12B documentation. Do not change the FIP, `metallb-vip-port`, MetalLB VIP,
student routes, Helm release, or existing monitoring workloads.

## Next permission boundary

Step 12C will decide the trusted certificate method and create the three
required Secrets without committing or printing their contents. It must not
start without explicit approval.
