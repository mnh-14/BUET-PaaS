# Step 10A — Install node_exporter on frontend-vm

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: explicitly approved with `Approve Step 10A — frontend-vm`
- Scope: only `frontend-vm` (`192.168.128.15`, floating IP `192.168.67.159`)
- Current state: **completed successfully**
- Other VMs authorized: none
- Prometheus configuration change authorized: none; that remains Step 11

## Pinned artifact

```text
Project: prometheus/node_exporter
Version: 1.12.1
Platform: linux/amd64
Official asset: node_exporter-1.12.1.linux-amd64.tar.gz
Official/downloaded SHA-256: b51d8a76aa2a9156a55d501aca6276fae09e262259a5e4e831d2c2222f084e63
Binary revision: 6044da783597cc3b57aef7580ddcdcff58a4ee99
```

The downloaded archive hash matched the checksum published on the official Prometheus GitHub release. The version also matches the node_exporter image already used by the cluster DaemonSet.

## Baseline

```text
hostname: frontend-vm
private IP: 192.168.128.15/24
OS: Ubuntu 24.04.3 LTS
architecture: x86_64
kernel: 6.8.0-139-generic
vCPU: 2
RAM: 1.9 GiB total, approximately 1.5 GiB available
root disk: 8.7 GiB total, 4.4 GiB available, 50% used
UFW: inactive
passwordless sudo: available
failed systemd units: none
```

Collision checks before installation:

```text
node_exporter executable in PATH: absent
/usr/local/bin/node_exporter: absent
/etc/systemd/system/node_exporter.service: absent
node_exporter user: absent
node_exporter unit enabled: not-found
node_exporter unit active: inactive
TCP 9100 listener: absent
```

Application baseline:

```text
Nginx: active; configuration syntax valid
Nginx listener: 0.0.0.0:80 and [::]:80
Next.js process: next-server v14.2.35
Next.js listener: 0.0.0.0:3000
http://127.0.0.1/: HTTP 200, content length 6302
http://127.0.0.1:3000/: HTTP 200, content length 6302
both paths returned the same ETag
```

Pre-install private connectivity:

```text
k3s-user -> frontend-vm:80: reachable
k3s-user -> frontend-vm:9100: timed out
```

The timeout is recorded before installation. After a local listener exists, it will distinguish whether the remaining path is blocked by the frontend OpenStack security group.

## New repository artifact

```text
monitoring/external-vms/frontend-vm/node_exporter.service
SHA-256: bb29cf26e93bb8fde6475534e3017756810a995e2602b798203056a8dac3fc7f
```

The unit runs as a dedicated non-login user, binds only to `192.168.128.15:9100`, and applies systemd hardening. It does not bind directly to a public wildcard address and does not change Nginx or Next.js.

## Rollback prepared before persistent mutation

If validation fails, remove only the artifacts introduced by this substep:

```bash
sudo systemctl disable --now node_exporter.service
sudo rm -f /etc/systemd/system/node_exporter.service
sudo rm -f /usr/local/bin/node_exporter
sudo systemctl daemon-reload
sudo systemctl reset-failed node_exporter.service
sudo userdel node_exporter
```

Safety conditions:

- Run the user deletion only if `node_exporter` was created by this step and owns no unrelated files/processes.
- Remove no application file, service, user, firewall rule, or package.
- Any future OpenStack rule must have its own recorded identity and may be removed independently.

## Errors and corrections before mutation

1. Private-IP SSH with strict checking stopped because `k3s-user` did not yet have an authoritative host-key entry. No insecure bypass was used. Direct strict SSH to the already trusted floating IP succeeded.
2. The first combined baseline wrapper had an unmatched quote and executed no remote checks.
3. A curl formatting wrapper lost quotes, printed the public login-page HTML, and emitted `Bad hostname`; it exposed no credential and changed nothing. Clean HEAD requests then confirmed HTTP 200.
4. A connectivity wrapper allowed Windows PowerShell to expand remote `$?` to `True`. The actual `nc` messages still showed port 9100 timed out and port 80 succeeded. No decision relies on the incorrect printed exit labels.

## Remaining authorized actions

1. Transfer and hash-check the reviewed unit.
2. Install the verified binary as root-owned mode `0755`.
3. Create only the dedicated `node_exporter` system user.
4. Install, validate, enable, and start only `node_exporter.service`.
5. Verify local metrics, private reachability, resource usage, security posture, and unchanged frontend health.
6. Stop before touching any other VM or Prometheus scrape configuration.

## Persistent installation executed

The reviewed unit was transferred to a temporary path and its remote SHA-256 matched the local value exactly:

```text
bb29cf26e93bb8fde6475534e3017756810a995e2602b798203056a8dac3fc7f
```

Only these persistent host objects were created:

