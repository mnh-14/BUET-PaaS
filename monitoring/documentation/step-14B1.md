# Step 14B1 - Install and locally verify node_exporter on registry-vm-2

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: covered by the user's sequential all-VM auto-approval after Step 14A1
- Result: **complete**
- VM: `registry-vm-2` (`192.168.128.152`)
- Prometheus/OpenStack change: none

## Before-state and safeguards

The VM is Ubuntu 24.04.3 LTS on `x86_64`. TCP 9100, the exporter user, binary,
and unit were absent. Root usage was 16%, no systemd unit was failed, Docker was
active/enabled, ports 80/443 were listening, and the Harbor HTTPS health API
returned 200. The audit-only Harbor request used `curl -k` because this step
did not alter or install Harbor trust material.

## Installation and result

The same official `node_exporter 1.12.1` archive and hashes recorded in Step
14A1 were verified before installation. A no-login service user and hardened
systemd unit were installed. The unit binds only to
`192.168.128.152:9100`; staging files were removed afterward.

Repository unit: `monitoring/external-vms/registry-vm-2/node_exporter.service`
(SHA-256 `63aeb8cd1af4080f4b2679f427dde2abc8ffa247b0189f13840a78f3e4fa4c4e`).

```text
node_exporter active/enabled: yes/yes
NRestarts:                    0
version:                      1.12.1
listener:                     192.168.128.152:9100 only
local metrics:                successful (680 node_* lines)
Docker active/enabled:        yes/yes
Harbor HTTPS health:          200
failed systemd units:         0
```

Control-plane access currently times out because `monitoring-exporter` is not
attached to this VM. No firewall, Harbor, Docker, Prometheus, or OpenStack
configuration was changed. Rollback follows Step 14A1's component-only method.

