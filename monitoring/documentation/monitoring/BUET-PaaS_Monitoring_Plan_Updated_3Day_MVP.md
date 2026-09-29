# BUET-PaaS Monitoring Plan — A to Z, Beginner-Friendly, 3-Day MVP

> **Team update:** This document keeps the original 3-day monitoring plan and its good component-by-component structure, but adds a safety-first Day-0 baseline, capacity checks, post-install regression checks, one-change-at-a-time VM monitoring, conditional Prometheus persistence, and clearer rollback/testing rules. Since the team has confirmed that the current system does not already have Prometheus/Grafana/Alertmanager monitoring, the plan treats the monitoring stack as a new isolated layer rather than migrating an existing monitoring system.

## Revision 2026-09-24 - Permanent team access, APIs, persistence, and logs

This revision keeps the original 3-day MVP instructions and adds the production
follow-up that the team explicitly requested.

The original port-forward and SSH-tunnel instructions remain valid as private
break-glass/admin access. They are not the final team access method. The final
team-facing design will use the existing, proven OpenStack ingress floating IP
`192.168.64.121`, HTTPS, an authenticated ingress gateway, and the existing
Kubernetes `ClusterIP` services. Raw Grafana, Prometheus, Alertmanager, and
exporter ports will not be opened directly to the Internet.

This revision also makes the following distinctions explicit:

- Prometheus stores metrics, not application logs.
- The current MVP storage is ephemeral and must not be described as durable.
- Prometheus, Grafana, and Alertmanager expose APIs, but those APIs require the
  same gateway, authentication, and least-privilege controls as their UIs.
- Centralized Kubernetes/VM/application logs require a later Loki + Grafana
  Alloy phase.
- Every infrastructure change remains one permission-gated step with baseline,
  validation, regression checks, documentation, and rollback.

If an older access or security example in this document appears to conflict
with Sections 22A-22E, the newer Sections 22A-22E govern permanent browser/API
access. In particular, "never expose publicly" means never expose the raw
service ports; one controlled HTTPS gateway on TCP 443 is the approved design.


> **Audience:** BUET-PaaS team members who may not have prior Prometheus/Grafana/Kubernetes monitoring experience.
>
> **Main idea:** আমরা existing BUET-PaaS architecture বা VM topology change করব না। Monitoring layer existing system-এর চারপাশে add করব।
>
> **Primary goal for first 3 days:**  
> 1. k3s cluster monitor করা  
> 2. standalone OpenStack VMs monitor করা  
> 3. actual services UP/DOWN check করা  
> 4. browser থেকে Grafana dashboard দেখা  
> 5. basic alerts পাওয়া  
>
> **Not in first 3 days:** Loki, Wazuh, OpenTelemetry, Tempo, ELK/EFK, custom Backend/Deployer business metrics.

---

# 0. এক লাইনে পুরো Monitoring Architecture

```text
OpenStack VMs + k3s Cluster
          |
          | metrics
          v
      Prometheus
          |
          v
       Grafana
          |
          v
   Admin Web Dashboard

Prometheus
   |
   +--> Alertmanager --> Alerts/Silences

Blackbox Exporter
   |
   +--> checks actual HTTP service availability

node_exporter
   |
   +--> CPU/RAM/Disk/Network metrics

kube-state-metrics
   |
   +--> Pod/Deployment/Job/Node state
```

---

# 1. আমাদের Existing Infrastructure — কিছু Move করব না

বর্তমান OpenStack network:

```text
kubenet
CIDR: 192.168.128.0/24
```

বর্তমান VMs:

| VM | Private IP | Floating IP | Role |
|---|---:|---:|---|
| `k3s-control-01` | `192.168.128.101` | `192.168.65.122` | k3s control plane |
| `k3s-worker-01` | `192.168.128.121` | none | k3s worker |
| `k3s-worker-02` | `192.168.128.122` | none | k3s worker |
| `k3s-worker-03` | `192.168.128.123` | none | k3s worker |
| `k3s-user` | `192.168.128.151` | `192.168.64.242` | admin/management VM |
| `frontend-vm` | `192.168.128.15` | `192.168.67.159` | Next.js frontend |
| `backend-vm` | `192.168.128.131` | `192.168.64.228` | FastAPI backend |
| `database-vm` | `192.168.128.92` | `192.168.65.140` | database |
| `registry-vm-2` | `192.168.128.152` | `192.168.67.192` | Harbor registry |
| `sonarqube` | `192.168.128.33` | `192.168.67.252` | SonarQube |

**Important:** `backend-vm` এবং `sonarqube` যদি intentionally SHUTOFF থাকে, monitoring-এ তাদের জন্য alert suppress/maintenance mode রাখতে হবে।

---

# 2. কোন Monitoring Tool কোথায় থাকবে?

## k3s cluster-এর ভিতরে

একটি dedicated namespace:

```text
monitoring
```

এর ভিতরে থাকবে:

```text
Prometheus
Grafana
Alertmanager
Prometheus Operator
kube-state-metrics
node-exporter DaemonSet
Blackbox Exporter
```

Optional:

```text
Headlamp
```

Headlamp আলাদা namespace-এ রাখা ভালো:

```text
headlamp
```

## Standalone VMs-এ

প্রতি standalone Linux VM-এ:

```text
node_exporter :9100
```

Install করা হবে।

Target:

```text
frontend-vm
backend-vm
database-vm
registry-vm-2
sonarqube
k3s-user
```

k3s control/worker nodes-এ manually node_exporter install করব না, কারণ kube-prometheus-stack DaemonSet দিয়ে automatically করবে।

---

# 3. Tool-by-Tool — একদম সহজভাবে

# 3.1 kube-prometheus-stack

## এটা কী?

এটা একটি Helm chart bundle।

অর্থাৎ একটা command দিয়ে অনেক monitoring component install করা যায়:

```text
Prometheus
Grafana
Alertmanager
Prometheus Operator
kube-state-metrics
node-exporter
rules
dashboards
```

## কেন এটা ব্যবহার করব?

Manually সব component আলাদা install করলে:

```text
install
connect
RBAC
ServiceMonitor
dashboards
alerts
config
```

সব নিজে করতে হবে।

`kube-prometheus-stack` এগুলোর অনেক কিছু ready করে দেয়।

## আমাদের জন্য advantage

- fast setup
- standard Kubernetes monitoring stack
- built-in Grafana dashboards
- built-in alert rules
- Prometheus Operator already configured
- node-exporter DaemonSet automatically deploy হয়

## UI আছে?

Indirectly yes, কারণ এটা Grafana + Prometheus + Alertmanager UI install করে।

---

# 3.2 Prometheus

## কাজ কী?

Prometheus metrics collect করে এবং time-series database হিসেবে store করে।

Example:

```text
CPU usage
RAM usage
Disk usage
Pod count
Job status
HTTP probe result
```

## কিভাবে collect করে?

Prometheus `scrape` করে।

মানে নির্দিষ্ট interval পর পর:

```text
GET http://target:port/metrics
```

call করে।

Example:

```text
node_exporter:9100/metrics
```

## Data flow

```text
VM
 |
node_exporter
 |
 v
/metrics
 |
 v
Prometheus
```

## Prometheus কী store করে?

Example:

```text
node_cpu_seconds_total
node_memory_MemAvailable_bytes
kube_pod_status_phase
kube_job_status_failed
probe_success
```

## UI আছে?

হ্যাঁ।

Prometheus নিজস্ব web UI দেয়।

Normally:

```text
port 9090
```

Use case:

- target UP/DOWN check
- PromQL query test
- metric exists কিনা check
- graph quick debug

### MVP access

```bash
kubectl -n monitoring get svc
```

তারপর Prometheus service name দেখে:

```bash
kubectl -n monitoring port-forward svc/<prometheus-service> 9090:9090
```

Browser:

```text
http://localhost:9090
```

---

# 3.3 Grafana

## কাজ কী?

Grafana visualization tool।

Prometheus data collect করে, Grafana সেটা সুন্দর dashboard হিসেবে দেখায়।

## Flow

```text
Prometheus
   |
   v
Grafana
   |
   v
Browser
```

## Grafana-তে কী দেখা যাবে?

- CPU graph
- RAM graph
- Disk graph
- Node status
- Pod status
- Deployment replicas
- Failed Jobs
- Alerts
- Service availability

## UI আছে?

হ্যাঁ। Grafana নিজেই full web UI।

Normally:

```text
port 3000
```

আমাদের আলাদা monitoring admin frontend বানানোর দরকার নেই।

### Access

```bash
kubectl -n monitoring get svc
```

Grafana service identify করে:

```bash
kubectl -n monitoring port-forward svc/<grafana-service> 3000:80
```

Browser:

```text
http://localhost:3000
```

## Login credentials

kube-prometheus-stack install করার পরে admin password secret থেকে পাওয়া যায়।

Typical command pattern:

```bash
kubectl -n monitoring get secret <grafana-secret> \
  -o jsonpath="{.data.admin-password}" | base64 -d
```

Exact secret name `kubectl get secret -n monitoring` দিয়ে first verify করতে হবে।

---

# 3.4 node-exporter

## কাজ কী?

Linux machine-এর OS metrics expose করে।

### Metrics

```text
CPU
RAM
filesystem
disk
network
load average
uptime
```

## কোথায় install হবে?

### k3s nodes

Automatically as DaemonSet:

```text
k3s-control-01
k3s-worker-01
k3s-worker-02
k3s-worker-03
```

### standalone VMs

Manually:

```text
frontend-vm
backend-vm
database-vm
registry-vm-2
sonarqube
k3s-user
```

## Default port

```text
9100
```

## UI আছে?

না।

Browser-এ:

```text
http://<vm-private-ip>:9100/metrics
```

দিলে raw metrics দেখা যায়।

Visualization Grafana-তে।

---

# 3.5 kube-state-metrics

## কাজ কী?

Kubernetes API-এর object state metrics এ convert করে।

### Example

```text
Node Ready?
Pod Running?
Pod Pending?
Deployment replicas ready?
Job succeeded?
Job failed?
```

## node-exporter vs kube-state-metrics

```text
node-exporter
    = machine health

kube-state-metrics
    = Kubernetes object health
```

## Deployment

kube-prometheus-stack-এর সাথে automatically আসে।

## UI?

না, raw `/metrics` endpoint।

Grafana ব্যবহার করব।

---

# 3.6 Alertmanager

## কাজ কী?

Prometheus alert rules fire করলে Alertmanager manage করে।

Example:

```text
Disk < 10%
```

Prometheus:

```text
ALERT
```

Alertmanager:

```text
group
silence
deduplicate
route
notify
```

## UI আছে?

হ্যাঁ।

এখানে দেখা যাবে:

```text
active alerts
silences
alert groups
```

MVP-তে email/Discord লাগবে না।

### Access

Service identify:

```bash
kubectl -n monitoring get svc
```

তারপর:

```bash
kubectl -n monitoring port-forward svc/<alertmanager-service> 9093:9093
```

Browser:

```text
http://localhost:9093
```

---

# 3.7 Blackbox Exporter

## সমস্যা কী solve করে?

ধরো:

```text
backend-vm UP
CPU OK
RAM OK
```

কিন্তু FastAPI process crashed।

node_exporter বলবে VM healthy।

Blackbox Exporter actual HTTP endpoint probe করবে।

Example:

```text
http://backend/health
```

## Output

```text
probe_success = 1
```

মানে service reachable।

```text
probe_success = 0
```

মানে service unavailable।

## আমাদের targets

Phase 1/Day 2-তে:

```text
Frontend
Backend
Deployer
Harbor
SonarQube
```

## UI?

না।

Prometheus + Grafana use করবে।

---

# 3.8 Headlamp

## এটা কী?

Headlamp Kubernetes web UI।

## কেন useful?

Browser থেকে দেখতে পারবে:

```text
Pods
Deployments
Jobs
Namespaces
YAML
Events
resource status
```

## Grafana vs Headlamp

```text
Grafana
= Monitoring

Headlamp
= Kubernetes visual administration
```

## কিভাবে deploy?

```bash
helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/
helm repo update

helm upgrade --install headlamp \
  headlamp/headlamp \
  --namespace headlamp \
  --create-namespace
```

Access:

```bash
kubectl -n headlamp port-forward svc/headlamp 8080:80
```

Browser:

```text
http://localhost:8080
```

## 3-Day priority

Optional।

Core monitoring stable হলে deploy করা যাবে।

---

# 4. এখন কোন Tool বাদ?

First 3 days-এ বাদ:

```text
Loki
Grafana Alloy
Wazuh
OpenTelemetry
Tempo
ELK/EFK
custom Backend metrics
custom Deployer metrics
student application logs
```

## কেন?

কারণ আমরা first MVP-তে চাই:

```text
system healthy কিনা
VM healthy কিনা
k3s healthy কিনা
service alive কিনা
```

Logs/tracing/security SIEM next phase।

---

# 4.5 — ZERO-CHANGE BASELINE (IMPORTANT: DO THIS BEFORE INSTALLING ANYTHING)

This section is mandatory for our team because the goal is to add monitoring **without disturbing the existing BUET-PaaS workloads**.

At this point, we already know from the team that the current system does **not** have Prometheus/Grafana/Alertmanager monitoring installed. We therefore do not need to design around an existing monitoring stack. However, we should still record the current Kubernetes state before making any changes.

## Rule: Day 0 is read-only

Before the first Helm installation:

- do not delete anything
- do not restart existing application Pods
- do not scale existing workloads
- do not edit existing Deployments/Services
- do not change existing namespaces
- do not change networking
- do not change application configuration
- do not install anything yet

The purpose is simply to create a **before-installation snapshot**.

## 4.5.1 Read-only cluster inventory

