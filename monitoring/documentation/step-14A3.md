# Step 14A3 - Prepare and offline-verify five new VM scrape targets

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 14A3 - prepare and offline verify all five new VM scrape targets`
- Result: **complete**
- Repository mutation: scrape overlay updated
- Live Helm/Kubernetes/Prometheus mutation: none

## Prepared configuration

The existing job `standalone-node-exporters` remains a single scrape job with
30-second interval, 10-second timeout, HTTP scheme, `/metrics` path, and stable
labels. Its already-live frontend target was retained and five verified private
targets were added:

```text
instance       service          target
frontend-vm    frontend         192.168.128.15:9100   (existing)
database-vm    database         192.168.128.92:9100   (new)
registry-vm-2  registry         192.168.128.152:9100  (new)
k3s-user       platform-admin   192.168.128.151:9100  (new)
backend-vm     backend          192.168.128.131:9100  (new)
sonarqube      code-quality     192.168.128.33:9100   (new)
```

Every static config also has:

```yaml
environment: buet-paas
deployment_type: standalone-vm
```

File: `monitoring/external-vms/scrape-values.yaml`

```text
previous SHA-256: a5b4c936232457e957f1c2b2fab3dfc3ec1799c9d21df0490fbc865caeef1a32
prepared SHA-256: 24c43588815d1b390036e2ec0ab53fab66cc7fd5e4b18b486233893ac9d40248
base values SHA:  c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b
```

No credential, token, kubeconfig, or public/floating IP was added.

## Pinned offline validation

The exact chart was pulled into isolated directory
`/tmp/buet-paas-step14a3` on `k3s-user`:

```text
chart:          kube-prometheus-stack 91.4.1
appVersion:     v0.94.0
OCI digest:     sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
archive SHA:    1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb
Helm:           v3.22.0
Kube version:   1.36.2
```

Lint command used both files in their required order: base values first,
scrape overlay second.

```text
1 chart(s) linted, 0 chart(s) failed
```

Focused rendering used only
`templates/prometheus/additionalScrapeConfigs.yaml`. The rendered Secret was
decoded offline and contained:

```text
jobs:            1
targets:         6
unique targets:  6
instance labels: 6
```

The decoded configuration exactly contained the six targets and labels listed
above. Evidence hashes:

```text
rendered manifest: 17ced4b61d54b99ac4fef527eb78674d394db8d4d015336c5c7c2f3b53d6c78e
decoded config:    e9d6136882a1a5b79f879e092dc03b758f0ab7d68a9219b2ab4d55c110dcc0e5
```

## Corrected non-mutating issues

The first decoder included the YAML quote characters and returned `base64:
invalid input` after the manifest had rendered successfully. A second sed
decoder was intercepted by local PowerShell regex parsing before remote
execution. A quote-safe character-class extraction then decoded the same
rendered payload successfully and produced all expected counts. Neither failed
attempt contacted the Kubernetes API or changed live state.

## Proof that live monitoring was not changed

After preparation:

```text
Helm release:                    monitoring-stack revision 5, deployed
Prometheus:                      Ready
live standalone exporter count: 1
live total count(up):            26
Kubernetes nodes:               4/4 Ready
```

Therefore the repository describes six targets, while live Prometheus still
scrapes only the previously applied frontend target.

## Cleanup and rollback

Before cleanup, `/tmp/buet-paas-step14a3` was resolved and its two input files,
chart/archive, rendered manifest, and decoded output were enumerated. Only that
exact directory was removed and absence was confirmed.

Because nothing was applied, rollback is repository-only: remove the five new
static configs from `monitoring/external-vms/scrape-values.yaml`, restoring its
previous hash. Do not perform that rollback unless separately requested.

## Next permission boundary

Step 14A4 may run an atomic Helm upgrade using the base values, scrape overlay,
and existing browser-access overlay, then verify all six standalone targets UP,
all previous targets healthy, and application regressions clean. It requires
separate explicit approval.

