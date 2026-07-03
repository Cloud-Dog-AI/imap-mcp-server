---
template-id: T-DOK
template-version: 1.0
applies-to: docs/DOCKER.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: public-standards

project: imap-mcp-server
doc-last-updated: 2026-06-18
doc-git-commit: 7683f39
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# Docker Guide

## Standard Build Path

```bash
cd /path/to/cloud-dog-ai/imap-mcp-server
set -a
source /path/to/cloud-dog-ai/env-public
set +a
bash docker-build.sh latest
```

Resulting tags:

- `cloud-dog/imap-mcp-server:latest`
- `<internal-registry>:443/cloud-dog/imap-mcp-server:latest`

## Push

```bash
docker push <internal-registry>:443/cloud-dog/imap-mcp-server:latest
```

## Local Runtime Notes

- The service expects Vault-backed configuration and private package access.
- For local functional runs, prefer `./server_control.sh --env tests/env-AT start all` over ad hoc `docker run`.
- Preprod deployment is Terraform-managed.

## Files

- Dockerfile: `Dockerfile`
- Build script: `docker-build.sh`
- Entrypoint: `docker-entrypoint.sh`
- Health probe: `healthcheck.sh`