Run:

```bash
kubectl get nodes -o wide
kubectl get namespaces
kubectl get pods -A -o wide
kubectl get deployments -A
kubectl get statefulsets -A
kubectl get daemonsets -A
kubectl get services -A
kubectl get jobs -A
kubectl get pvc -A
kubectl get storageclass
kubectl get ingress -A
kubectl cluster-info
kubectl version
helm version
```

Also record recent events:

```bash
kubectl get events -A --sort-by=.lastTimestamp
```

Save the output somewhere such as:

```text
monitoring/baseline/
```

For example:

```text
nodes.txt
pods-before.txt
deployments-before.txt
services-before.txt
jobs-before.txt
pvc-before.txt
storageclass.txt
events-before.txt
helm-before.txt
```

These files let us compare the cluster **before vs after** monitoring installation.

## 4.5.2 Confirm cluster capacity

Check each node:

```bash
kubectl describe node k3s-control-01
kubectl describe node k3s-worker-01
kubectl describe node k3s-worker-02
kubectl describe node k3s-worker-03
```

Look at:

```text
CPU capacity
Memory capacity
Allocatable CPU
Allocatable memory
DiskPressure
MemoryPressure
PIDPressure
```

The monitoring stack itself consumes CPU and RAM, so we should understand the available capacity before deploying it.

If `kubectl top nodes` works:

```bash
kubectl top nodes
```

If it fails because Metrics Server is not installed, **do not install Metrics Server just for this MVP**. That failure alone is not a blocker for Prometheus-based monitoring.

## 4.5.3 Confirm Helm state

Although the team knows there is no existing Prometheus/Grafana monitoring stack, check Helm releases once:

```bash
helm list -A
```

This is a read-only verification step and helps us avoid accidentally reusing an existing release name.

## 4.5.4 Define the safety checkpoint

Do not continue to installation until we have:

```text
[ ] Nodes are understood
[ ] Existing Pods are recorded
[ ] Existing Deployments are recorded
[ ] Existing Services are recorded
[ ] Existing Jobs are recorded
[ ] PVCs/StorageClasses are recorded
[ ] Recent events are recorded
[ ] Helm releases are recorded
[ ] Node pressure/capacity is understood
```

After the monitoring stack is installed, we will run the same important checks again and compare the result.

---

# 5. Installation-এর আগে কী কী জানা/verify করা লাগবে?

## 5.1 Admin VM

Preferred:

```text
k3s-user
```

এখানে `kubectl` + `helm` usable করতে হবে।

যদি kubeconfig এখনো না থাকে, bootstrap/recovery এর জন্য:

```text
k3s-control-01
```

use করা যাবে।

## 5.2 Check kubectl

```bash
kubectl version --client
kubectl get nodes -o wide
```

Expected:

```text
k3s-control-01 Ready
k3s-worker-01 Ready
k3s-worker-02 Ready
k3s-worker-03 Ready
```

## 5.3 Check Helm

```bash
helm version
```

If not installed, Helm install করতে হবে।

Ubuntu example:

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

তারপর:

```bash
helm version
```

## 5.4 Check StorageClass

```bash
kubectl get storageclass
```

Prometheus persistence পরে enable করতে StorageClass দরকার।

First 48h test temporary storage হলেও StorageClass status জানা জরুরি।

## 5.5 Check existing workloads

```bash
kubectl get pods -A
kubectl get deployments -A
kubectl get jobs -A
kubectl get svc -A
```

## 5.6 Check node resources

```bash
kubectl top nodes
```

যদি metrics-server না থাকে/command fail করে, installation-এর আগে সেটা issue না; Prometheus stack install করার পরে node metrics পাওয়া যাবে।

Also:

```bash
kubectl describe node k3s-control-01
kubectl describe node k3s-worker-01
```

Check:

```text
CPU capacity
RAM capacity
disk pressure
memory pressure
```

---

# 6. Repository Structure

BUET-PaaS repo-তে:

```text
monitoring/
├── README.md
├── prometheus/
│   └── values.yaml
├── blackbox/
│   ├── values.yaml
│   └── targets.yaml
├── external-vms/
│   └── scrape-config.yaml
├── dashboards/
│   └── buet-paas-overview.json
├── alerts/
│   └── basic-alerts.yaml
└── docs/
    └── troubleshooting.md
```

First 3 days-এর জন্য এই structure enough।

---

# 6.5 — SAFE INSTALLATION / ROLLBACK RULES

The monitoring stack should be isolated from application workloads as much as possible.

## Namespace isolation

All core monitoring components go into:

```text
monitoring
```

We do not place Prometheus/Grafana/Alertmanager into the application namespaces.

## Installation order

Use this order:

```text
1. Baseline / read-only checks
2. Create monitoring namespace
3. Add Helm repository
4. Create and review values.yaml
5. Helm install
6. Verify monitoring Pods
7. Re-check existing application workloads
8. Access Grafana / Prometheus / Alertmanager
9. Only then add standalone VM exporters
10. Only then add Blackbox probes
```

Do not combine all changes into one large troubleshooting session.

## Post-install regression check

Immediately after kube-prometheus-stack installation:

```bash
kubectl get pods -A
kubectl get deployments -A
kubectl get daemonsets -A
kubectl get services -A
kubectl get jobs -A
kubectl get events -A --sort-by=.lastTimestamp
```

Compare the important application workloads with the Day-0 baseline.

The expected result is:

```text
Existing application workloads remain healthy.
Only monitoring-related resources are newly added.
```

If an existing application unexpectedly changes state, **stop adding new monitoring components** and investigate before continuing.

## Rollback

If the monitoring Helm release itself must be removed:

```bash
helm uninstall monitoring -n monitoring
```

Then verify:

```bash
kubectl get pods -A
kubectl get deployments -A
kubectl get services -A
kubectl get events -A --sort-by=.lastTimestamp
```

Do not use rollback commands casually. First identify whether the problem is actually caused by the monitoring release.

---

# 7. DAY 1 — kube-prometheus-stack Deploy

# Step 1 — Admin host থেকে cluster verify

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get storageclass
helm version
```

যদি সব ঠিক থাকে next step।

---

# Step 2 — monitoring namespace create

```bash
kubectl create namespace monitoring
```

Verify:

```bash
kubectl get ns monitoring
```

---

# Step 3 — Helm repo add

```bash
helm repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts
```

Update:

```bash
helm repo update
```

Check:

```bash
helm search repo prometheus-community/kube-prometheus-stack
```

---

# Step 4 — values.yaml create

File:

```text
monitoring/prometheus/values.yaml
```

Beginner-friendly MVP:

```yaml
grafana:
  enabled: true

alertmanager:
  enabled: true

prometheus:
  enabled: true
  prometheusSpec:
    retention: 2d
    scrapeInterval: 30s
    evaluationInterval: 30s

kubeStateMetrics:
  enabled: true

nodeExporter:
  enabled: true
