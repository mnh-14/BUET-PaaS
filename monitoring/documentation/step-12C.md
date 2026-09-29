# Step 12C - Trusted TLS and authentication Secret preparation

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: `Approve Step 12C - prepare trusted TLS and authentication secrets`
- Current state: **Step 12C1 completed using VPN-only internal TLS**
- Kubernetes mutation: **four new Secrets in namespace `monitoring`**
- OpenStack/DNS/VM mutation: **none**
- Secrets created: **internal CA, leaf TLS, two independent auth Secrets**
- cert-manager installed: **no; intentionally unnecessary for this MVP**

## Initial public-ACME preflight pause

Step 12B referenced a future trusted certificate for:

```text
grafana.monitoring.192.168.64.121.sslip.io
prometheus.monitoring.192.168.64.121.sslip.io
alerts.monitoring.192.168.64.121.sslip.io
```

The selected floating IP `192.168.64.121` is inside RFC1918
`192.168.0.0/16`. It is reachable within the BUET/campus network path but is not
globally Internet-routable.

This makes the initially considered public ACME route unsafe to assume:

1. Let's Encrypt HTTP-01 validation must reach the hostname over public TCP 80.
   A public validator cannot route to `192.168.64.121`.
2. DNS-01 would avoid that network limitation, but the team does not control
   the `sslip.io` DNS zone and therefore cannot publish its required TXT record.
3. sslip.io is a shared domain and has documented global certificate-rate-limit
   exhaustion. Even on a publicly reachable IP, production issuance would not
   be a dependable ownership boundary.

Therefore installing cert-manager and creating a production Let's Encrypt
Certificate now would add cluster-wide CRDs/RBAC while being unable to satisfy
the required trusted-certificate outcome.

## Read-only preflight

The first SSH wrapper had unmatched nested quotes and exited before its remote
checks ran:

```text
bash: unexpected EOF while looking for matching quote
```

The command was simplified and retried. No state changed in either attempt.

Corrected checks established:

```text
cert-manager namespace: absent
cert-manager Pods: absent
cert-manager CRDs/APIs: absent
cert-manager Helm release: absent
Issuer/ClusterIssuer/Certificate resources: absent
IngressClass: traefik (default)
monitoring-public-tls Secret: absent
monitoring-prometheus-basic-auth Secret: absent
monitoring-alertmanager-basic-auth Secret: absent
monitoring Helm release: revision 4, deployed
monitoring browser Ingresses: absent
```

Existing student/application Ingress objects and the shared ingress path remain
unchanged.

## Supported options

### Option A - Team/private CA for the current private FIP

Use a private CA to issue one leaf certificate covering all three sslip.io
hostnames. Install only the CA public certificate into the trusted root store of
each authorized team device/browser.

Advantages:

- works with private `192.168.64.121`;
- no public DNS ownership or Internet-reachable validation is required;
- browsers become warning-free on devices where the CA is explicitly trusted.

Tradeoffs:

- every authorized device must install the CA certificate;
- the CA private key needs a deliberate protected storage/renewal policy;
- it is not publicly trusted outside managed team devices.

For this campus/private MVP, this is the recommended immediately workable
option.

### Option B - BUET/team-controlled domain with DNS-01

Obtain a controlled subdomain and permission/API credentials to create ACME TXT
records. A public CA can then validate domain control through DNS-01 even when
the service address is private.

Advantages:

- normal public browser trust;
- reliable domain ownership boundary;
- automatic renewal is possible.

Tradeoffs:

- requires DNS administrative cooperation/credentials;
- the domain and renewal process are not currently available.

This is the recommended production/end-state option.

### Rejected option - Let's Encrypt HTTP-01 on current sslip.io/private IP

This is not a valid plan because the ACME validator cannot publicly route to the
private address. Repeated production attempts could also consume shared-domain
or failed-validation limits without producing a usable certificate.

## Authentication Secret preparation decision

The two Basic Auth Secrets were initially withheld while the TLS trust model was
unresolved. After the user clarified that access is VPN-only and approved the
internal-TLS branch, separate random credentials were created for Prometheus
and Alertmanager without printing their values.

Once a TLS option is selected, credentials will be created without printing
them. Prometheus and Alertmanager will use different credentials. The user will
receive a safe manual retrieval/rotation procedure; credentials will not be
written to Git or Markdown.

## Pre-continuation no-change proof

```text
Kubernetes namespaces created: 0
Helm releases installed/upgraded: 0
CRDs created: 0
Secrets created/updated: 0
Ingresses created/updated: 0
OpenStack resources changed: 0
DNS records changed: 0
VM packages/files changed: 0
application source files changed: 0
```

Documentation integrity:

