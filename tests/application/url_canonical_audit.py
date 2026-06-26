"""PS-WEBUI-URL-CANONICAL v1.0 audit for the imap-mcp-server WebUI (W28E-1803C).

Hits the WebUI front door with redirects DISABLED and asserts:
  * every canonical WebUI route -> 200
  * every legacy alias          -> 308 + Location == canonical (named offender
    `/ui/login` -> `/login`)
  * one unknown WebUI path       -> 404 (WURL-007)

Emits a 12-column TSV. Base URL from env IMAP_WEBUI_BASE_URL
(default http://127.0.0.1:28980). Output path from env URL_AUDIT_OUT.
Environment label from env URL_AUDIT_ENV (local-docker | preprod).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

SERVICE = "imap-mcp-server"
ENVIRONMENT = os.environ.get("URL_AUDIT_ENV", "local-docker").strip()
BASE_URL = os.environ.get("IMAP_WEBUI_BASE_URL", "http://127.0.0.1:28980").rstrip("/")
PLAYWRIGHT_SPEC = "tests/application/AT_WEBUI_Login/test_webui_login.py"
EVIDENCE_PATH = "working/evidence/W28E-1803C/current/screenshots/"
OUT = Path(os.environ.get("URL_AUDIT_OUT", "url-canonical-audit.tsv"))

CANONICAL_ROUTES = [
    "/",
    "/login",
    "/profiles",
    "/mailbox-workspace",
    "/search-retrieve",
    "/audit-log",
    "/admin/users",
    "/admin/groups",
    "/admin/api-keys",
    "/admin/roles",
    "/admin/rbac",
    "/developer/api-docs",
    "/developer/mcp-console",
    "/developer/a2a-console",
    "/system/jobs",
    "/system/settings",
    "/system/gmail-settings",
    "/system/about",
]

LEGACY_ALIASES = {
    "/ui": "/",
    "/ui/": "/",
    "/ui/login": "/login",
    "/ui/admin/users": "/admin/users",
    "/dashboard": "/",
    "/diagnostics-audit": "/audit-log",
    "/legacy-diagnostics": "/audit-log",
    "/idam/users": "/admin/users",
    "/idam/groups": "/admin/groups",
    "/idam/api-keys": "/admin/api-keys",
    "/idam/roles": "/admin/roles",
    "/idam/rbac": "/admin/rbac",
    "/admin-control": "/admin/users",
    "/api-docs": "/developer/api-docs",
    "/mcp-console": "/developer/mcp-console",
    "/a2a-console": "/developer/a2a-console",
    "/jobs": "/system/jobs",
    "/settings": "/system/settings",
    "/gmail-settings": "/system/gmail-settings",
    "/about": "/system/about",
    "/mutation-gating": "/",
}

UNKNOWN_PATH = "/no-such-webui-page"


def _location_path(location: str | None) -> str:
    """Normalise a Location header to a path (drop scheme/host)."""
    if not location:
        return ""
    if location.startswith("/"):
        return location
    parts = urlsplit(location)
    return parts.path or location


def main() -> int:
    rows: list[list[str]] = []
    failures = 0
    with httpx.Client(follow_redirects=False, timeout=20.0, verify=False) as client:
        # Canonical routes -> 200
        for route in CANONICAL_ROUTES:
            url = f"{BASE_URL}{route}"
            try:
                resp = client.get(url)
                actual = resp.status_code
            except Exception as exc:  # noqa: BLE001 - record transport failures
                actual = -1
                _ = exc
            verdict = "PASS" if actual == 200 else "FAIL"
            if verdict != "PASS":
                failures += 1
            rows.append(
                [SERVICE, ENVIRONMENT, "anon", url, "200", str(actual), "", "", route, PLAYWRIGHT_SPEC, EVIDENCE_PATH, verdict]
            )

        # Legacy aliases -> 308 + Location == canonical
        for alias, canonical in sorted(LEGACY_ALIASES.items()):
            url = f"{BASE_URL}{alias}"
            try:
                resp = client.get(url)
                actual = resp.status_code
                actual_loc = _location_path(resp.headers.get("location"))
            except Exception as exc:  # noqa: BLE001
                actual = -1
                actual_loc = ""
                _ = exc
            verdict = "PASS" if (actual == 308 and actual_loc == canonical) else "FAIL"
            if verdict != "PASS":
                failures += 1
            rows.append(
                [SERVICE, ENVIRONMENT, "anon", url, "308", str(actual), canonical, actual_loc, canonical, PLAYWRIGHT_SPEC, EVIDENCE_PATH, verdict]
            )

        # Unknown WebUI path -> 404 (WURL-007)
        url = f"{BASE_URL}{UNKNOWN_PATH}"
        try:
            resp = client.get(url)
            actual = resp.status_code
        except Exception as exc:  # noqa: BLE001
            actual = -1
            _ = exc
        verdict = "PASS" if actual == 404 else "FAIL"
        if verdict != "PASS":
            failures += 1
        rows.append(
            [SERVICE, ENVIRONMENT, "anon", url, "404", str(actual), "", "", UNKNOWN_PATH, PLAYWRIGHT_SPEC, EVIDENCE_PATH, verdict]
        )

    header = [
        "service", "environment", "actor_role", "request_url", "expected_status",
        "actual_status", "expected_location", "actual_location", "canonical_route",
        "playwright_spec", "evidence_path", "verdict",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(header) + "\n")
        for row in rows:
            handle.write("\t".join(row) + "\n")

    total = len(rows)
    passed = total - failures
    print(f"URL canonical audit ({ENVIRONMENT}) {BASE_URL}: {passed}/{total} PASS, {failures} FAIL -> {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
