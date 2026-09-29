#!/usr/bin/env bash
set -euo pipefail

# Creates the Step 12C1 VPN-only internal PKI and authentication Secrets.
# This script intentionally never prints private keys, passwords, or Secret
# values. It fails rather than replacing any existing target Secret.

namespace=monitoring
ca_secret=monitoring-internal-ca
tls_secret=monitoring-public-tls
prometheus_secret=monitoring-prometheus-basic-auth
alertmanager_secret=monitoring-alertmanager-basic-auth

prometheus_user=prometheus-team
alertmanager_user=alertmanager-admin

hosts=(
  grafana.monitoring.192.168.64.121.sslip.io
  prometheus.monitoring.192.168.64.121.sslip.io
  alerts.monitoring.192.168.64.121.sslip.io
)

for command_name in kubectl openssl mktemp; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "Required command is missing: ${command_name}" >&2
    exit 1
  }
done

kubectl get namespace "${namespace}" >/dev/null

for secret_name in \
  "${ca_secret}" \
  "${tls_secret}" \
  "${prometheus_secret}" \
  "${alertmanager_secret}"; do
  if kubectl -n "${namespace}" get secret "${secret_name}" >/dev/null 2>&1; then
    echo "Refusing to replace existing Secret: ${namespace}/${secret_name}" >&2
    exit 1
  fi
done

umask 077
work_dir="$(mktemp -d)"
prometheus_password=''
alertmanager_password=''

cleanup() {
  prometheus_password=''
  alertmanager_password=''
  rm -rf -- "${work_dir}"
}
trap cleanup EXIT

openssl genrsa -out "${work_dir}/ca.key" 4096 >/dev/null 2>&1
openssl req -x509 -new -sha256 \
  -key "${work_dir}/ca.key" \
  -days 1825 \
  -subj '/CN=BUET-PaaS Monitoring Internal CA/O=BUET-PaaS' \
  -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -addext 'subjectKeyIdentifier=hash' \
  -out "${work_dir}/ca.crt" >/dev/null 2>&1

openssl genrsa -out "${work_dir}/tls.key" 3072 >/dev/null 2>&1
openssl req -new -sha256 \
  -key "${work_dir}/tls.key" \
  -subj '/CN=grafana.monitoring.192.168.64.121.sslip.io/O=BUET-PaaS' \
  -out "${work_dir}/tls.csr" >/dev/null 2>&1

cat >"${work_dir}/leaf.ext" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:${hosts[0]},DNS:${hosts[1]},DNS:${hosts[2]}
authorityKeyIdentifier=keyid,issuer
subjectKeyIdentifier=hash
EOF

openssl x509 -req -sha256 \
  -in "${work_dir}/tls.csr" \
  -CA "${work_dir}/ca.crt" \
  -CAkey "${work_dir}/ca.key" \
  -CAcreateserial \
  -days 365 \
  -extfile "${work_dir}/leaf.ext" \
  -out "${work_dir}/tls.crt" >/dev/null 2>&1

openssl verify -CAfile "${work_dir}/ca.crt" "${work_dir}/tls.crt" >/dev/null

prometheus_password="$(openssl rand -base64 36 | tr -d '\r\n')"
alertmanager_password="$(openssl rand -base64 36 | tr -d '\r\n')"

kubectl -n "${namespace}" create secret generic "${ca_secret}" \
  --type=Opaque \
  --from-file=ca.crt="${work_dir}/ca.crt" \
  --from-file=ca.key="${work_dir}/ca.key"

kubectl -n "${namespace}" create secret tls "${tls_secret}" \
  --cert="${work_dir}/tls.crt" \
  --key="${work_dir}/tls.key"

kubectl -n "${namespace}" create secret generic "${prometheus_secret}" \
  --type=kubernetes.io/basic-auth \
  --from-literal=username="${prometheus_user}" \
  --from-literal=password="${prometheus_password}"

kubectl -n "${namespace}" create secret generic "${alertmanager_secret}" \
  --type=kubernetes.io/basic-auth \
  --from-literal=username="${alertmanager_user}" \
  --from-literal=password="${alertmanager_password}"

kubectl -n "${namespace}" label secret \
  "${ca_secret}" \
  "${tls_secret}" \
  "${prometheus_secret}" \
  "${alertmanager_secret}" \
  app.kubernetes.io/part-of=buet-paas-monitoring \
  app.kubernetes.io/managed-by=step-12c1

echo 'Certificate verification: OK'
openssl x509 -in "${work_dir}/tls.crt" -noout \
  -subject -issuer -dates -fingerprint -sha256 -ext subjectAltName

echo 'Secret structure (values hidden):'
kubectl -n "${namespace}" describe secret \
  "${ca_secret}" \
  "${tls_secret}" \
  "${prometheus_secret}" \
  "${alertmanager_secret}"

echo 'Step 12C1 Secret creation completed without printing credentials or keys.'
