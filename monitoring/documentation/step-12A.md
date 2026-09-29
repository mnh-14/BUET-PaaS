# Step 12A - Read-only floating-IP and ingress preflight

## Status

- Date: 2026-09-24 (Asia/Dhaka)
- Permission: explicitly approved with `Approve Step 12A - read-only floating-IP and ingress preflight`
- Infrastructure mutation authorized: none
- Infrastructure mutation performed: none
- Current state: **completed; exact floating-IP/VIP path selected**

## Purpose

Determine the exact, safe network path for normal browser access to Grafana,
Prometheus, and Alertmanager without using port-forward as the primary access
method.

This step inspected only existing state. It did not create an Ingress, allocate
or associate a floating IP, edit a security group, install cert-manager, create
credentials, change DNS, or modify Traefik/MetalLB.

## Existing ingress architecture discovered

```text
IngressClass: traefik (default)
Traefik Service type: LoadBalancer
Traefik ClusterIP: 10.43.67.11
MetalLB VIP: 192.168.128.200
HTTP: 80 -> NodePort 31640 -> targetPort 8000
HTTPS: 443 -> NodePort 31451 -> targetPort 8443
externalTrafficPolicy: Cluster
```

Traefik runtime:

```text
chart: traefik-40.1.3+up40.1.0
image: rancher/mirrored-library-traefik:3.7.4
Deployment replicas: 1
ready/available: 1/1
Pod: on k3s-control-01
Pod IP: 10.42.0.123
CPU: approximately 2m
memory: approximately 29 MiB
```

The single Traefik replica is a current availability risk, even though it is
lightly loaded. Scaling it is a shared PaaS infrastructure change and is not
authorized by this preflight.

## Existing PaaS public path

The repository and live Ingress objects intentionally publish each student app
under two sslip.io hostnames:

```text
private VIP form: <app>.<namespace>.192.168.128.200.sslip.io
public form:      <app>.<namespace>.192.168.64.121.sslip.io
```

The live `default/lb-test-ingress` contains both forms and reports status VIP
`192.168.128.200`.

External tests from Windows proved:

```text
hello.192.168.64.121.sslip.io -> 192.168.64.121
TCP 80 on 192.168.64.121: reachable
TCP 443 on 192.168.64.121: reachable
HTTP route: 200
HTTPS route with certificate verification disabled: 200
```

This proves that floating IP `192.168.64.121` already reaches the shared
Traefik/MetalLB ingress path. It does not by itself reveal the Neutron port,
allowed-address-pair, or security-group association used to implement that
mapping.

## MetalLB state

```text
pool: paas-ip-pool
range: 192.168.128.200-192.168.128.225
assignment: automatic
advertisement: L2
BGP peers/advertisements: none
Traefik VIP: 192.168.128.200
current L2 announcing node: k3s-worker-03
```

All four MetalLB speaker Pods and the controller are Ready. No error, failure,
or panic was found in the current announcer's last hour of logs.

The speakers have unusually high historical restart counts:

```text
k3s-worker-01: 859
k3s-worker-02: 874
k3s-worker-03: 862
k3s-control-01: 5172
last recorded termination: 2026-09-23 around 08:04 UTC, reason Unknown
```

They have remained running since that event. Current events show only the known
`DNSConfigForming` nameserver-limit warning. The restart history is a reliability
risk to investigate separately; it is not evidence of a current outage.

## Proposed monitoring hostnames and collision check

The following names all resolve automatically to the existing floating IP:

```text
grafana.monitoring.192.168.64.121.sslip.io
prometheus.monitoring.192.168.64.121.sslip.io
alerts.monitoring.192.168.64.121.sslip.io
```

Current HTTP and HTTPS result for each is `404`, proving there is no existing
Ingress route collision.

These names are technically usable for host-based routing. They are not yet
safe login URLs because trusted TLS and authentication are absent.

## TLS finding

HTTPS is already transported through Traefik, but the certificate is not
browser-trusted:

```text
subject: CN=TRAEFIK DEFAULT CERT
issuer: CN=TRAEFIK DEFAULT CERT
Windows validation: SEC_E_UNTRUSTED_ROOT
```

The certificate SAN is an internal random Traefik name, not the proposed
monitoring hosts.

Cluster TLS/certificate state:

```text
cert-manager CRDs/controllers: absent
Traefik certificate resolvers: none configured
Traefik TLS Secrets for public hosts: none
only discovered kubernetes.io/tls Secret: kube-system/k3s-serving
```

Do not send Grafana or Basic Auth credentials over plain HTTP, and do not treat
clicking through a browser certificate warning as the final solution.

Preferred certificate identity order:

1. team-controlled DNS names pointing to the chosen floating IP plus a trusted
   certificate;
2. team/internal CA certificate with the CA installed on team devices;
3. sslip.io hostnames with an ACME-capable issuer, only after checking issuance
   and shared-domain rate-limit risk.

## Authentication and policy capability

Traefik CRDs, including `Middleware`, are installed. No Middleware objects
currently exist. Therefore Basic Auth, IP allowlisting, security headers, and
rate limiting can be added without replacing Traefik.

Current state:

```text
Grafana anonymous access: not enabled by our values
Prometheus ingress authentication: absent
Alertmanager ingress authentication: absent
Traefik access logs: disabled
Kubernetes NetworkPolicies: none
```