```text
original Downloads plan SHA-256:
0f9c7496c5b121a9c9757c41c6846252b0e0ba5d2d93515fc28de4787e10fecc

revised repository plan SHA-256 after recording this TLS constraint:
3dae8ee165a7a4d7f6c9c7678f8f900887908f37c1e63a6b37baa5cc76f23f8c

base monitoring values SHA-256 (unchanged):
c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b

external VM scrape values SHA-256 (unchanged):
a5b4c936232457e957f1c2b2fab3dfc3ec1799c9d21df0490fbc865caeef1a32
```

The trailing spaces detected on original plan lines 38-43 predate this step;
no trailing whitespace was introduced in the new Step 12C sections.

## Permission clarification that was resolved

To continue with the current private FIP and sslip.io names, approve the private
CA trust model. That continuation will be split safely:

1. install pinned cert-manager and create a namespace-scoped private CA/leaf
   certificate plus auth Secrets, without applying browser Ingresses;
2. export only the CA public certificate and give manual trust-store steps;
3. verify the certificate Secret and credential Secret structure without
   displaying sensitive values;
4. stop before Step 12D Ingress apply.

If a BUET/team-controlled DNS zone becomes available instead, do not approve the
private-CA continuation; provide the subdomain/DNS method and revise Step 12C to
use public ACME DNS-01.

## Step 12C1 continuation selected by the user

The user presented both possible approval phrases and asked for the best option.
VPN-only internal TLS was selected because it keeps the same clickable-link
experience without sending credentials as clear text over HTTP.

Approved scope:

```text
Approve Step 12C1 - prepare VPN-only internal TLS and authentication securely
```

Implementation deliberately did not install cert-manager. For three static MVP
hostnames, OpenSSL-generated internal PKI avoids new cluster-wide CRDs,
controllers, webhooks, and RBAC.

Created resources:

```text
monitoring/monitoring-internal-ca
  type: Opaque
  keys: ca.crt, ca.key

monitoring/monitoring-public-tls
  type: kubernetes.io/tls
  keys: tls.crt, tls.key

monitoring/monitoring-prometheus-basic-auth
  type: kubernetes.io/basic-auth
  keys: username, password

monitoring/monitoring-alertmanager-basic-auth
  type: kubernetes.io/basic-auth
  keys: username, password
```

Secret values, passwords, and private keys were not printed or written to Git.
The two auth passwords were independently generated random 48-character base64
strings. Their usernames are non-secret identifiers:

```text
Prometheus: prometheus-team
Alertmanager: alertmanager-admin
```

## Certificate evidence

```text
leaf subject: CN=grafana.monitoring.192.168.64.121.sslip.io, O=BUET-PaaS
leaf issuer: CN=BUET-PaaS Monitoring Internal CA, O=BUET-PaaS
leaf validity: 2026-09-24 11:40:58 UTC to 2027-09-24 11:40:58 UTC
leaf SHA-256 fingerprint:
4B:EE:EE:C8:2D:BC:B7:BF:69:4D:6B:62:10:66:A9:86:6A:FB:4F:A2:B7:E5:AA:07:AC:FA:2B:6B:87:51:BD:AE

CA validity: 2026-09-24 11:40:57 UTC to 2031-09-23 11:40:57 UTC
CA SHA-256 fingerprint:
73:5C:69:0E:91:32:3B:97:3F:20:69:BC:1B:EB:23:A5:CD:4B:96:F3:76:95:3D:8D:56:D3:71:96:DF:8E:DE:18
```

Leaf SANs:

```text
grafana.monitoring.192.168.64.121.sslip.io
prometheus.monitoring.192.168.64.121.sslip.io
alerts.monitoring.192.168.64.121.sslip.io
```

Stored TLS certificate/private key: `MATCH`.
Stored CA certificate/private key: `MATCH`.

Only `ca.crt` may be exported to authorized team devices. Never export
`ca.key`. Installing the CA certificate into a device trust store is a separate
manual security-sensitive action.

## Post-creation health and no-regression evidence

```text
monitoring Helm release: revision 4, deployed
monitoring Ingress count: 0
monitoring Pods: 9/9 Running and Ready, zero restarts
k3s nodes: 4/4 Ready
temporary ca.key/tls.key/tls.csr/leaf.ext files under /tmp: none
OpenStack changes: none
DNS changes: none
VM package/file changes: none
application source changes: none
```

## Step 12C1 errors and corrections

1. PowerShell added one final carriage-return byte after the remote script. All
   creation, labelling, certificate verification, and Secret description had
   completed, then Bash reported `$'\r': command not found`. The cleanup trap
   still ran. No creation retry was attempted; read-only checks confirmed all
   four Secrets and no temporary key files.
2. The first stored-certificate JSONPath used one excess escaped backslash, so
   OpenSSL received no certificate and the read-only command stopped. The
   corrected JSONPath read the stored certificate successfully.
3. A read-only `awk` formatter contained `$1`-`$4`, which PowerShell expanded
   locally and broke. The formatter was removed; plain `kubectl get` confirmed
   workload health.

