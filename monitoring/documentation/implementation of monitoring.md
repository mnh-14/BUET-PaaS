# Implementation of Monitoring

## Purpose

This file is the authoritative execution journal for adding the BUET-PaaS monitoring MVP. It records the plan, approval gates, commands, outputs, validation evidence, mistakes, corrections, and rollback information.

The source plan reviewed for this work is:

`C:\Users\USER\Downloads\BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md`

The source plan is reference material. Commands written in it are not executed automatically. The user's current request, explicit permission at each gate, observed infrastructure state, and safety checks control execution.

## Non-negotiable rules

1. Execute only one approved step at a time.
2. Show the result of the current step before requesting permission for the next step.
3. Never combine approval for multiple mutating steps.
4. Day-0 and preflight work is read-only.
5. Do not edit existing BUET-PaaS application files or workloads.
6. New repository artifacts go under a new `monitoring/` directory unless a later approved step explicitly requires otherwise.
7. Never delete, restart, scale, or reconfigure an existing workload as part of monitoring setup.
8. Pin Helm chart, container, and exporter versions before installation. Do not deploy floating `latest` versions.
9. Render and inspect Helm output before applying it to the cluster.
10. Capture before/after state and compare existing workloads after every cluster mutation.
11. Stop immediately if an existing application becomes unhealthy.
12. Do not expose Grafana, Prometheus, Alertmanager, Blackbox Exporter, or node_exporter publicly. Use the private network, `kubectl port-forward`, or an SSH tunnel.
13. Never record passwords, tokens, private keys, kubeconfig contents, or secret values in this file.
14. A rollback command is documented before its corresponding mutation is executed.
15. No Git commit, push, merge, or remote change is made without separate permission.

## Existing-code constraints discovered during review

- The frontend/FastAPI path deploys applications with local Docker.
- The separate Flask deployer manages Kubernetes resources but is not integrated with FastAPI.
- The deployer ingress is currently unauthenticated and has broad cluster permissions. Monitoring must not depend on or expand that exposure.
- MongoDB, application secrets, and deployment behavior are outside this monitoring MVP and must remain unchanged.
- The repository currently has no `monitoring/` implementation directory.
- Core monitoring will use its own Kubernetes namespace named `monitoring`.
- Headlamp, Loki, Wazuh, Tempo, OpenTelemetry, custom application metrics, and application log aggregation are explicitly deferred.

## Planned repository additions

No files below exist yet. They will be created only in approved steps.

```text
monitoring/
├── README.md
├── baseline/
│   └── <UTC timestamp>/
├── prometheus/
│   └── values.yaml
├── external-vms/
│   ├── scrape-config.yaml
│   └── node-exporter.service
├── blackbox/
│   ├── values.yaml
│   └── probes.yaml
├── dashboards/
│   └── buet-paas-overview.json
├── alerts/
│   └── basic-alerts.yaml
└── docs/
    └── troubleshooting.md
```

Generated baseline output may contain infrastructure metadata. Before committing any baseline file, it must be inspected for secrets, tokens, certificates, kubeconfig data, or sensitive annotations. Sensitive output remains local and ignored.

## Sequential implementation plan and permission gates

### Step 0 — Local safety preflight

Type: read-only.

Actions:

- Confirm repository root, branch, and clean/dirty state.
- Inventory existing files under any `monitoring/` path.
- Record the current commit ID.
- Confirm SSH key path without copying or displaying private-key content.
- Check availability of `ssh`, `kubectl`, and `helm` locally and/or on the intended admin host.
- Decide whether cluster commands will run from `k3s-user` or `k3s-control-01` based on actual working access.

Success criteria:

- Exact execution host is known.
- Working tree state and commit ID are recorded.
- No file or cluster state changed.

Next gate: obtain permission for Step 1.

### Step 1 — Establish read-only cluster access

Type: read-only remote access.

Actions:

- Connect using the confirmed username, address, and key.
- Run identity-only checks: hostname, user, date, OS, and tool versions.
- Run `kubectl auth can-i` checks needed for inventory and later monitoring installation.
- Do not install Helm or change kubeconfig in this step.

Success criteria:

- SSH succeeds.
- The intended cluster/context is identified.
- Required read access is confirmed.

Next gate: show output, then obtain permission for Step 2.

### Step 2 — Day-0 cluster baseline

Type: read-only cluster inspection.

Actions:

- Capture nodes, namespaces, pods, deployments, StatefulSets, DaemonSets, services, jobs, PVCs, StorageClasses, ingresses, Helm releases, cluster info, versions, and recent events.
- Capture node descriptions and pressure/capacity information.
- Attempt `kubectl top nodes`; record absence of Metrics Server as informational rather than installing it.
- Save command output under a timestamped local baseline directory.
- Redact or exclude sensitive data before considering any Git commit.

Success criteria:

- A complete before-install snapshot exists.
- All existing unhealthy workloads are identified as pre-existing.
- No cluster state changed.

Next gate: present the baseline summary and capacity decision, then obtain permission for Step 3.

### Step 3 — Capacity and compatibility decision

Type: analysis only.

Actions:

- Calculate whether the four-node k3s cluster has enough allocatable CPU, memory, and storage for the monitoring MVP.
- Identify the active StorageClass and whether Prometheus persistence is viable.
- Verify Kubernetes/k3s, Helm, and API compatibility with a pinned `kube-prometheus-stack` chart version using official release metadata.
- Propose conservative CPU/memory requests and limits.
- Decide whether initial Prometheus storage is ephemeral or persistent. Persistence is not enabled without evidence and permission.

Success criteria:

- A documented go/no-go recommendation exists.
- Exact versions and resource settings are selected.

Next gate: obtain permission to create local monitoring files in Step 4.

### Step 4 — Create local monitoring configuration only

Type: local repository additions; no cluster mutation.

Actions:

- Create the new `monitoring/` directory structure.
- Add a pinned and resource-bounded `prometheus/values.yaml`.
- Keep Grafana, Prometheus, Alertmanager, kube-state-metrics, and node-exporter internal-only.
- Configure two-day initial retention.
- Do not add standalone VM targets or Blackbox probes yet.
- Validate YAML and render the pinned Helm chart locally.
- Review rendered RBAC, DaemonSets, host mounts, services, resource requests, selectors, and CRDs.
- Record `git diff`, validation results, and file hashes.

Rollback:

- Remove only the newly created, explicitly listed monitoring files if permission is given.

Success criteria:

- Local configuration validates and renders successfully.
- Existing tracked files remain unchanged.
- No cluster resource exists yet.

Next gate: show the exact diff and obtain permission for Step 5.

### Step 5 — Create the monitoring namespace

Type: first cluster mutation.

Actions:

- Reconfirm that `monitoring` does not already exist.
- Create only the `monitoring` namespace.
- Record its YAML metadata without secret data.
- Re-run a focused existing-workload health check.

Rollback prepared in advance:

```bash
kubectl delete namespace monitoring
```

The rollback is not executed unless explicitly approved and confirmed safe.

Success criteria:

- Only the new namespace was added.
- Existing workloads are unchanged.

Next gate: obtain permission for Step 6.

### Step 6 — Prepare the pinned Helm source

Type: Helm client configuration and network access; no workload installation.

Actions:

- Add/update the official Prometheus Community chart repository.
- Verify chart provenance/metadata where available.
- confirm the selected exact chart version.
- Render again using the committed values.
- Save sanitized render/validation evidence.

Success criteria:

- The exact chart version is resolvable.
- Rendered resources match the reviewed plan.
- No monitoring workload has been installed.

Next gate: obtain permission for Step 7.

### Step 7 — Install kube-prometheus-stack

Type: cluster mutation.

Actions:

- Run one pinned `helm upgrade --install` command with `--atomic`, `--wait`, and an explicit timeout if compatibility permits.
- Record Helm output and release status.
- Verify Pods, StatefulSets, Deployments, DaemonSets, Services, PVCs, CRDs, targets, and events.

Rollback prepared in advance:

```bash
helm uninstall monitoring -n monitoring
```

Namespace deletion is a separate action and requires separate permission.

Success criteria:

- Core monitoring resources become Ready.
- node-exporter runs on the expected four k3s nodes.
- No unexpected LoadBalancer/NodePort/public service exists.

Next gate: do not continue until Step 8 comparison is complete.

### Step 8 — Mandatory post-install regression comparison

Type: read-only validation.

Actions:

- Capture the same important workload/resource/event views as Day 0.
- Compare existing application Pods, Deployments, DaemonSets, Services, Jobs, and events against the baseline.
- Attribute all expected additions to the `monitoring` release.
- Stop if any existing workload regressed.

Success criteria:

- Existing BUET-PaaS workloads remain healthy.
- Only expected monitoring resources were added.

Next gate: present comparison; obtain permission for Step 9.

### Step 9 — Verify UIs and built-in metrics privately

Type: temporary local access/read-only validation.

Actions:

- Port-forward Grafana, Prometheus, and Alertmanager one at a time.
- Retrieve the Grafana password for immediate use without writing it to this journal.
- Verify Prometheus targets, built-in Kubernetes dashboards, alert state, node metrics, kube-state metrics, and DaemonSet coverage.
- Terminate port-forward processes after verification.

Success criteria:

- All three UIs work through private/temporary access.
- Core targets are healthy or documented with a known reason.

Next gate: obtain separate permission for each standalone VM.

### Step 10 — Add standalone VM node_exporter one VM at a time

Type: remote VM mutation; six independent substeps.

Order:

1. `frontend-vm` — `192.168.128.15`
2. `database-vm` — `192.168.128.92`
3. `registry-vm-2` — `192.168.128.152`
4. `k3s-user` — `192.168.128.151`
5. `backend-vm` — `192.168.128.131`, only when intentionally active
6. `sonarqube` — `192.168.128.33`, only when intentionally active

For each VM, obtain fresh permission and then:

- Record baseline service/port/application health.
- Verify CPU architecture and OS.
- Download a pinned official node_exporter archive and verify its published checksum.
- Install a least-privilege system user, binary, and version-controlled systemd unit.
- Bind/restrict access to the private monitoring path; never open TCP 9100 to `0.0.0.0/0` in OpenStack security groups.
- Verify local metrics, private reachability from Prometheus, application health, and Prometheus target status.
- Stop before touching the next VM.

Rollback prepared per VM:

- Stop and disable only `node_exporter`.
- Remove only its installed unit and binary after explicit approval.
- Revert only the security-group rule created for that VM, if any.

### Step 11 — Add external VM scrape configuration

Type: local configuration plus controlled Helm upgrade.

Actions:

- Add only verified, reachable private-IP node_exporter targets.
- Give every target stable `instance`, `service`, and `environment` labels.
- Exclude intentionally inactive VMs until they are expected online.
- Render and review the Helm change before applying it.
- Verify each target and repeat the application regression check.

Success criteria:

- Every configured VM target is `UP`.
- No public exporter exposure exists.

Next gate: obtain permission for Step 12.

### Step 12 — Install and configure Blackbox Exporter

Type: local configuration and cluster mutation.

Actions:

- Discover and manually verify the actual URL, port, protocol, redirect behavior, and health path for Frontend, Backend, Deployer, Harbor, and SonarQube.
- Do not guess endpoints.
- Add a pinned Blackbox Exporter chart/config.
- Render and inspect it before installation.
- Install it internally in `monitoring`.
- Add one probe target at a time and verify `probe_success` before adding the next.
- Keep intentionally stopped services out of firing alerts or place them under documented maintenance silence.

Rollback:

- Remove only the Blackbox Helm release/config introduced by this step after explicit permission.

Success criteria:

- Every active configured service has a verified probe.
- No probe creates false permanent noise for intentionally stopped services.

Next gate: obtain permission for Step 13.

### Step 13 — Provision the BUET-PaaS overview dashboard

Type: version-controlled dashboard addition and controlled deployment.

Actions:

- Create dashboard JSON from verified metric names and labels, not assumptions.
- Provision it through the chart sidecar/ConfigMap rather than undocumented manual UI-only state.
- Include platform status, cluster resources, VM resources, and Kubernetes workload state.
- Validate every panel for a meaningful value and appropriate unit.

Success criteria:

- Dashboard is reproducible from Git.
- No panel is silently empty because of an incorrect label/query.

Next gate: obtain permission for Step 14.

### Step 14 — Add a small, tested alert set

Type: version-controlled PrometheusRule addition and controlled deployment.

Actions:

- Add only alerts backed by existing metrics: node readiness, external VM down, verified service probes, disk pressure/low space, crash looping, unavailable deployment, failed build Job, and target down.
- Include `for` durations, severity, service/instance labels, and actionable annotations.
- Validate rule syntax before applying.
- Test one safe alert path at a time without disrupting production workloads.
- Document Alertmanager silence procedure for planned maintenance.

Success criteria:

- Rules load without errors.
- A safe test alert transitions pending → firing → resolved as expected.
- Known maintenance targets do not generate uncontrolled noise.

Next gate: obtain permission for Step 15.

### Step 15 — Final validation and handoff

Type: read-only validation and documentation.

Actions:

- Run final cluster/workload regression checks.
- Record Helm releases, target status, alert status, dashboard availability, resource usage, and storage growth.
- Complete `monitoring/README.md` and troubleshooting instructions.
- Decide whether Prometheus persistence is justified from measured data; implementation would be a later separately approved step.
- Keep Headlamp as an optional, separately approved enhancement.

Success criteria:

- Monitoring is reproducible, private, documented, and does not regress existing workloads.
- Rollback scope and remaining work are explicit.

## Permission protocol

At the end of every step, report:

```text
Step:
Permission received:
Commands executed:
Exit status:
Important output:
Files/resources changed:
Validation result:
Rollback status:
Unexpected behavior:
Next proposed step:
```

The next step starts only after the user explicitly approves it.

## Execution journal

### Journal entry 000 — Plan preparation

- Timestamp: `2026-09-23 20:34:48 +06:00`
- Permission basis: user requested inspection and planning, plus creation of this audit Markdown file.
- Scope: local read-only inspection plus creation of this new file.
- Existing files modified: none.
- Cluster/VM mutations: none.

Commands and results:

```powershell
Get-Content -Raw -LiteralPath 'C:\Users\USER\Downloads\BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md'
```

Result: completed successfully; the source plan was read as reference material.

```powershell
Test-Path -LiteralPath '.\implementation of monitoring.md'
```

Output before creation:

```text
False
```

```powershell
git status --short --branch
```

Output before creation:

```text
## monitoring
```

Interpretation: the repository was clean and already on branch `monitoring` before this journal was created.

Decision: no implementation step has been executed. Await explicit permission for **Step 0 — Local safety preflight**.

### Journal entry 001 — Step 0: Local safety preflight

- Timestamp: `2026-09-23 20:42:58 +06:00`
- Permission received: `Approve Step 0`
- Step type: local read-only inspection.
- Existing files modified by the checks: none.
- Cluster/VM contact: none.
- Cluster/VM mutations: none.

#### Repository checkpoint

Command:

```powershell
hostname
whoami
Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short --branch
git diff --check
```

Output:

```text
DESKTOP-B76RJ77
desktop-b76rj77\codexsandboxoffline
2026-09-23 20:42:58 +06:00
E:/BUET/4-1/Sessional/Capstone/monitoring/BUET-PaaS
monitoring
3a4fc9417f4efc74a18d52559586515bae4bbc76
## monitoring
?? "implementation of monitoring.md"
```

`git diff --check` produced no output, meaning no whitespace errors were detected. The only worktree addition is this journal file.

#### Existing monitoring-path inventory

Command:

```powershell
if (Test-Path -LiteralPath '.\monitoring') {
  Get-ChildItem -LiteralPath '.\monitoring' -Recurse -Force
} else {
  Write-Output 'repo monitoring directory: absent'
}
```

Output:

```text
repo monitoring directory: absent
```

Conclusion: the future repository monitoring implementation can be isolated in a new directory without overwriting an existing monitoring directory.

#### Reference-file and journal metadata

Command:

```powershell
Get-Item -LiteralPath 'C:\Users\USER\Downloads\BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md'
Get-Item -LiteralPath '.\implementation of monitoring.md'
```

Output:

```text
C:\Users\USER\Downloads\BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md
Length: 34670 bytes
LastWriteTime: 2026-09-23 13:39:24

E:\BUET\4-1\Sessional\Capstone\monitoring\BUET-PaaS\implementation of monitoring.md
Length before this entry: 16791 bytes
LastWriteTime before this entry: 2026-09-23 20:37:16
```

