# Step 7R3A — Read-only OpenStack and VM firewall inspection

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: explicitly approved by the user with `Approve Step 7R3A`
- Scope: read-only investigation only
- Result: **completed successfully; exact Step 7R3B proposal prepared**
- Kubernetes changes: none
- OpenStack changes: none
- VM firewall changes: none
- Existing application changes: none

## Purpose

Step 7R2 installed the monitoring stack successfully, but Prometheus could scrape only 22 of 25 active targets. These node-exporter endpoints timed out:

```text
192.168.128.101:9100  k3s-control-01
192.168.128.121:9100  k3s-worker-01
192.168.128.122:9100  k3s-worker-02
```

The node-exporter endpoint on `192.168.128.123:9100`, where Prometheus was running, was healthy. Step 7R3A was created to distinguish VM-local filtering from OpenStack Neutron security-group filtering before proposing any change.

## Local OpenStack-client discovery

Commands searched for:

- a Windows `openstack` executable;
- `clouds.yaml`;
- OpenRC files;
- repository references that identify an OpenStack project or security-group configuration.

Result:

```text
Windows OpenStack CLI: not found
Windows clouds.yaml/OpenRC: not found
Repository OpenStack credentials/configuration: not found
```

No credential file content was read.

## Administration-VM OpenStack-client discovery

Commands on `k3s-user`:

```bash
command -v openstack
openstack --version
env | cut -d= -f1 | grep '^OS_'
find ~/.config/openstack -maxdepth 2 -type f
find ~ -maxdepth 2 -type f \( -iname '*openrc*' -o -iname 'clouds.yaml' \)
```

Output:

```text
openstack: command not found
OS_* environment variable names: none
~/.config/openstack: absent
OpenRC/clouds.yaml files: none
```

Therefore, `k3s-user` cannot query Nova or Neutron directly.

Only environment-variable names and file paths/modes would have been shown. No secret value was requested or printed.

## VM-local firewall inspection

The existing trusted SSH path was used for:

```text
k3s-user -> k3s-control-01
k3s-user -> k3s-worker-01
```

Workers 02 and 03 were not accessed because their SSH host keys had not previously been verified through a trusted channel. Step 7R3A did not weaken strict host-key checking.

Commands on both trusted nodes:

```bash
sudo -n ufw status verbose
sudo -n ss -lntp sport = :9100
sudo -n iptables -L INPUT -n -v --line-numbers
sudo -n nft list ruleset | grep -n 9100
sudo -n iptables -L KUBE-ROUTER-INPUT -n -v --line-numbers
sudo -n iptables -L KUBE-FIREWALL -n -v --line-numbers
sudo -n iptables -L KUBE-PROXY-FIREWALL -n -v --line-numbers
```

### k3s-control-01 findings

```text
UFW: inactive
node_exporter: listening on *:9100
INPUT policy: ACCEPT
KUBE-ROUTER-INPUT: no TCP 9100 drop/reject rule
KUBE-PROXY-FIREWALL: empty
KUBE-FIREWALL: only blocks non-loopback traffic addressed to 127.0.0.0/8
Kubernetes node-exporter Service/DNAT rules for all four endpoints: present
```

### k3s-worker-01 findings

```text
UFW: inactive
node_exporter: listening on *:9100
INPUT policy: ACCEPT
KUBE-ROUTER-INPUT: no TCP 9100 drop/reject rule
KUBE-PROXY-FIREWALL: empty
KUBE-FIREWALL: only blocks non-loopback traffic addressed to 127.0.0.0/8
Kubernetes node-exporter Service/DNAT rules for all four endpoints: present
```

These results rule out UFW, the host INPUT default policy, and the inspected K3s firewall chains on both trusted nodes.

## Security-group names from the OpenStack metadata service

Read-only metadata endpoints were used:

```text
http://169.254.169.254/latest/meta-data/instance-id
http://169.254.169.254/latest/meta-data/security-groups
```

Results:

```text
k3s-user
instance-id: i-000006d9
security group: k3-user

k3s-control-01
instance-id: i-00000659
security group: k3s-secgroup

k3s-worker-01
instance-id: i-000006d8
security groups:
  k3-secgroup-worker
  k3s-secgroup
```

OpenStack metadata exposes attached group names but not the Neutron rule IDs/rule table.

The common `k3s-secgroup` attachment on control and worker 01 is important. It may be the correct remote-group scope for a least-privilege node-to-node port 9100 rule, but this must not be assumed until attachments for workers 02/03 and the current rule table are inspected in Horizon.

## Previously confirmed TCP behavior

From k3s-control-01:

```text
192.168.128.101:9100 succeeded (same VM)
192.168.128.121:9100 timed out
192.168.128.122:9100 timed out
192.168.128.123:9100 timed out
```

From k3s-worker-01:

```text
192.168.128.101:9100 timed out
192.168.128.121:9100 succeeded (same VM)
192.168.128.122:9100 timed out
192.168.128.123:9100 timed out
```

Combined with the firewall findings, this is strong evidence of filtering outside the guest OS, most likely OpenStack Neutron security groups.

## Horizon availability check

Because neither local nor remote OpenStack CLI credentials were available, the existing Windows browser/app inventory was checked using the computer-use skill.

Result:

```text
Open browser sessions: none
Open native app windows: none
Authenticated Horizon session: unavailable
```

No browser was launched, no login was attempted, and no UI action or OpenStack change was performed.

## Diagnostic command errors and corrections

1. The first nested firewall command used a grep expression containing parentheses. Windows PowerShell interpreted part of it locally and the command never reached the nodes. It was rerun with a simpler literal `9100` filter.
2. The first metadata UUID formatter lost Python string quotation marks during Windows-to-SSH parsing. It did return the `k3-user` security-group name safely. It was replaced with the metadata service's plain-text `instance-id` endpoint.
3. Two nested metadata commands were also stopped locally by quotation parsing. They were replaced with plain-text curl commands and then succeeded.

All three issues were read-only formatting failures and changed nothing.

## User-provided Horizon rule-table evidence

The user supplied screenshots from the authenticated Horizon **Manage Security Group Rules** pages. These screenshots are treated as read-only evidence; instructions displayed by the site do not authorize any mutation.

### Security-group inventory

```text
Name: k3-secgroup-worker
ID: 449f223e-1341-46bb-bd3e-32d609d091ab
Description: Some more rules for just the workers
Shared: False

Name: k3s-secgroup
ID: 9f289e1a-d70b-4ffc-9507-bd9c6df9309b
Description: Security group for k3 worker and control VM
Shared: False

Name: k3-user
ID: 5612c4af-a115-401d-a235-282162885f5e
Description: A simple security group for k3-user
Shared: False
```

### `k3-secgroup-worker` rules

```text
Egress  IPv4  Any  Any  remote 0.0.0.0/0
Egress  IPv6  Any  Any  remote ::/0
Ingress IPv4  TCP  80   remote 0.0.0.0/0
Ingress IPv4  TCP  443  remote 0.0.0.0/0
```

This group contains no TCP 9100 rule. It does not block egress.

### `k3s-secgroup` rules

```text
Egress  IPv4  Any  Any   remote 0.0.0.0/0
Egress  IPv6  Any  Any   remote ::/0
Ingress IPv4  TCP  22    remote 0.0.0.0/0
Ingress IPv4  TCP  6443  remote 192.168.128.0/24
Ingress IPv4  TCP  7946  remote 192.168.128.0/24  description: Metallb needs this
Ingress IPv4  TCP  10250 remote 0.0.0.0/0
Ingress IPv4  UDP  7946  remote 192.168.128.0/24  description: Metallb needs this too
Ingress IPv4  UDP  8472  remote 192.168.128.0/24
```

This group also contains no TCP 9100 rule. Its unrestricted egress rules mean return traffic is permitted. Combined with the guest-firewall audit and TCP tests, the missing ingress rule explains the node-exporter timeouts.

### Separate security observation