```

Important:

This is MVP starter config, not final production config।

First 48h:

```text
retention = 2d
```

পরে actual disk usage দেখে 15 days persistence decide করব।

---

# Step 5 — Helm install

From repo root:

```bash
helm upgrade --install monitoring \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f monitoring/prometheus/values.yaml
```

---

# Step 6 — Wait and verify Pods

```bash
kubectl get pods -n monitoring -w
```

Expected types:

```text
grafana
prometheus
alertmanager
operator
kube-state-metrics
node-exporter
```

Eventually:

```text
Running
```

If one Pod fails:

```bash
kubectl describe pod <pod-name> -n monitoring
kubectl logs <pod-name> -n monitoring
```

---

# Step 7 — Check Services

```bash
kubectl get svc -n monitoring
```

You should see services for:

```text
Grafana
Prometheus
Alertmanager
kube-state-metrics
```

---

# Step 8 — Access Grafana

Find Grafana service:

```bash
kubectl get svc -n monitoring | grep -i grafana
```

Then:

```bash
kubectl -n monitoring port-forward svc/<grafana-service> 3000:80
```

Open:

```text
http://localhost:3000
```

## Get password

First:

```bash
kubectl get secret -n monitoring | grep -i grafana
```

Then:

```bash
kubectl get secret <grafana-secret> \
  -n monitoring \
  -o jsonpath="{.data.admin-password}" | base64 -d
```

Usually user:

```text
admin
```

---

# Step 9 — Check built-in dashboards

Grafana:

```text
Dashboards
```

Search:

```text
Kubernetes
Nodes
Pods
Namespaces
Workloads
```

Do not immediately build dashboards manually।

First confirm built-in dashboards work।

---

# Step 10 — Access Prometheus

Find service:

```bash
kubectl get svc -n monitoring | grep -i prometheus
```

Port-forward:

```bash
kubectl -n monitoring port-forward svc/<prometheus-service> 9090:9090
```

Open:

```text
http://localhost:9090
```

Check:

```text
Status -> Targets
```

Expected most targets:

```text
UP
```

---

# Step 11 — Access Alertmanager

Find service:

```bash
kubectl get svc -n monitoring | grep -i alertmanager
```

Port-forward:

```bash
kubectl -n monitoring port-forward svc/<alertmanager-service> 9093:9093
```

Open:

```text
http://localhost:9093
```

---

# Step 12 — Day 1 Success Checklist

Day 1 complete when:

```text
[ ] monitoring namespace exists
[ ] Prometheus running
[ ] Grafana running
[ ] Alertmanager running
[ ] kube-state-metrics running
[ ] node-exporter DaemonSet running on 4 k3s nodes
[ ] Grafana opens
[ ] Prometheus opens
[ ] Alertmanager opens
[ ] Kubernetes node metrics visible
[ ] Pods/Deployments/Jobs visible
```

---

# 7.5 — CHANGE ONE THING AT A TIME

For standalone VM monitoring, install `node_exporter` **one VM at a time**.

Recommended order:

```text
frontend-vm
database-vm
registry-vm-2
k3s-user
backend-vm (only if active)
sonarqube (only if active)
```

After each VM:

```text
1. Install node_exporter
2. Verify node_exporter locally
3. Confirm Prometheus can scrape it
4. Confirm Grafana sees the metrics
5. Check the VM/application is still healthy
6. Move to the next VM
```

This makes troubleshooting and rollback much easier.

Never expose port `9100` to the public Internet. Use the private OpenStack network only.

---

# 8. DAY 2 — Standalone VM Monitoring

আমাদের k3s nodes Day 1 থেকেই monitor হবে।

এখন standalone OpenStack VMs।

# 8.1 Target VMs

Active first:

```text
frontend-vm
database-vm
registry-vm-2
k3s-user
```

When active:

```text
backend-vm
sonarqube
```

---

# 8.2 node_exporter install concept

Per VM:

```text
Download binary
Create user
Install binary
Create systemd service
Start service
Verify :9100
```

---

# 8.3 Example node_exporter Installation

First check architecture:

```bash
uname -m
```

Usually:

```text
x86_64
```

Choose a pinned official node_exporter version.

Example pattern:

```bash
cd /tmp

wget https://github.com/prometheus/node_exporter/releases/download/v<VERSION>/node_exporter-<VERSION>.linux-amd64.tar.gz

tar -xzf node_exporter-<VERSION>.linux-amd64.tar.gz

sudo cp node_exporter-<VERSION>.linux-amd64/node_exporter /usr/local/bin/
```

Create system user:

```bash
sudo useradd \
  --system \
  --no-create-home \
  --shell /usr/sbin/nologin \
  node_exporter
```

Check:

```bash
/usr/local/bin/node_exporter --version
```

---

# 8.4 systemd service

Create:

```bash
sudo nano /etc/systemd/system/node_exporter.service
```

Content:

```ini
[Unit]
Description=Prometheus Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter

[Install]
WantedBy=multi-user.target
```

Reload:

```bash
sudo systemctl daemon-reload
```

Enable + start:

```bash
sudo systemctl enable --now node_exporter
```

Check:

```bash
sudo systemctl status node_exporter
```

---

# 8.5 Verify locally

```bash
curl http://127.0.0.1:9100/metrics | head
```

Check listening:

```bash
ss -lntp | grep 9100
```

---

# 8.6 Security Group

Do not expose:

```text
9100
```

to Internet।

Bad:

```text
0.0.0.0/0 -> TCP 9100
```

Good:

```text
kubenet/private monitoring path -> TCP 9100
```

Because all VMs are on:

```text
192.168.128.0/24
```

Prometheus should use private IP।

---

# 8.7 Prometheus-এ standalone VM add

Simplest first MVP approach:

Prometheus additional scrape config / Probe resource / file-based config use করা যেতে পারে।

Conceptual target list:

```yaml
- targets:
    - 192.168.128.15:9100
    - 192.168.128.92:9100
    - 192.168.128.152:9100
    - 192.168.128.151:9100
```

Optional active:

```yaml
    - 192.168.128.131:9100
    - 192.168.128.33:9100
```

Each target label:

```text
frontend-vm
database-vm
registry-vm-2
k3s-user
backend-vm
sonarqube
```

Better final config Git-এ থাকবে।

---

# 8.8 Prometheus target verify

Prometheus UI:

```text
Status -> Targets
```

You should see standalone node exporters:

```text
UP
```

If DOWN:

Check:

```bash
curl http://<private-ip>:9100/metrics
```

Then check:

```text
Security Group
Linux firewall
node_exporter service
routing
```

---

# 8.5 — BLACKBOX PROBES: VERIFY TARGETS BEFORE ADDING THEM

Do not guess service ports, URLs, or health-check paths.

For each service:

```text
1. Confirm the real private/reachable URL
2. Confirm the port
3. Confirm the endpoint/path
4. Test it manually
5. Add it to Blackbox
6. Verify probe_success
7. Only then create an alert
```

Prefer a real health endpoint such as:

```text
/health
/ready
```

when the application already provides one.

A successful HTTP connection alone may not prove that the application itself is healthy.

For intentionally stopped services such as a deliberately shut-off VM, do not create noisy permanent alerts. Use maintenance/silence rules when appropriate.

---

# 9. DAY 2 — Blackbox Exporter

# 9.1 Why now?

node_exporter tells:

```text
VM healthy
```

Blackbox tells:

```text
service healthy
```

Need both।

---

# 9.2 Helm install Blackbox Exporter

Add repo already exists if Prometheus repo added.

Check:

```bash
helm search repo prometheus-community/prometheus-blackbox-exporter
```

Install:

```bash
helm upgrade --install blackbox \
  prometheus-community/prometheus-blackbox-exporter \
  --namespace monitoring