None of these wrapper/formatting errors altered resources after creation.

## Current next boundary

Step 12C1 is complete. Step 12D must not begin until separately approved. It
will apply the already-reviewed Middlewares/redirect and atomically upgrade the
monitoring Helm release with the browser-access overlay. CA public-certificate
export/trust instructions and auth credential retrieval will be provided
without printing sensitive values in the automation log.

## Step 12C2 - Export CA public certificate and prepare Windows trust

Permission received:

```text
Approve Step 12C2 - export CA public certificate and prepare Windows trust instructions
```

Only `ca.crt` was read from the live `monitoring-internal-ca` Secret. Neither
`ca.key`, `tls.key`, nor either authentication password was requested or
printed.

Added:

```text
monitoring/ingress/certs/buet-paas-monitoring-ca.crt
monitoring/ingress/scripts/install-ca-current-user.ps1
monitoring/ingress/WINDOWS-TRUST.md
```

The PowerShell helper performs these operations in order:

1. resolve and load the local public certificate;
2. calculate SHA-256 over the DER certificate bytes;
3. stop on any fingerprint mismatch;
4. display subject, issuer, validity, SHA-1 thumbprint, and SHA-256 fingerprint;
5. make no trust-store change unless `-Install` is explicitly supplied;
6. avoid duplicate installation by exact thumbprint.

Validation-only command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\monitoring\ingress\scripts\install-ca-current-user.ps1
```

Output:

```text
Subject: O=BUET-PaaS, CN=BUET-PaaS Monitoring Internal CA
Issuer: O=BUET-PaaS, CN=BUET-PaaS Monitoring Internal CA
NotBefore: 2026-09-24 11:40:57Z
NotAfter: 2031-09-23 11:40:57Z
SHA-1 thumbprint: 54F86061294D752132D234EA3CC1FAD4D73C9F99
SHA-256: 735C690E91323B973F2069BC1BEB23A5CD4B96F376953D8D56D37196DF8EDE18
FingerprintMatch: True
Validation only: the Windows certificate store was not changed.
```

Read-only store verification returned:

```text
ABSENT: CurrentUser Root trust store was not changed
```

Prepared-file SHA-256 hashes:

```text
bad8b9f0bf280988cd5f4511a3b1047c5b456c607b2638c03ca4ead4c75bbbff  buet-paas-monitoring-ca.crt
792709516ef6c9de2c8fe01007516a1c11f48f8bc4e3a2dad366d58cd2865a7a  install-ca-current-user.ps1
ba1d84855c95201ce093e93debc5c32c9692a188d35b44315a3c0f31f026cfae  WINDOWS-TRUST.md
```

Sensitive-material scan:

```text
PASS: no private key or credential material in monitoring/ingress
```

### Step 12C2 errors and corrections

1. The initial helper used Bash-style backslashes to continue the
   `Import-Certificate` call. Code review caught it before any script execution;
   it was replaced with PowerShell backtick continuation.
2. The host execution policy blocked the first validation attempt before the
   script loaded. No policy or trust setting changed. Instructions now use a
   process-scoped `powershell.exe -ExecutionPolicy Bypass`; it does not change
   machine/user policy.
3. Windows PowerShell 5 evaluated the default parameter before `$PSScriptRoot`
   was available, producing an empty `Join-Path` input. Path resolution was
   moved after the parameter block. The corrected validation then passed.

### Trust-store mutation boundary

The CA is not installed automatically. The authorized user must review
`WINDOWS-TRUST.md`, validate the fingerprint, and then explicitly run the helper
with `-Install`. This affects only `Cert:\CurrentUser\Root`. Removal is manual
and gated by exact subject/fingerprint verification.

Step 12C2 is complete. The next infrastructure boundary is Step 12D Ingress
apply; it requires separate approval.

### User trust-store installation confirmation

The user first ran the validation-only helper from Windows Command Prompt using
the absolute repository path. It returned:

```text
SHA-1 thumbprint: 54F86061294D752132D234EA3CC1FAD4D73C9F99
SHA-256: 735C690E91323B973F2069BC1BEB23A5CD4B96F376953D8D56D37196DF8EDE18
FingerprintMatch: True
Validation only: the Windows certificate store was not changed.
```

The user then explicitly ran the same helper with `-Install`. The fingerprint
again matched and the helper reported:

```text
Installed the verified CA certificate in Cert:\CurrentUser\Root.
Close and reopen browsers before testing the monitoring URLs.
```

This confirms trust for the user's Windows account only. It does not install
the CA for every computer or Windows user. Each separately authorized team
device/user must validate and install the same public CA independently.

The first attempt had been made from `cmd.exe` with a PowerShell backtick split
across lines. CMD treated the tokens as separate commands and changed nothing.
The correction was a single-line `powershell.exe -File` invocation with the
absolute `E:\...\install-ca-current-user.ps1` path.
