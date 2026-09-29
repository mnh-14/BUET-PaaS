# BUET-PaaS monitoring

This directory contains the declarative configuration and validation evidence for the BUET-PaaS monitoring MVP.

## Current scope

- Kubernetes monitoring with `kube-prometheus-stack` chart version `91.4.1`
- Prometheus, Alertmanager, Grafana, kube-state-metrics, and node-exporter
- monitoring services remain private `ClusterIP`; authenticated HTTPS browser
  routes are active through the existing VPN-reachable shared Traefik ingress
- two-day Prometheus retention with ephemeral storage for the initial measurement period
- the standalone `frontend-vm` node_exporter target is active
- node_exporter is installed and control-plane reachable on all six standalone
  VMs. All six are now scraped and UP in Prometheus.
- Blackbox endpoint/TLS preflight complete for frontend, backend, deployer,
  Harbor, and SonarQube
- secure Blackbox chart 11.18.0 configuration is prepared and offline-verified;
  the pinned exporter and all five planned service probes are live and healthy
- the BUET-PaaS Monitoring Overview dashboard is prepared as provisioned JSON,
  renders to one sidecar-selected ConfigMap, and passes offline PromQL checks
- no credentials or kubeconfig data in the repository

The cluster installation and browser-access configuration remain declarative
and separately auditable. The reviewed files under `ingress/` were applied in
Step 12D after explicit approval; raw monitoring ports remain unexposed.

## Layout

```text
monitoring/
├── baseline/                      # sanitized Step 2 before-state evidence
├── prometheus/
│   └── values.yaml                # pinned chart overrides
└── scripts/
    └── render-kube-prometheus-stack.ps1
```

Rendered manifests and downloaded chart archives are verification artifacts. Keep them in a temporary/output directory outside the repository unless a later approved step explicitly changes that policy.

The `blackbox/` directory contains the public Harbor CA, base values, staged
target overlays, NetworkPolicy, and repeatable offline/live-read-only checks.

The `dashboards/` directory contains the provisioned BUET-PaaS overview JSON,
its deterministic Kustomize ConfigMap generator, and the offline validator.
The live dashboard is at
`https://grafana.monitoring.192.168.64.121.sslip.io/d/buet-paas-overview/buet-paas-monitoring-overview`.
Grafana's current domain enforcement redirects the dashboard sidecar's
localhost reload request; Step 16B used the configured Host header for a
verified reload. Fix that sidecar reload setting before relying on automatic
reload of later dashboard updates.

The `alerts/` directory contains four live MVP alert rules, an offline
validator, synthetic lifecycle tests, the maintenance policy, and the UI-only
operator runbook. Step 16D applied the rules; Step 16E recorded the team's
UI-only notification decision.

Project Markdown was gathered under [`documentation/`](documentation/INDEX.md)
for review and publishing from the `monitoring` branch. The admin integration
proposals and step records are indexed there; they have not been implemented
or deployed merely by being documented.

## Local validation

Use Helm `3.22.0` or a later compatible Helm 3 release. The script never runs `helm install`, `helm upgrade`, or `kubectl`.

```powershell
.\monitoring\scripts\render-kube-prometheus-stack.ps1 `
  -HelmPath 'C:\path\to\helm.exe' `
  -OutputDirectory "$env:TEMP\buet-paas-monitoring-render"
```

The script performs:

1. `helm pull` of the exact OCI chart version;
2. `helm show chart` and `helm show values` capture;
3. `helm lint` with the BUET-PaaS values;
4. `helm template` for namespace `monitoring` with Kubernetes version `1.36.2`;
5. SHA-256 hashing of the values file, chart archive, and rendered manifest.

It does not contact the Kubernetes API.

## Security rules

- Never commit Grafana passwords, Alertmanager receiver secrets, kubeconfigs, bearer tokens, private keys, or rendered Kubernetes Secret values.
- Grafana, Prometheus, and Alertmanager are reachable only through the
  VPN-facing authenticated HTTPS ingress; raw service ports stay private.
- node-exporter requires host visibility by design. Review its rendered DaemonSet before every chart-version change.
- The generic scheduler, controller-manager, etcd, and kube-proxy monitors are disabled for this k3s MVP because those endpoints are not discoverable as normal cluster Services and the k3s process already exposes unified metrics.

## Installation status

```text
Cluster installation: COMPLETE (Helm release monitoring-stack)
Namespace creation:   COMPLETE (monitoring)
Browser ingress:      COMPLETE (Helm revision 5 plus Traefik middleware)
VM exporters local:   6 COMPLETE
VM exporter network:  6 COMPLETE (restricted control-plane paths verified)
VM scrape overlay:    6 PREPARED and offline-verified
VM exporters scraped: 6 COMPLETE and UP (Helm revision 6)
Blackbox preflight:    COMPLETE
Blackbox config:       PREPARED and offline-verified
Blackbox live install: COMPLETE (separate Helm revision 9)
Blackbox probes:       5/5 COMPLETE and UP
Prometheus targets:    36 UP, zero DOWN
Day 2 monitoring:      COMPLETE
Day 3 dashboard code:  COMPLETE
Dashboard live apply:  COMPLETE (16 panels provisioned)
MVP alert-rule code:   PREPARED and offline-verified (4 rules)
Alert rules live:      COMPLETE (4 healthy, inactive)
Notification receiver: UI-only review chosen; Alertmanager route is null
Three-day MVP:        COMPLETE as operator-facing monitoring
Next:                 separate post-MVP hardening gates in documentation/step-13-plan.md
```
