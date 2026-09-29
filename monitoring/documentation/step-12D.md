# Step 12D - Apply admin-only authenticated VPN monitoring ingress

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: `Approve Step 12D - apply admin-only authenticated VPN monitoring ingress`
- Result: **completed successfully**
- Helm release: `monitoring-stack`, revision `5`, status `deployed`
- OpenStack/DNS/security-group mutation: **none**
- Existing application source mutation: **none**
- Credential/private-key disclosure: **none**

This step made the three monitoring UIs available as clickable HTTPS links on
the existing VPN-reachable ingress address. It did not make the raw monitoring
ports public and did not create a new floating IP, VM, load balancer, DNS zone,
or security-group rule.

## Approved URLs and audience

```text
Grafana:
https://grafana.monitoring.192.168.64.121.sslip.io

Prometheus (admin/operator Basic Auth):
https://prometheus.monitoring.192.168.64.121.sslip.io

Alertmanager (admin Basic Auth):
https://alerts.monitoring.192.168.64.121.sslip.io
```

These links are intended for authorized administrators/operators connected to
the BUET/OpenConnect VPN. Raw cluster-wide dashboards and APIs are not exposed
to normal PaaS project users. Project-scoped monitoring in the BUET-PaaS UI is a
later authorization/API feature.

## Inputs used

The live Helm upgrade reused the exact reviewed files:

```text
monitoring/prometheus/values.yaml
SHA-256 c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b

monitoring/external-vms/scrape-values.yaml
SHA-256 a5b4c936232457e957f1c2b2fab3dfc3ec1799c9d21df0490fbc865caeef1a32

monitoring/ingress/browser-access-values.yaml
SHA-256 0ad5a65f13efb7b4c3356ebe5ba748adf847cb11e62b9af3ccdddf3983696bf7

rendered monitoring/ingress kustomization
SHA-256 2587963b4a62c80dc6da9c8313681d9c324f85530ae59c565186cce146e69f0d
```

Pinned chart:

```text
kube-prometheus-stack 91.4.1
OCI digest sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
```

The four Secrets prepared in Step 12C1 already existed. Only their names and
types were verified; no secret payload was printed:

```text
monitoring-internal-ca               Opaque
monitoring-public-tls                kubernetes.io/tls
monitoring-prometheus-basic-auth     kubernetes.io/basic-auth
monitoring-alertmanager-basic-auth   kubernetes.io/basic-auth
```

## Before-state baseline

Read-only checks immediately before apply showed:

```text
Helm revision: 4, deployed
k3s nodes: 4/4 Ready
monitoring Pods: healthy
monitoring browser Ingresses: absent
monitoring Traefik Middlewares: absent
student route hello: HTTP 200
student route dummy-dev-frontend: HTTP 200
three monitoring hostnames -> 192.168.64.121
```

## Server-side dry run

The rendered standalone resources were checked with:

```bash
kubectl apply --server-side --dry-run=server -f <rendered-ingress-file>
```

All ten Traefik `Middleware` objects and the HTTP redirect `Ingress` passed.
The pinned Helm upgrade also passed server-side dry run and rendered revision 5.

## Live apply

The approved change used this sequence:

```bash
kubectl apply -f <rendered-ingress-file>

helm upgrade monitoring-stack \
  oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack \
  --version 91.4.1 \
  --namespace monitoring \
  --values monitoring/prometheus/values.yaml \
  --values monitoring/external-vms/scrape-values.yaml \
  --values monitoring/ingress/browser-access-values.yaml \
  --atomic --wait --timeout 30m
```

The wrapper was prepared to delete only the eleven standalone objects if Helm
failed. That rollback branch did not run because Helm completed successfully:

```text
Release "monitoring-stack" has been upgraded. Happy Helming!
STATUS: deployed
REVISION: 5
STEP12D_HELM_SUCCESS
```

Applied standalone objects:

```text
1 Ingress: monitoring-http-redirect
10 Traefik Middleware objects:
  monitoring-security-headers
  monitoring-https-redirect
  monitoring-grafana-rate-limit
  monitoring-prometheus-rate-limit
  monitoring-alertmanager-rate-limit
  monitoring-prometheus-auth
  monitoring-alertmanager-auth
  monitoring-grafana-chain
  monitoring-prometheus-chain
  monitoring-alertmanager-chain
```

Helm revision 5 created three TLS Ingresses, all referencing
`monitoring-public-tls`, while the HTTP-only ingress performs permanent HTTPS
redirects.

## Rollout observation

Prometheus and Alertmanager became Ready first. The new Grafana Pod initially
showed `2/3` because Grafana was performing its existing database migrations;
the old Grafana Pod stayed available during that period. Logs showed successful
migrations, no crash, and zero restarts. After migration the new Pod became
`3/3`, the old Pod terminated normally, and the atomic Helm command completed.

Final workload state:

```text
nodes: 4/4 Ready
monitoring Pods: 9, all containers Ready
Grafana: 3/3 Running, 0 restarts
Prometheus: 2/2 Running, 0 restarts
Alertmanager: 2/2 Running, 0 restarts
node-exporter: 4/4 Running
```

All monitoring Services remain `ClusterIP`.

## Verification evidence

### Routing, TLS, and headers

```text
HTTP Grafana -> 301 HTTPS
HTTP Prometheus -> 301 HTTPS
HTTP Alertmanager -> 301 HTTPS

Grafana /api/health -> 200, TLS verification result 0
Prometheus /-/ready without auth -> 401, TLS verification result 0
Alertmanager /-/ready without auth -> 401, TLS verification result 0
```

Grafana returned the expected security headers, including:

```text
Strict-Transport-Security: max-age=31536000
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
Referrer-Policy: same-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Windows `curl` needed `--ssl-no-revoke` because this internal CA has no public
CRL endpoint. Certificate-chain and hostname validation remained enabled and
reported `ssl_verify_result=0`; `-k/--insecure` was not used.

### Authentication boundary

Credentials were read into temporary remote shell variables directly from the
Kubernetes Secrets and were never echoed. Results:

```text
Prometheus authenticated /api/v1/status/buildinfo -> 200
Alertmanager authenticated /api/v2/status -> 200
Grafana anonymous /api/search -> 401
Grafana admin API login -> success
```

### Dashboards and metrics

```text
Grafana authenticated dashboard count: 23
Grafana Kubernetes-tagged dashboards: 16
Prometheus active targets: 26
Prometheus UP targets: 26
frontend-vm target:
  job=standalone-node-exporters
  health=up
  URL=http://192.168.128.15:9100/metrics
```

### External port boundary

From the VPN-connected workstation:

```text
192.168.64.121:80   open=True
192.168.64.121:443  open=True
192.168.64.121:3000 open=False
192.168.64.121:9090 open=False
192.168.64.121:9093 open=False
192.168.64.121:9100 open=False
```

### Existing application regression

```text
http://hello.192.168.64.121.sslip.io/ -> 200
http://dummy-dev-frontend.21050.192.168.64.121.sslip.io/ -> 200
```

No existing application Ingress, Service, Deployment, VM, floating-IP mapping,
or security-group rule was changed.

## Temporary-file cleanup

After successful verification, only the exact Step 12D staging artifacts were
removed:

```text
/tmp/buet-paas-step12d.1HXUlC -> removed
%TEMP%\step12d-kustomize-rendered.yaml -> absent/removed
```

The remote path was accepted only after matching
`/tmp/buet-paas-step12d.*`; the local filename was accepted only after resolving
inside the Windows temporary directory. No repository or application file was
deleted.

## Errors and corrections

All errors below were command-wrapper or verification-query issues. None
changed the intended live state.

1. The first baseline wrapper let local PowerShell parse part of a remote `jq`
   expression. It failed before SSH execution. The quote-safe retry succeeded.
2. The first dry-run wrapper had an unmatched nested quote and exited before
   apply. Explicit remote paths were used on retry; server-side dry run passed.
3. Two post-apply `jq` expressions were damaged by nested PowerShell/SSH quote
   escaping. Resource listings before those expressions succeeded; the failed
   expressions were replaced by a CR-stripped Bash stdin script.
4. The first corrected target-count expression had `jq` pipe-precedence wrong.
   It was changed to bind `.data.activeTargets` to `$t`; result was `26/26` UP.
5. A final Windows carriage return was passed to `wc -l` in one remote stdin
   script. Dashboard ConfigMaps were then listed directly; 23 were present, and
   Grafana's authenticated API independently confirmed 23 dashboards.
6. Initial Windows `curl` HTTPS checks returned `revocation status is unknown`.
   This was the expected lack of a public CRL for the private CA, not a hostname
   or chain failure. Retrying with `--ssl-no-revoke` (not `--insecure`) produced
   TLS verification result 0.

## Rollback boundary

Rollback requires separate approval. The safe order is:

```bash
helm rollback monitoring-stack 4 -n monitoring --wait --timeout 30m

kubectl delete ingress monitoring-http-redirect -n monitoring
kubectl delete middleware.traefik.io \
  monitoring-security-headers \
  monitoring-https-redirect \
  monitoring-grafana-rate-limit \
  monitoring-prometheus-rate-limit \
  monitoring-alertmanager-rate-limit \
  monitoring-prometheus-auth \
  monitoring-alertmanager-auth \
  monitoring-grafana-chain \
  monitoring-prometheus-chain \
  monitoring-alertmanager-chain \
  -n monitoring
```

Do not delete the TLS/authentication Secrets during an emergency route rollback;
keeping them allows forensic inspection and a controlled reapply. Do not change
the shared floating-IP/VIP path.

## Remaining manual check

Automated Step 12D verification passed. Step 12E remains a separate permission
boundary for the user/team to open the links in a freshly restarted trusted
browser while connected to OpenConnect VPN, confirm login/UI behavior, and
capture screenshots. No port-forward is required for these links.
