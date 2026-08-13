# BUET-PaaS — Project Documentation

**Team:** Cloudify (Team 23)
**Mentor:** Tirzok Private Limited

---

## 1. General Project Idea

BUET-PaaS is a **Git-to-Deploy DevSecOps backend** — a self-service Platform-as-a-Service built on top of BUET's own OpenStack private cloud. The goal is to give a developer inside BUET the same experience they'd get from a commercial PaaS (like Heroku, Vercel, or Render), but running entirely on university infrastructure, with security scanning baked into the pipeline rather than bolted on afterward.

### End Goal

A developer should be able to:

1. Push code to a Git repository.
2. Have the platform automatically detect the push, pull the code, run it through security scanning (SAST, secret detection, dependency/image scanning), build a container image, and push that image to a private registry.
3. Have the platform deploy the scanned, built image to a Kubernetes cluster (k3s) running on BUET's OpenStack cloud — without the developer touching `kubectl`, Docker, or OpenStack directly.
4. See the live status of their deployment (building → scanning → deploying → live) and get a public URL for their running service.

**Example:** A student pushes a Flask app to their repo. Within a few minutes, without any manual DevOps work, they get a link like `https://their-app.buet-paas.dev` serving their app — while behind the scenes the platform has already scanned their code for vulnerabilities and secrets, built and scanned the container image, and deployed it to the shared k3s cluster.

---

## 2. Architecture(s)

The project has two architecture views worth documenting: the high-level system architecture, and the detailed request/response flow for the build-and-deploy pipeline.

### 2.1 High-Level Architecture (Current)

```
Frontend  <——>  Backend  <——>  DB
```

- **Frontend** — user-facing dashboard (Next.js/TypeScript).
- **Backend** — orchestrator/API layer (FastAPI).
- **DB** — state store (MongoDB Atlas).

> *Note: this is the current high-level shape of the system as sketched by the team. Arrows in this diagram represent bidirectional communication between the three components; it does not yet capture the deploy/build pipeline detail — see §2.2 for that.*

### 2.2 Build → Deploy Sequence Flow

This diagram traces one deployment through the system, from the Backend kicking off a build to the k3s cluster confirming deployment.

**Diagram convention:** a **black arrow** is a request being initiated; an **orange arrow** is the reply/response to that request. Arrows are read as request → response pairs between the same two components unless otherwise noted.

**Flow, step by step:**

1. **Backend → Deploy Service:** `Start building (conf)` *(request, black)*
   **Deploy Service → Backend:** `200, Started` *(response, orange)*
   — Backend tells Deploy Service to kick off a build with a given config; Deploy Service immediately acks that it has started.

2. **Deploy Service → K3s Cluster:** `Build this (conf)` *(request, black)* — **`[no reply]`** ⚠️
   — Deploy Service asks the cluster to build the given config, but this call currently gets **no reply/confirmation**. This is a known gap (see Known Issues below): if this step fails silently, Deploy Service has no way to know.

3. **K3s Cluster → Deploy Service:** `Build-done (JobId)` *(request, black)*
   **Deploy Service → K3s Cluster:** `200 OK, start deploy (conf)` *(response, orange, with a `[50ms delay]` noted)*
   — Once the build finishes, the cluster notifies Deploy Service with a JobId; Deploy Service acknowledges and instructs the cluster to proceed with deployment using the given config.

4. **K3s Cluster → Deploy Service:** `deployment done ()` *(black, curved arrow)*
   — Cluster reports that the deployment has finished.

5. **Deploy Service → Backend:** `Deploy Done (conf)` *(request, black)*
   **Backend → Deploy Service:** `200, OK` *(response, orange)*
   — Deploy Service relays the final "done" status back to Backend, which acknowledges receipt.

### ⚠️ Known Issue in This Flow

Step 2 (`Build this (conf)` → K3s Cluster) has **no reply/confirmation**. If the build fails or the message is lost while the image-generation job is still "in flight," Deploy Service has no signal to detect the failure. This is an open design problem the team is actively addressing (see "What Needs to Be Done" below — event bus proposal).

> [!TIP]
> **Proposed Fix (Nafis):** Use `utils.create_from_dict(k3s_client, build_conf)`. It includes built-in mechanisms to monitor whether the applied resource is **Queued**, **Started**, or **Crashed**.

### 2.3 Deployer — Implementation Details (from codebase, `deployer/` folder)

The `deployer/` folder is the concrete Python implementation of the "Deploy Service" and "K3s Cluster" interaction described above. It talks to the k3s cluster via the official Kubernetes Python client, using a local kubeconfig.

