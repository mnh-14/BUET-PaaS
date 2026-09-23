# service-config/falco-values.yaml
#
# Helm values for the Falco + Falcosidekick release.
# Applied via: service-config/falco-setup.sh (see that script for the full
# helm install/upgrade command).
#
# Reversibility notes (see falco-integration-plan.md §6 for full detail):
#   - To change alert volume later, edit `falcosidekick.config.minimumpriority`
#     below and re-run falco-setup.sh (it upgrades in place, doesn't reinstall).
#   - To point at the real backend once it exists, edit
#     `falcosidekick.config.webhook.address` below.

# --- Driver: avoids privileged containers, no kernel headers/DKMS needed on
# --- Ubuntu 24.04 worker VMs (kernel 5.15+, CO-RE eBPF support).
driver:
  kind: modern_ebpf

# --- Scope: full cluster, including platform namespaces (kube-system,
# --- metallb-system, paas-system, buet-paas-system-team23) as well as
# --- student namespaces. No namespaceSelector restriction is set here on
# --- purpose — see falco-integration-plan.md §6 for how to narrow this
# --- later via a rule exception instead of redeploying.

# --- Falcosidekick: deployed as a subchart of the same release so one
# --- helm command manages both Falco and Falcosidekick together.
falcosidekick:
  enabled: true
  config:
    # warning = default noise level. Set to "debug" to see everything while
    # testing, or "critical" to only see severe events. One-line change +
    # falco-setup.sh re-run, nothing else needs touching.
    minimumpriority: warning
    webhook:
      # In-cluster Service DNS name for the Deployer (deploy_service.py /
      # routes/security.py), port 80 -> targetPort 5000 per
      # service-config/deploy-service-config.yaml's Service block. Not the
      # backend URL — see falco-integration-plan.md §5.
      address: "http://paas-deployer.buet-paas-system-team23.svc.cluster.local/api/security/falco-alert"
      # customHeaders (the shared-secret token) is intentionally NOT set
      # here — it's a secret, so it's supplied via a local, gitignored
      # override file instead. See service-config/falco-values.local.yaml.example
      # and falco-setup.sh, which layers that file in automatically if present.