```

Verify:

```bash
kubectl get pods -n monitoring | grep blackbox
kubectl get svc -n monitoring | grep blackbox
```

---

# 9.3 What service URLs to probe?

Only confirmed URLs।

Examples conceptually:

```text
Frontend:
http://192.168.128.15:<port>/

Backend:
http://192.168.128.131:<port>/health

Deployer:
http://<deployer-private-endpoint>:5000/health

Harbor:
http(s)://192.168.128.152:<port>/<health-path>

SonarQube:
http://192.168.128.33:9000/
```

**Do not guess actual ports/path.**

First verify manually:

```bash
curl -I http://<target>
```

or:

```bash
curl -fsS http://<target>/health
```

---

# 9.4 Important Blackbox metric

```text
probe_success
```

Values:

```text
1 = success
0 = failure
```

Grafana dashboard-এ Stat panel:

```text
Backend      UP
Deployer     UP
Harbor       UP
Frontend     UP
SonarQube    MAINTENANCE / UP
```

---

# 10. DAY 3 — Dashboard

First custom dashboard:

```text
BUET-PaaS Monitoring Overview
```

## Row 1 — Platform Status

Panels:

```text
k3s-control-01    UP/DOWN
worker-01         UP/DOWN
worker-02         UP/DOWN
worker-03         UP/DOWN

Frontend HTTP     UP/DOWN
Backend HTTP      UP/DOWN
Deployer HTTP     UP/DOWN
Harbor HTTP       UP/DOWN
SonarQube HTTP    UP/DOWN/MAINT
```

---

## Row 2 — k3s Resources

Panels:

```text
Cluster CPU
Cluster RAM
Running Pods
Pending Pods
Failed Pods
Pod Restarts
Running Jobs
Failed Jobs
```

---

## Row 3 — Standalone VM Resources

For each VM:

```text
CPU %
RAM %
Disk %
Network RX/TX
Up/Down
```

Especially:

```text
registry-vm-2 Disk
```

Important because Harbor images consume storage।

---

## Row 4 — Kubernetes Workloads

Panels:

```text
Deployment desired replicas
Deployment ready replicas
Unavailable replicas
Jobs succeeded
Jobs failed
Pod restart count
```

---

# 11. Example PromQL Queries

## Target UP/DOWN

```promql
up
```

## Node CPU usage

Conceptual:

```promql
100 - (
  avg by(instance) (
    rate(node_cpu_seconds_total{mode="idle"}[5m])
  ) * 100
)
```

## Memory usage %

```promql
100 *
(
  1 -
  node_memory_MemAvailable_bytes
  /
  node_memory_MemTotal_bytes
)
```

## Filesystem usage %

```promql
100 *
(
  1 -
  node_filesystem_avail_bytes
  /
  node_filesystem_size_bytes
)
```

Filter out tmpfs/overlay where appropriate।

## Failed Jobs

```promql
kube_job_status_failed > 0
```

## Pod Restarts

```promql
increase(kube_pod_container_status_restarts_total[15m])
```

## Service availability

```promql
probe_success
```

---

# 12. Alerts — প্রথমে শুধু Useful Alerts

Do not create 50 alerts।

Start with:

```text
KubernetesNodeNotReady
StandaloneVMDown
FrontendDown
BackendDown
DeployerDown
HarborDown
NodeDiskLow
RegistryDiskLow
PodCrashLooping
DeploymentUnavailable
BuildJobFailed
PrometheusTargetDown
```

---

# 13. Alert Rule Concept

Example:

```text
Backend probe fails
for 2 minutes
-> BackendDown
```

Example PromQL:

```promql
probe_success{service="backend"} == 0
```

With:

```yaml
for: 2m
```

---

# 14. Maintenance Mode

Important:

If:

```text
backend-vm SHUTOFF intentionally
sonarqube SHUTOFF intentionally
```

then alert should not keep firing।

Options:

1. temporarily silence in Alertmanager
2. disable target until service expected online
3. add maintenance label and alert filter

MVP easiest:

```text
Alertmanager Silence
```

---

# 15. Alertmanager UI কীভাবে use করব?

Access:

```text
http://localhost:9093
```

From UI:

```text
Alerts
Silences
Status
```

If SonarQube maintenance:

```text
Create Silence
matcher:
service="sonarqube"
```

Expiration:

```text
e.g. 6 hours
```

---

# 16. Headlamp Optional Day 3

If monitoring stable:

```bash
helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/
helm repo update

helm upgrade --install headlamp \
  headlamp/headlamp \
  --namespace headlamp \
  --create-namespace
