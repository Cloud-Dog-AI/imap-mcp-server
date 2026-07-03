---
template-id: T-BLR
template-version: 1.0
applies-to: BUILD.md
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
doc-age-policy: indefinite
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# Build Instructions

## Project
`imap-mcp-server` - IMAP mailbox access service with API, Web, MCP, and A2A servers.

## Prerequisites
- Python 3.11+
- Docker with BuildKit support
- pip

## Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

Resolve packages from a single public package index (no fallback index):
```bash
PYPI_URL=https://pypi.org/simple
pip install -e ".[dev]" --index-url "$PYPI_URL"
```

## Local Configuration
```bash
cat > .env.local <<'ENV'
CLOUD_DOG__API_SERVER__PORT=8070
CLOUD_DOG__WEB_SERVER__PORT=8071
CLOUD_DOG__MCP_SERVER__PORT=8072
CLOUD_DOG__A2A_SERVER__PORT=8073
IMAP_HOST=mail.example.com
IMAP_PORT=993
IMAP_USERNAME=user@example.com
ENV
```

## Run Locally
```bash
./server_control.sh --env ./.env.local start all
./server_control.sh --env ./.env.local status all
./server_control.sh --env ./.env.local stop all
```

## Run Tests
```bash
python -m pytest tests/quality --env ./.env.test -v
python -m pytest tests/unit --env ./.env.test -v
python -m pytest tests/system --env ./.env.test -v
python -m pytest tests/integration --env ./.env.test -v
python -m pytest tests/application --env ./.env.test -v
```

## Build
### Python Package
```bash
python -m pip install build
python -m build
```

### Docker Container
```bash
# Public build (default variant + public index)
./docker-build.sh latest --variant public
```

Build with a custom single package index and CA bundle:
```bash
PYPI_URL=https://pypi.org/simple \
PYPI_USERNAME=build-user \
PYPI_PASSWORD=build-password \
CUSTOM_CA_CERT=./certs/ca.pem \
PUBLICATION_TAG_SUFFIX=public-test ./docker-build.sh latest --variant public
```

## Docker Push
```bash
docker tag cloud-dog/imap-mcp-server:latest registry.example.com/team/imap-mcp-server:latest
docker push registry.example.com/team/imap-mcp-server:latest
```

## Configuration
Runtime configuration is resolved from shell variables, the env file supplied to `server_control.sh`, and `defaults.yaml`.

## Local Secrets
Put local-only values in the env file passed to `server_control.sh` or mounted into Docker. Do not commit real credentials.
