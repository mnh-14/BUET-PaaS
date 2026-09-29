# Step 14E2 - Verify restricted SonarQube exporter reachability

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Scope: screenshot review and read-only verification
- Result: **complete**
- Live monitoring change: none

## OpenStack evidence

The supplied Horizon Overview screenshot shows `monitoring-exporter` attached
to `sonarqube` while its existing `web-&-ssh` and `default` groups remain
attached. The displayed TCP 9100 rule references remote security group ID
beginning `9f289e1a-d70b`, the established `k3s-secgroup`; TCP 9100 is not
shown open from `0.0.0.0/0`.

## Verification

The request originated on `k3s-control-01` through the established `k3s-user`
SSH path:

```text
endpoint:                         192.168.128.33:9100/metrics
HTTP status:                      200
node_exporter_build_info count:   1
node_exporter service:            active and enabled
NRestarts:                        0
listener:                         192.168.128.33:9100 only
SonarQube API:                    UP, HTTP 200
failed systemd units:             0
```

The endpoint previously timed out before the security-group attachment. Its
successful response now confirms the intended restricted control-plane path.
No VM, OpenStack, Kubernetes, Helm, Prometheus, or SonarQube configuration was
changed by this verification.

## Next boundary

All six standalone VM exporters are installed and control-plane reachable.
Frontend is already scraped; Step 14A3 may now prepare and offline-verify the
five additional targets. Applying that overlay remains separately gated.