```

Verify:

```bash
kubectl get pods -n headlamp
kubectl get svc -n headlamp
```

Access:

```bash
kubectl -n headlamp port-forward svc/headlamp 8080:80
```

Browser:

```text
http://localhost:8080
```

Use cases:

```text
inspect Pods
inspect Jobs
view Events
view YAML
inspect Deployment replicas
```

Not a Prometheus replacement।

---

# 17. Troubleshooting A to Z

## Problem: Grafana Pod not Running

```bash
kubectl get pods -n monitoring
kubectl describe pod <grafana-pod> -n monitoring
kubectl logs <grafana-pod> -n monitoring
```

---

## Problem: Prometheus target DOWN

Check:

```text
target address
port
Security Group
firewall
service
routing
```

Manual:

```bash
curl http://<target>:9100/metrics
```

---

## Problem: node_exporter VM service not working

```bash
sudo systemctl status node_exporter
sudo journalctl -u node_exporter -n 100 --no-pager
ss -lntp | grep 9100
```

---

## Problem: Blackbox probe failure

First direct check:

```bash
curl -v http://<service>
```

If direct curl fails, Blackbox problem না; target service/network problem।

---

## Problem: Grafana dashboard empty

Check:

```text
Prometheus data source connected?
Prometheus target UP?
Query correct?
Time range correct?
```

Prometheus UI-তে same query test করো।

---

# 18. Security Rules

Never expose publicly:

```text
Prometheus 9090
Grafana 3000
Alertmanager 9093
node_exporter 9100
Blackbox Exporter
```

Use:

```text
kubectl port-forward
SSH tunnel
private network
```

First MVP-তে এটাই safest।

---

# 19. Data Persistence — এখন কী করব?

First 48 hours:

```text
temporary Prometheus retention
```

Use:

```text
2 days
```

Then measure:

```text
TSDB size
bytes/day
CPU
RAM
number of active series
```

Then decide persistent PVC।

Do not blindly allocate huge storage।

---

# 20. 3-Day Final Deliverable

After 3 days, team should have:

## UIs

```text
Grafana
Prometheus
Alertmanager
Headlamp (optional)
```

## Monitoring Coverage

```text
4 k3s nodes
Pods
Deployments
Jobs
standalone VMs
Frontend availability
Backend availability
Deployer availability
Harbor availability
SonarQube availability
```

## Metrics

```text
CPU
RAM
Disk
Network
Node Ready
Pod status
Pod restart
Deployment replica
Job failure
VM UP/DOWN
Service UP/DOWN
```

## Alerts

```text
Node down
VM down
Service down
Disk low
Pod crash
Deployment unavailable
Build job failed
```

---

# 21. What NOT to do yet

Do not spend the 3-day sprint on:

```text
Loki
Wazuh
OpenTelemetry
Tempo
custom Backend metrics
custom Deployer metrics
student logs
custom monitoring frontend
```

First make the foundation stable।

---

# 22. After 3 Days — Next Phase

Then:

```text
Backend :9102 custom metrics
Deployer :9101 custom metrics
pipeline stage metrics
build/deploy success history
polling metrics
```

After that:

```text
Loki + Alloy
```

Then:

```text
Wazuh / tracing if needed
```

---

# 22A. Permanent Browser Access through the Existing Ingress Floating IP

## Outcome

The team must be able to open the monitoring tools from a normal browser
without keeping a terminal or `kubectl port-forward` process running.

The approved target architecture is:

```text
Team browser
    |
    | HTTPS TCP 443
    v
Existing OpenStack ingress FIP 192.168.64.121
    |
    v
Existing Neutron port / MetalLB VIP 192.168.128.200
    |
    v
Existing k3s Traefik Ingress Controller
    |
    +--> Grafana ClusterIP
    +--> Prometheus ClusterIP
    +--> Alertmanager ClusterIP
```

The Kubernetes services remain `ClusterIP`. The ingress gateway, not the raw
service ports, is the only browser-facing entry point.

## Floating-IP decision after Step 12A evidence

Use the existing public PaaS ingress path:

```text
192.168.64.121 floating IP
    -> 192.168.128.200 fixed IP
    -> metallb-vip-port
    -> MetalLB L2 advertisement
    -> Traefik LoadBalancer Service
