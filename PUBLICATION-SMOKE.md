---
template-id: T-PRE
template-version: 1.0
applies-to: PUBLICATION-SMOKE.md
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

# Publication smoke test

External local-Docker smoke. Starts the published image with the checked-in
example env file and probes the local API, Web, MCP, and A2A surfaces.
The health smoke verifies local configuration and transport startup only.

```bash
set -euo pipefail
TAG="${TAG:-latest}"
NAME="${NAME:-imap-mcp-server-publication-smoke}"
SMOKE_ATTEMPTS="${SMOKE_ATTEMPTS:-120}"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" --network host \
  -e CLOUD_DOG_ENV_FILE=/app/env \
  -v "$PWD/docker-env.public.example:/app/env:ro" \
  "cloud-dog/imap-mcp-server:$TAG"

probe_url() {
  local url="$1" code attempt
  for attempt in $(seq 1 "$SMOKE_ATTEMPTS"); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' -m 5 "$url" || true)"
    case "$code" in
      2*|3*|401|403|405) echo "PASS $url -> $code"; return 0 ;;
    esac
    sleep 1
  done
  echo "FAIL $url -> ${code:-000}" >&2
  docker logs "$NAME" >&2 || true
  return 1
}

probe_url http://127.0.0.1:8787/health
probe_url http://127.0.0.1:8071/
probe_url http://127.0.0.1:8788/health
probe_url http://127.0.0.1:8789/health
probe_url http://127.0.0.1:8789/.well-known/agent.json

echo "RESULT: PASS"
```

Expected result: all probes pass. HTTP redirects or auth-gated 401/403 responses
are acceptable because they prove that the published surface is running and
routing.
