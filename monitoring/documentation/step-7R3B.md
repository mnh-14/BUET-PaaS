# Step 7R3B — Add and verify the node-exporter OpenStack rule

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: explicitly approved by the user with `Approve Step 7R3B`
- Current state: **completed successfully**
- OpenStack rule created: yes, manually by the user in Horizon
- Kubernetes changes: none
- Existing application changes: none

## Authorized change

Exactly one new security-group rule is authorized:

```text
Applied security group: k3s-secgroup
Applied group ID: 9f289e1a-d70b-4ffc-9507-bd9c6df9309b
Direction: Ingress
Ether Type: IPv4
Protocol: TCP
Port range: 9100 to 9100
Remote source type: Security Group
Remote security group: k3s-secgroup
Remote group ID: 9f289e1a-d70b-4ffc-9507-bd9c6df9309b
Description: Prometheus node-exporter between K3s nodes
```

No existing rule is authorized for deletion or modification. A `0.0.0.0/0` remote source is not authorized.

## Fresh pre-change baseline

UTC timestamp:

```text
2026-09-24T07:15:56Z
```

Helm:

```text
release: monitoring-stack
namespace: monitoring
status: deployed
revision: 1
```

Monitoring Pods:

```text
Alertmanager: 2/2 Running, 0 restarts
Grafana: 3/3 Running, 1 historical startup restart
Prometheus Operator: 1/1 Running, 0 restarts
kube-state-metrics: 1/1 Running, 0 restarts
node-exporter: four Pods, all 1/1 Running, 0 restarts
Prometheus: 2/2 Running, 0 restarts
```

Nodes:

```text
k3s-control-01 Ready, CPU 2%, memory 29%
k3s-worker-01  Ready, CPU 3%, memory 37%
k3s-worker-02  Ready, CPU 4%, memory 20%
k3s-worker-03  Ready, CPU 3%, memory 23%
```

Prometheus targets:

```json
{
  "activeTargets": 25,
  "healthCounts": {
    "up": 22,
    "down": 3
  }
}
```

Down targets:

```text
node-exporter 192.168.128.101:9100 context deadline exceeded
node-exporter 192.168.128.121:9100 context deadline exceeded
node-exporter 192.168.128.122:9100 context deadline exceeded
```

Fresh TCP test from the control plane:

```text
192.168.128.101:9100 succeeded (same VM)
192.168.128.121:9100 timed out
192.168.128.122:9100 timed out
192.168.128.123:9100 timed out
```

The nonzero TCP-test exit status is expected because three connections timed out.

## OpenStack execution-path attempts

The computer-use skill was selected because Step 7R3A proved that no local or remote OpenStack CLI credential path exists.

The browser inventory initially returned no browsers or applications. The following supported browser targets were then attempted in order:

```text
Chrome -> Browser is not available
Edge -> Browser is not available
in-app browser -> Browser is not available
```

No Horizon page was opened, no authentication was attempted, no form was prepared, and no rule was submitted.

## Required manual Horizon action

On the already authenticated Horizon page:

1. open `Project -> Network -> Security Groups`;
2. locate `k3s-secgroup` with ID `9f289e1a-d70b-4ffc-9507-bd9c6df9309b`;
3. select `Manage Rules`;
4. select `Add Rule`;
5. enter only the authorized values below:

```text
Rule: Custom TCP Rule
Direction: Ingress
Open Port: Port
Port: 9100
Remote: Security Group
Security Group: k3s-secgroup
Description: Prometheus node-exporter between K3s nodes
```

6. verify that the remote value is the security group, not `0.0.0.0/0`;
7. submit once;
8. capture the resulting rule row or rule ID;
9. do not change or delete any existing rule.

## Verification waiting after manual creation

After the user confirms that the rule exists, run:

1. TCP 9100 tests from control and worker 01 to all four nodes;
2. Prometheus active-target API summary;
3. require all four node-exporter targets to be `up`;
4. require overall target health to become 25/25 up;
5. inspect the `TargetDown` alert until it clears or its configured delay is identified;
6. verify Helm release, all monitoring Pods, and all nodes remain healthy;
7. compare application state with the pre-change baseline;
8. record the exact new rule identity for rollback.

## Rollback

If verification fails or the resulting rule is broader than authorized:

1. delete only the newly created TCP 9100 self-referencing rule;
2. do not modify any pre-existing rule;
3. repeat connectivity and Prometheus target checks;
4. document the rollback result.