```text
system user: node_exporter, non-login, no home directory created
binary: /usr/local/bin/node_exporter, root:root, mode 0755
unit: /etc/systemd/system/node_exporter.service, root:root, mode 0644
enablement symlink: multi-user.target.wants/node_exporter.service
```

Installation/activation result:

```text
systemd-analyze verify: passed
unit enabled: yes
unit active: yes
version: 1.12.1
platform: linux/amd64
restarts: 0
```

Installed hashes:

```text
/usr/local/bin/node_exporter:
1108f7453ecfe4a72f131c73b69537c171840ad4f1713a2402328ad56cf12e09

/etc/systemd/system/node_exporter.service:
bb29cf26e93bb8fde6475534e3017756810a995e2602b798203056a8dac3fc7f
```

## Local metrics and resource validation

```text
listener: 192.168.128.15:9100 only
metrics endpoint: healthy locally
metric lines returned: 949
node_exporter_build_info: version 1.12.1
node_uname_info nodename: frontend-vm
memory after startup: approximately 6 MiB
NRestarts: 0
```

Systemd security analysis:

```text
overall exposure: 4.1 OK
non-root user: yes
NoNewPrivileges: yes
capability bounding set: empty
OS filesystem: strict read-only
home directories: protected
kernel modules/tunables/logs/control groups: protected
```

The service intentionally retains read access to host `/proc`, `/sys`, devices, and networking needed for exporter collectors; these account for the remaining analyzer exposure score.

## Frontend regression check

After node_exporter started:

```text
Nginx: active
Nginx config check: successful
Next.js PID: still 4386, unchanged
Nginx HTTP: 200
direct Next.js HTTP: 200
content length: still 6302
ETag: still 9lvwk88co14uc
failed systemd units: 0
```

No Nginx, Next.js, application, package, UFW, or system networking configuration was changed.

## Network exposure result

```text
frontend local private-IP metrics: reachable
Windows -> floating IP 192.168.67.159:9100: blocked
k3s-user -> private IP 192.168.128.15:9100: timed out
k3s-control-01 -> private IP 192.168.128.15:9100: timed out
```

The direct Windows SSH attempt to `k3s-control-01` used the wrong key for that VM and failed authentication before executing a test. The verified nested path `Windows -> k3s-user -> k3s-control-01` was then used successfully; its TCP and HTTP tests both timed out.

This proves:

- node_exporter itself is healthy;
- it is not publicly reachable;
- UFW is not the blocker;
- the required K3s-to-frontend private path is blocked before reaching the guest listener.

## OpenStack metadata evidence

Read-only frontend metadata returned:

```text
instance ID: i-0000067a
attached security groups:
  web-&-ssh
  default
```

OpenStack metadata does not expose Neutron rule IDs or the full rule tables. No OpenStack rule was created, modified, or deleted.

## Temporary-file cleanup

Before deletion, the staging directory was inventoried and contained only the downloaded archive, extracted binary, `LICENSE`, `NOTICE`, and the transferred unit. Those exact temporary files/directories were removed individually.

```text
STAGING_CLEANUP=PASS
```

The installed binary and systemd unit were not removed.

## Current pause and required evidence

Step 10A is not fully complete because Prometheus/K3s private reachability is a required success condition.

Before proposing any OpenStack mutation, obtain screenshots of:

1. Horizon `Project -> Network -> Security Groups -> web-&-ssh -> Manage Rules`;
2. Horizon `Project -> Network -> Security Groups -> default -> Manage Rules` if it contains relevant private/group-based ingress.

The preferred eventual rule shape, subject to the rule-table review, is:

```text
Direction: Ingress
Ether Type: IPv4
Protocol: TCP
Port: 9100
Remote: Security Group
Remote group: k3s-secgroup
Destination/applied group: the narrowly appropriate group attached to frontend-vm
```

Do not use `0.0.0.0/0`, the floating IP, or the whole public Internet. Do not add this rule until its exact destination group and rollback identity are reviewed and separately approved.

No other VM and no Prometheus scrape configuration may be touched while Step 10A is paused.

## Horizon rule-table evidence supplied by the user

The user supplied the `Manage Security Group Rules` screenshot for:

```text
name: web-&-ssh
ID: 107653fc-ce63-4baa-adfd-8bd98f9348f4
displayed rules: 8
```

Current rules visible in the screenshot:

```text
Egress IPv4 any -> 0.0.0.0/0
Egress IPv6 any -> ::/0
Ingress IPv4 ICMP any <- 0.0.0.0/0
Ingress IPv4 TCP 22 <- 0.0.0.0/0
Ingress IPv4 TCP 80 <- 0.0.0.0/0
Ingress IPv4 TCP 443 <- 0.0.0.0/0
Ingress IPv4 TCP 3000 <- 0.0.0.0/0
Ingress IPv4 TCP 9000 <- 0.0.0.0/0
```

There is no TCP 9100 ingress rule. This explains why the healthy private listener cannot be reached from K3s.