#### SSH key verification

The private-key content was not opened or printed.

Metadata command:

```powershell
Get-Item -LiteralPath 'C:\Users\USER\Downloads\mykey.pem' |
  Select-Object FullName,Length,LastWriteTime
```

Output:

```text
C:\Users\USER\Downloads\mykey.pem
Length: 1676 bytes
LastWriteTime: 2026-09-23 13:35:08
```

The first ACL check ran under the sandbox identity:

```powershell
icacls 'C:\Users\USER\Downloads\mykey.pem'
```

Output:

```text
C:\Users\USER\Downloads\mykey.pem: Access is denied.
Successfully processed 0 files; Failed processing 1 files
```

Cause: earlier SSH hardening intentionally removed access for the sandbox group. This was not a key-file defect. The check was repeated read-only under the user's Windows identity after approval escalation.

Corrected command:

```powershell
icacls 'C:\Users\USER\Downloads\mykey.pem'
```

Corrected output:

```text
C:\Users\USER\Downloads\mykey.pem DESKTOP-B76RJ77\USER:(R)
Successfully processed 1 files; Failed processing 0 files
```

Conclusion: the key exists and has the required restricted read ACL. No ACL was changed.

#### Local tool availability

Commands:

```powershell
Get-Command ssh
Get-Command kubectl
Get-Command helm
ssh -V
kubectl version --client=true -o yaml
```

Output:

```text
ssh=C:\WINDOWS\System32\OpenSSH\ssh.exe
kubectl=C:\Program Files\Docker\Docker\resources\bin\kubectl.exe
helm=NOT_FOUND
OpenSSH_for_Windows_9.5p2, LibreSSL 3.8.2
kubectl client gitVersion: v1.34.1
kubectl platform: windows/amd64
kustomizeVersion: v5.7.1
```

Conclusion: local SSH and kubectl clients exist. Helm is not installed locally.

#### Local Kubernetes and SSH configuration presence

The initial check attempted to derive a home directory using:

```powershell
[Environment]::GetFolderPath('UserProfile')
```

It returned an empty path inside the sandbox, causing `Join-Path` and subsequent `Test-Path` calls to fail. This was a diagnostic-command mistake only; it changed nothing.

Corrected commands used explicit, already-known user paths:

```powershell
Test-Path -LiteralPath 'C:\Users\USER\.kube\config'
Test-Path -LiteralPath 'C:\Users\USER\.ssh\config'
Test-Path -LiteralPath 'C:\Users\USER\.ssh\known_hosts'
```

Output:

```text
DEFAULT_KUBECONFIG_EXISTS=False
SSH_CONFIG_EXISTS=False
KNOWN_HOSTS_EXISTS=True
KUBECONFIG_ENV_SET=False
```

Conclusion:

- This workstation has no default kubeconfig and no `KUBECONFIG` environment override.
- Cluster operations cannot currently run through the local kubectl client.
- There is no local SSH config alias to identify the admin host/user.
- The target control-plane host is already present in `known_hosts`.
- Helm will need to be used on a remote admin/control host or installed locally in a later separately approved step.

#### Execution-host decision

The source plan prefers `k3s-user` (`192.168.64.242`) and permits `k3s-control-01` (`192.168.65.122`) for bootstrap/recovery. Current evidence does not establish working credentials for `k3s-user`. A previous connection to `ubuntu@192.168.65.122` reached the SSH server but the server rejected this key.

Therefore, the exact execution host cannot safely be declared yet. Step 1 must resolve one of these access paths without changing either host:

1. Preferred: confirmed username/key for `k3s-user` at `192.168.64.242`.
2. Fallback: correct username or authorized key for `k3s-control-01` at `192.168.65.122`.

#### Step 0 result

```text
Step: 0 — Local safety preflight
Permission received: yes
Exit status: completed with one documented and corrected local path-detection error
Files/resources changed: this journal entry only
Validation result: repository checkpoint complete; SSH key ACL valid; local SSH/kubectl available; local Helm and kubeconfig unavailable
Rollback status: not applicable; no infrastructure mutation occurred
Unexpected behavior: sandbox home-path discovery returned empty; corrected with an explicit path
Next proposed step: Step 1 — Establish read-only cluster access
```

Step 1 must not begin until the user supplies or confirms a working SSH username/key combination for one approved host and explicitly approves Step 1.

### Journal entry 002 — Step 1: Establish read-only cluster access

- Permission received: `Approve Step 1`
- User-provided evidence: OpenStack instance inventory and a teammate shell prompt showing user `ubuntu` on `k3s-user`.
- Selected administration host: `k3s-user`
- Floating address: `192.168.64.242`
- Private address: `192.168.128.151`
- Local key used: `C:\Users\USER\Downloads\mykey.pem`
- Remote changes: none.
- Kubernetes changes: none.
- Local SSH configuration changes: none; the host was already trusted in `known_hosts`.

#### Local key and host-trust precheck

Commands:

```powershell
ssh-keygen -lf 'C:\Users\USER\Downloads\mykey.pem'
ssh-keygen -F '192.168.64.242' -f 'C:\Users\USER\.ssh\known_hosts'
```

Relevant output:

```text
2048 SHA256:TmNLEHlMBV1TCiH2DF11w8cIynM3Z5WuIAPXZWwdRXE no comment (RSA)
192.168.64.242 already has ED25519, RSA, and ECDSA host-key entries.
```

The public host-key bodies are intentionally not duplicated in this journal. No private-key content was displayed.

#### First SSH and authorization check

Command pattern:

```powershell
ssh \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o ConnectTimeout=15 \
  -o StrictHostKeyChecking=yes \
  -i 'C:\Users\USER\Downloads\mykey.pem' \
  ubuntu@192.168.64.242 \
  '<identity, tool-version, context, and kubectl auth can-i checks>'
```

Remote identity output:

```text
hostname: k3s-user
user: ubuntu
remote time: 2026-09-23T15:23:03+00:00
OS/kernel: Linux 5.15.0-181-generic x86_64 GNU/Linux
```

Remote tools:

```text
kubectl: /usr/bin/kubectl
kubectl client: v1.33.13 linux/amd64
kustomize: v5.6.0
helm: /usr/local/bin/helm
helm: v3.22.0
kubectl context: default
```

Authorization queries and output:

```text
kubectl auth can-i get nodes                              -> yes
kubectl auth can-i list pods --all-namespaces            -> yes
kubectl auth can-i list deployments.apps --all-namespaces -> yes
kubectl auth can-i list services --all-namespaces        -> yes
kubectl auth can-i list storageclasses.storage.k8s.io    -> yes
kubectl auth can-i list events --all-namespaces          -> yes
kubectl auth can-i create namespaces                     -> yes
kubectl auth can-i create deployments.apps -n monitoring -> yes
```

Warnings correctly noted that Nodes, StorageClasses, and Namespaces are cluster-scoped resources.

#### Cluster identity

The first formatting attempt for this check failed before producing the intended output:

```text
bash: unexpected EOF while looking for matching quote
bash: syntax error: unexpected end of file
```

Cause: nested Windows PowerShell, SSH, and remote Bash quoting. No remote subcommand or state change occurred.

A second attempt successfully obtained the API endpoint and TCP reachability, but optional `sed` and `find -printf` formatting was again altered during cross-shell argument parsing:

```text
api_server=https://192.168.128.101:6443
context=default
sed: unexpected ','
find: paths must precede expression
192.168.128.101:22 reachable
192.168.128.121:22 reachable
192.168.128.122:22 reachable
192.168.128.123:22 reachable
```

The formatting failures were corrected by replacing the filters with simpler read-only commands:

```bash
ls -la ~/.ssh
kubectl version -o json
```

Corrected output:

```text
Kubernetes API: https://192.168.128.101:6443
kubectl context: default
kubectl client: v1.33.13
k3s server: v1.36.2+k3s1
```

Kubectl emitted this warning:

```text
version difference between client (1.33) and server (1.36) exceeds the supported minor version skew of +/-1
```

This is not an access blocker, but it must be considered during Step 3 compatibility review. Cluster operations should prefer a kubectl version within one minor release of the server.

Remote SSH directory metadata showed:

```text
authorized_keys  mode 600
id_ed25519       mode 600
id_ed25519.pub   mode 644
known_hosts      mode 600
known_hosts.old  mode 600
```

Only filenames, modes, and sizes were inspected. Key contents were not read or copied.

#### Access from k3s-user to private k3s nodes

The following read-only hostname checks were attempted from `k3s-user` using its existing SSH identity and strict host-key checking:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes ubuntu@192.168.128.101 hostname
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes ubuntu@192.168.128.121 hostname
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes ubuntu@192.168.128.122 hostname
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes ubuntu@192.168.128.123 hostname
```

Output:

```text
192.168.128.101 -> k3s-control-01
192.168.128.121 -> k3s-worker-01
192.168.128.122 -> host key is not known; strict verification stopped the connection
192.168.128.123 -> host key is not known; strict verification stopped the connection
```

All four private addresses accepted TCP connections on port 22. Worker 02 and Worker 03 were not added to `known_hosts`, because their fingerprints must first be verified through a trusted source or console.

To access the already trusted nodes manually from `k3s-user`:

```bash
ssh ubuntu@192.168.128.101  # control plane
ssh ubuntu@192.168.128.121  # worker 01
```

For workers 02 and 03, first compare the presented host-key fingerprint with the VM console or a trusted teammate. Only after it matches should the new host key be accepted:

```bash
ssh ubuntu@192.168.128.122
ssh ubuntu@192.168.128.123
```

Direct node SSH is not required for the Day-0 Kubernetes inventory because `kubectl` on `k3s-user` can query all nodes centrally.

#### Step 1 result

```text
Step: 1 — Establish read-only cluster access
Permission received: yes
Commands executed: SSH identity/tool checks, Kubernetes context/version checks, authorization checks, API endpoint inspection, private-node TCP/SSH identity checks
Exit status: successful, with two documented command-formatting corrections
Files/resources changed: this journal entry only
Validation result: k3s-user is a working administration host; kubectl and Helm are installed; Kubernetes API access and required permissions are available
Rollback status: not applicable; no infrastructure mutation occurred
Unexpected behavior: kubectl client/server version skew warning; worker 02/03 host keys not yet trusted; two cross-shell output-filter quoting errors
Next proposed step: Step 2 — Day-0 cluster baseline
```

Do not begin Step 2 until the user reviews this result and explicitly approves Step 2.

### Journal entry 003 — Step 2: Day-0 cluster baseline

- Permission received: `Approve Step 2`
- User clarification: explain every stage plainly and disclose confusion/errors immediately.
- Phase purpose: capture the cluster's condition before monitoring exists, so later changes can be attributed correctly.
- Cluster changes: none.
- VM changes: none.
- Local additions: sanitized baseline evidence under `monitoring/baseline/20260923T154047Z/` and this journal entry.

#### What was read

The following commands were executed through the already verified `k3s-user` SSH path:

```bash
date -u +%Y%m%dT%H%M%SZ
kubectl get nodes -o wide
kubectl get namespaces
kubectl get pods -A -o wide
kubectl get deployments -A
kubectl get statefulsets -A
kubectl get daemonsets -A
kubectl get services -A
kubectl get jobs -A
kubectl get pvc -A
kubectl get storageclass
kubectl get ingress -A
kubectl cluster-info
kubectl version -o json
helm version --short
helm list -A
kubectl get events -A --sort-by=.lastTimestamp
kubectl top nodes
kubectl describe node k3s-control-01
kubectl describe node k3s-worker-01
kubectl describe node k3s-worker-02
kubectl describe node k3s-worker-03
kubectl get namespace monitoring
kubectl get crd
```

These commands list or describe existing state. None creates, updates, patches, restarts, scales, or deletes a resource.

#### Snapshot identity

```text
Snapshot UTC timestamp: 20260923T154047Z
Kubernetes API: https://192.168.128.101:6443
Context: default
kubectl client: v1.33.13
k3s server: v1.36.2+k3s1
Helm: v3.22.0
```

The existing kubectl version-skew warning remains. It was not changed during this step.

#### Node and capacity results

```text
k3s-control-01  Ready  4 CPU  ~8 GiB  current CPU 2%  current memory 21%
k3s-worker-01   Ready  4 CPU  ~8 GiB  current CPU 2%  current memory 35%
k3s-worker-02   Ready  4 CPU  ~8 GiB  current CPU 2%  current memory 13%
k3s-worker-03   Ready  4 CPU  ~8 GiB  current CPU 2%  current memory 12%
```

All nodes reported:

```text
MemoryPressure=False
DiskPressure=False
PIDPressure=False
Ready=True
```

Requested-resource allocation before monitoring:

```text
k3s-control-01  CPU 33%  memory 31%
k3s-worker-01   CPU 12%  memory 14%
k3s-worker-02   CPU 15%  memory 15%
k3s-worker-03   CPU 13%  memory 12%
```

The control plane has CPU limits totaling 118%, which is permitted Kubernetes overcommit. Actual CPU was 2%, but Step 3 must still choose conservative monitoring requests/limits.

#### Existing resource counts

```text
namespaces=16
pods=48
deployments=25
statefulsets=1
daemonsets=2
services=26
jobs=4
pvcs=1
storageclasses=1
ingresses=18
```

#### Pre-existing unhealthy state

These issues existed before monitoring:

```text
2105062/to-do-backend-deployment-6b849bbf9d-xnt9s
  READY: 0/1
  STATUS: CrashLoopBackOff
  RESTARTS: 35 at first snapshot
  warning: readiness probe returns HTTP 404

buet-paas-system-team23/to-do-frontend-v-infinity-2105062-build-job-z8vpq
  READY: 0/1
  STATUS: Error
