# Step 14D1 - Install and locally verify node_exporter on backend-vm

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: covered by the user's sequential all-VM auto-approval after Step 14A1
- Result: **complete**
- VM: `backend-vm` (`192.168.128.131`)
- Prometheus/OpenStack change: none

## Before-state and safeguards

The VM is Ubuntu 24.04.3 LTS on `x86_64`. TCP 9100, the exporter user, binary,
and unit were absent. Root usage was 67%, no systemd unit was failed, and
`buet-backend` was active/enabled. Its listeners on 8020 and 9000-9008 were
recorded. `GET /health` returned HTTP 200 with status `ok`, version `0.2.0`, and
MongoDB connected. The first wrapper stopped locally on a PowerShell quote
error; no SSH command or change occurred.

## Installation and result

The official pinned `node_exporter 1.12.1` archive and binary checksums from
Step 14A1 passed. The hardened service binds only to
`192.168.128.131:9100`; staging files were removed.

Repository unit: `monitoring/external-vms/backend-vm/node_exporter.service`
(SHA-256 `db5670f279c3421d24507a4f967b83d4b977cc30767f0196c1a84fa196cd19f2`).

```text
node_exporter active/enabled: yes/yes
NRestarts:                    0
version:                      1.12.1
listener:                     192.168.128.131:9100 only
local metrics:                successful (589 node_* lines)
buet-backend active/enabled:  yes/yes
backend /health:              HTTP 200, status ok, MongoDB connected
application listeners:        preserved
failed systemd units:         0
```

Control-plane access currently times out because `monitoring-exporter` is not
attached. No backend, firewall, Prometheus, or OpenStack configuration was
changed. Rollback follows Step 14A1's component-only method.

## Cross-system regression result

After all four VM-local installations, all four k3s nodes remained Ready and
all nine monitoring Pods were Running with zero restarts. Prometheus reported
Ready, `count(up)=26`, and no series for `count(up == 0)`. The first attempt to
use a pre-existing temporary port-forward found it closing/reset; Kubernetes
API service proxy was then used successfully and no new port-forward was
created.

The control-plane reachability wrapper was initially invalid because local
PowerShell expanded remote shell variables; the corrected explicit checks
showed frontend 200 and the four new exporters timing out. SonarQube also timed
out and remains unmodified because its changed SSH host key is not trusted.

