# syntax=docker/dockerfile:1
# imap-mcp-server — Dockerfile (PS-91)
# Multi-stage build: proxy/CA support, private PyPI auth via BuildKit secret, non-root runtime.

# ── Builder ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ARG HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY} \
    http_proxy=${http_proxy} https_proxy=${https_proxy} no_proxy=${no_proxy}

ARG CUSTOM_CA_CERT
RUN if [ -n "${CUSTOM_CA_CERT}" ] && [ -f "${CUSTOM_CA_CERT}" ]; then \
      cp "${CUSTOM_CA_CERT}" /usr/local/share/ca-certificates/custom-ca.crt && \
      update-ca-certificates; \
    fi

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
# Install platform packages from public Gitea PyPI per §3.2.0.
ARG PYPI_URL=https://gitea.cloud-dog.net/api/packages/Cloud-Dog-External/pypi/simple
RUN --mount=type=secret,id=pip_conf,target=/etc/pip.conf \
    pip install --no-cache-dir \
      --trusted-host gitea.cloud-dog.net \
      --trusted-host files.pythonhosted.org \
      cloud-dog-config cloud-dog-logging "cloud-dog-api-kit==0.13.0" "cloud-dog-idam>=0.5.2,<0.6" cloud-dog-db "cloud-dog-jobs>=0.3.0" && \
    pip install --no-cache-dir \
      --trusted-host gitea.cloud-dog.net \
      --trusted-host files.pythonhosted.org \
      "."

# ── Final ────────────────────────────────────────────────────────
FROM python:3.12-slim
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.vendor="Cloud-Dog, Viewdeck Engineering Limited"

ARG HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY} \
    http_proxy=${http_proxy} https_proxy=${https_proxy} no_proxy=${no_proxy}

ARG CUSTOM_CA_CERT
RUN if [ -n "${CUSTOM_CA_CERT}" ] && [ -f "${CUSTOM_CA_CERT}" ]; then \
      cp "${CUSTOM_CA_CERT}" /usr/local/share/ca-certificates/custom-ca.crt && \
      update-ca-certificates; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl netcat-openbsd procps net-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ ./src/
COPY database/ ./database/
COPY ui/dist/ ./ui/dist/
COPY pyproject.toml ./
COPY defaults.yaml config.yaml server_control.sh docker-entrypoint.sh healthcheck.sh ./

RUN mkdir -p /app/logs /app/data/audit /app/data/downloads /app/data/archive /app/.pids /app/certs && \
    chmod +x /app/docker-entrypoint.sh /app/healthcheck.sh /app/server_control.sh

RUN useradd --system --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src

EXPOSE 8787 8788

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=5 \
  CMD /app/healthcheck.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["all"]