```

The build Job later completed with another Pod, so the Error Pod is historical evidence rather than a currently failed Job object.

Additional existing warnings:

```text
CoreDNS: DNSConfigForming — nameserver limit exceeded
MetalLB speaker on all four nodes: DNSConfigForming — nameserver limit exceeded
```

Monitoring installation must not be blamed for these baseline problems. Post-install comparison will specifically check that they have not worsened and that no new application failures appear.

#### Storage result

```text
Default StorageClass: local-path
Provisioner: rancher.io/local-path
Reclaim policy: Delete
Binding: WaitForFirstConsumer
Volume expansion: disabled
Existing PVCs: 1, Falco Redis, Bound, 1 GiB
```

No Prometheus PVC or persistence was created. Whether to use ephemeral or persistent Prometheus storage remains a Step 3 decision.

#### Existing Helm and monitoring collision result

Existing releases:

```text
falco         namespace falco        chart falco-9.2.0
traefik       namespace kube-system  chart traefik-40.1.3+up40.1.0
traefik-crd   namespace kube-system  chart traefik-crd-40.1.3+up40.1.0
```

Collision checks:

```text
monitoring namespace: does not exist
Prometheus/Grafana/Alertmanager Helm release: none
Prometheus Operator CRDs: none
```

This confirms monitoring will be a new isolated layer rather than an upgrade of an existing stack.

#### Command errors and corrections

1. A compact custom-column node query failed:

```text
error: unterminated filter
```

Cause: JSONPath quoting did not survive the Windows PowerShell → SSH → Bash chain. The successful `kubectl top nodes` output was unaffected. The missing condition/capacity data was collected using the simpler, authoritative `kubectl describe node <name>` command for all four nodes.

2. The first unavailable-deployment filter failed:

```text
awk: cmd. line:1: != {print}
awk: syntax error
```

Cause: PowerShell expanded the remote awk `$3` and `$4` expressions before SSH. It was replaced with a grep expression that contains no shell variables.

Corrected output:

```text
2105062  to-do-backend-deployment  0/1  1  0
```

Neither error changed local or remote state.

#### Baseline files added

```text
monitoring/baseline/20260923T154047Z/README.md
monitoring/baseline/20260923T154047Z/nodes.txt
monitoring/baseline/20260923T154047Z/capacity-before.txt
monitoring/baseline/20260923T154047Z/resource-counts-before.txt
monitoring/baseline/20260923T154047Z/workload-problems-before.txt
monitoring/baseline/20260923T154047Z/storage-before.txt
monitoring/baseline/20260923T154047Z/helm-before.txt
monitoring/baseline/20260923T154047Z/versions-before.txt
monitoring/baseline/20260923T154047Z/warning-events-before.txt
```

The files are sanitized summaries. They exclude kubeconfig data, credentials, token values, private keys, node machine IDs, and full node annotations.

#### Step 2 result

```text
Step: 2 — Day-0 cluster baseline
Permission received: yes
Commands executed: read-only Kubernetes/Helm inventory, capacity, pressure, event, and collision checks
Exit status: baseline completed; two formatting/filter commands failed and were safely corrected
Files/resources changed: new local baseline documentation and this journal entry only
Validation result: four nodes Ready; sufficient apparent headroom for Step 3 evaluation; pre-existing application and DNS warnings recorded
Rollback status: no cluster rollback needed; no cluster mutation occurred
Unexpected behavior: kubectl version skew warning; one pre-existing CrashLooping deployment; one historical Error build Pod; pre-existing DNSConfigForming warnings
Next proposed step: Step 3 — Capacity and compatibility decision
```

Step 3 is analysis only. It will select a compatible pinned chart version, conservative resource requests/limits, and an initial storage approach. It will not install anything. Do not begin Step 3 until the user explicitly approves it.

### Journal entry 004 — Step 3: Capacity and compatibility decision

- Permission received: `Approve Step 3`
- User requirement added: beginning with Step 3, every step receives a standalone file (`step-3.md`, `step-4.md`, and so on) containing commands, outputs, decisions, errors, and traceability information.
- Additional VM access recorded for future steps: `ubuntu@backend-vm`, `ubuntu@frontend-vm`, and `nayeem@registry-vm-2`. None of these standalone VMs was accessed in Step 3.
- Phase purpose: decide whether the cluster can safely host the monitoring MVP and select exact compatibility, storage, exposure, and resource settings.
- Cluster changes: none.
- Existing tracked files changed: none.
- Standalone record: `step-3.md`.

#### Read-only checks

```text
1. kubectl get services,endpoints,endpointslices -n kube-system -o wide
2. kubectl get --raw /metrics, filtered only for k3s/control-plane metric prefixes
3. Official Kubernetes, k3s, Prometheus Operator, and kube-prometheus-stack compatibility/values research
```

Results:

```text
- No existing kube-system Service/EndpointSlice for scheduler, controller-manager, etcd metrics, or kube-proxy metrics.
- The authenticated Kubernetes API metrics endpoint returns unified k3s process metrics.
- Chart selected: kube-prometheus-stack 91.4.1, operator v0.94.0, Kubernetes constraint >=1.25.0-0.
- Cluster: v1.36.2+k3s1; capacity decision: GO.
- Initial storage: ephemeral with two-day Prometheus retention.
- Exposure: ClusterIP only; no Ingress, NodePort, or LoadBalancer.
- Initial generic embedded-component targets and their rules will be disabled to avoid missing/duplicate targets.
- Proposed listed long-running requests: 880m CPU and 1600 MiB memory cluster-wide.
```

Important prerequisite:

```text
The k3s-user VM has kubectl v1.33.13 against API server v1.36.2.
Kubernetes supports kubectl only within one minor version of the API server.
Use a verified compatible client before Step 5, the first cluster mutation.
```

No command failed in Step 3. The Endpoints API printed an expected deprecation warning because the evidence command intentionally requested both Endpoints and EndpointSlices.

#### Step 3 result

```text
Step: 3 — Capacity and compatibility decision
Permission received: yes
Commands executed: read-only endpoint and metrics discovery plus official-source compatibility research
Exit status: completed
Files/resources changed: new step-3.md and this master-journal entry only
Validation result: GO for local-only Step 4; no cluster installation authorized
Rollback status: no cluster rollback needed
Unexpected behavior: none; one expected Endpoints deprecation warning recorded
Next proposed step: Step 4 — Create local monitoring configuration only
```

Do not begin Step 4 until the user reviews `step-3.md` and explicitly approves Step 4.

### Journal entry 005 — Step 4: Create and validate local monitoring configuration

- Permission received: `Approve Step 4`
- Phase purpose: turn the approved Step 3 design into reproducible local configuration and inspect the exact manifests without changing Kubernetes or any VM.
- Kubernetes changes: none.
- Standalone VM changes: none.
- Existing tracked files changed: none.
- Standalone record: `step-4.md`.

Files added:

```text
monitoring/README.md
monitoring/prometheus/values.yaml
monitoring/scripts/render-kube-prometheus-stack.ps1
step-4.md
```

Validation toolchain:

```text
Helm: v3.22.0+g144ca65, downloaded to a temporary directory only
Helm archive SHA-256: matched the official get.helm.sh checksum
Chart: kube-prometheus-stack 91.4.1
Chart appVersion: v0.94.0
Chart kubeVersion: >=1.25.0-0
OCI digest: sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
Digest result: matched the pinned publisher digest
Helm lint: 1 chart linted, 0 failed
Helm template: passed with Kubernetes version 1.36.2 and CRDs included
```

Rendered result:

```text
Total objects: 114
CRDs: 10
Deployments: 3
DaemonSets: 1
Prometheus custom resources: 1
Alertmanager custom resources: 1
Services: 7, all ClusterIP
Ingresses: 0
PVCs: 0
NodePort/LoadBalancer services: 0
Runtime external/static scrape configuration: 0
Disabled embedded k3s component targets present: 0
```

Security inspection:

```text
Grafana/Prometheus/Alertmanager remain internal.
Rendered Secret contents stayed in the temporary manifest and were not printed or copied into the repository.
node-exporter uses hostNetwork, hostPID, and read-only host mounts as expected.
No rendered privileged: true marker was found for node-exporter.
```

Errors and corrections:

```text
Attempt 1 stopped because Windows PowerShell treated Helm's successful OCI stderr status as NativeCommandError under strict error handling.
Attempt 2 completed but retained a confusing PowerShell error-record wrapper.
Final script uses ProcessStartInfo, captures both native streams directly, checks the Helm exit code, and retested cleanly.
No error touched the cluster, any VM, or existing repository source.
```

#### Step 4 result

```text
Step: 4 — Create and validate local monitoring configuration
Permission received: yes
Commands executed: local tool discovery, verified temporary Helm download, pinned OCI pull, Helm lint/template, sanitized manifest inspection, hashes, and repository integrity checks
Exit status: completed
Files/resources changed: four new local documentation/configuration files; no tracked source modification
Validation result: PASS
Rollback status: local additions are individually listed in step-4.md; no cluster rollback needed
Unexpected behavior: Helm success text on stderr required two safe renderer improvements; fully documented
Next proposed step: Step 5 — verify server-matched kubectl and create only the monitoring namespace
```

Do not begin Step 5 until the user reviews `step-4.md` and explicitly approves Step 5.

### Journal entry 006 — Step 5: Create the monitoring namespace

- Permission received: `Approve Step 5`
- Phase purpose: perform the first minimal cluster mutation by creating only the empty namespace boundary for later monitoring resources.
- Standalone record: `step-5.md`.

#### Safety gate

The existing SSH route was used through `k3s-user` to `k3s-control-01`. The server-bundled client avoided the unsupported standalone kubectl clients:

```text
host: k3s-control-01
user: ubuntu with non-interactive sudo available
k3s kubectl client: v1.36.2+k3s1
Kubernetes server: v1.36.2+k3s1
context: default
can create namespaces: yes
can get namespaces: yes
monitoring namespace before mutation: absent
```

The `kubectl auth can-i` commands printed the expected warning that namespaces are not namespace-scoped. Both commands succeeded and returned `yes`.

#### Mutation

Exact cluster-changing command:

```text
sudo -n k3s kubectl create namespace monitoring
```

Output:

```text
namespace/monitoring created
```

#### Verification

```text
namespace: monitoring
UID: aefef0b6-83cc-4700-815a-7592fed5225b
creationTimestamp: 2026-09-23T16:46:29Z
status: Active
labels: kubernetes.io/metadata.name=monitoring
namespace count: 17 (Step 2 before count: 16)
workloads/Services in monitoring: none
Secrets: none
PVCs: none
Helm releases: none
representative Prometheus Operator CRDs: absent
```

Kubernetes automatically created `serviceaccount/default` and `configmap/kube-root-ca.crt`. These are normal namespace bootstrap objects and were not separately submitted by our command.

No Helm chart, monitoring workload, CRD, PVC, Ingress, NodePort, LoadBalancer, Secret, RBAC object, or application change was made in Step 5.

#### Step 5 result

```text
Step: 5 — Create the monitoring namespace
Permission received: yes
Commands executed: matching-client safety gate, one namespace create command, read-only namespace/object/Helm/CRD verification
Exit status: completed
Files/resources changed: Kubernetes namespace monitoring plus controller-generated default ServiceAccount/root CA ConfigMap; new local step-5.md and journal entry
Validation result: namespace Active; exact namespace delta +1; no monitoring workload or release installed
Rollback status: documented but not executed
Unexpected behavior: none; expected cluster-scoped authorization warnings recorded
Next proposed step: Step 6 — prepare and remotely re-render the pinned OCI chart without installation
```

Do not begin Step 6 until the user reviews `step-5.md` and explicitly approves Step 6.

### Journal entry 007 — Step 6: Prepare and remotely validate the pinned Helm chart

- Permission received: `Approve Step 6`
- Phase purpose: prepare the exact reviewed artifact on `k3s-user`, re-run lint/template there, and prove that no release was installed.
- Kubernetes changes: none.
- Standalone application VM changes: none.
- Remote file changes: protected artifacts under `/tmp/buet-paas-monitoring-step6-20260923` on `k3s-user`.
- Standalone record: `step-6.md`.

Verified inputs:

```text
Remote Helm: v3.22.0+g144ca65
Values SHA-256: 2d98fe9150c90ae7709864590b3145a94c8e369f6b1e9c06c9cf8d53f79a57b7
Chart: kube-prometheus-stack 91.4.1
Chart appVersion: v0.94.0
Chart kubeVersion: >=1.25.0-0
OCI digest: sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
Chart archive SHA-256: 1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb
All immutable input checks matched Steps 3 and 4.
```

Validation:

```text
Helm lint: 1 chart linted, 0 failed
Helm template: passed
Rendered object count: 114, matching Step 4
Ingress/PVC/NodePort/LoadBalancer matches: 0
Disabled generic k3s component target matches: 0
Explicit ClusterIP lines: 6; seventh Service uses Kubernetes default ClusterIP
Remote render file: mode 600 inside a mode-700 directory
Rendered Secret bodies: not printed, copied, or installed
```

Read-only inspection mistakes:

```text
One Service filter assumed fixed indentation and undercounted.
One retention grep lost quoting and returned "Trailing backslash".
An indentation-flexible Service filter still missed quoted ClusterIP values.
One quote-tolerant regex was parsed locally by PowerShell and never reached SSH.
Simple corrected filters returned six explicit ClusterIP lines and zero public service types.
No inspection error changed any file or cluster resource.
```

Final non-installation proof:

```text
monitoring namespace: Active
monitoring workloads/Services: none
Secrets/PVCs: none
Prometheus Operator CRDs: absent
Helm releases: none
Only Step 5 default ServiceAccount and root CA ConfigMap exist.
```

#### Step 6 result

```text
Step: 6 — Prepare and remotely validate the pinned Helm chart
Permission received: yes
Commands executed: protected directory creation, SCP, hash/digest/metadata verification, Helm lint/template, sanitized render inspection, and non-installation checks
Exit status: completed
Files/resources changed: temporary protected Step 6 files on k3s-user plus new local step-6.md/journal entry; no Kubernetes change
Validation result: PASS; remote render matches Step 4 structure and inputs
Rollback status: no cluster rollback; temporary files retained for exact Step 7 reuse
Unexpected behavior: four harmless cross-shell/filtering issues, fully corrected and documented
Next proposed step: Step 7 — install the pinned monitoring release with atomic/wait safeguards
```

Do not begin Step 7 until the user reviews `step-6.md`, understands the CRD rollback limitation, and explicitly approves Step 7.

### Journal entry 008 — Step 7: First kube-prometheus-stack installation attempt

- Permission received: `Approve Step 7`
- Phase purpose: install the pinned monitoring release with atomic/wait safeguards.
- Result: installation timed out because Grafana never became Ready; Helm atomically uninstalled the release.
- Standalone record: `step-7.md`.

Preflight:

```text
Values and chart hashes matched Steps 4/6.
Required authorization checks: yes.
monitoring namespace: empty.
monitoring Helm release/CRDs: absent.
all nodes: Ready.
pre-existing to-do-backend deployment: still 0/1 with 66 restarts before installation.
```

Executed mutation:

```text
helm upgrade --install monitoring-stack \
  /tmp/buet-paas-monitoring-step6-20260923/kube-prometheus-stack-91.4.1.tgz \
  --namespace monitoring \
  --values /tmp/buet-paas-monitoring-step6-20260923/values.yaml \
  --atomic --wait --timeout 15m --history-max 10
```

Progress:

```text
Prometheus: 2/2 Running
Alertmanager: 2/2 Running
Prometheus Operator: Ready
kube-state-metrics: Ready
node-exporter: 4/4 Ready
Grafana sidecars: Ready
Grafana main container: never Ready; restarted four times
```

Root cause:

```text
Grafana 13.2.2 performed lengthy first-run SQLite migrations with a 500m CPU limit.
No startup probe was configured.
The default liveness window expired before port 3000 opened.
Each restart preserved and advanced migrations, but Helm reached 15 minutes first.
No OOM, invalid configuration, permission denial, or image-pull failure was observed.
```

Final Helm output:

```text
Error: release monitoring-stack failed, and has been uninstalled due to atomic being set: context deadline exceeded
```

Post-rollback state:

```text
Helm release: absent
monitoring workloads/Services/PVCs: absent
release RBAC and webhook configurations: absent
10 Prometheus Operator CRDs: retained and empty
Secret monitoring-stack-kube-prom-admission: retained; contains ca/cert/key only, values not displayed
all four nodes: Ready
pre-existing to-do-backend deployment: still 0/1
```

Diagnostic issues:

```text
One local polling wrapper syntax error did not reach or interrupt Helm.
One read-only tar lookup assumed a nested dependency archive and failed.
The corrected expanded dependency path exposed the Grafana startup/liveness defaults.
No diagnostic error changed state.
```

#### Step 7 result

```text
Step: 7 — First kube-prometheus-stack installation attempt
Permission received: yes
Exit status: failed with atomic uninstall
Cluster residue: namespace from Step 5, 10 empty CRDs, one orphan webhook certificate Secret
Existing application changes: none
Manual cleanup/retry: not performed
Recommended next step: Step 7R1 — locally prepare and validate Grafana startup-probe/CPU corrections
```

Do not proceed to Step 8. Do not delete residue or retry installation until the user reviews `step-7.md` and explicitly approves Step 7R1.

### Journal entry 009 — Step 7R1: prepare and validate retry settings

Date: 2026-09-24 (Asia/Dhaka)

Permission received:

```text
approves Step 7R1
```

Scope and result:

```text
Local/offline phase only: yes
Kubernetes changes: none
OpenStack changes: none
Existing application changes: none
Result: completed successfully
```

Local values correction:

```text
File: monitoring/prometheus/values.yaml
Grafana CPU limit: 500m -> 1
Grafana CPU request: 100m (unchanged)
Startup probe: /api/health, initial delay 10s, period 10s, timeout 5s, failure threshold 90
Liveness/readiness probes: retained
Values SHA-256: c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b
```

Pinned validation:

```text
Helm: v3.22.0+g144ca65
Chart: kube-prometheus-stack 91.4.1
Chart SHA-256: 1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb
Kubernetes render target: 1.36.2
Helm lint: 1 chart linted, 0 failed
Focused Grafana Deployment SHA-256: f9436be302bac7a1877121cac328e8ff0d38beb8278c80cbcaf877977995180d
Rendered startup probe: confirmed
Rendered Grafana CPU limit: 1
Embedded credentials in retained evidence: none
```

Correction recorded:

```text
The initial full manifest included a random Helm-generated Grafana password.
It was never applied and the newly generated full manifest was deleted immediately.
A focused Deployment-only render was retained because it contains Secret references, not Secret values.
The first credential assertion incorrectly classified a Secret reference as embedded data; the corrected assertion passed.
```

Detailed commands, outputs, error, correction, hashes, and proposed retry procedure are recorded in `step-7R1.md`.

Do not proceed with cluster mutation until the user explicitly approves Step 7R2.

### Journal entry 010 — Step 7R2: successful atomic installation retry

Date: 2026-09-24 (Asia/Dhaka); remote cluster timestamps are UTC 2026-09-23.

Permission received:

```text
Approve Step 7R2
```

Authorized and completed mutations:

```text
Deleted only verified orphan Secret monitoring/monitoring-stack-kube-prom-admission.
Uploaded corrected values as /tmp/buet-paas-monitoring-step6-20260923/values-step7r2.yaml.
Installed Helm release monitoring-stack with --atomic --wait --timeout 25m.
No OpenStack or existing application configuration was changed.
```

Verified inputs:

```text
corrected values SHA-256: c28981cb9c37400cece05f3fad5001b54031c79562354975bbc49a907111bc0b
chart SHA-256: 1bd5e7a88e758ed3ec22db0fe6e72b1352f3f0e7e5a93c79979f7edf361becdb
chart: kube-prometheus-stack 91.4.1
Helm lint: 1 chart linted, 0 failed
full remote render: PASS
```

Installation command:

```text
helm upgrade --install monitoring-stack \
  /tmp/buet-paas-monitoring-step6-20260923/kube-prometheus-stack-91.4.1.tgz \
  --namespace monitoring \
  --values /tmp/buet-paas-monitoring-step6-20260923/values-step7r2.yaml \
  --atomic --wait --timeout 25m --history-max 10
