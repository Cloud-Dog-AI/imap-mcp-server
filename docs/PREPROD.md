---
template-id: T-PRE
template-version: 1.0
applies-to: docs/PREPROD.md
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

# PREPROD Deployment — IMAP MCP Server

## Overview

- Public URL: `https://imapmcpserver0.cloud-dog.net`
- Container hostname: `imapmcpserver0.example.invalid`
- Image: `registry.example.invalid/cloud-dog/imap-mcp-server:latest`
- Terraform container definition: `/path/to/example-deploy-repo/terraform/docker-host.example.invalid/27 MLAgents/imapmcpserver_containers.tf.json`
- Terraform image reference: `/path/to/example-deploy-repo/terraform/docker-host.example.invalid/27 MLAgents/docker_images.tf.json`
- Operator overlay: `private/env-PREPROD`

Health was verified during W28A-962 with:

```bash
curl -fsS https://imapmcpserver0.cloud-dog.net/health | python3 -m json.tool
```

## Runtime Shape

| Surface | External URL |
|---|---|
| Web and REST | `https://imapmcpserver0.cloud-dog.net` |
| REST base | `https://imapmcpserver0.cloud-dog.net/api/v1` |
| MCP HTTP | `https://imapmcpserver0.cloud-dog.net/mcp` |
| A2A HTTP | `https://imapmcpserver0.cloud-dog.net/a2a` |

## Secrets and Config

Preprod runtime values come from:

- Terraform container env in `docker-host.example.invalid/27 MLAgents`
- shared Vault blob under `cloud_dog_ai/config`
- local operator overlay `private/env-PREPROD` for pytest and smoke commands against preprod

Relevant Vault branches:

- `dev.services.imapmcpserver0`
- `dev.email.imap_operations_cloud_dog_net`
- `dev.idp.google`
- `dev.idp.keycloak.clients.notification_agent_test`

## Build and Deploy

1. Load Vault-backed operator credentials.

```bash
set -a
source /path/to/cloud-dog-ai/env-public
set +a
```

2. Build and tag the image.

```bash
cd /path/to/cloud-dog-ai/imap-mcp-server
bash docker-build.sh latest
```

3. Push the image.

```bash
docker push registry.example.invalid/cloud-dog/imap-mcp-server:latest
```

4. Apply the Terraform target.

```bash
cd '/path/to/example-deploy-repo/terraform/docker-host.example.invalid/27 MLAgents'
terraform apply -auto-approve \
  -target=docker_image.imapmcpserver \
  -target=docker_container.imapmcpserver0
```

5. Verify public health.

```bash
curl -fsS https://imapmcpserver0.cloud-dog.net/health | python3 -m json.tool
```

## Preprod Test Usage

Run remote checks against preprod with the committed tier env plus the operator overlay:

```bash
python3 -m pytest tests/system --env tests/env-ST --env private/env-PREPROD -v
python3 -m pytest tests/integration --env tests/env-IT --env private/env-PREPROD -v
```

## Troubleshooting

- Re-read health: `curl -fsS https://imapmcpserver0.cloud-dog.net/health`
- Inspect Terraform target: `terraform state show docker_container.imapmcpserver0`
- Inspect host-mounted logs on the target host under `/opt/docker/imapmcpserver0/logs`