**Files:**

| File | Purpose |
|---|---|
| `deploy.py` | Entry point. Reads a `user_config` dict and a CLI arg (`build` or `deploy`) and either submits a build Job or a full app deployment to the cluster. |
| `k3s_conf.py` | Two manifest-builder classes: `JobPipelineBuilder` (build pipeline Jobs) and `PaaSManifestBuilder` (application Deployment/Service/Ingress/etc). |
| `priority-classes.yaml` | Two Kubernetes `PriorityClass` definitions so live apps can preempt build jobs for resources. |
| `builder-config/Dockerfile` | Image for the build-job container — bundles Kaniko (image build/push) and Trivy (vuln/secret scan) binaries on Alpine. |
| `builder-config/scripts/clone-git.sh` | Shallow-clones the target repo into `/workspace`. |
| `builder-config/scripts/run-trivy.sh` | Runs `trivy fs` against `/workspace` for vulnerabilities and secrets, configurable severity/exit-code (currently commented out in `deploy.py`, not yet wired into the active pipeline). |
| `builder-config/scripts/run-kaniko.sh` | Generates a Docker auth config for the Harbor registry from `HARBOR_USER`/`HARBOR_PASS`, then runs the Kaniko executor to build and push the image (`--skip-tls-verify` currently enabled). |
| `builder-config/install-docker.sh` | Docker install helper script. |

**Build pipeline (`JobPipelineBuilder`):** assembles a single Kubernetes `Job` manifest whose container runs a sequence of shell scripts (currently: clone → kaniko build/push; Trivy scan step exists but is disabled). The Job:
- Runs under the low-priority `builder-rank` `PriorityClass` (yields cluster resources to live apps).
- Uses `restartPolicy: Never`, `backoffLimit: 1`, and a 600s TTL after finishing (auto-cleanup).
- Pushes the built image to Harbor at `{DEFAULT_HARBOR_IP}/buet-paas-student-apps/{image}`.