```

Installation result:

```text
Helm status: deployed
Revision: 1
Grafana: 3/3 Running, one startup-probe restart
Prometheus: 2/2 Running
Alertmanager: 2/2 Running
Prometheus Operator: 1/1 Running
kube-state-metrics: 1/1 Running
node-exporter: 4/4 Pods Running
Grafana health: database ok, version 13.2.2
Prometheus readiness: Ready
Alertmanager readiness: OK
Grafana dashboard ConfigMaps: 23
```

Grafana behavior:

```text
The first startup-probe window allowed about 15 minutes of migrations.
Grafana restarted once at that threshold, retained SQLite progress in the Pod emptyDir, completed migrations/plugins, and became Ready before the Helm timeout.
Transient SQLite lock/prune messages occurred during first provisioning; final API and readiness checks passed.
```

Prometheus target result:

```text
active targets: 25
up: 22
down: 3
down targets: node-exporter on 192.168.128.101, .121, and .122 port 9100
```

Read-only TCP checks from control plane and worker 01 proved that port 9100 succeeds only to the same VM and times out between VMs. This points to OpenStack security-group and/or VM firewall filtering. No network rule was changed.

Firing alerts correctly included the pre-existing `2105062/to-do-backend` failure, the node-exporter `TargetDown`, and the normal Watchdog alert.

Final cluster state:

```text
all four nodes: Ready
node utilization: CPU 2-4%, memory 15-42%
six other listed 2105062 deployments: 1/1
pre-existing to-do-backend deployment: still 0/1
existing application edits/restarts by this step: none
```

Errors/corrections recorded:

```text
Initial SSH probes were blocked locally by sandbox permissions and never reached the VM.
One remote-exit label was locally expanded to True; fail-fast validation was rerun and passed.
Two read-only JSONPath formatters failed due cross-shell quoting; simpler checks replaced them.
One dashboard inventory printed non-secret dashboard JSON; a corrected names/count query returned 23.
```

The full command, rollout, verification, target, alert, connectivity, warning, and correction record is in `step-7R2.md`.

Recommended next permission boundary: Step 7R3A, read-only inspection of OpenStack security groups and VM firewall policy for inter-node TCP 9100. Do not add a network rule until a separate Step 7R3B approval.

### Journal entry 011 — Step 7R3A: partial read-only network inspection

Date: 2026-09-24 (Asia/Dhaka)

Permission received:

```text
Approve Step 7R3A
```

Scope/result:

```text
Read-only investigation: yes
Kubernetes changes: none
OpenStack changes: none
VM firewall changes: none
Existing application changes: none
Result: VM side completed; Neutron rule table blocked by unavailable authenticated Horizon/CLI access
```

OpenStack client discovery:

```text
Windows OpenStack CLI/clouds.yaml/OpenRC: absent
k3s-user OpenStack CLI/OS_* variables/clouds.yaml/OpenRC: absent
Open browser/native-app sessions: none
```

Trusted-node firewall findings:

```text
k3s-control-01 and k3s-worker-01:
  UFW inactive
  node_exporter listening on *:9100
  INPUT policy ACCEPT
  no TCP 9100 drop/reject in inspected K3s chains
  only KUBE-FIREWALL drop protects 127.0.0.0/8 from non-loopback traffic
```

Metadata findings:

```text
k3s-user: k3-user
k3s-control-01: k3s-secgroup
k3s-worker-01: k3-secgroup-worker, k3s-secgroup
```

Combined with Step 7R2 connectivity tests, the remaining block is strongly localized outside the guest firewall, most likely to OpenStack Neutron security groups.

The full commands, outputs, cross-shell corrections, preliminary least-privilege rule shape, and remaining Horizon inspection are recorded in `step-7R3A.md`.

Step 7R3A is not fully closed. The user must open/log into Horizon and expose the Security Groups page, or provide screenshots of rules and port attachments. Do not create Step 7R3B changes until that read-only evidence is obtained and separately approved.

#### Step 7R3A continuation — Horizon screenshots received

The user supplied authenticated Horizon screenshots for the security-group inventory and these rule tables:

```text
k3-secgroup-worker
ID: 449f223e-1341-46bb-bd3e-32d609d091ab
Rules: unrestricted IPv4/IPv6 egress; public TCP 80 and 443 ingress

k3s-secgroup
ID: 9f289e1a-d70b-4ffc-9507-bd9c6df9309b
Rules:
  unrestricted IPv4/IPv6 egress
  TCP 22 from 0.0.0.0/0
  TCP 6443 from 192.168.128.0/24
  TCP/UDP 7946 from 192.168.128.0/24
  TCP 10250 from 0.0.0.0/0
  UDP 8472 from 192.168.128.0/24
```

Confirmed conclusion:

```text
Neither group permits TCP 9100 ingress.
Egress is not restricted.
The absent ingress rule explains the inter-VM node-exporter timeouts.
No OpenStack rule was changed.
```

Separate security note: exposing SSH 22 and kubelet 10250 to `0.0.0.0/0` deserves a later hardening review but is outside the monitoring change scope.

Remaining Step 7R3A evidence: confirm security-group attachments for `k3s-worker-02` and `k3s-worker-03`. Control and worker 01 are already proven to have `k3s-secgroup`. Do not authorize or execute Step 7R3B until both remaining attachments are known.

#### Step 7R3A completion — worker attachments confirmed

The user supplied Horizon Overview data for the remaining workers:

```text
k3s-worker-02
ID: 35c75c5d-57b5-4b9d-8007-40664f2d96b5
IP: 192.168.128.122
groups: k3-secgroup-worker, k3s-secgroup

