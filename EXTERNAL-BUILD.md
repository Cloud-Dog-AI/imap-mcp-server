---
template-id: T-EXT
template-version: 1.0
applies-to: EXTERNAL-BUILD.md
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

# External Build Guide — imap-mcp-server

This guide lets an external builder build, run, and smoke-test `imap-mcp-server`
from the published source only, with no access to any private network, registry,
or secret store. Every command below resolves packages from a public package
index (default: `https://pypi.org/simple`).

> SAFETY: This guide never connects to a live IMAP server. The smoke test starts
> the service with placeholder configuration and probes only its local HTTP
> surfaces (API / Web / MCP / A2A). Do not point the operations profile at a real
> mailbox during smoke testing.

## 1. Prerequisites

| Platform | Requirements |
|----------|--------------|
| Linux    | Docker 24+ with BuildKit, or Python 3.12 + `pip` |
| macOS    | Docker Desktop 4.x (BuildKit on by default), or Python 3.12 + `pip` |
| Windows  | Docker Desktop with WSL2 backend, or Python 3.12 + `pip` (PowerShell paths) |

All platform packages (`cloud-dog-config`, `cloud-dog-logging`,
`cloud-dog-api-kit`, `cloud-dog-idam`, `cloud-dog-db`, `cloud-dog-jobs`,
`cloud-dog-storage`) must be resolvable from the chosen public index. If a
platform package is not yet published to the public index, the build will fail
at the `pip install` step — report that gap; do **not** add `--extra-index-url`
or a private index to work around it (forbidden by PS-97 §3.3 / §4).

## 2. Get the source

Clone from the public boundary repository (no private remotes):

```bash
git clone https://github.com/cloud-dog-ai/imap-mcp-server.git
cd imap-mcp-server
git remote -v   # MUST show only the public remote
```

## 3. Docker build path (recommended)

The build defaults to the public variant (`Dockerfile.public`) and the public
package index.

### Linux / macOS

```bash
# Default public build (index-url = https://pypi.org/simple)
./docker-build.sh latest --variant public

# Optional: pin a different public index
PYPI_URL="https://pypi.org/simple" ./docker-build.sh latest --variant public
```

### Windows (PowerShell)

```powershell
# Use Git Bash / WSL to run the build script, or invoke buildx directly:
docker buildx build --load -f Dockerfile.public -t cloud-dog/imap-mcp-server:latest .
```

The image is tagged `cloud-dog/imap-mcp-server:latest`. No internal registry tag
is applied for the public variant.

## 4. Run the publication smoke

Follow the shell block in [PUBLICATION-SMOKE.md](PUBLICATION-SMOKE.md). It starts
the image with [docker-env.public.example](docker-env.public.example) and probes
the local surfaces:

| Surface | Port |
|---------|------|
| API     | 8787 |
| Web     | 8071 |
| MCP     | 8788 |
| A2A     | 8789 |

A `2xx`, `3xx`, `401`, `403`, or `405` response on each surface is a PASS — it
proves the surface is up and routing without requiring a real mailbox.

## 5. Pure-source path (no Docker)

```bash
python3 -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# Resolve from a single public index only (no extra/find-links):
python -m pip install --index-url https://pypi.org/simple ".[dev]"

# Compile-check the package:
python -m compileall src

# Local surface run (placeholder config — no live mailbox):
cp docker-env.public.example .env
./server_control.sh --env .env start all
./server_control.sh --env .env status all
./server_control.sh --env .env stop all
```

## 6. Reproducible dependency set

A locked dependency manifest is provided in
[`requirements.lock`](requirements.lock). To reproduce the exact resolved set:

```bash
python -m pip install --index-url https://pypi.org/simple --no-deps -r requirements.lock
```

The lock is generated from `pyproject.toml`; see the header of
`requirements.lock` for the generation command and a hash-consistency check.

## 7. Returning evidence

Place all build/smoke output under `evidence/` at the repo root and return a
single tarball with a checksum:

```bash
mkdir -p evidence
./docker-build.sh latest --variant public 2>&1 | tee evidence/docker-build.log
# ...run PUBLICATION-SMOKE.md, capturing stdout to evidence/smoke.log...
tar -czf imap-mcp-external-build-evidence.tgz evidence/
sha256sum imap-mcp-external-build-evidence.tgz > imap-mcp-external-build-evidence.tgz.sha256
```

Return both `imap-mcp-external-build-evidence.tgz` and its `.sha256` file.
