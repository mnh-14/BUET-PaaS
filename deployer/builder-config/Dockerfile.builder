FROM gcr.io/kaniko-project/executor:v1.20.0 AS kaniko_source
FROM aquasec/trivy:latest AS trivy_source

FROM alpine:3.19

# Install base utilities
RUN apk add --no-cache git bash curl ca-certificates jq

# Copy Kaniko & Trivy binaries
COPY --from=kaniko_source /kaniko /kaniko
COPY --from=trivy_source /usr/local/bin/trivy /usr/local/bin/trivy

ENV PATH=$PATH:/kaniko
ENV SSL_CERT_DIR=/kaniko/ssl/certs
ENV KANIKO_DIR=/kaniko

# 1. Increases timeout to 20 minutes
# 2. Uses GitHub Container Registry mirror (ghcr.io)
RUN trivy image --download-db-only --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --timeout 15m

# COPY ALL MODULAR SCRIPTS INTO /usr/local/bin/
COPY scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh

# NO ENTRYPOINT! Commands are driven explicitly by Kubernetes Job YAML.