k3s-worker-03
ID: 19b98734-4477-4cbd-b46f-93122576a268
IP: 192.168.128.123
groups: k3-secgroup-worker, k3s-secgroup
```

All four K3s nodes are confirmed members of `k3s-secgroup`. Step 7R3A is complete.

Exact proposed Step 7R3B rule:

```text
Applied group: k3s-secgroup (9f289e1a-d70b-4ffc-9507-bd9c6df9309b)
Direction: ingress
Ether Type: IPv4
Protocol: TCP
Port range: 9100-9100
Remote source: security group k3s-secgroup (self-reference)
Description: Prometheus node-exporter between K3s nodes
```

Expected result: all four node-exporter targets become reachable and Prometheus target health changes from 22/25 to 25/25. Rollback is deletion of only the newly created rule, identified and recorded at creation time.

No OpenStack change has yet been made. Step 7R3B requires separate explicit approval.

### Journal entry 012 — Step 7R3B approved; paused at manual rule creation

Date: 2026-09-24 (Asia/Dhaka)

Permission received:

```text
Approve Step 7R3B
```

Authorized rule:

```text
Applied group: k3s-secgroup (9f289e1a-d70b-4ffc-9507-bd9c6df9309b)
Ingress IPv4 TCP 9100-9100
Remote source: k3s-secgroup self-reference
Description: Prometheus node-exporter between K3s nodes
```

Fresh pre-change baseline:

```text
Helm release: deployed, revision 1
monitoring Pods: healthy
nodes: four Ready
Prometheus targets: 22 up, 3 down
down: node-exporter on .101, .121, .122
control-plane TCP test: own 9100 succeeds; other three time out
```

Execution-path blocker:

```text
OpenStack CLI credentials: unavailable
Chrome automation surface: unavailable
Edge automation surface: unavailable
in-app browser surface: unavailable
Horizon form opened/submitted: no
OpenStack mutation: none
```

The exact manual Horizon fields, post-change verification, and rollback are recorded in `step-7R3B.md`.

Step 7R3B remains paused until the user creates exactly the authorized rule in the already authenticated Horizon session and confirms the resulting rule row/ID. No verification should assume the rule exists before that confirmation.

#### Step 7R3B completion — rule created and verified

The user supplied a Horizon screenshot confirming exactly one new rule on `k3s-secgroup`:

```text
Ingress IPv4 TCP 9100
Remote IP prefix: none
Remote security group: k3s-secgroup
Description: Prometheus node-exporter between K3s nodes
Displayed rule count: 9, previously 8
```

Post-change inter-node verification:

```text
Source k3s-control-01 -> TCP 9100 on .101, .121, .122, .123: all succeeded
Source k3s-worker-01  -> TCP 9100 on .101, .121, .122, .123: all succeeded
```

Prometheus verification:

```text
active targets: 25
up: 25
down: 0
all four node-exporter lastError fields: empty
node_uname_info series: 4, one for each control/worker node
TargetDown alert: cleared
```

Non-regression:

```text
Helm monitoring-stack: deployed, revision 1
all monitoring Pods: Ready
all Kubernetes nodes: Ready
node CPU: 2-4%
node memory: 20-37%
six previously healthy 2105062 deployments: still healthy
pre-existing to-do-backend: still 0/1 CrashLoopBackOff
Kubernetes/application edits by Step 7R3B: none
```

Step 7R3B completed successfully. The single OpenStack rule is retained because it achieved the intended least-privilege result; rollback was not required. Full commands, before/after evidence, alert inventory, and rollback identifier are in `step-7R3B.md`.

### Journal entry 013 — Step 8 post-install regression comparison

Date: 2026-09-24 (Asia/Dhaka)

Permission received:

```text
now go for the next stage
```

Scope: read-only comparison of the live cluster against the Day-0 baseline. No Kubernetes, OpenStack, Helm, application, or tracked repository resource was changed.

Result:

```text
nodes Ready: 4/4
monitoring Pods Ready: 9/9
node-exporter DaemonSet: 4 desired, 4 ready
monitoring Helm release: deployed, revision 1
monitoring Services: 8, all ClusterIP
monitoring NodePort/LoadBalancer/Ingress/PVC: none
new non-monitoring unavailable Deployment: none
pre-existing 2105062/to-do-backend: still 0/1 CrashLoopBackOff
Step 8: PASS
```

Raw cluster totals changed after Day 0 because teammates continued creating and cleaning up unrelated resources. The comparison therefore separated the `monitoring` namespace contribution from the concurrent net delta. Monitoring accounts for exactly 1 namespace, 9 Pods, 3 Deployments, 2 StatefulSets, 1 DaemonSet, and 8 internal Services; it accounts for no application Ingress, Job, or PVC.

All expected release-named ClusterRoles, ClusterRoleBindings, and admission webhooks were present. The queried monitoring custom-resource set contained 41 Prometheus/Alertmanager/ServiceMonitor/PrometheusRule objects. The previously reviewed 10 Prometheus Operator CRDs back these objects.

The event comparison found only the known student backend failures and the already known node nameserver-limit warning, now also emitted by the healthy node-exporter Pods. No event showed an existing application regression.

Two read-only capture attempts had shell quoting/filter errors. Both errors, their zero-change impact, and corrected commands are recorded in `step-8.md`.

Step 8 is complete. Step 9 remains gated on separate explicit permission; it will use temporary private access for UI/API verification and will terminate the access processes afterward.

### Journal entry 014 — Step 9 private UI and built-in metric verification

Date: 2026-09-24 (Asia/Dhaka)

Permission received:

```text
Approve Step 9
```

Private access method:

```text
Windows loopback -> temporary SSH tunnel -> k3s-user loopback -> temporary kubectl port-forward -> ClusterIP service
```

Grafana result:

```text
login UI HTTP: 200
health: database ok, version 13.2.2
authenticated API: successful
password printed or stored: no
datasources: Prometheus healthy/default; Alertmanager present
provisioned dashboards: 23
requested dashboard models fetched: Nodes, Pods, Namespaces, Workloads, Pod
panels across the five fetched models: 65
live metrics through Grafana: 4 nodes, 66 Pods, 18 namespaces, 34 Deployments, 4 node exporters
```

Prometheus result:

```text
ready/UI HTTP: 200
active targets: 25
up: 25
down: 0
TargetDown alert: absent
live node/kube-state queries: successful
```

Alertmanager result:

```text
ready/UI HTTP: 200
version: 0.34.0
received alerts: 8
silences: 0
active warning alerts: four, all for the pre-existing 2105062 backend fault
```

Browser automation limitation:

```text
available Windows apps: none
available browser surfaces: none
```

An automated visual click-through/screenshot was therefore unavailable. UI HTML, authenticated APIs, dashboard models, datasource health, and live data queries were all verified successfully instead.

Cleanup:

```text
Step 9 Windows listeners 3000/9090/9093: closed
Step 9 remote listeners 13000/19090/19093: closed
verified Step 9 kubectl processes terminated: PIDs 64172, 65787, 66063
```

The first Grafana bind attempt found an older remote loopback-only Grafana port-forward on port 3000, PID 38379, started before Step 9. It was not changed. Step 9 used port 13000 instead.

Several read-only shell/PowerShell parsing errors and their corrections are documented in `step-9.md`. None changed cluster state or exposed the Grafana password.

Final regression result:

```text
Helm monitoring-stack: deployed, revision 1
nodes: 4/4 Ready
monitoring Pods: 9/9 Ready
new unavailable application Deployment: none
known 2105062/to-do-backend: still 0/1
persistent cluster/OpenStack/application changes in Step 9: none
Step 9: PASS; automated browser control unavailable, later resolved by user-supplied visual confirmation
```

Step 10 remains gated on separate permission. It begins with only `frontend-vm` and is a remote VM mutation; no other VM may be touched under that approval.

#### Step 9 visual confirmation supplied by the user

The user subsequently opened Grafana through the private localhost tunnel, authenticated successfully, and supplied a screenshot of the **Dashboards** page.

The screenshot visibly confirms:

```text
Grafana UI rendered in the browser
authenticated Dashboards page accessible
23 provisioned dashboards visible
Kubernetes compute, namespace, Pod, workload, and networking dashboards present
Node Exporter dashboards present
Prometheus / Overview present
Alertmanager / Overview present
```

This resolves the practical browser-access question and supplements the earlier authenticated API, dashboard-model, datasource-health, and live-metric verification. Automated browser control remained unavailable, but it is no longer a visual-verification blocker because the user provided direct browser evidence.

No dashboard, cluster resource, tunnel configuration, or application workload was changed by this documentation update. Step 9 final status is **PASS**.

#### Step 9 Prometheus and Alertmanager visual confirmation

The user subsequently supplied Prometheus screenshots showing:

```text
up: 25 result series, all value 1
count(kube_node_info): 4
count(node_uname_info): 4
count(kube_pod_info): 66
Target health UI: visible targets UP
```

The user also supplied Alertmanager screenshots showing:

```text
Alerts UI: expected groups visible
namespace 2105062: 4 alerts
namespace monitoring: 1 visible alert
Silences UI: No silences found
Status UI: version 0.34.0, cluster disabled
```

The default Alertmanager UI omits inhibited/suppressed alerts unless those filters are selected, so six visible alerts are consistent with the eight total objects previously returned by the API. The disabled cluster state is expected for one Alertmanager replica. The effective route uses the `null` receiver; no external notification integration has been configured by this monitoring work.

With the earlier Grafana screenshot, all three Day-1 monitoring UIs now have direct user-supplied browser evidence. The Day-1 core monitoring checklist is complete. No monitoring or application resource was changed while recording this evidence.

### Journal entry 015 — Step 10A frontend-vm node_exporter installation

Date: 2026-09-24 (Asia/Dhaka)

Permission received:

```text
Approve Step 10A — frontend-vm
```

Scope: `frontend-vm` only. No other standalone VM and no Prometheus scrape configuration was authorized.

Pinned artifact:

```text
node_exporter: 1.12.1 linux/amd64
official/downloaded archive SHA-256: b51d8a76aa2a9156a55d501aca6276fae09e262259a5e4e831d2c2222f084e63
```

Baseline:

```text
Ubuntu 24.04.3 LTS, x86_64
node_exporter binary/user/unit/listener: absent
UFW: inactive
frontend Nginx and Next.js: HTTP 200
k3s-user -> frontend:9100: timed out
```

Created objects:

```text
repository: monitoring/external-vms/frontend-vm/node_exporter.service
frontend system user: node_exporter
frontend binary: /usr/local/bin/node_exporter
frontend unit: /etc/systemd/system/node_exporter.service
```

Validation:

```text
unit enabled/active: yes/yes
restarts: 0
listener: 192.168.128.15:9100 only
local metrics: 949 lines
node_exporter version: 1.12.1
systemd security exposure: 4.1 OK
memory: approximately 6 MiB
floating-IP TCP 9100: blocked
frontend Nginx/Next.js after install: unchanged, HTTP 200
```

Private network limitation:

```text
k3s-user -> frontend:9100: timed out
k3s-control-01 -> frontend:9100: timed out
frontend attached OpenStack groups: web-&-ssh, default
```

The service is healthy locally, but OpenStack Neutron blocks the K3s-to-frontend path. No OpenStack rule was changed because the attached groups' rule tables have not yet been reviewed. Temporary download/staging files were removed after exact-path verification.

Step 10A is paused, not complete. The required next evidence is the Horizon `Manage Rules` view for `web-&-ssh` and, if relevant, `default`. After reviewing it, propose one exact TCP 9100 rule with remote security group `k3s-secgroup`, record rollback, and require separate permission before creation.

Full commands, hashes, outputs, errors/corrections, rollback, and pause reason are in `step-10A.md`.

#### Step 10A Horizon rule review and Step 10A-R1 proposal

The user supplied the `web-&-ssh` rule table for group ID `107653fc-ce63-4baa-adfd-8bd98f9348f4`.

Observed:

```text
TCP 9100 rule: absent
public IPv4 ingress: ICMP, TCP 22, 80, 443, 3000, and 9000
unrestricted IPv4/IPv6 egress: present
```

The absent TCP 9100 rule explains the K3s-to-frontend timeout. The broad public rules are pre-existing and will not be changed under monitoring scope.

Recommendation: do not modify `web-&-ssh`. Under a separately approved Step 10A-R1, create a new `monitoring-exporter` security group with only TCP 9100 ingress from remote security group `k3s-secgroup`, then attach it additively to `frontend-vm` while retaining `web-&-ssh` and `default`.

No OpenStack mutation has been made. Exact fields, verification sequence, and rollback are recorded in `step-10A.md`.

#### Step 10A completion — dedicated security group attached and verified

The user manually created:

```text
security group: monitoring-exporter
ID: c83ef330-b742-4420-b010-06bf63c56765
ingress: IPv4 TCP 9100
remote security group: k3s-secgroup
description: Prometheus to standalone VM node_exporters
```

The user then attached it only to `frontend-vm`, retaining the pre-existing `web-&-ssh` and `default` groups.

Verification:

```text
k3s-control-01 -> frontend:9100: succeeded
k3s-control-01 -> frontend /metrics: 949 lines
reported exporter version: 1.12.1
reported nodename: frontend-vm
k3s-user -> frontend:9100: still blocked, expected source restriction
floating IP -> frontend:9100: blocked
node_exporter: enabled, active, 0 restarts
frontend Nginx/Next.js: unchanged, HTTP 200
nodes: 4/4 Ready
monitoring Pods: 9/9 Ready
```

The first corrected-path wrapper had a local PowerShell pipe-parsing error and did not execute the K3s-source test. A pipe-free corrected command used one temporary metrics file on the control node, removed it after inspection, and passed.

Step 10A is complete. Prometheus configuration was intentionally not changed; `frontend-vm` is reachable from K3s and ready for the later external-target configuration step. No other VM was changed.

### Journal entry 016 - Step 11A1 frontend-vm scrape configuration preparation

Permission received:

```text
Approve Step 11A1 - prepare frontend-vm scrape configuration
```

This permission was limited to repository preparation and offline validation.
No Helm upgrade, Kubernetes apply, VM change, or OpenStack change was performed.

The pinned OCI chart `kube-prometheus-stack:91.4.1` confirmed that
`prometheus.prometheusSpec.additionalScrapeConfigs` accepts a list. Its digest
remained:

```text
sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9
```

A new additive overlay was created:

```text
monitoring/external-vms/scrape-values.yaml
SHA-256: a5b4c936232457e957f1c2b2fab3dfc3ec1799c9d21df0490fbc865caeef1a32
```

It defines only one target, `192.168.128.15:9100`, under job
`standalone-node-exporters`, with stable labels `instance=frontend-vm`,
`service=frontend`, `environment=buet-paas`, and
`deployment_type=standalone-vm`. Existing `monitoring/prometheus/values.yaml`
was not changed.

Validation result:

```text
local/remote hashes: matched
Helm lint: 1 chart linted, 0 failed
focused additionalScrapeConfigs render: passed and decoded as expected
live release: monitoring-stack revision 1, deployed
live Prometheus additional scrape reference: none
live additional scrape Secret: absent
temporary validation directory: removed and deletion verified
```

The first combined decode wrapper failed locally because PowerShell detected an
unterminated quote. It stopped before SSH execution and changed nothing. The
corrected workflow separated render and decode.

Step 11A1 is complete. The file is prepared but not live. Step 11A2, if
separately approved, will atomically apply both the base values and this overlay,
then verify operator reconciliation and the `frontend-vm` target state. Full
commands, output, error/correction, cleanup, rollback, and the next permission
boundary are recorded in `step-11A1.md`.

### Journal entry 017 - Revised plan for floating-IP access, APIs, storage, and logs

The user authorized a documentation-only revision and explicitly requested a
floating-IP solution. No cluster, OpenStack, VM, Helm release, or application
state was changed.

The supplied source plan was copied unchanged into the repository:

```text
monitoring/BUET-PaaS_Monitoring_Plan_Updated_3Day_MVP.md
source and pre-revision SHA-256:
0f9c7496c5b121a9c9757c41c6846252b0e0ba5d2d93515fc28de4787e10fecc
```

The Downloads source remains unchanged. The revised repository copy has:

```text
SHA-256: 42913085c51d7a5372749c44d0767a09900ec7553c0667db09a39584dfd01950
```

The original MVP plan was preserved. Sections 22A-22E now define a dedicated
monitoring floating IP, HTTPS/authenticated Traefik ingress, least-privilege
OpenStack rules, protected API access, explicit current storage limitations,
and a later Loki + Grafana Alloy log phase. Raw ports
3000/9090/9093/9100/9115 remain prohibited from public exposure.

The preferred floating-IP target is a dedicated load-balancer VIP or designated
worker ingress entry point. The frontend floating IP must not be reused, and the
control-plane floating IP is only a last-resort fallback. Step 12A will determine
the exact path through a read-only preflight before any network change.

The immediate next permission boundary remains Step 11A2: apply and verify the
already prepared frontend-vm scrape overlay. The following browser-access work
starts at Step 12A and remains split into read-only inspection, local config,
OpenStack path creation, ingress application, and security/regression testing.

The first multi-update patch was rejected before writing because it targeted
the same file twice. Two smaller patches succeeded. Full revision rationale,
QA, rollback, and ordering are recorded in `step-12-plan.md`.

### Journal entry 018 - Step 11A2 frontend-vm scrape applied and verified

Permission received:

```text
Approve Step 11A2 - apply and verify frontend-vm scrape configuration
```

The prepared overlay was applied with pinned kube-prometheus-stack chart
`91.4.1` and digest
`sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9`.
Local and remote hashes for both values files matched before mutation.

Baseline:

```text
release revision: 1, deployed
active targets: 25
targets UP: 25
standalone targets: 0
nodes: 4/4 Ready
monitoring workloads: healthy
```

The server-side dry-run succeeded with Secrets hidden. A read-only jq formatter
first failed because of nested PowerShell quoting; a quote-free retry succeeded
and changed nothing.

The first atomic upgrade used a 15-minute timeout. Prometheus accepted the new
Secret reference, but a Grafana rolling-update Pod needed to pull an
approximately 460 MB image and initialize a fresh ephemeral SQLite database.
Successful migrations exceeded the total Helm timeout. Revision 2 failed with
`context deadline exceeded`; `--atomic` automatically created deployed revision
3 as a rollback to revision 1. The old Grafana Pod remained available, the
additional scrape reference disappeared, and the Grafana credential fingerprint
remained unchanged.

After verifying the clean rollback, the same configuration was retried with a
30-minute timeout. Revision 4 completed successfully and is deployed.

Final verification:

```text
Prometheus additional scrape Secret/key: present and exact
active targets: 26
targets UP/DOWN: 26/0
frontend target count: 1
frontend health/lastError: up/empty
frontend scrape URL: http://192.168.128.15:9100/metrics
up query: 1
node_uname_info nodename: frontend-vm
nodes: 4/4 Ready
monitoring workloads: healthy
Grafana: 3/3 Ready, 0 restarts
dashboard ConfigMaps: 23
node-exporter DaemonSet: 4/4 Ready
```

The pre-existing `2105062/to-do-backend-deployment` remained 0/1. No new
application regression appeared. On `frontend-vm`, node_exporter remained
enabled/active with zero restarts and 949 metrics; Nginx and Next.js both passed
local HTTP checks.

No OpenStack rule, VM configuration, application file, credential, or raw
public port was changed. The exact temporary validation directory was removed
and deletion verified. Full commands, outputs, error/correction, rollback, and
verification are recorded in `step-11A2.md`.

### Journal entry 019 - Step 12A partial read-only floating-IP/ingress preflight

Permission received:

```text
Approve Step 12A - read-only floating-IP and ingress preflight
```

No infrastructure mutation was authorized or performed.

The cluster already has a shared ingress architecture:

```text
default IngressClass: traefik
Traefik Service: LoadBalancer
MetalLB VIP: 192.168.128.200
public ingress floating IP: 192.168.64.121
ports: HTTP 80 and HTTPS 443
MetalLB pool: 192.168.128.200-192.168.128.225
advertisement: L2
current VIP announcer: k3s-worker-03
```

Live repository, Kubernetes, DNS, TCP, and HTTP evidence proved that student
application hostnames using `192.168.64.121.sslip.io` reach the Traefik VIP.
Both public TCP 80 and 443 are reachable. HTTPS currently presents the
self-signed `TRAEFIK DEFAULT CERT`, which Windows rejects as untrusted.

The proposed Grafana, Prometheus, and Alertmanager sslip.io hostnames resolve to
`192.168.64.121` and currently return 404 on both HTTP and HTTPS, so no route
collision exists.

No cert-manager installation, public TLS Secret, Traefik certificate resolver,
auth Middleware, or NetworkPolicy exists. Traefik is one replica on
`k3s-control-01`. MetalLB is currently healthy and lightly loaded, but all
speaker Pods have very high historical restart counts ending around
2026-09-23 08:04 UTC; recent announcer logs showed no errors.

The existing FIP is the proven lowest-complexity route, but cannot have
monitoring-only security-group restrictions on shared TCP 443. A dedicated FIP
offers stronger network isolation but requires verified Neutron port,
allowed-address-pair/anti-spoofing, security-group, quota, and possibly Octavia
information.

`k3s-user` has neither OpenStack CLI nor an authenticated OpenStack environment.
The computer-use skill found no available Horizon browser surface, so no login
or UI action was attempted.

Step 12A is paused pending Horizon screenshots for the `192.168.64.121`
Floating IP row, the port/fixed-IP details representing `192.168.128.200`, and
the Load Balancers list, plus confirmation whether the team controls a DNS
domain. Full commands, findings, errors/corrections, security tradeoffs, and the
evidence request are recorded in `step-12A.md`.

#### Step 12A completion - existing FIP and sslip.io selected

The user supplied the requested Horizon evidence:

```text
192.168.64.121 -> fixed IP 192.168.128.200, Active
port name: metallb-vip-port
port fixed IP: 192.168.128.200
port MAC: fa:16:3e:09:77:a8
port device/status: Detached/Down
floating-IP quota: 8/50 allocated
OpenStack ports: 23/500 used
Load Balancers page: unable to retrieve load balancers
```

The detached dummy port is consistent with the verified MetalLB design: the
Neutron port reserves the address and holds the FIP association, while MetalLB
advertises the VIP from a K3s node. Public HTTP/HTTPS success proves the path is
operational.

The DNS misunderstanding was resolved before continuing: DNS `A` records map
IPv4 addresses; `AAAA` records map IPv6 addresses. A team-controlled domain is
not required for the MVP because sslip.io automatically resolves hostnames that
contain `192.168.64.121` to that IPv4 address.

The user explicitly selected:

```text
Use existing floating IP 192.168.64.121 with sslip.io hostnames
```

Selected URLs:

```text
https://grafana.monitoring.192.168.64.121.sslip.io
https://prometheus.monitoring.192.168.64.121.sslip.io
https://alerts.monitoring.192.168.64.121.sslip.io
```

No new FIP, Neutron port, MetalLB VIP, Octavia load balancer, or OpenStack
security-group rule will be created for the MVP. The revised monitoring plan
and `step-12-plan.md` were updated to replace the original dedicated-FIP
assumption with this evidence-selected path.

Step 12A is complete. No infrastructure state changed. Step 12B remains a
separately approved local-only preparation of the Ingress, trusted-TLS
references, authentication, security headers/rate limits, verification, and
rollback configuration.

### Journal entry 020 - Step 12B secure ingress prepared locally

Permission received:

```text
Approve Step 12B - prepare secure monitoring ingress configuration locally
```

This authorized repository preparation and offline validation only. No
Kubernetes, OpenStack, DNS, browser, or VM mutation was performed.

Added:

```text
monitoring/ingress/browser-access-values.yaml
monitoring/ingress/middlewares.yaml
monitoring/ingress/http-redirect-ingress.yaml
monitoring/ingress/kustomization.yaml
monitoring/ingress/README.md
step-12B.md
```

`monitoring/README.md` was updated only to replace stale pre-installation status
with the verified current state and mark browser ingress as not applied.

The configuration prepares HTTPS host routes for Grafana, Prometheus, and
Alertmanager on the selected sslip.io names. It references but does not create
one TLS Secret and separate Prometheus/Alertmanager Basic Auth Secrets. Grafana
keeps native named-user authentication with anonymous access and sign-up
disabled. Security headers, independent rate limits, correct external URLs, and
an HTTP-to-HTTPS redirect are prepared.

Offline validation with the pinned kube-prometheus-stack `91.4.1` chart and
Kubernetes `1.36.2` target succeeded:

```text
Helm lint: 1 chart linted, 0 failed
Helm template: succeeded
Kustomize render: succeeded
standalone objects: 10 Middleware, 1 Ingress
Grafana/Prometheus/Alertmanager Services: ClusterIP
credential/certificate payload keys in monitoring/ingress: none
```

The base values, standalone scrape overlay, and revised monitoring plan kept
their pre-step hashes. No application source was modified.

The first documentation patch was rejected atomically because an old README's
mojibake tree characters did not match. The first rendered-object count also
reported zero because its regex did not account for Windows CRLF. The patch was
split safely and the regex corrected to `\r?$`, yielding 10 Middleware and 1
Ingress. Neither issue changed infrastructure.

NetworkPolicy is deferred because current CNI policy enforcement has not been
demonstrated. Step 12C is the next permission boundary: select a trusted TLS
method and create the required TLS/auth Secrets without printing or committing
sensitive values. Full commands, outputs, hashes, and rollback boundaries are
in `step-12B.md`.

### Journal entry 021 - Step 12C TLS preflight found a trust-model blocker

Permission received:

```text
Approve Step 12C - prepare trusted TLS and authentication secrets
```

Before adding cluster-wide certificate machinery or credentials, a read-only
preflight rechecked cert-manager, Issuers, Certificate objects, target Secret
names, the default IngressClass, the monitoring Helm release, and existing
Ingress objects.

The cluster has no cert-manager namespace, Pods, CRDs, Helm release, Issuer, or
Certificate. None of the three planned Secrets exists. Monitoring remains Helm
revision 4 and deployed; no monitoring browser Ingress exists.

The decisive finding is that `192.168.64.121` is an RFC1918 private address.
Public ACME HTTP-01 validators cannot route to it. DNS-01 cannot be used for the
selected names because the team does not control the sslip.io DNS zone. sslip.io
also has documented shared-domain certificate rate-limit exhaustion. Installing
cert-manager and attempting Let's Encrypt production issuance would therefore
add cluster-wide resources without a dependable path to a trusted certificate.

No mutation was made. Authentication Secrets were also withheld so that
credentials are not prepared for transport over an unresolved TLS trust path.

The recommended immediately workable MVP choice is a private/team CA whose
public root is installed only on authorized devices. The preferred production
end state is a BUET/team-controlled subdomain using ACME DNS-01. A separate
explicit approval is required before adopting the private-CA trust model,
installing cert-manager, or creating any certificate/authentication Secret.

The first read-only SSH wrapper had unmatched nested quotes and exited before
running its checks. A simplified retry succeeded. Neither command changed live
state. Full evidence, options, and the exact continuation boundary are recorded
in `step-12C.md`.

The repository monitoring plan and `step-12-plan.md` were updated to preserve
this new constraint. The Downloads source remains unchanged at SHA-256
`0f9c7496c5b121a9c9757c41c6846252b0e0ba5d2d93515fc28de4787e10fecc`;
the revised repository plan is now
`3dae8ee165a7a4d7f6c9c7678f8f900887908f37c1e63a6b37baa5cc76f23f8c`.

#### Step 12C1 continuation - VPN-only internal TLS selected and prepared

The user clarified that monitoring is reachable only after OpenConnect VPN and
that the goal is clickable links rather than Internet exposure. Between plain
VPN HTTP and VPN-only internal TLS, internal TLS was selected because it
preserves the same link experience without transmitting login credentials in
clear text.

cert-manager was intentionally not installed. A minimal OpenSSL workflow
created four new Secrets in `monitoring`:

```text
monitoring-internal-ca              Opaque
monitoring-public-tls               kubernetes.io/tls
monitoring-prometheus-basic-auth    kubernetes.io/basic-auth
monitoring-alertmanager-basic-auth  kubernetes.io/basic-auth
```

No password, password hash, certificate private key, or CA private key was
printed or committed. The TLS leaf covers all three monitoring sslip.io names,
expires on 2027-09-24, and chains to the internal CA expiring on 2031-09-23.
Both stored certificate/private-key pairs matched.

After creation, Helm remained revision 4/deployed, monitoring Ingress count
remained zero, all nine monitoring Pods were Ready with zero restarts, all four
nodes were Ready, and no temporary key files remained. No OpenStack, DNS, VM,
application, or Ingress change occurred.

Three non-mutating wrapper errors were corrected: a final PowerShell carriage
return after successful script completion, an over-escaped JSONPath, and local
PowerShell expansion of awk `$1`-`$4`. No Secret was recreated or overwritten.
Full certificate metadata, resource structure, health evidence, and error trace
are in `step-12C.md`.

#### Step 12C2 - CA public certificate and Windows trust instructions

Permission received to export only the internal CA public certificate and
prepare Windows trust instructions. `ca.crt` was read from the Kubernetes
Secret; no CA/leaf private key or authentication password was read or printed.

Added a public `.crt`, a fingerprint-pinned validation/install helper, and
manual trust/rollback guidance under `monitoring/ingress`. Validation succeeded
with the expected SHA-256 fingerprint
`735C690E91323B973F2069BC1BEB23A5CD4B96F376953D8D56D37196DF8EDE18`.
The exact CA remained absent from `Cert:\CurrentUser\Root`, proving this step did
not mutate the Windows trust store.

Three local compatibility issues were traced and corrected: Bash-style line
continuation caught before execution, execution-policy blocking before script
load, and Windows PowerShell 5 parameter-time `$PSScriptRoot` behavior. The
successful run was validation-only. No system execution policy was changed.

Step 12C2 is complete. CA installation remains a deliberate manual action using
the reviewed `-Install` switch, and Step 12D Ingress apply remains separately
permission-gated. Full commands, outputs, hashes, and rollback instructions are
in `step-12C.md` and `monitoring/ingress/WINDOWS-TRUST.md`.

The user subsequently validated the exact CA fingerprint and explicitly ran the
helper with `-Install` from their own Windows Command Prompt. It confirmed
installation in `Cert:\CurrentUser\Root`. An earlier CMD attempt incorrectly
used PowerShell backtick line continuation and changed nothing; the successful
form was a single-line command with the absolute repository path. Browser
restart is required before HTTPS verification. Trust is scoped to that Windows
user; other authorized devices/users must install the public CA separately.

### Journal entry 022 - Step 12D authenticated VPN ingress applied

Permission received:

```text
Approve Step 12D - apply admin-only authenticated VPN monitoring ingress
```

The before-state showed Helm revision 4 deployed, four Ready nodes, healthy
monitoring Pods, no monitoring browser Ingress/Middleware, and both tested
student routes returning HTTP 200. The three planned hostnames resolved to the
existing VPN-reachable `192.168.64.121` ingress path.

Server-side dry runs passed for ten Traefik Middleware objects, one HTTP redirect
Ingress, and the pinned kube-prometheus-stack `91.4.1` upgrade. The live change
then applied those standalone objects and ran an atomic Helm upgrade with the
base values, frontend VM scrape overlay, and browser-access overlay. Helm
completed successfully at revision 5; the failure-only cleanup branch did not
run.

Grafana took several minutes to migrate its existing database and temporarily
showed 2/3 containers Ready while the old Pod remained available. Migration
logs completed successfully; the new Pod became 3/3 with zero restarts. All
nine monitoring Pods and all four nodes are healthy, and every monitoring
Service remains `ClusterIP`.

Verified outcomes:

```text
all three HTTP hosts -> 301 HTTPS
Grafana health -> 200 with valid internal TLS
Prometheus and Alertmanager without auth -> 401
Prometheus and Alertmanager with Secret-backed auth -> 200
Grafana anonymous dashboard API -> 401
Grafana authenticated dashboard count -> 23
Prometheus targets -> 26/26 UP
frontend-vm exporter -> UP
raw ports 3000/9090/9093/9100 -> closed on 192.168.64.121
student hello route -> 200
student dummy-dev-frontend route -> 200
```

No credential or private key was printed. No OpenStack, DNS, security-group,
floating-IP, VM, application-source, or existing application-resource change
was made.

Several non-mutating wrapper issues were traced: nested PowerShell/SSH quote
escaping broke one baseline wrapper and two `jq` queries; one `jq` expression
had pipe-precedence wrong; a final carriage return reached `wc`; and Windows
`curl` could not find a CRL endpoint for the private CA. Quote-safe Bash stdin,
a corrected `$t` binding, direct ConfigMap/API counting, and
`--ssl-no-revoke` (never `--insecure`) resolved them. TLS chain and hostname
verification returned result 0.

Full commands, hashes, outputs, errors, and the exact rollback boundary are in
`step-12D.md`. Step 12E remains separately permission-gated for manual
trusted-browser login/UI checks and screenshots; port-forward is no longer
required for normal admin access through these VPN links.

After all checks passed, the exact remote staging directory
`/tmp/buet-paas-step12d.1HXUlC` and the single local temporary rendered manifest
were removed using validated paths. Repository files and live Kubernetes
resources were not part of that cleanup.

### Journal entry 023 - Step 12E manual browser verification started

Permission received:

```text
Approve Step 12E - manually verify trusted-browser monitoring access
```

The browser-control inventory returned no available apps or browsers. Opening
the Grafana URL in Chrome returned `Browser is not available: chrome`; the
visible built-in browser returned `Browser is not available: iab`; lookup by
URL returned `No browser is available`. These were non-mutating capability
errors. No authentication dialog was automated and no TLS warning was bypassed.

The full manual checklist and required screenshots are recorded in
`step-12E.md`. Automated prerequisites from Step 12D remain passing, but Step
12E is intentionally not marked complete until the user opens all three links
from a VPN-connected, CA-trusting browser and supplies the UI evidence.

#### Step 12E-1 - Grafana dashboard list verified

The user supplied a screenshot of the Grafana Dashboards page. Grafana rendered
normally after login, no certificate warning appeared, and the provisioned
Alertmanager, CoreDNS, Grafana, Kubernetes, Node Exporter, and Prometheus
dashboard groups were visible. No credential appeared in the screenshot. This
confirms the trusted-browser/login/list portion; the Step 12D API count remains
the exact evidence for 23 dashboards. Nodes Overview is the next sequential
manual check.

#### Step 12E-2 - Grafana Nodes Overview verified

The supplied `Kubernetes / Compute Resources / Nodes Overview` screenshot shows
a one-hour time range, four nodes, 62 Pods, populated cluster CPU/memory panels,
and per-node CPU and memory series for `k3s-control-01` and all three workers.
No `No data` or panel error is visible. The Grafana browser portion is complete;
Prometheus Target health is the next sequential manual check.

#### Step 12E-3 - Prometheus Target health verified

The authenticated `/targets` screenshot shows the Prometheus Target health UI
and green `UP` states for the visible Grafana, Alertmanager, API server, CoreDNS,
and kubelet pools. Kubelet pools report `4 / 4 up`; no `DOWN` target is visible.
This is consistent with the Step 12D API count of 26/26 UP. The node-count query
is the remaining Prometheus browser check.

#### Step 12E-4 - Prometheus node-count query verified

The screenshot shows `count(kube_node_info)` executing successfully with one
result series and value `4`. This matches the four Ready k3s nodes. Prometheus
trusted-browser, authentication, target-health, and query checks are complete;
Alertmanager Alerts is the next sequential manual check.

#### Step 12E-5 - Alertmanager Alerts and Silences verified

The authenticated Alertmanager Alerts screenshot shows one ungrouped alert and
four alerts for namespace `2105062`. A second screenshot shows the Silences UI
with no active, pending, or expired silence listed. No silence was created and
no credential was exposed. The read-only Status page is the final sequential
browser check.

#### Step 12E-6 - Alertmanager Status verified; Step 12E complete

The user supplied a text excerpt of the authenticated Alertmanager Status page.
It shows `Cluster Status: disabled`, no peers, version metadata (branch `HEAD`,
build date `20260816-16:36:04`, Go `1.26.6`), and the start of the Config
section. The full configuration was not supplied or recorded. Disabled cluster
peering is expected with the current single Alertmanager replica; it does not
mean the Alertmanager service is down. Alerts had already rendered and the
authenticated API check returned HTTP 200.

All Step 12E browser checks are now complete. Grafana, Prometheus, and
Alertmanager were accessed through their VPN HTTPS links without port-forward.
No browser certificate warning or login failure was reported. No Kubernetes,
OpenStack, application, alert, or silence mutation occurred in this step. The
five visible alerts remain for a separately scoped operational review.

### Journal entry 024 - Three-day continuation revised after Step 12E

The user requested the next steps according to the 3-day plan and authorized a
plan update only. No live command or infrastructure mutation was performed.

Current mapping:

```text
Day 1 core monitoring and browser access: complete
Day 2 standalone VM monitoring: frontend-vm complete; remaining VMs pending
Day 2 Blackbox service probes: pending
Day 3 dashboard and useful alert rules: pending
```

The continuation was revised because persistence sizing before adding the
intended exporters and probes would measure only a partial ingestion load. The
new order starts with Step 13A, a read-only audit of the five visible alerts,
current health, VM exporter readiness, confirmed service endpoints, and
storage/capacity evidence. Remaining VM exporters then proceed one VM per
approval, followed by confirmed Blackbox probes and the provisioned dashboard
and alert rules. Persistence is sized after at least 48 hours of representative
load.

Project-scoped monitoring for normal BUET-PaaS users is separated from the raw
admin tools. Loki + Alloy remains a post-MVP pilot after storage, privacy,
retention, and access review. Headlamp remains deferred.

The detailed permission gates, acceptance criteria, and immediate approval
phrase are recorded in `step-13-plan.md`; Section 22E of the main monitoring
plan and the historical `step-12-plan.md` status were updated accordingly.

### Journal entry 025 - Step 13A read-only audit completed

Permission received:

```text
Approve Step 13A - run read-only stability, alerts, targets, and capacity audit
```

No live state was changed. Helm revision 5 remains deployed, all four nodes and
nine monitoring Pods are Ready, and Prometheus has 26/26 targets UP.

The alert audit found four actionable warnings, all caused by the existing
`2105062/to-do-backend-deployment` failure. The application starts and listens
on port 8000, but generated readiness and liveness probes call `/`, receive 404,
and the liveness probe restarts the container. `Watchdog` is intentionally
always active and `InfoInhibitor` is a suppressed built-in helper. One
`CPUThrottlingHigh` info alert was pending and had not entered Alertmanager.
No alert was silenced or edited.

VM inspection confirmed frontend node_exporter active. Database, registry,
k3s-user, and backend are active but have no exporter; database is selected as
the next VM. SonarQube reports `UP` through its HTTP API, but SSH stopped at a
changed host-key warning. The fingerprint is recorded in `step-13A.md` and must
be independently verified before any SonarQube VM work.

Confirmed future Blackbox endpoints returned success for frontend, backend,
deployer, Harbor, and SonarQube. Harbor redirects HTTP to HTTPS; the final probe
must validate TLS rather than inherit the audit-only insecure diagnostic.

Prometheus currently has about 4.28 hours of data, 142,221 active series,
approximately 453 MiB of block plus WAL data, and no PVC. Prometheus, Grafana,
and Alertmanager storage remains ephemeral. The default `local-path`
StorageClass has reclaim policy `Delete` and does not support expansion. This
is insufficient evidence for persistence sizing, so Step 17 remains blocked
until the intended targets/probes have produced at least 48 hours of
representative ingestion.

Read-only command issues were traced: the distroless Prometheus image has no
shell, one nested awk expression was misquoted, direct control-node SSH used
the wrong key, and two nested loop wrappers failed quoting before checks. API
metrics, unfiltered listeners, the established k3s-user SSH path, and six
explicit control-node `nc` checks produced the required evidence. No retry
changed state.

Full commands, matrices, capacity evidence, errors, and the next split approval
boundaries are in `step-13A.md`. The next permission is Step 14A1, which changes
only database-vm by installing and locally verifying node_exporter.

### Journal entry 026 - Step 14 VM-local node_exporter installations completed

Permission received for Step 14A1 and sequential automatic approval for the
remaining eligible VMs. The pinned official node_exporter `1.12.1` archive and
binary SHA-256 values were verified independently on every host before
installation. No unverified artifact was installed.

Completed in order:

```text
database-vm    192.168.128.92:9100   active/enabled, NRestarts=0
registry-vm-2  192.168.128.152:9100  active/enabled, NRestarts=0
k3s-user       192.168.128.151:9100  active/enabled, NRestarts=0
backend-vm     192.168.128.131:9100  active/enabled, NRestarts=0
```

Every service uses a no-login `node_exporter` user, the reviewed hardened unit,
and a private-fixed-IP-only listener. Local `/metrics` checks passed. MongoDB,
Docker/Harbor, Kubernetes/Helm tooling, and the BUET backend all passed their
respective before/after regression checks. Existing k3s-user port-forward
listeners were not changed. Temporary download and transfer files were removed.

After the four installations, all four k3s nodes remained Ready, all nine
monitoring Pods were Running with zero restarts, Prometheus was Ready,
`count(up)` remained 26, and `count(up == 0)` returned no series. Prometheus was
not changed and therefore does not yet know about the four new exporters.

Control-plane checks returned HTTP 200 for the already configured frontend
exporter and timed out for the four new endpoints. This is the expected secure
state until the existing `monitoring-exporter` OpenStack security group is
attached to those VMs. No security group, firewall, scrape values, Helm release,
Kubernetes object, or application configuration was changed.

SonarQube was not modified. Its changed SSH host key remains blocked pending
independent verification of fingerprint
`SHA256:+FDZkJcqkKQULlQOuWUukqFHZNqWzltyjhwPE5G/AzE`.

Non-mutating issues were recorded: two PowerShell/remote-shell quoting attempts
failed before valid execution; one `grep -m1` metrics check caused an expected
early-pipe curl message; the old k3s-user systemd reported an unrelated snapd
`RestartMode` warning; a variable-based reachability wrapper was invalid; and
the pre-existing Prometheus port-forward closed during a check. Corrected
variable-free commands and the Kubernetes API service proxy produced the final
evidence. Details and rollback boundaries are in `step-14A1.md` through
`step-14D1.md`.

### Journal entry 027 - Step 14A2 control-plane exporter reachability verified

Permission received:

```text
Approve Step 14A2 - verify control-plane reachability to all standalone VM exporters
```

The user's four Horizon screenshots showed `monitoring-exporter` attached to
database-vm, registry-vm-2, k3s-user, and backend-vm while their existing
security groups remained attached. The displayed TCP 9100 source was the
established `k3s-secgroup`, not `0.0.0.0/0`.

A read-only check originating on `k3s-control-01` returned HTTP 200 and exactly
one `node_exporter_build_info` series from frontend-vm and all four newly
installed exporters. Direct host checks showed the four new services active,
enabled, version 1.12.1, zero restarts, private-IP-only listeners, and zero
failed systemd units.

Regression checks showed all four Kubernetes nodes Ready, all nine monitoring
Pods Running with zero restarts, Prometheus Ready, 26 existing UP targets, no
DOWN target series, and Helm release revision 5 still deployed. The count
remains 26 because no scrape configuration or live monitoring state was changed.

Full endpoint and service evidence is in `step-14A2.md`. The next permission
boundary is repository-only Step 14A3: add the four reachable endpoints to the
declarative scrape overlay and run pinned offline Helm lint/render validation.

### Journal entry 028 - SonarQube trust blocker cleared and exporter installed

The user supplied a successful interactive SSH transcript for `sonarqube`. Its
ED25519 fingerprint exactly matched the fingerprint recorded in Step 13A:

```text
SHA256:+FDZkJcqkKQULlQOuWUukqFHZNqWzltyjhwPE5G/AzE
```

This cleared the previous identity blocker. Under the user's earlier sequential
all-VM auto-approval, Step 14E1 proceeded with read-only preflight, checksum-
pinned node_exporter 1.12.1 installation, and regression checks.

The exporter is active, enabled, restart-free, and bound only to
`192.168.128.33:9100`; local metrics succeeded. Docker remained active,
SonarQube and its database containers retained their healthy states, and the
SonarQube status API remained `UP` with HTTP 200. Two pre-existing defunct
`grep` processes were observed before and after and were not touched.

All four k3s nodes remained Ready and Prometheus remained Ready with its 26
existing UP targets. The control plane cannot yet reach the new SonarQube
exporter because its `monitoring-exporter` security group attachment is still
pending. No OpenStack, firewall, Kubernetes, Helm, Prometheus, SonarQube, or
database configuration changed. Full evidence is in `step-14E1.md`.

### Journal entry 029 - SonarQube restricted exporter path verified

The user supplied a Horizon Overview screenshot showing `monitoring-exporter`
attached to `sonarqube`, with the existing `web-&-ssh` and `default` groups
retained. TCP 9100 was sourced from the established `k3s-secgroup`, not
`0.0.0.0/0`.

A read-only request from `k3s-control-01` returned HTTP 200 and exactly one
`node_exporter_build_info` series from `192.168.128.33:9100/metrics`. The
service remained active/enabled with zero restarts and a private-IP-only
listener. SonarQube remained UP with HTTP 200 and the host had zero failed
systemd units.

No state was changed during verification. All six standalone exporters are now
installed and reachable over their restricted control-plane paths. Frontend is
already scraped; the other five remain absent from Prometheus pending the
repository-only Step 14A3 preparation and a later separately approved apply.
Full evidence is in `step-14E2.md`.

### Journal entry 030 - Step 14A3 five new scrape targets prepared offline

Permission received:

```text
Approve Step 14A3 - prepare and offline verify all five new VM scrape targets
```

The declarative `standalone-node-exporters` overlay retained frontend and added
database, registry, k3s-user, backend, and SonarQube using only private IPs and
stable instance/service/environment/deployment labels. The prepared overlay
SHA-256 is
`24c43588815d1b390036e2ec0ab53fab66cc7fd5e4b18b486233893ac9d40248`.

Helm 3.22.0 pulled the exact kube-prometheus-stack 91.4.1 OCI chart with digest
`sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9`.
Lint passed with zero failures. The focused additional-scrape Secret rendered
and decoded to one job, six targets, six unique target addresses, and six
instance labels.

The first decoder retained YAML quote characters and failed base64 decoding; a
second sed expression was parsed locally by PowerShell. A quote-safe decoder
then validated the same rendered payload. These errors were non-mutating.

Live Helm remained revision 5, Prometheus remained Ready with 26 total UP
targets and one standalone exporter target, and all four nodes remained Ready.
The exact temporary validation directory was enumerated, removed, and confirmed
absent. No Helm upgrade or Kubernetes/Prometheus mutation occurred. Full
evidence and rollback are in `step-14A3.md`.

### Journal entry 031 - Step 14A4 standalone VM targets applied and verified

Permission received:

```text
Approve Step 14A4 - atomically apply and verify all standalone VM scrape targets
```

Before-state was Helm revision 5 deployed, four Ready nodes, nine healthy
monitoring Pods, Prometheus Ready, 26 UP targets, and one live standalone
exporter. All six private exporter endpoints returned HTTP 200 from
`k3s-control-01`. Remote hashes of the base, scrape, and browser-access inputs
matched the reviewed repository files.

The first server dry-run stopped before mutation because `helm upgrade` does
not accept the supplied lint/template-only `--kube-version` flag. The corrected
server dry-run used `--hide-secret`, planned revision 6, and left live revision
5 unchanged. The live command then used the pinned chart 91.4.1 and
`--atomic --timeout 15m`; it completed as deployed revision 6 without rollback.

Prometheus returned six `up=1` standalone series with the exact intended
instance/service labels. Total UP targets increased from 26 to 31, exactly the
five additions, and no DOWN series exists. Four nodes and all nine monitoring
Pods remained healthy with zero restarts.

VPN browser regression checks returned Grafana 200, Prometheus/Alertmanager
401 without credentials, and HTTP-to-HTTPS 301. Windows Schannel initially
reported the known unavailable private-CA CRL status; `--ssl-no-revoke`
preserved CA and hostname verification and returned TLS verification result 0.
No insecure TLS bypass was used for monitoring ingress.

All six VM exporter services remained active with zero restarts. Frontend,
MongoDB, Harbor, Kubernetes admin tooling, BUET backend, and SonarQube health
checks passed. The isolated staging directory was enumerated, deleted, and
confirmed absent. No credential was printed. Full commands, evidence, and the
revision-5 rollback command are in `step-14A4.md`.

### Journal entry 032 - Step 15A Blackbox endpoint and TLS preflight completed

Permission received:

```text
Approve Step 15A - run read-only Blackbox endpoint and TLS preflight
```

No state changed. Direct checks confirmed the BUET-PaaS frontend HTTP 200 with
its page marker, backend `/health` HTTP 200 with status ok and MongoDB
connected, and SonarQube status API HTTP 200 with status UP. The deployer
ClusterIP Service has a Ready endpoint and its service proxy `/health` returned
status ok; stable service DNS is selected instead of a Pod IP.

Harbor HTTP returned 308 to its private-IP HTTPS URL. Its leaf certificate SAN
covers `192.168.128.152`; the matching Harbor-CA verified the chain and IP under
TLS 1.3, and the API returned HTTP 200 with all components healthy. Default
trust failed as expected because the private CA is not globally installed.
Future configuration must mount the public CA and must not disable TLS
verification.

No existing Blackbox resource or service port 9115 was found. Current nodes
have ample CPU/memory for the small probe set. Since Blackbox accepts target
parameters, the prepared design keeps it ClusterIP-only and adds a
Prometheus-only ingress NetworkPolicy; it never accepts user-controlled targets.

One nested curl timing format and later jsonpath/JSON marker patterns were
misquoted. Corrected literal checks supplied the valid evidence; all attempts
were read-only. Helm remained deployed revision 6 and Prometheus remained at
31 UP targets with none DOWN. Full certificate metadata, endpoint matrix,
security constraints, and corrections are in `step-15A.md`.

### Journal entry 033 - Step 15B secure Blackbox configuration prepared

Permission received:

```text
Approve Step 15B - prepare and offline verify secure Blackbox configuration
```

Pinned prometheus-blackbox-exporter chart 11.18.0 / app v0.28.0 was pulled and
verified offline. The rendered container reference is immutable at image digest
`sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc`.
Repository configuration now defines four narrowly scoped
HTTP modules, strict Harbor public-CA verification, a ClusterIP-only service,
non-root/read-only runtime controls, bounded resources, and a NetworkPolicy
allowing port 9115 only from the live Prometheus Pod identity.

The initial chart render exposed its deep-merged generic `http_2xx` module.
The final overlay explicitly removes it, leaving only frontend, JSON-ok,
Harbor-TLS, and SonarQube-UP modules. No private key or credential is present.
Blackbox v0.28.0 loaded the exact rendered config and returned that the config
file was valid.

Rollout inputs are split deliberately: `targets-frontend.yaml` renders one
canary ServiceMonitor for Step 15C, while `targets-all.yaml` renders the five
preflight-confirmed services for later Step 15D. Both combinations passed Helm
lint; the canary rendered one ServiceMonitor, the full overlay rendered five,
and neither rendered an Ingress. The standalone Kustomize output rendered one
public-CA ConfigMap and one Prometheus-only NetworkPolicy.

Final live checks proved no implementation occurred: Helm remained revision 6,
all four nodes and nine monitoring Pods stayed healthy, Prometheus remained at
31 UP with zero DOWN, and no Blackbox resource existed. The ephemeral validator
container, newly pulled image cache, and isolated staging directory were
removed. Assertion and shell-quoting corrections were non-mutating and are
documented in `step-15B.md`.

Next permission boundary:

```text
Approve Step 15C - install Blackbox Exporter and activate only the frontend canary probe
```

### Journal entry 034 - Step 15C frontend Blackbox canary installed

Permission received:

```text
Approve Step 15C - install Blackbox Exporter and activate only the frontend canary probe
```

Pre-state was clean: no Blackbox resource existed, kube-prometheus-stack
remained revision 6, all four nodes and nine monitoring Pods were healthy, and
Prometheus reported 31 UP with zero DOWN. Repository input hashes and pinned
chart 11.18.0 OCI/archive digests matched Step 15B.

The public Harbor CA ConfigMap and Prometheus-only NetworkPolicy passed a
server-side dry run using the server-bundled k3s kubectl. The separate
Blackbox Helm release also passed server dry-run with base values plus only
`targets-frontend.yaml`. The standalone objects were applied, followed by an
atomic Helm install. Helm returned revision 1 deployed; rollback was not used.

The resulting Service is ClusterIP-only on 9115 and has no Ingress. The Pod is
Ready with zero restarts, immutable image digest, non-root UID/GID 1000,
read-only root filesystem, all capabilities dropped, no privilege escalation,
no service-account token mount, and the public CA mounted read-only. The live
CA byte hash matches the repository, and the config contains exactly four
reviewed modules with no generic `http_2xx` module.

Exactly one frontend ServiceMonitor exists. Prometheus reports its target UP
with empty error, `probe_success=1`, HTTP 200, IPv4, and a millisecond-scale
duration. Total UP increased from 31 to 32, zero DOWN remains, all six
standalone exporters remain UP, four nodes remain Ready, and all ten monitoring
Pods are Running with zero restarts. No backend, deployer, Harbor, or SonarQube
probe was introduced.

A display-newline CA hash mismatch and an active-target scrape-URL selector
assumption were corrected using byte-exact output and Kubernetes discovery
labels; neither changed state. The isolated staging directory was enumerated
and removed. Full evidence and the unexecuted rollback procedure are in
`step-15C.md`.

Next permission boundary:

```text
Approve Step 15D1 - prepare and offline verify the frontend plus backend Blackbox target overlay
```

### Journal entry 035 - Step 15D1 backend probe overlay prepared

Permission received:

```text
Approve Step 15D1 - prepare and offline verify the frontend plus backend Blackbox target overlay
```

The repository now contains a cumulative `targets-frontend-backend.yaml`
overlay. It retains the healthy frontend target and adds only backend
`http://192.168.128.131:8020/health` through the reviewed `http_json_ok`
module. Both targets have stable service, environment, and deployment labels;
deployer, Harbor, and SonarQube are absent.

