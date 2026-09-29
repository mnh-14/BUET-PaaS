# Step 14A2 - Verify control-plane reachability to standalone VM exporters

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 14A2 - verify control-plane reachability to all standalone VM exporters`
- Scope: read-only network, service, and monitoring regression checks
- Result: **complete**
- Live configuration changes: none

## OpenStack evidence accepted

The user supplied Horizon Overview screenshots for `database-vm`,
`registry-vm-2`, `k3s-user`, and `backend-vm`. Each screenshot showed the
existing VM security groups retained and the existing `monitoring-exporter`
group added. Its ingress is TCP 9100 from remote security group ID beginning
`9f289e1a-d70b`, which is the established `k3s-secgroup`. No screenshot showed
a TCP 9100 rule from `0.0.0.0/0`.

## Control-plane reachability

The test originated on `k3s-control-01`, reached through the established
`k3s-user` SSH path. For every endpoint, `curl` required a successful response,
reported the HTTP code, and the full metrics stream was checked for exactly one
`node_exporter_build_info` line.

```text
source:       k3s-control-01
frontend-vm:  192.168.128.15:9100   HTTP 200   build_info=1
database-vm:  192.168.128.92:9100   HTTP 200   build_info=1
registry-vm:  192.168.128.152:9100  HTTP 200   build_info=1
k3s-user:     192.168.128.151:9100  HTTP 200   build_info=1
backend-vm:   192.168.128.131:9100  HTTP 200   build_info=1
```

This confirms that the restricted security-group path works from the k3s
control plane. It does not expose the exporters through the monitoring browser
Ingress or add them to Prometheus.

## Host service cross-check

The four newly installed hosts were checked directly without mutation:

```text
VM             service  enabled  restarts  version  listener
database-vm    active   yes      0         1.12.1  192.168.128.92:9100
registry-vm-2  active   yes      0         1.12.1  192.168.128.152:9100
k3s-user       active   yes      0         1.12.1  192.168.128.151:9100
backend-vm     active   yes      0         1.12.1  192.168.128.131:9100
```

All four reported revision
`6044da783597cc3b57aef7580ddcdcff58a4ee99` and zero failed systemd units.

## Monitoring regression check

```text
k3s nodes:                4/4 Ready
monitoring Pods:          9 Running, zero restarts
Prometheus readiness:     ready
existing count(up):       26
existing count(up == 0):  no series
Helm release:             monitoring-stack revision 5, deployed
```

The target count correctly remains 26. This step did not edit the standalone
scrape overlay or apply a Helm upgrade, so the four new exporters are reachable
but are not yet Prometheus targets.

## Mutation and rollback

This verification changed no VM, firewall, OpenStack, Kubernetes, Helm,
Prometheus, or application state. There is therefore no rollback for Step
14A2. The security-group attachments were performed manually before approval
and were only observed here.

## Next permission boundary

Step 14A3 will update the repository scrape overlay with the four reachable
targets and perform offline/pinned Helm lint and focused render only. It will
not change the live cluster. Applying the rendered configuration remains a
later, separate approval.

