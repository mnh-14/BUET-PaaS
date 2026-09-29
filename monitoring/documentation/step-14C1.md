# Step 14C1 - Install and locally verify node_exporter on k3s-user

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: covered by the user's sequential all-VM auto-approval after Step 14A1
- Result: **complete**
- VM: `k3s-user` (`192.168.128.151`)
- Prometheus/OpenStack change: none

## Before-state and safeguards

The VM is Ubuntu 22.04.5 LTS on `x86_64`. The exporter user, binary, unit, and
TCP 9100 listener were absent. Root usage was 21%; Docker was active/enabled;
four Kubernetes nodes were Ready; Helm release `monitoring-stack` revision 5
was deployed. Existing localhost listeners on 13000, 19090, and 19093 were
recorded and not changed.

## Installation and result

The official pinned `node_exporter 1.12.1` archive and binary checksums from
Step 14A1 passed. The hardened service binds only to
`192.168.128.151:9100`. `systemd-analyze verify` emitted an unrelated warning
that the older host systemd does not recognize `RestartMode` in the existing
`snapd.service`; the node_exporter unit itself verified and started normally.

Repository unit: `monitoring/external-vms/k3s-user/node_exporter.service`
(SHA-256 `47efcc84a74afee0e1f4c97092610fc17690587b28c65a27f5e0951c1edb49e2`).

```text
node_exporter active/enabled: yes/yes
NRestarts:                    0
version:                      1.12.1
listener:                     192.168.128.151:9100 only
local metrics:                successful (416 node_* lines)
Kubernetes nodes Ready:       4/4
Helm monitoring release:      revision 5, deployed
existing local listeners:     preserved
failed systemd units:         0
```

Control-plane access currently times out because `monitoring-exporter` is not
attached. No port-forward, Docker, Kubernetes, Helm, firewall, or OpenStack
state was modified. Rollback follows Step 14A1's component-only method.

