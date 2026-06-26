---
template-id: T-BLD
template-version: 1.0
applies-to: docs/BUILD.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

project: imap-mcp-server
doc-last-updated: 2026-06-18
doc-git-commit: 7683f39
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# Build Guide — imap-mcp-server

## Prerequisites

- Linux shell with `bash`
- Python `3.10+`
- Docker with BuildKit and `docker buildx`
- Access to Cloud-Dog Vault via `/opt/iac/Development/cloud-dog-ai/env-vault`
- Access to private PyPI at `https://<internal-pypi>/simple/`

## Source Build

```bash
cd /opt/iac/Development/cloud-dog-ai/imap-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

If private package credentials are required in the current shell:

```bash
set -a
source /opt/iac/Development/cloud-dog-ai/env-vault
set +a
```

## Local Runtime

Preferred local control path:

```bash
set -a
source /opt/iac/Development/cloud-dog-ai/env-vault
set +a
./server_control.sh --env tests/env-AT start all
```

Standard local listener set:

- API: `127.0.0.1:28983`
- WebUI: `127.0.0.1:28980`
- MCP: `127.0.0.1:28981`
- A2A: `127.0.0.1:28982`

Status and shutdown:

```bash
./server_control.sh --env tests/env-AT status all
./server_control.sh --env tests/env-AT stop all
```

## Test Execution

```bash
set -a
source /opt/iac/Development/cloud-dog-ai/env-vault
set +a
python3 -m pytest tests/quality --env tests/env-QT -v
python3 -m pytest tests/unit --env tests/env-UT -v
python3 -m pytest tests/integration --env tests/env-IT -v
TEST_RUNTIME_MODE=local-server python3 -m pytest tests/application --env tests/env-AT -v --timeout=600
```

## Docker Build

Use the repo build script rather than ad hoc `docker build`:

```bash
set -a
source /opt/iac/Development/cloud-dog-ai/env-vault
set +a
bash docker-build.sh latest
```

The build script:

- resolves private PyPI credentials
- uses BuildKit secret mounts
- tags `cloud-dog/imap-mcp-server:latest`
- tags `<internal-registry>:443/cloud-dog/imap-mcp-server:latest`

## Registry Push

```bash
docker push <internal-registry>:443/cloud-dog/imap-mcp-server:latest
```

## Standalone Playwright

```bash
cd /opt/iac/Development/cloud-dog-ai/cloud-dog-ai-ui-monorepo
set -a
source ../env-vault
set +a
npx playwright test --config apps/imap-mcp/playwright.config.ts --project=chromium --workers=1
```