Pinned chart 11.18.0 OCI/archive digests and all repository input hashes
matched. Helm lint passed independently for frontend-only, frontend-plus-
backend, and all-target stages. Their renders contained one, two, and five
ServiceMonitors respectively. The cumulative render's exact target names,
URLs, modules, and labels were inspected, and a negative assertion confirmed
that no later-stage target was present. The immutable v0.28.0 exporter image
accepted the rendered four-module configuration; no generic module or private
key was present.

Before and after validation, live Blackbox revision 1 remained deployed with
exactly the frontend ServiceMonitor. Its target stayed UP with
`probe_success=1` and HTTP 200; Prometheus remained at 32 UP and zero DOWN.
Thus Step 15D1 changed only repository files. The isolated staging directory
and newly pulled validator image cache were removed. Full hashes and evidence
are in `step-15D1.md`.

Next permission boundary:

```text
Approve Step 15D2 - atomically apply and verify the backend Blackbox probe
```

### Journal entry 036 - Step 15D2 backend Blackbox probe deployed

Permission received:

```text
Approve Step 15D2 - atomically apply and verify the backend Blackbox probe
```

Initial preflight confirmed Blackbox revision 1 frontend-only at 32 UP/zero
DOWN and backend `/health` returning status ok with MongoDB connected. Pinned
chart and input hashes matched, and the cumulative overlay passed server dry
run before each atomic upgrade.