```

Horizon and live network evidence confirmed this association is Active. The
`metallb-vip-port` is intentionally detached from a Nova instance; MetalLB
advertises the VIP from a K3s node. The public HTTP and HTTPS paths already
work. OpenStack floating-IP quota is 8/50, but no new allocation is required.

The team explicitly selected `192.168.64.121` for monitoring. Do not allocate a
new floating IP, create a second VIP port, use Octavia, or attach a floating IP
to a worker/control VM for this MVP. Octavia currently returns an unable-to-
retrieve error in Horizon.

Do not reuse the `frontend-vm` floating IP. Monitoring will share the existing
cluster ingress controller, not the frontend VM or its reverse proxy.

## URL design

Use three sslip.io hostnames that automatically resolve through DNS A records
to the selected IPv4 floating IP. A record means IPv4; AAAA means IPv6.

```text
https://grafana.monitoring.192.168.64.121.sslip.io
https://prometheus.monitoring.192.168.64.121.sslip.io
https://alerts.monitoring.192.168.64.121.sslip.io
```

Host-based routing is preferred because it avoids subpath rewrites and keeps
each tool's externally advertised URL correct.

No separately controlled DNS domain is required for routing because sslip.io
derives the IPv4 address from each hostname. Host-based routing is retained;
path-based routing is not planned. Trusted TLS is still required because the
current `TRAEFIK DEFAULT CERT` does not match these names and is not trusted.

### TLS trust constraint discovered in Step 12C

Routing and public-certificate ownership are different concerns. The selected
address `192.168.64.121` is RFC1918 private space. It is reachable on the
BUET/campus path but not globally Internet-routable. Therefore a public ACME
HTTP-01 validator cannot reach these sslip.io names. DNS-01 also cannot be used
without control of the sslip.io DNS zone. sslip.io has additionally experienced
shared-domain public-CA rate-limit exhaustion.

Do not install cert-manager and repeatedly attempt Let's Encrypt HTTP-01 for
this private address. The permitted trust models are:

1. **Current private/campus MVP:** issue a private-CA leaf certificate for the
   three names and install only that CA's public certificate into authorized
   team device trust stores. Protect and plan renewal of the CA private key.
2. **Preferred production end state:** obtain a BUET/team-controlled subdomain
   and DNS-01 capability, then use a public ACME issuer with automatic renewal.

The private-CA model requires explicit approval because it changes the trust
store of every authorized client. The production model requires DNS ownership
that is not currently available. Plain HTTP, the Traefik default certificate,
and browser-warning bypass remain unacceptable final states.

The team approved the private/team-CA model for VPN-only access in Step 12C1.
The certificate and authentication Secrets were prepared, Step 12D applied the
routes, and Step 12E verified all three interfaces from a trusted browser. Only
the CA public certificate may be distributed to authorized devices; never
export the CA private key. The leaf certificate expires on 2027-09-24 and must
be renewed before then.

## Authentication and authorization

| Tool | Browser access | Required control |
|---|---|---|
| Grafana | Team-facing | HTTPS, named users, Viewer by default, limited Admin accounts |
| Prometheus | Operations/team only | HTTPS, ingress authentication, source restriction where possible |
| Alertmanager | Administrators only | HTTPS, stronger ingress authentication, no student/public access |
| node_exporter | None | Private TCP 9100 only; scraped by Prometheus |
| kube-state-metrics | None | Cluster-private only |

Prometheus and Alertmanager must not rely on obscurity. Put them behind an
authenticated reverse proxy/Ingress middleware. Prefer OIDC/OAuth2 if the team
has an identity provider; otherwise use strong Basic Auth stored in a
Kubernetes Secret outside Git until OIDC is available.

Grafana requirements:

- rotate the bootstrap admin password;
- create named team accounts or configure OAuth/OIDC;
- use Viewer as the default role;
- keep anonymous access disabled;
- store credentials/tokens in Kubernetes Secrets, never in this repository.

## OpenStack security-group policy

The selected floating IP and VIP already serve student applications on public
TCP 80/443. OpenStack security groups operate on IP/port, not HTTP hostname, so
restricting shared TCP 443 to a team CIDR would also restrict student apps.

For this MVP, make no OpenStack security-group change. Protect monitoring at
the HTTPS/Ingress/application layers with trusted TLS, authentication,
authorization, security headers, and rate limiting. A future dedicated FIP may
be considered if monitoring-only network allowlisting becomes a requirement.

Never add public ingress for:

```text
3000  Grafana raw service
9090  Prometheus raw service
9093  Alertmanager raw service
9100  node_exporter
9115  Blackbox Exporter
```

Keep the existing floating-IP mapping, `metallb-vip-port`, MetalLB VIP, and all
application security groups unchanged.

## Permission-gated implementation sequence

### Step 12A - Read-only ingress and floating-IP preflight

Inspect without changing anything:

- current Traefik Deployment/DaemonSet, Service, ports, and node placement;
- ServiceLB/MetalLB address pools and advertisements;
- worker/control listeners on TCP 80/443;
- OpenStack ports, security groups, floating-IP quota, and Octavia availability;
- DNS/domain and TLS certificate options;
- intended users and their source CIDRs;
- collisions with existing student application routes;
- current Kubernetes and application health baseline.

Output: one selected ingress target and exact network path. Stop for approval.

### Step 12B - Prepare browser-access configuration locally

Add repository configuration without applying it:

- ingress routes for the three tools;
- TLS secret references, but no secret values;
- auth middleware/proxy configuration;
- Grafana public URL settings;
- Prometheus and Alertmanager external URL settings;
- rate-limit/security-header policy; do not assume a monitoring-only OpenStack
  allowlist is possible on the shared FIP;
- NetworkPolicy if supported;
- verification and rollback commands.

Render/lint locally against the pinned chart and inspect only the relevant
resources. Stop for approval.

### Step 12C - Prepare TLS and authentication Secrets

After separate approval:

- keep floating IP `192.168.64.121` and `metallb-vip-port` unchanged;
- first resolve the Step 12C trust-model gate: private/team CA for managed
  devices, or a controlled DNS zone with public ACME DNS-01;
- do not attempt public ACME HTTP-01 against private `192.168.64.121`;
- only after the trust model is explicitly approved, provision a certificate
  for the three sslip.io hosts or approved replacement hostnames;
- create Grafana/team accounts or identity integration;
- create separate Prometheus and Alertmanager authentication material;
- create Kubernetes Secrets without printing or committing their values;
- verify the existing FIP/VIP path again before applying routes.

Step 12C1 completed using the approved private/team-CA branch without
installing cert-manager. Four monitoring Secrets were created, values hidden,
and the leaf/CA key pairs were verified. No Ingress was applied.

### Step 12D - Apply authenticated HTTPS ingress

After separate approval:

- use the separately prepared credentials/certificate Secrets without printing
  or committing them;
- apply the reviewed ingress configuration atomically where possible;
- wait for reconciliation;
- confirm certificates, host routing, and external URLs;
- keep raw services as `ClusterIP`.

Implementation status (2026-09-24): **complete**. The approved VPN-only HTTPS
routes were applied with Helm revision 5 and the reviewed Traefik middleware.
All raw monitoring Services remain `ClusterIP`; ports 3000, 9090, 9093, and
9100 are not reachable on the ingress address. Automated TLS, authentication,
target-health, dashboard-count, and application-regression checks passed. Step
12E subsequently completed trusted-browser/UI verification.

### Step 12E - Browser, security, and regression verification

Verify all of the following:

```text
Grafana opens through HTTPS from an approved browser
Prometheus opens only after authentication
Alertmanager opens only for administrators
unauthenticated requests are rejected
raw ports 3000/9090/9093/9100 remain unreachable publicly
Grafana dashboards still query Prometheus
Prometheus targets remain healthy
student frontend/backend behavior is unchanged
all k3s nodes and monitoring Pods remain healthy
```

Port-forward remains documented as the emergency fallback.

Implementation status (2026-09-24): **complete**. Grafana dashboards and node
panels, Prometheus targets and node-count query, and Alertmanager Alerts,
Silences, and Status were verified through the VPN HTTPS links. No certificate
warning or failed login was reported. The five visible Alertmanager alerts are
carried into Step 13A for read-only cause and severity review.

## Browser-access rollback

Rollback in reverse dependency order:

1. remove only the new ingress routes/auth middleware;
2. verify the tools remain available privately by port-forward;
3. remove only monitoring-specific TLS/auth Secrets after confirming no other
   resource uses them;
4. do not disassociate `192.168.64.121`;
5. do not delete or edit `metallb-vip-port` or VIP `192.168.128.200`;
6. do not remove monitoring workloads, existing application routes/rules, or
   existing application floating IPs.

Every rollback target must be identified by exact resource name/ID before
deletion.

---

# 22B. Metrics API Access Plan

## Available APIs

Prometheus already provides the main metrics API:

```text
GET /api/v1/query
GET /api/v1/query_range
GET /api/v1/series
GET /api/v1/labels
GET /api/v1/targets
```

Example use cases:

```text
instant health:       query=up
node count:           query=count(kube_node_info)
pod inventory:        query=count(kube_pod_info)
time-range CPU/RAM:   /api/v1/query_range
target audit:         /api/v1/targets
```

Alertmanager provides `/api/v2/alerts`, `/api/v2/silences`, and status APIs.
Grafana provides authenticated health, search, dashboard, annotation, and
service-account APIs.

Exporter `/metrics` endpoints are scrape endpoints, not team/public APIs. They
remain private.

## API security design

API clients use the same HTTPS floating-IP gateway. Do not expose the raw
Prometheus or Alertmanager service directly.

Requirements:

- dedicated service identity/token per integration;
- read-only access wherever possible;
- token stored in a secret manager or protected environment, not Git;
- source-IP restriction for automated clients when practical;
- request timeout, response-size limits, and rate limiting;
- audit which client owns every token;
- no Grafana bootstrap-admin credential in application code.

Prometheus queries can be expensive. Define approved recording rules or a
small internal API facade for frequently repeated application queries rather
than allowing arbitrary high-cardinality queries from untrusted clients.

## API verification

Test through the final HTTPS URL:

```text
valid identity + safe query -> HTTP 200 and expected JSON
missing/invalid identity    -> HTTP 401/403
raw service from Internet   -> blocked
expensive/oversized request -> limited or rejected
```

API enablement is a separate permission-gated step after browser ingress is
stable.

---

# 22C. What Is Logged Now and the Centralized Logging Plan

## Current state

Prometheus stores time-series metrics; it does not store application logs.
Grafana visualizes data; it is not a log database. Alertmanager manages current
alert groups and silences; it is not a durable alert-history database.

The monitoring Pods write their own process logs to stdout/stderr. These can be
read with `kubectl logs`, subject to container runtime rotation and Pod
lifecycle. They are not currently collected into a centralized searchable log
store.

Current centralized student-application logs: **not implemented**.

## Planned architecture

After core metrics, browser ingress, and storage are stable:

```text
Kubernetes Pod logs + selected VM/system logs
                   |
                   v
              Grafana Alloy
                   |
                   v
                  Loki
                   |
                   v
          Grafana Explore/Dashboards
