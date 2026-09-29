# Step 14E1 - Verify SSH identity and install node_exporter on sonarqube

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: covered by the user's earlier sequential all-VM auto-approval
- Result: **complete locally**
- VM: `sonarqube` (`192.168.128.33`)
- OpenStack/Prometheus change: none

## SSH trust blocker resolved

The user connected interactively and supplied the observed ED25519 fingerprint:

```text
SHA256:+FDZkJcqkKQULlQOuWUukqFHZNqWzltyjhwPE5G/AzE
```

It exactly matched the fingerprint recorded during Step 13A. The user accepted
the key and successfully reached the expected Ubuntu `sonarqube` host. This
cleared the prior changed-host-key blocker.

An additional local `ssh-keyscan | ssh-keygen` diagnostic returned `not a
public key file`; it made no remote change. The verified user evidence was used
as the trust anchor, and the automation client recorded that key using
`accept-new`. All subsequent SSH/SCP operations required strict host-key
checking.

## Before-state

```text
OS/architecture:        Ubuntu 22.04.5 LTS, x86_64
node_exporter:          user, binary, unit, and TCP 9100 listener absent
root filesystem:       64% used
Docker:                active and enabled
sonarqube container:   Up
sonarqube-db container: Up and healthy
SonarQube API:          status UP, HTTP 200, version 26.8.0.126808
failed systemd units:  0
```

The first zombie-process awk expression was altered by local PowerShell `$3`
expansion and failed without changing state. The corrected check found two
pre-existing defunct `grep` processes with parent PID 1433. They remained the
same after installation and were not terminated in this step.

## Installation

The official `node_exporter 1.12.1` Linux amd64 archive and extracted binary
were verified before installation:

```text
archive SHA-256: b51d8a76aa2a9156a55d501aca6276fae09e262259a5e4e831d2c2222f084e63
binary SHA-256:  1108f7453ecfe4a72f131c73b69537c171840ad4f1713a2402328ad56cf12e09
revision:       6044da783597cc3b57aef7580ddcdcff58a4ee99
```

A no-login service user and the reviewed hardened systemd unit were installed.
The unit binds only to `192.168.128.33:9100`. The older host systemd emitted
the same unrelated existing `snapd.service` `RestartMode` warning seen on
k3s-user; the node_exporter unit verified and started successfully. Exact
download and transfer staging files were removed.

Repository unit: `monitoring/external-vms/sonarqube/node_exporter.service`
(SHA-256 `285e24c929c494d1e8fb589cca52dc1efe81a6abbe5fabbdc7ecc9fa6ce155d4`).

## Verification

```text
node_exporter active/enabled: yes/yes
NRestarts:                    0
version:                      1.12.1
listener:                     192.168.128.33:9100 only
local metrics:                successful (473 node_* lines)
Docker active/enabled:        yes/yes
sonarqube container:          still Up
sonarqube-db:                 still Up and healthy
SonarQube API:                still UP, HTTP 200
failed systemd units:         0
Kubernetes nodes:             4/4 Ready
Prometheus:                   Ready, existing count(up)=26
```

The control plane currently times out connecting to
`192.168.128.33:9100`. This is expected because the existing restricted
`monitoring-exporter` security group has not yet been attached to SonarQube.
No broad TCP 9100 rule was created.

## Next boundary and rollback

Manually attach `monitoring-exporter` to `sonarqube` while retaining every
existing security group, then provide the Overview screenshot. A later
read-only check will confirm control-plane HTTP 200 before the scrape overlay
is prepared.

If separately approved, rollback removes only the node_exporter service,
binary, and dedicated user after ownership checks. Docker, SonarQube, its
database, and their data must not be changed.