The public exposure of SSH, the direct Next.js port 3000, ICMP, and port 9000 is pre-existing and outside Step 10A. None of those rules will be edited or deleted as part of monitoring.

## Recommended Step 10A-R1 OpenStack design

Do not add the exporter rule to the existing broad `web-&-ssh` group. Create a dedicated additive group so monitoring access has an independent lifecycle and rollback:

```text
new security group name: monitoring-exporter
description: Private Prometheus access to standalone VM node_exporters

new ingress rule:
  Direction: Ingress
  Ether Type: IPv4
  Protocol: TCP
  Port: 9100
  Remote: Security Group
  Remote Security Group: k3s-secgroup
  Remote Security Group ID: 9f289e1a-d70b-4ffc-9507-bd9c6df9309b
  Description: Prometheus to standalone VM node_exporters

first attachment only:
  frontend-vm
  instance ID: i-0000067a
```

Attachment safety rule: retain both existing groups, `web-&-ssh` and `default`; add `monitoring-exporter` as a third group. Do not replace or detach an existing group.

This design does not expose port 9100 to `0.0.0.0/0` or the floating-IP public path. Only ports originating from members of `k3s-secgroup` may reach the exporter.

Planned verification after creation/attachment:

1. record the new group ID and exact rule row;
2. confirm frontend has all three intended group attachments;
3. test TCP and `/metrics` from `k3s-control-01`;
4. confirm floating-IP TCP 9100 remains blocked;
5. confirm node_exporter remains enabled, active, and restart-free;
6. repeat Nginx/Next.js HTTP regression checks;
7. stop before Step 11 adds any Prometheus scrape configuration.

Rollback if verification fails:

1. detach only `monitoring-exporter` from `frontend-vm`;
2. delete only the new `monitoring-exporter` group and its rule after confirming no other VM is attached;
3. leave `web-&-ssh`, `default`, and every pre-existing rule untouched;
4. keep or separately roll back the locally healthy node_exporter only if explicitly required.

## Step 10A-R1 user-executed OpenStack change

The user manually created the proposed dedicated security group and supplied the post-creation rule-table screenshot:

```text
name: monitoring-exporter
ID: c83ef330-b742-4420-b010-06bf63c56765
displayed rules: 3
```

Rules:

```text
Egress IPv4 any -> 0.0.0.0/0
Egress IPv6 any -> ::/0
Ingress IPv4 TCP 9100 <- remote security group k3s-secgroup
Description: Prometheus to standalone VM node_exporters
```

The ingress row has no remote IP prefix. It is not a `0.0.0.0/0` ingress rule.

The user then supplied the frontend Edit Instance and Overview evidence. Final attachments are:

```text
web-&-ssh          retained
default            retained
monitoring-exporter added
```

No existing group was removed or altered. No other VM was attached under Step 10A.

## Post-attachment network verification

From the actual `k3s-control-01` node, which is a member of `k3s-secgroup`:

```text
TCP 192.168.128.15:9100: succeeded
HTTP /metrics: succeeded
metric lines: 949
node_exporter version: 1.12.1
node_uname_info nodename: frontend-vm
```

Negative-path tests:

```text
k3s-user -> frontend:9100: timed out
Windows -> floating IP 192.168.67.159:9100: blocked
```

`k3s-user` belongs to a different source security group, so its continued timeout is expected and confirms the rule is not private-CIDR-wide. The floating-IP failure confirms the exporter is not publicly reachable.

The first post-attachment control-plane wrapper contained a nested pipe that Windows PowerShell interpreted locally. It failed before the control-plane test ran and changed nothing. The corrected test downloaded metrics to one explicitly named temporary file on `k3s-control-01`, inspected it, deleted it, verified deletion, and passed.

## Final regression state

```text
node_exporter: enabled, active, 0 restarts
node_exporter listener: 192.168.128.15:9100 only
Nginx: active, HTTP 200
Next.js: same PID 4386, HTTP 200, same ETag/content length
failed frontend systemd units: 0
Kubernetes nodes: 4/4 Ready
monitoring Pods: 9/9 Ready
Helm monitoring-stack: deployed, revision 1
new unavailable application Deployment: none
known 2105062/to-do-backend fault: unchanged
```

Prometheus scrape configuration was not changed, so `frontend-vm` is reachable from K3s but is not yet a Prometheus target. That remains the separately controlled external-target configuration step.

## Final Step 10A result

```text
pinned/checksum-verified exporter installed: yes
least-privilege system user/unit: yes
private-IP-only listener: yes
K3s source reachability: yes
non-K3s admin source blocked: yes
floating-IP/public source blocked: yes
frontend regression: none
other VMs changed: none
Prometheus configuration changed: none
Step 10A: complete
```

Rollback was not required. If later required, first detach `monitoring-exporter` from `frontend-vm`; delete the group only after confirming no other VM uses it; then use the previously documented host rollback only if the local exporter must also be removed.
