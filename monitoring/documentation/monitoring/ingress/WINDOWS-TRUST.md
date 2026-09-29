# Windows trust instructions for the monitoring internal CA

## Security boundary

The file `certs/buet-paas-monitoring-ca.crt` is the CA **public certificate**.
It is safe to distribute to authorized BUET-PaaS monitoring users.

Never export or distribute:

```text
monitoring-internal-ca / ca.key
monitoring-public-tls / tls.key
Prometheus or Alertmanager password values
```

Installing a CA means the device will trust certificates issued by that CA.
Only install it after verifying the fingerprint below from a trusted copy of
this repository.

## Expected identity

```text
Subject: CN=BUET-PaaS Monitoring Internal CA, O=BUET-PaaS
Issuer:  CN=BUET-PaaS Monitoring Internal CA, O=BUET-PaaS
Valid:   2026-09-24 11:40:57 UTC through 2031-09-23 11:40:57 UTC

SHA-256:
73:5C:69:0E:91:32:3B:97:3F:20:69:BC:1B:EB:23:A5:CD:4B:96:F3:76:95:3D:8D:56:D3:71:96:DF:8E:DE:18
```

## Step 1 - Validate only

Open PowerShell in the repository root and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\monitoring\ingress\scripts\install-ca-current-user.ps1
```

`Bypass` applies only to this child PowerShell process; it does not change the
machine or user execution-policy setting. Review the local script before use.

Expected final messages:

```text
FingerprintMatch: True
Validation only: the Windows certificate store was not changed.
```

Stop if the fingerprint does not match. Do not bypass the script check.

## Step 2 - Install for only the current Windows user

This command changes the current user's trusted-root store. It does not require
LocalMachine trust and should not be run on an unauthorized/shared device.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\monitoring\ingress\scripts\install-ca-current-user.ps1 `
  -Install
```

Expected result:

```text
Installed the verified CA certificate in Cert:\CurrentUser\Root.
```

Close every Chrome/Edge window and reopen the browser. Chrome and Edge normally
use the Windows certificate store. Firefox may require importing the same
public `.crt` under Settings -> Privacy & Security -> Certificates -> View
Certificates -> Authorities, depending on organization policy and Firefox
configuration.

Installing the CA does not make the monitoring links active. Step 12D must
separately apply the Ingress routes.

## Verification after Step 12D

Connect OpenConnect VPN, then open:

```text
https://grafana.monitoring.192.168.64.121.sslip.io/
https://prometheus.monitoring.192.168.64.121.sslip.io/
https://alerts.monitoring.192.168.64.121.sslip.io/
```

The browser certificate chain must end at `BUET-PaaS Monitoring Internal CA`
without a certificate warning.

## Rollback / remove trust

First locate the exact certificate by subject and fingerprint:

```powershell
Get-ChildItem Cert:\CurrentUser\Root |
  Where-Object Subject -eq 'O=BUET-PaaS, CN=BUET-PaaS Monitoring Internal CA' |
  Select-Object Subject, Thumbprint, NotAfter
```

Do not remove anything unless both subject and fingerprint match the validated
certificate. Removal is intentionally not automated in this repository.

To remove it manually, open `certmgr.msc`, navigate to Trusted Root
Certification Authorities -> Certificates, locate the exact
`BUET-PaaS Monitoring Internal CA`, verify its fingerprint, and delete only that
certificate.