Two acceptance failures triggered the prepared automatic rollback safely. The
first revision-2 attempt produced successful frontend/backend probes, but the
verifier raced Prometheus discovery and rolled back to the revision-1 config as
deployed revision 3. The second revision-4 attempt proved two active UP targets
and two successful HTTP-200 probes, but `count(up)` remained 32. It rolled back
to the healthy config as revision 5.

Diagnosis showed that chart metric relabeling distinguishes probe metrics but
not Prometheus-generated `up` series. Both ServiceMonitors therefore had the
same target labels. All staged overlays were corrected with supported
pre-scrape `additionalRelabeling` for instance, target, service, environment,
and deployment type. All three rollout stages passed offline lint/render again,
and the pinned exporter accepted the configuration.

The final atomic upgrade from revision 5 deployed revision 6. Exactly two
ServiceMonitors and active targets now exist with unique labels. Frontend and
backend both report `probe_success=1`, HTTP 200, bounded durations, health UP,
and empty errors. Prometheus now reports 33 UP and zero DOWN. Six standalone
exporters, four nodes, and all ten monitoring Pods remain healthy; Blackbox had
no restart and its logs contain only INFO entries. kube-prometheus-stack stayed
at revision 6.

The manual API service-proxy probe was denied while Prometheus scraping worked,
consistent with the Prometheus-only NetworkPolicy. No public exposure or
application change occurred. The validation image cache and isolated staging
directory were removed. Full attempt history, hashes, corrections, rollback
evidence, and final metrics are in `step-15D2.md`.

Next permission boundary:

```text
Approve Step 15D3 - prepare and offline verify the frontend, backend, and deployer Blackbox target overlay
```

### Journal entry 037 - Step 15D3 deployer probe overlay prepared

Permission received:

```text
Approve Step 15D3 - prepare and offline verify the frontend, backend, and deployer Blackbox target overlay
```

The repository now contains cumulative
`targets-frontend-backend-deployer.yaml`. It retains the live frontend and
backend targets and adds only the proven in-cluster deployer Service DNS health
URL through `http_json_ok`. Explicit pre-scrape labels are present on all three
targets; Harbor and SonarQube are absent.

