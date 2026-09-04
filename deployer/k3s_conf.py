import os
import yaml
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv


DEFAULT_BUILDER_NAMESPACE = "buet-paas-system-team23"
DEPLOY_PRIORITY = "deployment-rank"
BUILD_PRIORITY = "builder-rank"
load_dotenv()
BUILDER_IMAGE = os.getenv("BUILDER_IMAGE_SOURCE", "192.168.67.192:80/paas-system/paas-builder:v1.2")
TTL_AFTER_FINISHED = 600  # seconds
DEFAULT_PRIVATE_IP = os.getenv("DEFAULT_PRIVATE_IP", "192.168.68.121")
DEFAULT_HARBOR_IP = os.getenv("DEFAULT_HARBOR_IP", "192.168.68.121")
DEFAULT_FLOATING_IP = os.getenv("DEFAULT_FLOATING_IP", "192.168.68.121")
HARBOR_USER = os.getenv("HARBOR_USER", "admin")
HARBOR_PASS = os.getenv("HARBOR_PASS", "")
DEPLOYMENT_ENVIRONMENT: bool = os.getenv("DEPLOYMENT_ENVIRONMENT", "production").lower() == "production"

class PaaSManifestBuilder:
    """
    Modular, Enterprise-Grade Kubernetes Manifest Builder for PaaS Platforms.
    Orchestrates Deployments, Services, Ingresses, Autoscalers, Volumes, and CronJobs.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._validate_config()
        
        # Core Parameters
        self.app_name = config["app_name"].lower().strip()
        self.image = config["image"].strip()
        self.namespace = config.get("namespace", "default").lower().strip()
        self.worker_ip = config.get("worker_ip", "").strip()
        self.container_port = int(config.get("container_port", 80))
        self.domain = config.get("domain_override", "").strip()
        self.domains = [f"{self.app_name}.{self.namespace}.{DEFAULT_PRIVATE_IP}.sslip.io", f"{self.app_name}.{self.namespace}.{DEFAULT_FLOATING_IP}.sslip.io"]  
        
        # Automatic Wildcard DNS Resolution
        if config.get("domain_override"):
            self.domains.append(config["domain_override"].strip())
        # elif self.worker_ip:
        #     self.domain = f"{self.app_name}.{self.worker_ip}.sslip.io"
        # else:
        #     raise ValueError("Must provide either 'worker_ip' or 'domain_override'!")

    def _validate_config(self):
        """Validates mandatory input parameters."""
        if not self.config.get("app_name"):
            raise ValueError("CRITICAL: 'app_name' is mandatory!")
        if not self.config.get("image"):
            raise ValueError("CRITICAL: 'image' is mandatory!")

    # ------------------------------------------------------------------
    # SUB-BUILDER 1: PERSISTENT VOLUME CLAIM (STORAGE ADD-ON)
    # ------------------------------------------------------------------
    def build_pvc(self) -> Optional[Dict[str, Any]]:
        """Generates PersistentVolumeClaim if user requested persistent storage."""
        storage_cfg = self.config.get("persistent_storage")
        if not storage_cfg:
            return None

        return {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": f"{self.app_name}-pvc",
                "namespace": self.namespace
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "storageClassName": "local-path", # K3s default storage provider
                "resources": {
                    "requests": {
                        "storage": storage_cfg.get("size", "10Gi")
                    }
                }
            }
        }

    # ------------------------------------------------------------------
    # SUB-BUILDER 2: DEPLOYMENT (PODS + MIGRATIONS + LIFECYCLE)
    # ------------------------------------------------------------------
    def build_deployment(self) -> Dict[str, Any]:
        """Generates Deployment with initContainers, probes, and grace periods."""
        replicas = int(self.config.get("replicas", 2))
        env_vars = self.config.get("env_vars", {})
        formatted_env = [{"name": k, "value": str(v)} for k, v in env_vars.items()]


        # 1. POD-LEVEL SECURITY CONTEXT (Applies to all containers in the Pod)
        pod_security_context = {
            # Enforces Linux Kernel default seccomp syscall filtering (Blocks dangerous system calls)
            "seccompProfile": {
                "type": "RuntimeDefault"
            }
        }
        # Optional: Force container to run as unprivileged user if app supports it
        if self.config.get("run_as_non_root", False):
            pod_security_context["runAsNonRoot"] = True
            pod_security_context["runAsUser"] = 10001
            pod_security_context["runAsGroup"] = 10001


        # 2. CONTAINER-LEVEL SECURITY CONTEXT (Applies to the specific application process)
        container_security_context = {
            # HARD BLOCK: Prevents 'sudo', setuid, or privilege escalation attacks
            "allowPrivilegeEscalation": False,
            # LEAST PRIVILEGE: Drops ALL Linux Kernel Admin Capabilities (CAP_SYS_ADMIN, CAP_NET_ADMIN, etc.)
            "capabilities": {
                "drop": ["ALL"]
            },
            # Optional: Lock root filesystem to read-only
            "readOnlyRootFilesystem": self.config.get("read_only_rootfs", False)
        }


        # Base Pod Template Specification
        pod_spec: Dict[str, Any] = {
            "priorityClassName": DEPLOY_PRIORITY,
            "terminationGracePeriodSeconds": int(self.config.get("grace_period_seconds", 30)),
            "securityContext": pod_security_context, # <------- INJECTED POD LEVEL SECURITY CONTEX
            "containers": [{
                "name": self.app_name,
                "image": DEFAULT_HARBOR_IP+"/buet-paas-student-apps/"+self.image,
                "imagePullPolicy": "Always",
                # "securityContext": container_security_context, # <-------------- INJECTED CONTAINER LEVEL SECURITY CONTEXT
                "ports": [{"name": "http", "containerPort": self.container_port}],
                "env": formatted_env,
                "resources": {
                    "requests": {
                        "cpu": self.config.get("cpu_request", "100m"),
                        "memory": self.config.get("memory_request", "128Mi")
                    },
                    "limits": {
                        "cpu": self.config.get("cpu_limit", "250m"),
                        "memory": self.config.get("memory_limit", "256Mi")
                    }
                },
                "livenessProbe": {
                    "httpGet": {"path": self.config.get("health_path", "/"), "port": self.container_port},
                    "initialDelaySeconds": 15, "periodSeconds": 10
                },
                "readinessProbe": {
                    "httpGet": {"path": self.config.get("health_path", "/"), "port": self.container_port},
                    "initialDelaySeconds": 5, "periodSeconds": 5
                },
                "lifecycle": {
                    "preStop": {
                        "exec": {"command": ["/bin/sh", "-c", "sleep 5"]} # Zero-downtime drain
                    }
                }
            }]
        }

        # MODULE A: Database Pre-Deploy Migration Command (initContainers)
        if self.config.get("pre_deploy_cmd"):
            pod_spec["initContainers"] = [{
                "name": f"{self.app_name}-db-migrate",
                "image": self.image,
                "command": ["/bin/sh", "-c", self.config["pre_deploy_cmd"]],
                "env": formatted_env
            }]

        # MODULE B: Attach Persistent Storage Volume if enabled
        if self.config.get("persistent_storage"):
            mount_path = self.config["persistent_storage"].get("mount_path", "/app/data")
            pod_spec["containers"][0]["volumeMounts"] = [{
                "name": "persistent-data",
                "mountPath": mount_path
            }]
            pod_spec["volumes"] = [{
                "name": "persistent-data",
                "persistentVolumeClaim": {"claimName": f"{self.app_name}-pvc"}
            }]

        # MODULE C: Hardware Node Placement (High-Memory vs Standard nodes)
        if self.config.get("instance_tier"):
            pod_spec["nodeSelector"] = {"instance-tier": self.config["instance_tier"]}

        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": f"{self.app_name}-deployment",
                "namespace": self.namespace,
                "labels": {"app": self.app_name, "managed-by": "paas-backend"}
            },
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": self.app_name}},
                "template": {
                    "metadata": {"labels": {"app": self.app_name}},
                    "spec": pod_spec
                }
            }
        }

    # ------------------------------------------------------------------
    # SUB-BUILDER 3: SERVICE (INTERNAL LOAD BALANCER)
    # ------------------------------------------------------------------
    def build_service(self) -> Dict[str, Any]:
        """Generates ClusterIP Service."""
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"{self.app_name}-service",
                "namespace": self.namespace,
                "labels": {"app": self.app_name}
            },
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": self.app_name},
                "ports": [{
                    "name": "http",
                    "protocol": "TCP",
                    "port": 80,
                    "targetPort": self.container_port
                }]
            }
        }

    # ------------------------------------------------------------------
    # SUB-BUILDER 4: INGRESS (ROUTING & FREE SSL)
    # ------------------------------------------------------------------
    def build_ingress(self) -> Dict[str, Any]:
        """Generates Ingress with Traefik routing and Cert-Manager SSL support."""
        annotations = {
            "kubernetes.io/ingress.class": "traefik"
        }
        
        # Enable Automatic Free SSL via Let's Encrypt if requested
        tls_spec = []
        if self.config.get("enable_ssl", False):
            annotations["cert-manager.io/cluster-issuer"] = "letsencrypt-prod"
            tls_spec = [{
                "hosts": self.domains,
                "secretName": f"{self.app_name}-tls-cert"
            }]

        rules = []
        for domain in self.domains:
            rules.append({
                "host": domain,
                "http": {
                    "paths": [{
                        "path": "/",
                        "pathType": "Prefix",
                        "backend": {
                            "service": {
                                "name": f"{self.app_name}-service",
                                "port": {"number": 80}
                            }
                        }
                    }]
                }
            })

        ingress_manifest = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": f"{self.app_name}-ingress",
                "namespace": self.namespace,
                "annotations": annotations
            },
            "spec": {
                "rules": rules
            }
        }

        if tls_spec:
            ingress_manifest["spec"]["tls"] = tls_spec

        return ingress_manifest

    # ------------------------------------------------------------------
    # SUB-BUILDER 5: HORIZONTAL POD AUTOSCALER (AUTOSCALING TIER)
    # ------------------------------------------------------------------
    def build_hpa(self) -> Optional[Dict[str, Any]]:
        """Generates HPA for auto-scaling pods based on CPU utilization."""
        hpa_cfg = self.config.get("autoscaling")
        if not hpa_cfg or not hpa_cfg.get("enabled", False):
            return None

        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": f"{self.app_name}-hpa",
                "namespace": self.namespace
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": f"{self.app_name}-deployment"
                },
                "minReplicas": int(hpa_cfg.get("min_replicas", 2)),
                "maxReplicas": int(hpa_cfg.get("max_replicas", 10)),
                "metrics": [{
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": int(hpa_cfg.get("target_cpu_percent", 80))
                        }
                    }
                }]
            }
        }

    # ------------------------------------------------------------------
    # SUB-BUILDER 6: CRON JOBS (SCHEDULED BACKGROUND TASKS)
    # ------------------------------------------------------------------
    def build_cronjobs(self) -> List[Dict[str, Any]]:
        """Generates list of scheduled CronJob tasks."""
        cron_list = self.config.get("cron_jobs", [])
        manifests = []
        
        formatted_env = [{"name": k, "value": str(v)} for k, v in self.config.get("env_vars", {}).items()]

        for idx, cron in enumerate(cron_list):
            manifests.append({
                "apiVersion": "batch/v1",
                "kind": "CronJob",
                "metadata": {
                    "name": f"{self.app_name}-cron-{cron.get('name', idx)}",
                    "namespace": self.namespace
                },
                "spec": {
                    "schedule": cron["schedule"], # e.g. "0 2 * * *"
                    "jobTemplate": {
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [{
                                        "name": f"cron-{idx}",
                                        "image": self.image,
                                        "command": ["/bin/sh", "-c", cron["command"]],
                                        "env": formatted_env
                                    }],
                                    "restartPolicy": "OnFailure"
                                }
                            }
                        }
                    }
                }
            })
        return manifests

    # ------------------------------------------------------------------
    # MASTER ORCHESTRATOR: ASSEMBLES ALL MANIFESTS EFFICIENTLY
    # ------------------------------------------------------------------
    def build_all(self) -> Dict[str, Any]:
        """Assembles all active sub-builders into a clean dictionary payload."""
        payload: Dict[str, Any] = {}

        # 1. PVC (Must be created before Deployment mounts it)
        pvc = self.build_pvc()
        if pvc:
            payload["pvc"] = pvc

        # 2. Deployment, Service, Ingress (Core Stack)
        payload["deployment"] = self.build_deployment()
        payload["service"] = self.build_service()
        payload["ingress"] = self.build_ingress()

        # 3. HPA (Autoscaler)
        hpa = self.build_hpa()
        if hpa:
            payload["hpa"] = hpa

        # 4. CronJobs (Background Tasks)
        #cronjobs = self.build_cronjobs()
        #if cronjobs:
        #    payload["cronjobs"] = cronjobs

        return payload

    def build_all_listed(self) -> Dict[str, Any]:
        k3s_list_object = {
            "apiVersion": "v1",
            "kind": "List",
            "items": list(self.build_all().values())
        }
        return k3s_list_object




class JobPipelineBuilder:
    def __init__(self, app_name: str, builder_image: str = BUILDER_IMAGE, namespace: str = DEFAULT_BUILDER_NAMESPACE):
        if not app_name:
            raise ValueError("CRITICAL: 'app_name' is mandatory!")

        self.app_name = app_name.lower().strip()
        self.namespace = namespace.lower().strip()
        self.builder_image = builder_image

        self._script_list: List[str] = []
        self._env_vars: Dict[str, str] = {}

        self.priority_class_name = BUILD_PRIORITY
        self.ttl_after_finished = TTL_AFTER_FINISHED

    def apply_git_cloner(self, git_url: str, branch: str = "main") -> "JobPipelineBuilder":
        self._script_list.append("/usr/local/bin/clone-git.sh")
        self._env_vars["GIT_URL"] = git_url
        self._env_vars["GIT_BRANCH"] = branch
        return self

    def apply_trivy_scan(self, severity: str = "CRITICAL,HIGH", fail_on_cve: bool = True) -> "JobPipelineBuilder":
        self._script_list.append("/usr/local/bin/run-trivy.sh")
        self._env_vars["EXIT_CODE"] = "1" if fail_on_cve else "0"
        return self

    def apply_kaniko_build(self, image_destination: str, dockerfile_path: str = "Dockerfile", insecure: bool = False) -> "JobPipelineBuilder":
        self._script_list.append("/usr/local/bin/run-kaniko.sh")
        self._env_vars["IMAGE_DESTINATION"] = DEFAULT_HARBOR_IP+"/buet-paas-student-apps/"+image_destination
        # self._env_vars["IMAGE_DESTINATION"] = f"{DEFAULT_PRIVATE_IP}/buet-paas-student-apps/{self.app_name}-{self.namespace}:{image_tag}"
        self._env_vars["DOCKERFILE_PATH"] = dockerfile_path

        # READS FROM THE .env FILE THAT WAS LOADED BY load_dotenv()!
        if DEPLOYMENT_ENVIRONMENT:
            self._env_vars["HARBOR_USER"] = HARBOR_USER
            self._env_vars["HARBOR_PASS"] = HARBOR_PASS

        # if insecure:
        #     self._env_vars["EXTRA_FLAGS"] = "--insecure"
        self._env_vars["EXTRA_FLAGS"] = "--skip-tls-verify"

        return self

    def build(self) -> Dict[str, Any]:
        if not self._script_list:
            raise ValueError("CRITICAL: You must apply at least one task step before calling build()!")

        multiline_script_block = "\n".join(self._script_list)

        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": f"{self.app_name}-{self.namespace}-build-job",
                "namespace": self.namespace,
                "labels": {
                    "app": self.app_name,
                    "paas-stage": "build-job",
                    "managed-by": "paas-backend"
                }
            },
            "spec": {
                "ttlSecondsAfterFinished": self.ttl_after_finished,
                "backoffLimit": 1,
                "template": {
                    "spec": {
                        "priorityClassName": self.priority_class_name,
                        "restartPolicy": "Never",
                        "containers": [{
                            "name": "paas-builder",
                            "image": self.builder_image,
                            "command": ["/bin/bash", "-e", "-c"],
                            "args": [multiline_script_block],
                            "envFrom": [{"secretRef": {"name": "paas-deployer-env"}}],
                            "env": [{"name": k, "value": str(v)} for k, v in self._env_vars.items()],
                            "resources": {
                                "requests": {
                                    "cpu": "250m",
                                    "memory": "512Mi"
                                },
                                "limits": {
                                    "cpu": "1000m",
                                    "memory": "1.5Gi"
                                }
                            }
                        }]
                    }
                }
            }
        }
