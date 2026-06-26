# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""IT1.23 — JSON-RPC tools/call envelope test (T-TST-MCP canonical pattern).

Template-id: T-TST-MCP
Template-version: 1.0
Extends-via: PS-REQ-TEST-TRACE v1.0 §6 + AGENT-LESSONS.md §1.1 (MCP protocol)

Covers: FR-01 (MCP surface exposed via JSON-RPC 2.0 tools/call envelope)
Covers: FR-05 (mail tools accessible via MCP)

This test issues a real JSON-RPC 2.0 ``tools/call`` envelope against the
imap-mcp MCP endpoint, following the canonical T-TST-MCP-EXAMPLE.py template.
The in-process FastAPI TestClient is used so no live IMAP server is required;
the profile_list tool is safe to call without IMAP credentials (returns an empty
list from the local in-memory store).
"""

from __future__ import annotations

import json

import pytest

from tests.helpers.live_runtime import mcp_client


# ---------------------------------------------------------------------------
# Helpers — canonical MCP JSON-RPC pattern (T-TST-MCP-EXAMPLE §helpers)
# ---------------------------------------------------------------------------

_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _mcp_post(client, token: str | None, payload: dict) -> object:
    """POST a JSON-RPC envelope to /mcp with required MCP headers."""
    headers = dict(_MCP_HEADERS)
    if token:
        headers["x-api-key"] = token
    return client.post("/mcp", json=payload, headers=headers)


def _parse_jsonrpc(response) -> dict:
    """Parse a JSON-RPC 2.0 response body.

    The MCP server may respond with a plain JSON object or with an SSE
    ``data:`` line.  Both shapes are handled here per the template pattern.
    """
    text = response.text
    # SSE shape: "data: {...}"
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    # Plain JSON shape (in-process TestClient)
    try:
        return response.json()
    except Exception as exc:
        raise AssertionError(f"Could not parse MCP response body: {text[:500]}") from exc


def _mcp_initialize(client, token: str) -> None:
    """Perform the required JSON-RPC initialize handshake (AGENT-LESSONS.md §1.9)."""
    resp = _mcp_post(client, token, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}},
    })
    assert resp.status_code == 200, f"initialize failed: {resp.status_code} {resp.text}"


# ---------------------------------------------------------------------------
# IT1.23-A: tools/call happy path — profile_list via JSON-RPC envelope
# ---------------------------------------------------------------------------

@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-01")
def test_it123_mcp_jsonrpc_tools_call_profile_list() -> None:
    """IT1.23-A: admin invokes profile_list via a real JSON-RPC tools/call envelope.

    REQ: FR-01 — imap-mcp exposes MCP surface via JSON-RPC 2.0 tools/call.

    Sends:
        {"jsonrpc":"2.0","method":"tools/call","params":{"name":"profile_list",
         "arguments":{"include_disabled":false}},"id":2}

    Asserts:
        - HTTP 200
        - Response body is a valid JSON-RPC 2.0 result (``"result"`` key present,
          no ``"error"`` key)
        - result.content is a non-empty list with at least one element of type
          ``"text"`` (the canonical MCP content envelope)
    """
    client = mcp_client(env_files=["tests/env-IT"])
    seed_api_key = str(getattr(client.app.state, "seed_api_key", "") or "")

    try:
        _mcp_initialize(client, seed_api_key)

        resp = _mcp_post(client, seed_api_key, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "profile_list",
                "arguments": {"include_disabled": False},
            },
        })

        assert resp.status_code == 200, f"tools/call returned {resp.status_code}: {resp.text}"
        msg = _parse_jsonrpc(resp)

        # Must be a valid JSON-RPC 2.0 result — no error key.
        assert "error" not in msg, f"Unexpected JSON-RPC error: {msg.get('error')}"
        assert "result" in msg, f"Missing 'result' in JSON-RPC response: {msg}"

        result = msg["result"]
        content = result.get("content")
        assert isinstance(content, list), f"result.content must be a list, got: {content!r}"
        assert len(content) > 0, "result.content must be non-empty"
        first = content[0]
        assert isinstance(first, dict), f"result.content[0] must be a dict, got: {first!r}"
        assert first.get("type") == "text", (
            f"result.content[0].type must be 'text', got: {first.get('type')!r}"
        )
        # The text payload must be valid JSON (tool result serialised as JSON string).
        text_payload = first.get("text", "")
        try:
            json.loads(text_payload)
        except ValueError as exc:
            raise AssertionError(
                f"result.content[0].text is not valid JSON: {text_payload[:200]}"
            ) from exc
    finally:
        client.close()


# ---------------------------------------------------------------------------
# IT1.23-B: anon tools/call is rejected (negative test)
# ---------------------------------------------------------------------------

@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.negative
@pytest.mark.req("FR-04")
def test_it123_mcp_jsonrpc_tools_call_anon_denied() -> None:
    """IT1.23-B: anon JSON-RPC tools/call is rejected (401 or JSON-RPC error).

    REQ: FR-04 — authentication required; anon denied across all surfaces.

    An unauthenticated caller posting a tools/call envelope MUST receive either
    HTTP 401 or a JSON-RPC error envelope with a non-success code.  This mirrors
    the CS-011 anon-denial contract (D-IMAP-IDENTITY-COLLAPSE-1 fix).
    """
    client = mcp_client(env_files=["tests/env-IT"])

    try:
        resp = _mcp_post(client, None, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "profile_list",
                "arguments": {"include_disabled": False},
            },
        })

        if resp.status_code == 200:
            # Some MCP transport layers return 200 with a JSON-RPC error envelope.
            msg = _parse_jsonrpc(resp)
            assert "error" in msg, (
                "Expected JSON-RPC error envelope for anon tools/call, got successful result"
            )
        else:
            assert resp.status_code == 401, (
                f"Expected 401 for anon tools/call, got {resp.status_code}: {resp.text}"
            )
    finally:
        client.close()