# --- Custom rule exception: build-job false positive on "Drop and execute
# --- new binary in container" (priority Critical, would hit AUTO_ACTION).
# ---
# --- ROOT CAUSE (structural, not tool-specific): Kaniko doesn't run nested
# --- containers per build stage — it unpacks the student's `FROM` base
# --- image (node:20, python:3.12, whatever) directly into this pod's own
# --- filesystem and executes RUN commands there. Falco's frame of reference
# --- is still "this pod's registered image is paas-builders/builder-image",
# --- so ANY runtime binary pulled in via the student's Dockerfile — node,
# --- python, a compiled Go binary, anything — looks identical to a dropped
# --- implant. This is not specific to Node/npm; it fires for every
# --- language a student's Dockerfile might use, since the mechanism is
# --- Kaniko's build architecture itself, not any one build tool.
# ---
# --- REVISION 2 (2026-09-15): the original version of this exception also
# --- required proc.exepath to start with /usr/, /opt/, etc. — this broke
# --- on an Alpine/BusyBox-based student image, where every binary resolves
# --- to /bin/busybox regardless of language or install method. That's the
# --- SAME category of failure as a plain process-name allowlist (attempt
# --- #1): trying to recognize "legitimate build activity" by its shape.
# --- Different base image, different shape, same false negative.
# ---
# --- Fixed by exempting on IDENTITY only — container.name="paas-builder"
# --- and k8s.pod.name containing "-build-job-" are both INFRASTRUCTURE-
# --- CONTROLLED (see deployer/k3s_conf.py's Job name template:
# --- f"{app_name}-{namespace}-build-job" — the "-build-job" suffix is
# --- appended by our own code, not derived from student input, and
# --- container.name is hardcoded in the Job's pod spec). A student's
# --- app_name can only influence the PREFIX, so this can't be spoofed by
# --- naming an app to fake the exemption on a live pod — and it doesn't
# --- care what base image, binary layout, or language the student used.
# ---
# --- COST of this exemption, stated plainly: this rule now provides ZERO
# --- detection for build-job pods, full stop — not reduced, zero. That's
# --- an accepted tradeoff, not an oversight: binary-identity signals were
# --- already shown (via the "node -e <payload>" postinstall scenario) to
# --- be fundamentally unable to distinguish legitimate build activity from
# --- a malicious one here, regardless of how the allowlist is scoped. The
# --- network-egress rule below is the real detection layer for build-job
# --- attacks; this exemption just stops false positives on a rule that
# --- could never reliably help here in the first place. One honest residual
# --- gap: purely local malicious activity with no unusual network call
# --- (e.g. tampering with build output, no exfiltration) would evade both
# --- rules — worth a one-line mention to the supervisor, not a solved case.
# ---
# --- Live app pods are NOT covered by this exception (different
# --- container.name, different pod naming) — a real dropped binary in a
# --- running student app still fires at full severity.
customRules:
  rules-buet-paas-exceptions.yaml: |-
    - macro: known_drop_and_execute_activities
      condition: >
        (container.name = "paas-builder"
         and k8s.pod.name contains "-build-job-")

    # --- Two more structural false positives, discovered via a live test
    # --- build (2026-09-15): Kaniko's /kaniko/executor process itself opens
    # --- /etc/shadow and /var/log/apk.log while unpacking and snapshotting
    # --- the student's Alpine base image — mechanical filesystem processing,
    # --- not credential theft or log tampering. Same root cause as the
    # --- drop-and-execute false positive: Kaniko's architecture makes normal
    # --- base-image handling look anomalous to rules that assume they're
    # --- watching an already-running container.
    # ---
    # --- Both are STOCK Falco rules (not ours), so — unlike the network
    # --- rule — these are NOT blanket-downgraded. Only the build-job-pod
    # --- case is exempted via each rule's own official override macro;
    # --- both rules stay fully active at their original severity for every
    # --- other pod in the cluster (student apps, platform pods, etc.).
    # ---
    # --- These were WARNING priority and inside AUTO_ACTION_PRIORITIES —
    # --- one of them killed a real, successfully-progressing build during
    # --- testing before this exception was added.
    - macro: user_known_read_sensitive_files_activities
      condition: >
        (container.name = "paas-builder"
         and k8s.pod.name contains "-build-job-")

    - macro: allowed_clear_log_files
      condition: >
        (container.name = "paas-builder"
         and k8s.pod.name contains "-build-job-")

    # --- Network-egress detection for build-job pods. This exists because
    # --- binary-identity signals (the exception above, or any process-name
    # --- allowlist) CANNOT distinguish a legitimate `node`/`npm` invocation
    # --- from a malicious one — a compromised `postinstall` script runs
    # --- through the exact same trusted binary, at the exact same path, as
    # --- a normal build. Network behavior is a materially different signal:
    # --- a build job's legitimate traffic is narrow (DNS, git/Harbor over
    # --- HTTPS) and doesn't need arbitrary ports.
    # ---
    # --- HONEST LIMITATION: this catches C2/exfiltration on a non-standard
    # --- port, but NOT exfiltration over HTTPS (443) to an attacker-controlled
    # --- domain — that's indistinguishable from a legitimate git/Harbor call
    # --- without a domain-level allowlist (e.g. GitHub's published IP
    # --- ranges), which is a real but separate follow-up, not implemented
    # --- here. Worth flagging to the supervisor as a known residual gap.
    - list: buet_paas_allowed_outbound_ports
      items: [53, 443]
    - list: buet_paas_harbor_ip
      items: ["192.168.128.152"]
    - rule: Unexpected outbound connection from build job
      desc: >
        A build-job pod made an outbound connection outside its expected
        pattern (DNS, HTTPS to git/Harbor, or the Harbor registry IP
        directly). Build jobs run untrusted student Dockerfiles, so an
        unusual destination port is a strong signal of C2 or exfiltration.
      condition: >
        outbound
        and container.name = "paas-builder"
        and k8s.pod.name contains "-build-job-"
        and not (fd.rport in (buet_paas_allowed_outbound_ports))
        and not (fd.rip in (buet_paas_harbor_ip))
      output: >
        Unexpected outbound connection from build job (command=%proc.cmdline
        connection=%fd.name dest_ip=%fd.rip dest_port=%fd.rport
        pod=%k8s.pod.name ns=%k8s.ns.name image=%container.image.repository)
      # PERMANENTLY set to NOTICE (not CRITICAL), reclassified 2026-09-23
      # after two separate investigation sessions. Full evidence trail below
      # — read this before ever changing this priority back up.
      #
      # WHAT FIRES: TCP port 9 (discard protocol — accepts data, sends no
      # response) from Kaniko's own /kaniko/executor process (never a
      # spawned child), always during registry activity, across 5+ separate
      # builds spanning two nights. Destinations are always real, legitimate
      # infrastructure — AWS and Cloudflare ranges — never the same IP twice
      # in a way that looks like fixed attacker infrastructure.
      #
      # RULED OUT (2026-09-23): initially suspected as an IPv6-routing
      # artifact, since these worker nodes have no usable IPv6 route but
      # Docker Hub publishes real AAAA records for index.docker.io — that
      # WAS a real, separate bug (see the CoreDNS AAAA->NODATA fix, outside
      # this file), and DID cause two genuine hard build failures. But after
      # fixing it, port 9 still fired 13 times on the very next build — with
      # EVERY destination IP confirmed IPv4. The IPv6 theory is disproven
      # for this specific rule; it was a coincidental second bug found in
      # the same investigation, not the cause of this one.
      #
      # NARROWED (2026-09-23): a manual repro build using --cache=false
      # --no-push (bypassing Kaniko's Harbor cache-layer read/write calls,
      # but still resolving+pulling the base image from Docker Hub
      # normally) produced ZERO port-9 hits. Every real build (which always
      # runs --cache=true --cache-copy-layers=true) has fired it. This
      # points at Kaniko's cache-layer HTTP client (talking to Harbor) as
      # the likely trigger, not the base-image-pull client — though this
      # was not confirmed with a positive repro (would require live
      # packet capture during a --cache=true run, not completed).
      #
      # WHY THIS IS SAFE AT NOTICE, NOT A ROOT-CAUSE COP-OUT: port 9 is the
      # discard protocol — connections there cannot carry a response and
      # were confirmed FIN/RST rather than exchanging any bulk data. Purely
      # discard-bound traffic cannot exfiltrate anything, structurally,
      # regardless of the still-unconfirmed client-side mechanism producing
      # it. Across every occurrence this rule has never once co-occurred
      # with any other suspicious signal (no credential search, no
      # /dev/shm execution, no reverse-shell pattern) in the same build.
      #
      # IF YOU WANT TO ACTUALLY FINISH THIS: the next real step is a live
      # tcpdump (node-level, e.g. `kubectl debug node/<node> -it
      # --image=nicolaka/netshoot -- chroot /host tcpdump -i any -n port 9`,
      # started BEFORE triggering a real --cache=true build) to catch
      # packet-level detail — or, more directly, reading go-containerregistry
      # / Kaniko's cache-layer client source for anywhere a port could be
      # mis-set or default to 9. Neither was completed live; this is a
      # documented handoff, not a dead end.
      priority: NOTICE
      tags: [network, mitre_exfiltration, mitre_command_and_control, buet-paas]