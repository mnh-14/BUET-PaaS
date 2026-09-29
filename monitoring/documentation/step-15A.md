# Step 15A - Read-only Blackbox endpoint and TLS preflight

## Status

- Date: 2026-09-25 (Asia/Dhaka)
- Permission: `Approve Step 15A - run read-only Blackbox endpoint and TLS preflight`
- Result: **complete**
- Live/repository configuration mutation: none

## Confirmed probe matrix

| Service | Recommended target | Status and semantic marker | Decision |
|---|---|---|---|
| BUET-PaaS frontend | `http://192.168.128.15/` | HTTP 200; `BUET-PaaS` marker present | GO |
| BUET-PaaS backend | `http://192.168.128.131:8020/health` | HTTP 200; status `ok`, version `0.2.0`, MongoDB connected | GO |
| PaaS deployer | `http://paas-deployer.buet-paas-system-team23.svc.cluster.local/health` | service proxy 200; body status `ok`; Pod Ready 1/1 | GO |
| Harbor | `https://192.168.128.152/api/v2.0/health` | verified TLS; HTTP 200; status/components healthy | GO with mounted Harbor CA |
| SonarQube | `http://192.168.128.33:9000/api/system/status` | HTTP 200; status `UP` | GO |

The frontend public/nginx path is preferred over port 3000 because it represents
the VM's real application entry point. The backend health response includes its
database dependency. MongoDB itself is therefore not added as a separate HTTP
probe. The deployer uses stable Kubernetes service DNS rather than Pod or
ClusterIP identity.

## Deployer evidence

```text
namespace:       buet-paas-system-team23
Service:         paas-deployer, ClusterIP, port 80
service IP:      10.43.78.157
endpoint:        10.42.2.104:5000
Pod:             paas-deployer-b4bcb5857-s5wtb
Pod state:       1/1 Running, zero restarts
/health body:    {"status":"ok"}
```

The Kubernetes API service proxy returned the health body. This is a read-only
way to confirm Service routing without creating a diagnostic Pod. The eventual
Blackbox target should use the in-cluster DNS name listed in the matrix.

## Harbor redirect and TLS findings

Harbor HTTP returns:

```text
HTTP/1.1 308 Permanent Redirect
Location: https://192.168.128.152:443/api/v2.0/health
```

The direct HTTPS target is preferred so the probe explicitly measures TLS.

Leaf certificate:

```text
subject:             CN=192.168.128.152
issuer:              CN=Harbor-CA
SANs:                192.168.128.152, 192.168.67.192
valid:               2026-09-04 through 2028-12-07
SHA-256 fingerprint: 4D:50:44:43:4E:43:7C:7A:86:68:4E:3D:88:DB:B8:AA:
                     F1:D3:61:5D:04:C0:46:A4:87:73:FF:3E:8A:91:EC:58
public file SHA-256: 2f0641e5290a58706352a50553ec7391cbadc889af4381c7bd96d08e7e583145
```

Harbor CA:

```text
subject/issuer:      CN=Harbor-CA (self-signed CA)
valid:               2026-09-04 through 2036-09-01
SHA-256 fingerprint: F2:2D:B8:38:48:10:85:E2:17:CD:50:36:6A:3D:91:48:
                     4E:F5:D0:9B:19:8A:B3:4E:BD:9B:FD:B5:6D:67:BD:FB
public file SHA-256: 6fecd502db98d54578c590c385df4a3d590caf495e26ed770e54bdc2f6df6d44
source path:         /etc/docker/certs.d/192.168.128.152/ca.crt
```

Both certificates are valid for more than 90 days. Verification with that CA
returned TLS 1.3, `TLS_AES_256_GCM_SHA384`, hostname/IP match, and
`Verification: OK`. The health API then returned HTTP 200 and all components
healthy.

Default trust correctly failed with `unable to get local issuer certificate`
and verification result 20. This is not an endpoint failure; it proves the
future Blackbox Pod must mount the public Harbor CA and reference it in its TLS
module. `insecure_skip_verify` is prohibited.

## Proposed module semantics for Step 15B

The offline configuration should prepare a small allowlisted set:

```text
frontend module:  require HTTP 200 and BUET-PaaS body marker
JSON-ok module:   require HTTP 200 and status=ok (backend and deployer)
Harbor module:    require HTTP 200, verified Harbor CA/SAN, healthy marker
SonarQube module: require HTTP 200 and status=UP marker
```

Use GET, bounded timeouts shorter than the Prometheus scrape timeout, and IPv4
where protocol selection is configurable. Do not probe login credentials,
write endpoints, repository operations, database ports, Pod IPs, floating IPs,
or student application endpoints in this platform-level MVP.

## Security and capacity preflight

```text
existing Blackbox resources: absent
Service port 9115:            unused
existing NetworkPolicies:     none
node CPU usage:               2% to 6%
node memory usage:            23% to 41%
Prometheus placement:         k3s-worker-03
Prometheus current targets:   31 UP, zero DOWN
Helm revision:                6, deployed
```

Blackbox Exporter must remain `ClusterIP`; no Ingress, NodePort, floating-IP
rule, or raw 9115 exposure is allowed. Because Blackbox accepts a target
parameter and can otherwise become an internal request proxy, Step 15B must
also prepare an ingress NetworkPolicy that allows port 9115 only from the
Prometheus Pod identity. The policy and Pod labels must be rendered and checked
before any apply. No user-controlled target may be passed through the platform
frontend or API.

## Corrected non-mutating diagnostics

One nested curl timing format lost its quoting, causing curl to treat format
fragments as hostnames and print the frontend/JSON response bodies. No request
wrote data and no credential was present; status and body evidence remained
read-only. Timing values from that wrapper were discarded.

A service-port jsonpath expression also lost quoting and failed to parse. The
first JSON marker expressions were similarly malformed. Corrected simple YAML
port scanning and literal response-marker checks confirmed port 9115 unused and
all expected markers present. No failed wrapper changed state.

## Result and next boundary

All five platform endpoints are safe candidates for a narrowly scoped
Blackbox MVP. Harbor is conditional on strict CA mounting and verification.
Step 15B may export only the public Harbor CA, prepare a pinned Blackbox chart
overlay, allowlisted modules/targets, ClusterIP Service, and Prometheus-only
NetworkPolicy, then lint/render offline. It must not apply live resources.