```

Alloy is preferred over starting a new Promtail deployment. Scope collection
carefully:

- monitoring namespace logs;
- student application namespace logs;
- ingress/controller logs;
- selected VM service/journald logs only when a secure transport is designed;
- labels limited to useful low-cardinality fields such as cluster, namespace,
  workload, Pod, container, service, and environment.

Do not turn request IDs, user IDs, full URLs, stack traces, or arbitrary JSON
fields into high-cardinality index labels.

## Log safety and retention

Before ingestion:

- identify and redact passwords, tokens, cookies, Authorization headers, and
  student personal data;
- define who may view which namespaces;
- measure bytes/day;
- choose a short initial retention;
- define persistent storage and disk alerts;
- document deletion and incident-access procedures.

Start with a limited namespace pilot. Expand only after disk usage and query
performance are measured. Loki + Alloy requires its own plan, values files,
capacity review, rollback, and explicit approval.

---

# 22D. Persistence and Backup Before Depending on the URLs

The current MVP settings are deliberately ephemeral:

```text
Prometheus retention: 2d, no PVC
Grafana persistence: disabled
Alertmanager storage: no PVC
```

Consequences:

- Prometheus history may disappear when its Pod/storage is recreated;
- manually created Grafana users/dashboards/settings may disappear;
- Alertmanager silences/state may disappear;
- provisioned dashboards in Git/ConfigMaps can be recreated, but manual-only
  changes are not a backup strategy.

After measuring the first 48 hours, prepare a separate persistence step:

1. confirm the StorageClass, reclaim policy, expansion support, and free quota;
2. record Prometheus TSDB bytes/day and active-series count;
3. size a Prometheus PVC for the agreed retention plus safety margin;
4. add a small Grafana PVC or provision all important dashboards/config as
   code;
5. decide whether Alertmanager silence persistence is required and add its PVC;
6. add PVC usage and disk-full alerts;
7. test one controlled restart and recovery;
8. document snapshot/backup and restore procedures.

No PVC or retention increase should be applied merely because a browser URL
exists. Capacity evidence and a separate approval are required.

---

# 22E. Revised Permission-Gated Order from the Current State

The original Day-0 through initial stack installation work remains valid. From
the current implementation state, use this order:

```text
11A2  COMPLETE - frontend-vm exporter and Prometheus target UP
12A-E COMPLETE - VPN HTTPS ingress, authentication, and browser verification
13A   COMPLETE - stability, alert, target, endpoint, and capacity audit
14A-D Local node_exporter install and restricted control-plane reachability
      complete on database, registry, k3s-user, and backend; scrape is pending
14E   SonarQube host key, exporter install, and restricted control-plane path
      verified; Prometheus scrape is pending
14A3  Six-target standalone scrape overlay prepared; pinned lint and focused
      render passed; live atomic apply is pending
14A4  COMPLETE - Helm revision 6 deployed atomically; all six standalone VM
      exporters UP, 31 total targets UP, and zero targets DOWN
15A   COMPLETE - frontend, backend, deployer, Harbor, and SonarQube endpoints
      confirmed; Harbor requires its public CA with strict TLS verification
15B   COMPLETE - pinned secure Blackbox configuration and staged target
      overlays passed Helm render and native exporter parser validation
15C   COMPLETE - ClusterIP exporter revision 1 and frontend canary are healthy
15D1  COMPLETE - cumulative frontend-plus-backend overlay passed lint,
      render, isolation, and native config validation
15D2  COMPLETE - uniquely labeled frontend/backend probes are both UP;
      safe verifier rollbacks exposed and corrected duplicate `up` labels
15D3  COMPLETE - cumulative frontend/backend/deployer overlay passed pinned
      lint, render, isolation, security, and native config validation
15D4  COMPLETE - Blackbox revision 7; frontend/backend/deployer probes UP,
      34 total targets UP, zero DOWN, rollback guard not triggered
15D5  COMPLETE - cumulative strict-TLS Harbor overlay passed endpoint/CA,
      pinned lint/render, isolation, security, and native config validation
15D6  COMPLETE - Blackbox revision 8; strict-TLS Harbor and prior probes UP,
      35 total targets UP, zero DOWN, rollback guard not triggered
15D7  COMPLETE - SonarQube HTTP 200/status UP and exact final five-target
      overlay passed pinned lint/render, isolation, and native validation
15D8  COMPLETE - Blackbox revision 9; all five service probes UP,
      36 total targets UP, zero DOWN, rollback guard not triggered
16A   COMPLETE - 16-panel overview dashboard, deterministic ConfigMap, and
      offline validator prepared; Kustomize and PromQL checks passed
16B   COMPLETE - provisioned 16-panel overview dashboard live; all 16 queries
      executed against Prometheus, 36 targets UP and zero DOWN
16C   COMPLETE - four focused MVP alert rules and maintenance policy prepared;
      offline promtool and read-only live query checks passed
16D   COMPLETE - four PrometheusRule alerts live, healthy and inactive;
      synthetic pending/firing/resolved tests passed without service disruption
16E   COMPLETE - team chose manual Grafana/Alertmanager UI review for MVP;
      effective Alertmanager receiver is null, no email/chat receiver configured
17A-E Measure representative 48-hour load, then add persistence per component
18    Add project-scoped monitoring API/UI for normal BUET-PaaS users
19    Pilot Loki + Alloy only after storage/privacy/access review
```

Each numbered substep is a separate permission boundary. The authoritative
detailed continuation and acceptance criteria are in `step-13-plan.md`. Do not
combine VM installations, scrape changes, probes, alert rules, persistence,
user API integration, and logging into one change window.

---

# 23. Final Mental Model

```text
Prometheus
= data collector + time-series database

Grafana
= monitoring website/dashboard

Alertmanager
= alert management website

node_exporter
= Linux VM/node metrics exporter

kube-state-metrics
= Kubernetes object-state exporter

Blackbox Exporter
= real service reachability checker

Headlamp
= optional Kubernetes web management UI

kube-prometheus-stack
= installer/bundle that gives us most of the monitoring stack quickly
```

---

# 24. Original 3-Day Order and Revised Continuation

The following list is retained as the original MVP order. Items already
completed must not be repeated. After the current implementation point, follow
Section 22E for the floating-IP browser access, API, persistence, and logging
continuation.

```text
1. Verify k3s
2. Verify kubectl
3. Verify Helm
4. Check StorageClass
5. Create monitoring namespace
6. Install kube-prometheus-stack
7. Open Grafana
8. Confirm built-in Kubernetes dashboards
9. Open Prometheus
10. Check targets
11. Open Alertmanager
12. Install standalone VM node_exporter
13. Add VM targets to Prometheus
14. Install Blackbox Exporter
15. Add service probes
16. Build BUET-PaaS Overview dashboard
17. Add 8-12 basic alerts
18. Test safely
19. Document commands/results
20. Optional Headlamp
```

এই order follow করলে first 3 days-এর monitoring MVP practical এবং demonstrable হবে।