**Deploy pipeline (`PaaSManifestBuilder`):** builds the full set of application manifests from a single config dict — `Deployment`, `Service` (ClusterIP), `Ingress` (Traefik, with optional Let's Encrypt TLS via cert-manager), optional `PersistentVolumeClaim`, optional `HorizontalPodAutoscaler`, and optional `CronJob`s. Notable design points:
- Live-app pods run under the high-priority `deployment-rank` `PriorityClass` so they can evict build jobs if the cluster is under resource pressure.
- Pod/container security context is scaffolded (seccomp `RuntimeDefault`, non-root option, capability drop, read-only rootfs option) but several hardening options are currently commented out/disabled.
- Domain resolution auto-generates `sslip.io` wildcard domains from the app name, namespace, and both the private and floating cluster IPs, with support for a custom domain override.
- Liveness/readiness probes, resource requests/limits, and a graceful pre-stop drain (`sleep 5`) are set by default for every deployment.

**Config surface (`user_config` in `deploy.py`):** currently a hardcoded dict (not yet wired to the Backend/API) covering app name, namespace, container port, replica count, resource requests/limits, and env vars, with many advanced features (persistent storage, autoscaling, cron jobs, SSL, pre-deploy migration hooks) already supported by the manifest builder but left commented out / unused in the current example.

### 2.4 Mapping Files to Architecture — When and How to Modify

This maps each `deployer/` file to the step(s) of the sequence flow (§2.2) it implements, so a teammate knows exactly which file to touch for a given change.

| File | Maps to (sequence step) | When you'd need to modify it | How to modify it |
|---|---|---|---|
| `deploy.py` | Steps 1–5 (Backend ↔ Deploy Service ↔ K3s Cluster, entry point for both `Start building` and the deploy trigger) | You're wiring the Backend's real API calls into the Deploy Service instead of the hardcoded `user_config`; or changing what CLI actions (`build`/`deploy`) exist. | Replace the hardcoded `user_config` dict with parameters received from the Backend (e.g. via function args or an HTTP/queue payload). Keep `build_image()` and `deploy_application()` as the two entry points so the request/response contract with Backend stays stable. |
| `k3s_conf.py` → `JobPipelineBuilder` | Step 2 (`Build this (conf)` → K3s Cluster) and Step 3 (`Build-done (JobId)` back to Deploy Service) | You're changing what happens *during* the build — adding/removing a pipeline stage (e.g. re-enabling Trivy), changing scheduling/priority, or changing how the Job reports completion. | Add a new `.apply_*_step()` method (following the pattern of `apply_git_cloner`/`apply_kaniko_build`) that appends a script path + env vars, then call it in `deploy.py`'s `build_image()`. To fix the "no reply" gap, this is the layer where a completion callback/event publish would be added at the end of the Job's script sequence. |
| `k3s_conf.py` → `PaaSManifestBuilder` | Step 3's second half (`start deploy (conf)`) through Step 4 (`deployment done`) | You're changing what gets deployed for the app itself — networking, scaling, storage, security context, health checks, TLS. | Edit or add a `build_*()` sub-method (mirrors `build_deployment`, `build_service`, `build_ingress`, `build_hpa`, `build_pvc`, `build_cronjobs`) and register it in `build_all()`. Toggle existing commented-out options (e.g. `run_as_non_root`, `enable_ssl`) via the `user_config`/`config` dict rather than hardcoding. |
| `priority-classes.yaml` | Cross-cutting — affects whether Step 2's build Job or a live app's Deployment wins scheduling priority | You're changing the resource-contention policy between running user apps and background builds. | Edit the `value` fields to change relative priority, or add new `PriorityClass`es for additional tiers (e.g. a "critical" tier), then reference the new class name in `k3s_conf.py`'s `pod_spec["priorityClassName"]`. Must be applied to the cluster (`kubectl apply -f priority-classes.yaml`) before it takes effect. |
| `builder-config/Dockerfile` | The container image that runs Step 2's Job | You're adding a new build-pipeline tool (e.g. Gitleaks, OPA-Gatekeeper conftest), upgrading Kaniko/Trivy versions, or changing the base image. | Add a new `COPY --from=<tool>_source` stage for the tool's binary, install any new dependencies via `apk add`, then rebuild and push this image to Harbor so `BUILDER_IMAGE_SOURCE` points at the new tag. |
| `builder-config/scripts/clone-git.sh` | Start of Step 2 (fetching the code before "Build this") | You need different clone behavior — e.g. supporting private repos with auth tokens, submodules, or shallow-clone depth changes. | Edit the `git clone` invocation directly; keep using `GIT_URL`/`GIT_BRANCH` env vars so `JobPipelineBuilder.apply_git_cloner()` doesn't need to change. |
| `builder-config/scripts/run-trivy.sh` | Security scanning sub-step within Step 2 (currently disabled) | You're re-enabling or tuning vulnerability/secret scanning as part of "what needs to be done." | Adjust severity/exit-code behavior here if needed, then re-enable the corresponding `builder.apply_trivy_scan(...)` line in `deploy.py`'s `build_image()` so it's included in the Job's script sequence. |
| `builder-config/scripts/run-kaniko.sh` | The actual "build" in Step 2, whose completion feeds Step 3's `Build-done (JobId)` | You're changing registry auth, target registry, or Kaniko build flags (e.g. removing `--skip-tls-verify` once Harbor TLS is fully trusted). | Edit the Kaniko executor flags or the Docker auth-config generation block; keep reading `IMAGE_DESTINATION`/`HARBOR_USER`/`HARBOR_PASS` from env vars so `JobPipelineBuilder.apply_kaniko_build()` continues to work unchanged. |
| `builder-config/install-docker.sh` | Supporting/setup script, not part of the live request flow | You're changing how Docker gets installed on a node/VM that needs it (e.g. a builder VM). | Standard shell-script edit; run manually on the target VM, not part of the Kubernetes Job flow. |

---

## 3. How to update the build pipeline 
 To update the build pipeling (meaning adding new actions like sonarcube scans) the folders inside `deployer/builder-config` needs to be modified
 - First: The `Dockerfile` must include the new binaries and other necessary tools to complete the task
 - Second: A new `taskname.sh` script must be made ready to execute the task with proper prints. This will help with the debugging or logging, for the users or admins to troubleshoot.
 - Third: After including this .sh script, the new builder image must be build using docker.
 - Four: After the image is ready the image is to push under tag `192.168.64.121/paas-builder/builder-image:latest` and `192.168.64.121/paas-builder/builder-image:vx.x` [x.x is the latest version]

Example Commands:
```bash
docker login
docker build -t my-image-builder:v2.5 .
docker tag my-image-builder:v2.5 192.168.64.121/paas-builder/builder-image:latest 192.168.64.121/paas-builder/builder-image:v2.5
docker push 192.168.64.121/paas-builder/builder-image:latest 192.168.64.121/paas-builder/builder-image:v2.5
```

---

## 4. Current State

*(Placeholder — each teammate should fill in their own component's status below. Keep entries factual and dated where possible.)*

### Frontend
- Status: _TBD — fill in_
- Notes: _TBD_

### Backend / Orchestrator
- Status: _TBD — fill in_
- Notes: _TBD_

### Deploy Service (`deployer/`)
- Status: Prototype exists and is functional as a standalone script — not yet wired to the Backend/API.
- Notes: `deploy.py` currently takes a hardcoded config dict and a CLI arg (`build`/`deploy`); it isn't yet triggered by the Backend or driven by real user input. Trivy scanning step is implemented but disabled in the active build pipeline. Several manifest features (autoscaling, persistent storage, cron jobs, SSL, pre-deploy hooks) are supported by `PaaSManifestBuilder` but unused in the current example config. _(Add anything else here.)_

### K3s Cluster / Kubernetes Layer
- Status: _TBD — fill in_
- Notes: _TBD_

### Image Registry
- Status: _TBD — fill in_
- Notes: Deployer code pushes/pulls images against a Harbor instance (`buet-paas-student-apps` project), authenticating via `HARBOR_USER`/`HARBOR_PASS` env vars. _(Add current Harbor setup status/details here.)_

### Security Scanning (SonarQube / Trivy / Gitleaks / OPA-Gatekeeper)
- Status: _TBD — fill in_
- Notes: _TBD_

### OpenStack Infrastructure
- Status: _TBD — fill in_
- Notes: _TBD_

### Observability (Prometheus/Grafana, ELK/EFK, Wazuh)
- Status: _TBD — fill in_
- Notes: _TBD_

---


## 5. What Is Done

*(Placeholder — list completed work here, one bullet per item, tag with component/owner if helpful.)*

- Deployer prototype: git-clone → Kaniko build → push to Harbor, packaged as a Kubernetes Job container (Alpine + Kaniko + Trivy binaries).
- Deployer prototype: full application manifest generation (Deployment, Service, Ingress w/ Traefik + optional TLS, optional PVC/HPA/CronJobs) via `PaaSManifestBuilder`.
- Priority-based scheduling set up so live app pods (`deployment-rank`) can preempt build jobs (`builder-rank`) under resource pressure.
- Auto-generated `sslip.io` wildcard domains per app/namespace, with custom-domain override support.
- Default resource requests/limits, liveness/readiness probes, and graceful shutdown drain wired into every deployment by default.
-

---


## 6. What Needs to Be Done

*(Placeholder — list remaining/planned work here. A few known items to seed this list with, based on team discussion and the current codebase — edit/expand freely.)*

- [💡] **Proposed Soln** Resolve the "no reply" gap in the build request to K3s Cluster (step 2 above) — likely via an event bus (RabbitMQ / NATS / Kafka / Redis Streams) so each stage publishes a completion event the next stage listens for, instead of a fire-and-forget call.
- [ ] Alternative under consideration: a sequential build-job pipeline (git pull → code scan → image gen → image scan → push to registry) that triggers deploy-service only once all steps succeed.
- [ ] Decide how code/artifacts are shared between the image builder and the code scanner.
- [ ] Wire `deployer/deploy.py` up to the Backend so `user_config` comes from real API/user input instead of a hardcoded dict.
- [ ] Re-enable the Trivy scan step in the build Job pipeline (currently implemented but commented out in `deploy.py`).
- [ ] Decide on and enable the security-hardening options already scaffolded in `PaaSManifestBuilder` (non-root enforcement, container-level security context, read-only rootfs) which are currently present in code but disabled/commented out.
- [ ] Remove `--skip-tls-verify` from the Kaniko push once Harbor's TLS setup is fully trusted end-to-end from the builder Job.
- [ ] Migrate orchestrator, dashboard, and state store fully onto OpenStack.
- [ ] Replace GitHub polling with a webhook relay.
- [ ] Stand up BUET SSO integration.
- [ ] Wire in security scanning tools (SonarQube, Trivy, Gitleaks, OPA-Gatekeeper) into the pipeline.
- [ ] Set up observability stack (Prometheus/Grafana, ELK/EFK, Wazuh).
- [ ] Run pilot validation with real student/team projects.

---

## 6. Team

| Name | Student ID |
|---|---|
| Himel Sutrodhar | 2105073 |
| Suprio Paul | 2105085 |
| Md Nafis Hussain | 2105086 |
| Zahid Al Hasan Brinto | 2105087 |
| Nayeem-Uz-Zaman | 2105090 |
| Nahian Reza Nuhas | 2105101 |

---

*Last updated: [fill in date] — please update this doc as the project evolves rather than letting it go stale.*
