# Step 7R1 — Prepare and validate Grafana retry settings

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: explicitly approved by the user
- Result: completed successfully
- Scope: local files and offline Helm validation only
- Kubernetes changes: none
- OpenStack changes: none
- Existing application changes: none

## Purpose

Step 7 failed because Grafana 13.2.2 was repeatedly restarted by its liveness probe while it was still completing first-run SQLite migrations. Step 7R1 prepares a safer retry without installing anything.

The approved correction was:

1. increase only Grafana's CPU limit from `500m` to `1` CPU;
2. keep its CPU request at `100m`;
3. add a startup probe against `/api/health`;
4. retain the existing liveness and readiness probes;
5. validate the pinned chart locally;
6. use a proposed 25-minute Helm timeout only in the later, separately approved retry.

## Initial inspection

Working directory:

```text
E:\BUET\4-1\Sessional\Capstone\monitoring\BUET-PaaS
```

Commands:

```powershell
Get-Content -Raw '.\monitoring\prometheus\values.yaml'
Get-Content '.\implementation of monitoring.md' -Tail 80
git status --short --branch
git ls-files --modified
```

Relevant initial state:

```text
branch: monitoring
Grafana CPU limit: 500m
Grafana startup probe: absent
tracked modified files: none
monitoring implementation files: untracked
```

No `ssh`, `kubectl`, Helm install/upgrade, or OpenStack command was executed during this step.

## Approved local values change

File changed:

```text
monitoring/prometheus/values.yaml
```

Previous section:

```yaml
grafana:
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 500m
      memory: 512Mi
```

New section:

```yaml
grafana:
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 1
      memory: 512Mi
  # Grafana 13 performs lengthy first-run SQLite migrations. Give that initial
  # startup enough time to finish before the normal liveness probe takes over.
  startupProbe:
    httpGet:
      path: /api/health
      port: grafana
    initialDelaySeconds: 10
    periodSeconds: 10
    timeoutSeconds: 5
    failureThreshold: 90
```

No other values were changed.

The probe permits approximately 15 minutes for first startup before Kubernetes restarts Grafana. When it succeeds, the chart's normal liveness and readiness probes take over.

## Pinned-chart lint and full render

Inputs:

```text
Helm: v3.22.0+g144ca65
Chart: kube-prometheus-stack 91.4.1
Chart archive SHA-256: 1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb
Kubernetes render target: 1.36.2
```

Commands:

```powershell
$helmPath = 'C:\Users\USER\AppData\Local\Temp\buet-paas-monitoring-step4\windows-amd64\helm.exe'
$chartPath = 'C:\Users\USER\AppData\Local\Temp\buet-paas-monitoring-step4\render-final\kube-prometheus-stack-91.4.1.tgz'

& $helmPath lint $chartPath `
  --values '.\monitoring\prometheus\values.yaml' `
  --kube-version '1.36.2'

& $helmPath template monitoring-stack $chartPath `
  --namespace monitoring `
  --values '.\monitoring\prometheus\values.yaml' `
  --kube-version '1.36.2' `
  --include-crds
```

Output:

```text
==> Linting ...\kube-prometheus-stack-91.4.1.tgz
1 chart(s) linted, 0 chart(s) failed
values SHA-256: c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b
initial full-render SHA-256: e59ffc62217b1b11043a4872d95a86d3704a32918b02ea5f696601bfb2c04e75
```

## Security correction during validation

The first full rendered manifest was written under the repository validation directory. Inspection showed that Helm's Grafana chart generated a random initial admin password in the rendered Secret. This was only locally generated data and was never sent to Kubernetes, but it should not be retained in repository evidence.

Correction:

```text
monitoring/validation/step-7r1-20260924/rendered.yaml
```

was immediately deleted. The deletion was limited to the new file created in this step. The random render-time value is not a cluster credential and was never installed.

The full-render comparison also showed a changed Grafana Secret checksum. That checksum change was caused by the chart's random password generation, not by an additional configuration change.

## Safe focused render

To preserve useful evidence without Secret data, only the Grafana Deployment template was rendered. A fixed validation-only password was supplied to make chart evaluation deterministic, but the focused Deployment output contains only Kubernetes `secretKeyRef` references and does not contain that value.

Command:

```powershell
& $helmPath template monitoring-stack $chartPath `
  --namespace monitoring `
  --values '.\monitoring\prometheus\values.yaml' `
  --kube-version '1.36.2' `
  --set-string 'grafana.adminPassword=STEP7R1-VALIDATION-ONLY-NOT-A-CLUSTER-CREDENTIAL' `
  --show-only 'charts/grafana/templates/deployment.yaml'
```

Evidence file:

```text
monitoring/validation/step-7r1-20260924/grafana-deployment-validation.yaml
SHA-256: f9436be302bac7a1877121cac328e8ff0d38beb8278c80cbcaf877977995180d
```

Rendered Grafana container settings:

```yaml
startupProbe:
  failureThreshold: 90
  httpGet:
    path: /api/health
    port: grafana
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
livenessProbe:
  failureThreshold: 10
  httpGet:
    path: /api/health
    port: grafana
  initialDelaySeconds: 60
  timeoutSeconds: 30
readinessProbe:
  httpGet:
    path: /api/health
    port: grafana
resources:
  limits:
    cpu: 1
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

Credential-content check:

```text
Embedded credential data or validation placeholder: none
Unsafe full rendered manifest: removed
```

## Validation-check error and correction

The first credential check searched for `GF_SECURITY_ADMIN_PASSWORD` and `admin-password`. It returned a failure because those names legitimately appear in Deployment `secretKeyRef` fields.

This was a read-only assertion error; it did not change any file or system. The corrected check searched for embedded `data:`, `stringData:`, or the literal validation-only value. It passed and confirmed that the focused evidence contains references only, not credential values.

## Final Step 7R1 result

```text
values change: completed
Helm lint: passed (1 chart, 0 failures)
focused Grafana render: passed
startup probe rendered: yes
normal liveness/readiness retained: yes
Grafana CPU request: 100m (unchanged)
Grafana CPU limit: 1
credential values in retained evidence: none
Kubernetes/OpenStack contacted: no
cluster changes: none
existing application changes: none
```

## Proposed Step 7R2 — not yet authorized

Step 7R2 would be the actual cluster retry. It must not start without explicit user permission. Its proposed sequence is:

1. run read-only cluster health and residue checks;
2. confirm that no admission webhook configuration points to the orphan Step 7 Secret;
3. remove only that verified orphan Secret if required for a clean retry;
4. transfer the updated values file and verify its SHA-256 hash remotely;
5. render/lint remotely with the already pinned chart;
6. retry the atomic Helm installation with `--wait --timeout 25m`;
7. monitor Grafana migration/startup and all stack workloads;
8. verify rollback state again if the retry fails.

The 10 empty Prometheus Operator CRDs retained by Step 7 are expected Helm CRD behavior and do not need to be deleted before retry.