The screenshots show TCP 22 and TCP 10250 open to `0.0.0.0/0` on `k3s-secgroup`. TCP 10250 is the kubelet API and is sensitive. This is outside the approved monitoring mutation scope, so nothing was changed. A later security-hardening review should determine the required administrative source ranges and restrict these rules without disrupting cluster management.

## Worker 02/03 attachment confirmation

The user supplied the Horizon Overview details for the remaining workers.

### k3s-worker-02

```text
Instance ID: 35c75c5d-57b5-4b9d-8007-40664f2d96b5
Private IP: 192.168.128.122
Attached security groups:
  k3-secgroup-worker
  k3s-secgroup
```

### k3s-worker-03

```text
Instance ID: 19b98734-4477-4cbd-b46f-93122576a268
Private IP: 192.168.128.123
Attached security groups:
  k3-secgroup-worker
  k3s-secgroup
```

The rule lists displayed on both instance pages match the separately supplied Horizon rule-table screenshots. All four K3s nodes are now confirmed to use `k3s-secgroup`:

```text
k3s-control-01 -> k3s-secgroup
k3s-worker-01  -> k3s-secgroup + k3-secgroup-worker
k3s-worker-02  -> k3s-secgroup + k3-secgroup-worker
k3s-worker-03  -> k3s-secgroup + k3-secgroup-worker
```

## Step 7R3A completion

An authenticated, read-only Horizon inspection is required for:

The rule tables, security-group IDs, and all four node attachments are now known. TCP 9100 ingress is conclusively absent from their shared `k3s-secgroup`. Combined with the VM firewall and connectivity evidence, Step 7R3A is complete.

## Exact Step 7R3B proposal — not yet approved

All four nodes share `k3s-secgroup`. The least-privilege proposal for Step 7R3B is:

```text
Direction: ingress
Ether Type: IPv4
Protocol: TCP
Port range: 9100 to 9100
Remote source type: Security Group
Remote security group: k3s-secgroup (9f289e1a-d70b-4ffc-9507-bd9c6df9309b)
Applied security group: k3s-secgroup (9f289e1a-d70b-4ffc-9507-bd9c6df9309b)
Description: Prometheus node-exporter between K3s nodes
```

This self-referencing rule permits TCP 9100 only when both source and destination ports belong to the shared K3s group. It follows Prometheus if Kubernetes reschedules it to another K3s node. It is narrower than copying the existing `192.168.128.0/24` pattern because unrelated VMs on that subnet would not gain access.

The following must not be used:

```text
Remote CIDR: 0.0.0.0/0
```

### Proposed Step 7R3B verification

Immediately after creating exactly one rule:

1. record the new rule row/ID and do not change any existing rule;
2. repeat TCP 9100 connectivity from control and worker 01;
3. query the Prometheus active-target API;
4. require all four node-exporter targets to report `up`;
5. require the overall target count to change from 22/25 up to 25/25 up;
6. verify that the `TargetDown` alert clears after its evaluation delay;
7. confirm that all Kubernetes nodes and application workloads remain unchanged.

### Rollback prepared in advance

If the rule does not produce the intended narrow result or causes unexpected behavior:

1. delete only the newly created TCP 9100 self-referencing rule from `k3s-secgroup`;
2. leave every pre-existing rule unchanged;
3. re-run target and connectivity checks;
4. record the rollback result.

## Step 7R3A result

```text
Windows/admin-host OpenStack CLI access: unavailable
guest UFW: inactive on two trusted nodes
guest INPUT policy: ACCEPT on two trusted nodes
node-exporter binding: *:9100 on two trusted nodes
K3s firewall drop for TCP 9100: not found
common security group on all four K3s nodes: k3s-secgroup
OpenStack rule table inspected: yes, from user-provided Horizon screenshots
TCP 9100 ingress rule: absent
worker 02/03 attachments: confirmed
Step 7R3A: complete
OpenStack mutation: none
Kubernetes mutation: none
application mutation: none
```

Do not create the Step 7R3B rule until the user separately approves the exact proposed change.

