#!/usr/bin/env bash
set -euo pipefail

prom_path='/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/query?query='
query() {
  expression="$1"
  encoded="$(jq -nr --arg expr "$expression" '$expr | @uri')"
  kubectl get --raw "${prom_path}${encoded}"
}

echo 'RULE_SELECTOR'
kubectl get prometheus monitoring-stack-kube-prom-prometheus -n monitoring -o json | jq '{ruleSelector:.spec.ruleSelector,ruleNamespaceSelector:.spec.ruleNamespaceSelector}'
echo 'EXISTING_RELEVANT_RULES'
kubectl get prometheusrule -A -o json | jq '[.items[] as $item | $item.spec.groups[].rules[] | select(.alert == "KubeNodeNotReady" or .alert == "KubePodCrashLooping" or .alert == "KubeDeploymentReplicasMismatch" or .alert == "KubeJobFailed" or .alert == "NodeFilesystemAlmostOutOfSpace" or .alert == "TargetDown") | {name:.alert,expr:.expr,for:.for,namespace:$item.metadata.namespace}]'
echo 'VM_TARGETS'
query 'up{job="standalone-node-exporters"}' | jq '[.data.result[] | {target:.metric.target,service:.metric.service,instance:.metric.instance,value:.value[1]}]'
echo 'PROBE_TARGETS'
query 'probe_success{deployment_type="blackbox"}' | jq '[.data.result[] | {target:.metric.target,service:.metric.service,value:.value[1]}]'
echo 'VM_ROOT_DISK'
query '100 * node_filesystem_avail_bytes{job="standalone-node-exporters",mountpoint="/",fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{job="standalone-node-exporters",mountpoint="/",fstype!~"tmpfs|overlay"}' | jq '[.data.result[] | {instance:.metric.instance,service:.metric.service,value:.value[1]}]'
echo 'ROOT_READONLY'
query 'node_filesystem_readonly{job="standalone-node-exporters",mountpoint="/"}' | jq '[.data.result[] | {instance:.metric.instance,value:.value[1]}]'
echo 'FIRING_ALERTS'
kubectl get --raw '/api/v1/namespaces/monitoring/services/http:monitoring-stack-kube-prom-prometheus:9090/proxy/api/v1/alerts' | jq '[.data.alerts[] | select(.state == "firing") | {name:.labels.alertname,severity:.labels.severity,namespace:.labels.namespace,pod:.labels.pod}]'
echo 'RESTART_TOP5'
query 'topk(5, sum by (namespace,pod) (increase(kube_pod_container_status_restarts_total[1h])))' | jq '[.data.result[] | {namespace:.metric.namespace,pod:.metric.pod,value:.value[1]}]'