Pinned chart 11.18.0 OCI/archive digests matched prior evidence. Helm lint and
render passed for the one-, two-, three-, and five-target stages. The new
three-target render contains exactly three ServiceMonitors, two uses of
`http_json_ok`, and all exact names and URLs. Negative assertions excluded the
later targets. The immutable Blackbox v0.28.0 image accepted the four-module
configuration. ClusterIP-only exposure, zero Ingresses, the Prometheus-only
NetworkPolicy, container hardening, and strict Harbor CA verification all
remain intact.

An initial assertion expected eight spaces before rendered module list items;
Helm emitted six. The rendered modules were correct. The assertion was fixed,
and the full verifier then exited successfully. Before and after checks proved
the live release remained revision 6 with only frontend/backend, Prometheus 33
UP and zero DOWN, four Ready nodes, and ten healthy monitoring Pods. No live
resource changed. Temporary validation files and the unused validator image
cache were removed. Complete hashes and evidence are in `step-15D3.md`.

Next permission boundary:

```text
Approve Step 15D4 - atomically apply and verify the deployer Blackbox probe
```

### Journal entry 038 - Step 15D4 deployer Blackbox probe deployed

Permission received:

```text
Approve Step 15D4 - atomically apply and verify the deployer Blackbox probe
```

Preflight proved Blackbox revision 6 had only the healthy frontend/backend
targets, Prometheus was 33 UP with zero DOWN, and the deployer Service proxy
returned `{"status":"ok"}`. Repository hashes and the pinned chart 11.18.0
OCI/archive identities matched the reviewed Step 15D3 evidence.

The cumulative three-target inputs passed Helm server dry-run, then an atomic
upgrade deployed Blackbox revision 7. The bounded verifier converged without
rollback. Frontend, backend, and deployer each report `probe_success=1`, HTTP
200, bounded duration, target health UP, empty error, and unique stable labels.
Prometheus now reports 34 UP and zero DOWN.

Regression checks confirmed all six standalone exporters UP, four nodes Ready,
ten monitoring Pods Running with zero restarts, the frontend marker present,
backend status ok with MongoDB connected, and deployer status ok.
kube-prometheus-stack stayed revision 6. Blackbox remains ClusterIP-only with
no Ingress, the same Prometheus-only NetworkPolicy, immutable image, non-root
read-only container controls, and no suspicious log entries. No application,
OpenStack, DNS, ingress, public port, credential, or TLS secret changed.

The exact staging directory was enumerated and removed. Full hashes, probe
results, dry-run evidence, security state, and rollback design are recorded in
`step-15D4.md`.

Next permission boundary:

```text
Approve Step 15D5 - prepare and offline verify the frontend, backend, deployer, and Harbor Blackbox target overlay
```

### Journal entry 039 - Step 15D5 strict-TLS Harbor overlay prepared

Permission received:

```text
Approve Step 15D5 - prepare and offline verify the frontend, backend, deployer, and Harbor Blackbox target overlay
```

The repository now contains cumulative
`targets-frontend-backend-deployer-harbor.yaml`. It retains the three live
targets and adds only Harbor at `https://192.168.128.152/api/v2.0/health`
through `http_harbor_tls`; SonarQube is absent. Harbor has unique stable labels
and uses the mounted public CA with `insecure_skip_verify: false`.

A fresh read-only Harbor check matched the reviewed CA byte hash and SHA-256
fingerprint. CA-verified HTTPS returned verification result 0, HTTP 200,
top-level healthy status, and healthy component statuses. The pinned chart
OCI/archive identities also matched.

Helm lint/render passed for the cumulative one-, two-, three-, four-, and five-
target stages. The four-target render has exactly four ServiceMonitors and the
expected one frontend, two JSON-ok, and one strict-TLS module selections.
SonarQube was excluded by a negative assertion. The immutable v0.28.0 exporter
accepted the four-module configuration; no generic module or private key was
present. ClusterIP-only exposure, zero Ingresses, NetworkPolicy, CA mount, and
container hardening remained intact.

Before and after checks proved live Blackbox remained revision 7 with only
frontend/backend/deployer, Prometheus 34 UP and zero DOWN, four Ready nodes,
and ten healthy monitoring Pods. Harbor was not applied. The exact temporary
tree and unused validator Docker cache image were removed. Complete evidence
and hashes are in `step-15D5.md`.

Next permission boundary:

```text
Approve Step 15D6 - atomically apply and verify the Harbor Blackbox probe
```

### Journal entry 040 - Step 15D6 strict-TLS Harbor probe deployed

Permission received:

```text
Approve Step 15D6 - atomically apply and verify the Harbor Blackbox probe
```

Preflight proved Blackbox revision 7 had the three healthy prior probes,
Prometheus 34 UP with zero DOWN, and the live Harbor CA ConfigMap byte-for-byte
matched the reviewed public CA. CA-verified Harbor HTTPS returned HTTP 200 and
healthy overall/component status. Repository and pinned chart identities
matched Step 15D5.

The exact cumulative four-target inputs passed Helm server dry-run, then an
atomic upgrade deployed revision 8. The bounded verifier converged without
rollback. Frontend, backend, deployer, and Harbor are all UP with successful
semantic probes, HTTP 200, bounded duration, empty target errors, and unique
labels. Harbor additionally reports `probe_http_ssl=1`; its earliest leaf
certificate expiry is 2028-12-07 and passed the greater-than-90-days gate.
Prometheus now reports 35 UP and zero DOWN.

Regression checks confirmed six standalone exporters, four Ready nodes, ten
monitoring Pods with zero restarts, and healthy frontend/backend/deployer/
Harbor responses. Blackbox remains ClusterIP-only with no Ingress, the same
Prometheus-only NetworkPolicy, immutable image, public CA mount, and hardened
container. Logs had no error/fatal/panic. No application, Harbor setting,
certificate, Secret, DNS, OpenStack, or public port changed.

The exact staging directory was enumerated and removed. Full evidence, hashes,
TLS metrics, security state, and rollback design are in `step-15D6.md`.

Next permission boundary:

```text
Approve Step 15D7 - revalidate SonarQube and offline verify the final five-target Blackbox overlay
```

### Journal entry 041 - Step 15D7 final SonarQube overlay verified

Permission received:

```text
Approve Step 15D7 - revalidate SonarQube and offline verify the final five-target Blackbox overlay
```

A fresh read-only SonarQube status request returned HTTP 200, version
26.8.0.126808, and status UP. The existing `targets-all.yaml` hash remained
unchanged and contains only the four live targets plus SonarQube through the
reviewed `http_sonarqube_up` module with unique stable labels.

Pinned chart identities matched. All cumulative one- through five-target Helm
lint/renders passed. Exact final names, URLs, module counts, and SonarQube
target/service/instance relabeling were asserted. The immutable v0.28.0 binary
accepted the four-module config. ClusterIP-only exposure, zero Ingresses,
strict Harbor CA, NetworkPolicy, and container hardening remained intact.

Two first verifier attempts failed only because new assertions did not account
for Helm's quoted metric-relabel scalar and list-item dash serialization. The
rendered configuration was correct; the assertions were corrected, and the
complete suite passed. No live state changed. Before/after checks showed
Blackbox revision 8, four live probes, 35 UP, zero DOWN, four Ready nodes, and
ten monitoring Pods with zero restarts. SonarQube remains not live.

The exact temporary tree and unused validator image cache were removed. Full
evidence and hashes are in `step-15D7.md`.

Next permission boundary:

```text
Approve Step 15D8 - atomically apply and verify the SonarQube Blackbox probe
```

### Journal entry 042 - Step 15D8 final SonarQube probe deployed

Permission received:

```text
Approve Step 15D8 - atomically apply and verify the SonarQube Blackbox probe
```

Preflight proved Blackbox revision 8 had four healthy probes, Harbor SSL 1,
Prometheus 35 UP with zero DOWN, and SonarQube returned HTTP 200/status UP.
Repository and pinned chart identities matched the reviewed Step 15D7 inputs.

The exact final five-target inputs passed Helm server dry-run, then an atomic
upgrade deployed revision 9. The bounded verifier converged without rollback.
Frontend, backend, deployer, Harbor, and SonarQube all report
`probe_success=1`, HTTP 200, bounded duration, health UP, empty errors, and
unique stable labels. Harbor retained SSL 1 and safe certificate validity.
SonarQube's success proves the status-UP body requirement. Prometheus now
reports 36 UP and zero DOWN.

Regression checks confirmed all six standalone exporters UP, four nodes Ready,
ten monitoring Pods Running with zero restarts, and healthy direct responses
from all five services. Blackbox remains ClusterIP-only with no Ingress, the
Prometheus-only NetworkPolicy, immutable image, public Harbor CA mount, and
hardened container. Logs had no error/fatal/panic. No application, service
setting, certificate, Secret, DNS, OpenStack, or public port changed.

The exact staging directory was enumerated, removed, and confirmed absent.
Full evidence, hashes, final metrics, security state, and rollback design are
in `step-15D8.md`. Day 2 monitoring is complete: six VM exporters and five
service probes are live and healthy.

Next permission boundary:

```text
Approve Step 16A - prepare and offline verify the BUET-PaaS Monitoring Overview dashboard as code
```

### Journal entry 043 - Step 16A overview dashboard prepared and offline-verified

Permission received:

```text
Approve Step 16A - prepare and offline verify the BUET-PaaS Monitoring Overview dashboard as code
```

The repository now contains the 16-panel `BUET-PaaS Monitoring Overview`
dashboard with stable UID `buet-paas-overview`, schema version 39, the existing
Prometheus datasource UID, deterministic Kustomize ConfigMap generation, and a
repeatable offline verifier. It covers global target state, Kubernetes nodes
and workloads, six standalone VMs, five Blackbox services, firing alerts, CPU,
memory, and root-filesystem capacity.

Local JSON validation confirmed 16 unique panel IDs/titles and 16 Prometheus
queries. The isolated verifier rendered exactly one labeled ConfigMap with no
Secret or Ingress. The cluster's immutable Prometheus v3.14.0 image reported
`SUCCESS: 16 rules found` for the extracted expressions. Deployable inputs
also passed the secret-like-material scan.

Initial validation found malformed threshold-object closures in the draft JSON
and overly narrow/self-matching verifier assertions. These were corrected
locally before the final complete run; nothing defective was applied.

Read-only regression evidence showed Blackbox revision 9,
kube-prometheus-stack revision 6, 36 Prometheus targets UP, zero DOWN, and ten
monitoring Pods Running with zero restarts. The custom dashboard ConfigMap is
still absent, proving Step 16A made no live change. The exact temporary tree
and unused Docker validator image were removed. Full hashes and evidence are
in `step-16A.md`.

Next permission boundary:

```text
Approve Step 16B - atomically apply and verify the BUET-PaaS Monitoring Overview dashboard
```

### Journal entry 044 - Step 16B overview dashboard provisioned

Permission received:

```text
Approve Step 16B - atomically apply and verify the BUET-PaaS Monitoring Overview dashboard
```

Preflight matched the Step 16A JSON, Kustomization, and rendered ConfigMap
hashes. Grafana had 23 dashboard ConfigMaps; Blackbox was revision 9,
kube-prometheus-stack revision 6, and Prometheus 36 UP with zero DOWN.
The exact one-ConfigMap manifest passed server dry-run.

The first guarded apply removed the new ConfigMap after Grafana API
verification failed. `enforce_domain=true` redirected localhost reload/API
requests to the HTTPS hostname, whose internal CA the dashboard sidecar does
not trust. A read-only test proved the configured Host header works against
the local Grafana API. The corrected transaction created the same ConfigMap,
called the dashboard reload API successfully, and verified Grafana returned
UID `buet-paas-overview`, 16 panels, and `provisioned=true`.

All 16 PromQL expressions executed successfully against live Prometheus.
The key stat panels returned 36 targets UP, zero DOWN, four Ready nodes, six
standalone VMs UP, and five service probes UP. The dashboard HTTPS link passed
CA verification and redirected unauthenticated access to Grafana login.
Grafana now has 24 provisioned dashboard ConfigMaps. Monitoring remains 36 UP,
zero DOWN, ten Pods Running with zero restarts, and unchanged Helm revisions.

The localhost sidecar reload redirect should be corrected in a later approved
monitoring-stack configuration change so future dashboard edits reload
automatically. Step 16B made only the dashboard ConfigMap live. Temporary
staging was removed. Full evidence is in `step-16B.md`.

Next permission boundary:

```text
Approve Step 16C - prepare and offline verify the BUET-PaaS MVP alert rules
```

### Journal entry 045 - Step 16C focused alert rules prepared

Permission received:

```text
Approve Step 16C - prepare and offline verify the BUET-PaaS MVP alert rules
```

Read-only inventory found six firing alerts. `Watchdog` and `InfoInhibitor`
are expected; four warning alerts concern a crash looping `to-do-backend`
Pod and its Deployment in namespace `2105062`. The one-hour restart query
showed about 17 restarts for that Pod. Existing kube-prometheus-stack rules
already cover scrape failure, Kubernetes nodes, Pod crash loops, unavailable
Deployments, failed Jobs, and k3s node disk space.

One new PrometheusRule was prepared with four focused gaps: Blackbox semantic
probe failure, missing service probe targets, missing standalone VM exporter
targets, and low writable root disk on standalone VMs. A maintenance document
defines short, exact silences and handling of fleet-count alerts. The rule
selects the live `release=monitoring-stack` label.

Kustomize rendered one PrometheusRule with no Secret or ConfigMap. The rendered
object matched the source, and pinned Prometheus v3.14.0 `promtool` reported
`SUCCESS: 4 rules found`. All four exact expressions executed successfully
against live Prometheus with zero current matches. The new rule remains absent
from Kubernetes; 36 targets were UP and zero DOWN. Temporary validation files
and the unused validator image were removed. Full evidence and hashes are in
`step-16C.md`.

Next permission boundary:

```text
Approve Step 16D - atomically apply and verify the BUET-PaaS MVP alert rules
```

### Journal entry 046 - Step 16D focused alert rules deployed

Permission received:

```text
Approve Step 16D - atomically apply and verify the BUET-PaaS MVP alert rules
```

Preflight matched the reviewed Step 16C rule, Kustomization, and rendered
manifest hashes. The one-rule manifest passed server dry-run, and a guarded
transaction created `monitoring/buet-paas-mvp-alerts`. Rollback was prepared
but not triggered.

Prometheus loaded both rule groups. All four new alerts reported `health=ok`,
`state=inactive`, zero attached alerts, and recent evaluations. The rule object
count increased from 30 to 31. Six pre-existing built-in alerts remained
firing; a separate `CPUThrottlingHigh` appeared pending and was not from the
new rule set. Prometheus stayed at 36 UP and zero DOWN, monitoring Pods stayed
Running with zero restarts, and Helm revisions 6 and 9 were unchanged.

Pinned `promtool test rules` passed synthetic service-probe
pending/firing/resolved checks, missing-target hold periods, and VM disk-low
hold period. No real workload or metric was disrupted. The exact temporary
staging tree and unused validator image were removed. Full evidence and
script hashes are in `step-16D.md`.

Step 16E is the remaining MVP notification decision: retain authenticated
Alertmanager/Grafana UI review or configure a team-owned receiver with its
credential stored outside Git.

### Journal entry 047 - Step 16E UI-only alert review selected

The team decided that the MVP will review alerts through the authenticated
Grafana and Alertmanager browser interfaces. A read-only Alertmanager status
check found route receiver `null` and only the `null` receiver configured.
No notification destination, Secret, route, or other infrastructure setting
was changed.

Alertmanager's API showed `Watchdog` plus four active warnings about the
existing crash looping student Pod and Deployment in namespace `2105062`.
The `InfoInhibitor` control alert is typically hidden by inhibition in the
default view. Prometheus retained 36 targets UP and the four custom BUET-PaaS
rules remained live. The team review cadence, browser links, incident triage,
and maintenance handling are documented in
`monitoring/alerts/UI-ONLY-RUNBOOK.md`; Step 16E evidence is in `step-16E.md`.

The three-day operator-facing monitoring MVP is complete. Manual review does
not page anyone during unattended hours. The existing student workload issue,
48-hour storage sizing before persistence, Grafana sidecar automatic reload,
project-scoped user monitoring, and centralized logging remain separate
follow-up work.
