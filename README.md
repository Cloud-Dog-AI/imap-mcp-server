---
template-id: T-RME
template-version: 1.0
applies-to: README.md
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

# IMAP MCP Server

`imap-mcp-server` exposes mail-profile health, API, Web UI, MCP, and A2A-compatible endpoints for local publication smoke tests.

## Publication Quick Start

Prerequisites:

- Docker 24 or newer with BuildKit enabled
- Python 3.12 if you run the package locally
- Public package index: `https://pypi.org/simple`

Build the public image:

```bash
./docker-build.sh latest --variant public
```

Run the local smoke by executing the shell block in [PUBLICATION-SMOKE.md](PUBLICATION-SMOKE.md) with `TAG=latest`.

The smoke run uses [docker-env.public.example](docker-env.public.example) and probes:

- API: `8787`
- Web: `8071`
- MCP: `8788`
- A2A: `8789`

## Local Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]" --index-url https://pypi.org/simple
```

Runtime configuration is loaded from the env file passed to `server_control.sh`, then from shell environment variables, then from `defaults.yaml`.

## Documentation

- [BUILD.md](BUILD.md)
- [EXTERNAL-BUILD.md](EXTERNAL-BUILD.md)
- [PUBLICATION-SMOKE.md](PUBLICATION-SMOKE.md)
- [docker-env.public.example](docker-env.public.example)

## Licence

Apache-2.0 - Copyright (c) 2026 Cloud-Dog, Viewdeck Engineering Limited

## Security & Publication Notes

Authentication and authorisation use the platform IDAM credential/cert model; do not commit secrets.
This public source mirror excludes internal operations material; build artefacts (e.g. the UI bundle) are regenerated at build time.