## User-provided rule-creation evidence

The user supplied a post-creation Horizon screenshot for:

```text
Security group: k3s-secgroup
Group ID: 9f289e1a-d70b-4ffc-9507-bd9c6df9309b
Displayed rule count: 9 (previously 8)
```

The new row shows:

```text
Direction: Ingress
Ether Type: IPv4
IP Protocol: TCP
Port Range: 9100
Remote IP Prefix: none
Remote Security Group: k3s-secgroup
Description: Prometheus node-exporter between K3s nodes
```

This matches the authorized rule exactly. No broad remote CIDR was added and no existing rule was changed or removed.

The Horizon table does not display the Neutron rule UUID. For rollback, identify the unique row by the combination of group, direction, protocol, port, remote group, and description above.

## Post-change connectivity verification

UTC timestamp:

```text
2026-09-24T07:23:48Z
```

From `k3s-control-01`:

```text
192.168.128.101:9100 succeeded
192.168.128.121:9100 succeeded
192.168.128.122:9100 succeeded
192.168.128.123:9100 succeeded
```

From `k3s-worker-01`:

```text
192.168.128.101:9100 succeeded
192.168.128.121:9100 succeeded
192.168.128.122:9100 succeeded
192.168.128.123:9100 succeeded
```

The rule fixed inter-node TCP 9100 while remaining scoped to members of `k3s-secgroup`.

## Prometheus target verification

Immediately after the rule:

```json
{
  "status": "success",
  "activeTargets": 25,
  "healthCounts": {
    "up": 25
  }
}
```

All node-exporter targets reported `up` with an empty `lastError`:

```text
192.168.128.101:9100 up
192.168.128.121:9100 up
192.168.128.122:9100 up
192.168.128.123:9100 up
```

This is the required improvement from the pre-change `22/25` state to `25/25`.

## Real node-metric verification

Prometheus query:

```promql
node_uname_info
```

UTC verification time:

```text
2026-09-24T07:24:41Z
```

Result: four series, one for every node:

```text
192.168.128.101:9100 -> k3s-control-01
192.168.128.121:9100 -> k3s-worker-01
192.168.128.122:9100 -> k3s-worker-02
192.168.128.123:9100 -> k3s-worker-03
```

All reported Linux kernel `5.15.0-181-generic`. This proves that Prometheus is receiving host metrics, not only establishing TCP connections.

## Alert verification

`TargetDown` was absent from the post-change Prometheus alert API response, so it cleared without requiring a manual restart or configuration reload.

Alerts that remained:

```text
Watchdog: expected always-firing health alert
InfoInhibitor: firing in monitoring
CPUThrottlingHigh: pending/info in monitoring
KubePodCrashLooping: firing for namespace 2105062
KubePodNotReady: firing for namespace 2105062
KubeDeploymentReplicasMismatch: firing for namespace 2105062
KubeDeploymentRolloutStuck: firing for namespace 2105062
```

The four `2105062` alerts correspond to the known pre-existing `to-do-backend` failure. The pending CPU observation does not indicate a failed Step 7R3B network change.

## Monitoring and cluster non-regression

```text
Helm monitoring-stack: deployed, revision 1
Alertmanager: 2/2 Running
Grafana: 3/3 Running
Prometheus Operator: 1/1 Running
kube-state-metrics: 1/1 Running
node-exporter: 4/4 Running
Prometheus: 2/2 Running
all four nodes: Ready
```

Post-change utilization:

```text
k3s-control-01 CPU 2%, memory 28%
k3s-worker-01  CPU 3%, memory 37%
k3s-worker-02  CPU 3%, memory 20%
k3s-worker-03  CPU 4%, memory 23%
```

Application comparison:

```text
six previously healthy deployments in namespace 2105062: still 1/1
pre-existing to-do-backend deployment: still 0/1 CrashLoopBackOff
application deployments edited/restarted by Step 7R3B: none
```

## Final Step 7R3B result

```text
OpenStack rules added: exactly 1
rule scope: TCP 9100 only between k3s-secgroup members
existing OpenStack rules changed/deleted: none
Kubernetes resources changed: none
application resources changed: none
inter-node TCP 9100: PASS from two tested source nodes to all four nodes
Prometheus targets: 25/25 up
node metric series: 4/4
TargetDown alert: cleared
rollback required: no
Step 7R3B: complete
```