Recommended access model:

```text
Grafana: native named-user login; Viewer by default
Prometheus: Traefik authentication; operations/team only
Alertmanager: separate/stronger authentication; administrators only
exporter endpoints: never exposed
```

Credentials and certificate private keys must be Kubernetes Secrets created
outside Git and must never be printed in the journal.

## Shared versus dedicated floating IP

### Existing FIP `192.168.64.121`

Advantages:

- live and proven path to Traefik;
- proposed hostnames resolve now;
- no new floating-IP allocation or MetalLB Service is needed;
- smallest shared-infrastructure change.

Limitations:

- shares the public ingress IP with student applications;
- OpenStack security-group restrictions cannot distinguish monitoring hostnames
  from student hostnames on the same TCP 443 endpoint;
- monitoring isolation must rely primarily on TLS, authentication, and
  application-layer authorization;
- Traefik remains a single replica.

### Dedicated monitoring FIP

Advantages:

- allows an independently managed Neutron port/security group;
- can restrict TCP 443 to approved team/campus/VPN CIDRs without affecting
  student applications;
- cleaner ownership and rollback.

Required evidence before selecting this path:

- free floating-IP quota;
- whether Octavia is usable in this project;
- the exact current Neutron association for `192.168.64.121`;
- whether a second MetalLB VIP such as `192.168.128.201` can be represented by
  a Neutron port/allowed-address-pair without violating anti-spoofing;
- which security group is attached to that port;
- whether the existing pattern can be reproduced without editing node ports or
  the student ingress path.

The dedicated FIP remains an optional future network-isolation improvement.
For this MVP, the existing FIP is the proven, lower-complexity path selected by
the team after reviewing the evidence below.

## OpenStack inspection limitation

On `k3s-user`:

```text
openstack CLI: absent
OS_AUTH_URL/OpenStack environment: absent
```

The computer-use skill was used only to look for an already available Horizon
browser session. No Windows app or browser surface was exposed to the tool, so
Horizon could not be inspected and no login was attempted.

Previous user-supplied evidence confirms worker security-group rules allow
public TCP 80/443, and live reachability confirms the existing public path.
That evidence does not identify the VIP's Neutron port or quota.

## Read-only errors and corrections

1. A combined SSH wrapper had an unmatched quote around a JSONPath expression.
   It failed before its remote checks ran and changed nothing. Quote-sensitive
   output was removed from the retry.
2. The first retry used Ingress name `lb-test`; the actual name is
   `lb-test-ingress`. Kubernetes returned NotFound and `set -e` stopped the
   remaining read-only commands. The corrected command succeeded.
3. Initial mixed PowerShell output did not render the TCP booleans clearly.
   A direct string-form retry recorded TCP 80 and 443 as `True`.

## User-supplied OpenStack evidence

The user supplied Horizon screenshots showing:

```text
floating IP: 192.168.64.121
mapped fixed IP: 192.168.128.200
pool: Buet_Provider_Network
status: Active

port name: metallb-vip-port
fixed IP: 192.168.128.200
MAC: fa:16:3e:09:77:a8
attached device: Detached
port status: Down
admin state: True

floating-IP quota: 8 of 50 allocated
OpenStack ports: 23 of 500 used
Load Balancers page: unable to retrieve load balancers
```

The detached/down dummy Neutron port is consistent with this working design:
it reserves the fixed IP and provides the floating-IP association while
MetalLB, rather than a Nova device attachment, advertises the VIP. Live public
HTTP and HTTPS success is the decisive proof that the path works.

The user asked why a DNS A record was needed. The distinction was clarified
before proceeding:

```text
A record    -> IPv4
AAAA record -> IPv6
```

No team-controlled domain is required for this MVP because sslip.io
automatically returns an IPv4 A record derived from each hostname.

## Evidence-selected decision

The user explicitly selected:

```text
Use existing floating IP 192.168.64.121 with sslip.io hostnames
```

Final path:

```text
grafana.monitoring.192.168.64.121.sslip.io     --+
prometheus.monitoring.192.168.64.121.sslip.io  ---+--> 192.168.64.121
alerts.monitoring.192.168.64.121.sslip.io      --+
                                                       |
                                                       v
                                  metallb-vip-port / 192.168.128.200
                                                       |
                                                       v
                                           MetalLB -> Traefik
```

No new floating IP, Neutron port, MetalLB VIP, Octavia load balancer, or
OpenStack security-group rule will be created for the MVP. Because TCP 443 is
shared with student applications, monitoring-specific protection must be
implemented with trusted TLS, authentication, authorization, security headers,
and rate limiting.

## No-change verification

```text
Kubernetes resources created/updated/deleted: none
Helm releases changed: none
OpenStack resources changed: none
security-group rules changed: none
floating IPs changed: none
DNS changed: none
Windows/browser settings changed: none
```

## Step 12A result and next boundary

```text
exact public FIP selected: 192.168.64.121
exact private VIP selected: 192.168.128.200
Neutron port identified: metallb-vip-port
hostnames selected: three sslip.io names
new OpenStack resource required: no
trusted TLS currently present: no
authentication currently present: no
Step 12A: complete
```

Step 12B will prepare Ingress, TLS references, and authentication configuration
locally and validate it offline. It will not apply anything and requires
separate explicit approval.
