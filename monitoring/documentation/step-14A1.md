# Step 14A1 - Install and locally verify node_exporter on database-vm

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: `Approve Step 14A1 - install and locally verify node_exporter on database-vm`
- Result: **complete**
- VM: `database-vm` (`192.168.128.92`)
- Prometheus/OpenStack change: none

## Before-state

Read-only SSH preflight confirmed Ubuntu 24.04.3 LTS on `x86_64`, passwordless
administrative access, no `node_exporter` user/binary/unit, and no listener on
TCP 9100. Root usage was 42% and no systemd unit was failed. MongoDB was
active/enabled and listening on the same two addresses/port 27017 recorded
before installation.

The first preflight wrapper had unmatched remote quote syntax and performed no
change. The corrected variable-free command produced the before-state above.

## Installation

The official `node_exporter 1.12.1` Linux amd64 archive was downloaded from the
Prometheus GitHub release on the VM. Installation continued only after these
checks passed:

```text
archive SHA-256: b51d8a76aa2a9156a55d501aca6276fae09e262259a5e4e831d2c2222f084e63
binary SHA-256:  1108f7453ecfe4a72f131c73b69537c171840ad4f1713a2402328ad56cf12e09
revision:       6044da783597cc3b57aef7580ddcdcff58a4ee99
```

A system user with no login shell was created. The binary was installed at
`/usr/local/bin/node_exporter`; the reviewed hardened unit was installed at
`/etc/systemd/system/node_exporter.service`. The unit binds only to
`192.168.128.92:9100`, passed `systemd-analyze verify`, and was enabled and
started. The exact staging files were then removed.

Repository unit: `monitoring/external-vms/database-vm/node_exporter.service`
(SHA-256 `b85b534b443a5f1a49aaa05a9a3c4263db61592e0c9368a8b90d0045f3c87cb0`).

## Verification

```text
node_exporter active/enabled: yes/yes
NRestarts:                    0
version:                      1.12.1
listener:                     192.168.128.92:9100 only
local metrics:                successful (397 node_* lines)
MongoDB active/enabled:       yes/yes
failed systemd units:         0
```

One verification wrapper used PowerShell `$()` expansion locally and failed
before a valid remote check. The corrected expansion-free check passed. A
`curl: (23)` message came from `grep -m1` closing a successful metrics stream
early; a complete follow-up metrics count passed.

Control-plane access to `192.168.128.92:9100` currently times out, as expected
because the existing `monitoring-exporter` security group is not yet attached
to this VM. No broad firewall rule was added.

## Rollback

If separately approved: stop/disable the service, remove only the unit and
installed binary, reload systemd, and remove the `node_exporter` system user
only after confirming no other file owns it. MongoDB must not be changed.

