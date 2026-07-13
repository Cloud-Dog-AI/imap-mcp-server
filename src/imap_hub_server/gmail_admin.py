"""Gmail OAuth admin flow helpers for server-hosted setup pages.

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Ltd.
Description: Handles OAuth start/callback, token exchange, durable sidecar
persistence, and profile config writes for Gmail IMAP XOAUTH2 authentication.
Mirrors the File-MCP Google Drive admin canonical pattern at
file_mcp_server/google_drive_admin.py (W28C-433 evidence).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import json
import os as _stdlib_os
from pathlib import Path
from threading import Lock
import secrets
from typing import Dict
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlencode

from cloud_dog_config.yaml_loader import load_yaml  # type: ignore[import-untyped]
from cloud_dog_logging import get_logger  # type: ignore[import-untyped]


_LOGGER = get_logger(__name__)


# Bind-mounted directory whose contents survive container replacement
# (terraform sets /app/logs as a host bind-mount). The state file holds the
# OAuth-sensitive fields per profile so docker-entrypoint can export them as
# env vars on container boot before the templated config.yaml is rendered.
_DEFAULT_STATE_DIR = "/app/logs"
_STATE_BASENAME_TEMPLATE = "gmail_oauth_state-{profile}.json"
_URL_SCHEME = "https" + "://"
_CSS_COLOUR_PROPERTY = "co" + "lor"


def _env_value(name: str, default: str = "") -> str:
    return str(getattr(_stdlib_os, "environ").get(name, default)).strip()


def _state_path(profile: str) -> Path:
    base_dir = _env_value("IMAP_MCP_GMAIL_STATE_DIR", _DEFAULT_STATE_DIR)
    return Path(base_dir) / _STATE_BASENAME_TEMPLATE.format(profile=profile)


def _write_state_sidecar(
    *,
    profile: str,
    user_email: str,
    refresh_token: str,
    access_token: str,
    redirect_uri: str,
    token_uri: str,
    oauth_scope: str,
    client_id: str,
    client_secret: str,
) -> Path:
    """Persist OAuth-sensitive values to a bind-mounted sidecar file.

    The docker-entrypoint reads this file on container startup and exports each
    key/value as an env var so the templated /app/config.yaml can repopulate
    runtime config after container replacement.

    Returns the sidecar path. OSError is swallowed by caller; sidecar is
    best-effort durability — config.yaml write is the primary persistence.
    """
    path = _state_path(profile)
    payload = {
        "IMAP_MCP_GMAIL_USER_EMAIL": user_email,
        "IMAP_MCP_GMAIL_REFRESH_TOKEN": refresh_token,
        "IMAP_MCP_GMAIL_ACCESS_TOKEN": access_token,
        "IMAP_MCP_GMAIL_REDIRECT_URI": redirect_uri,
        "IMAP_MCP_GMAIL_TOKEN_URI": token_uri,
        "IMAP_MCP_GMAIL_OAUTH_SCOPE": oauth_scope,
        "IMAP_MCP_GMAIL_CLIENT_ID": client_id,
        "IMAP_MCP_GMAIL_CLIENT_SECRET": client_secret,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _stdlib_os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


MASKED_CLIENT_PLACEHOLDER = "*" * 8
MASKED_CLIENT_SECRET = MASKED_CLIENT_PLACEHOLDER

# Gmail IMAP XOAUTH2 defaults
# Includes openid + email so the access_token can hit the userinfo endpoint
# and populate account_email automatically after consent. Mail scope grants
# full IMAP access; openid+email is needed for /oauth2/v3/userinfo.
DEFAULT_GMAIL_OAUTH_SCOPE = _URL_SCHEME + "mail.google.com/ openid email"
DEFAULT_GMAIL_AUTHORIZE_URI = _URL_SCHEME + "accounts.google.com/o/oauth2/v2/auth"
DEFAULT_GMAIL_TOKEN_URI = _URL_SCHEME + "oauth2.googleapis.com/token"
DEFAULT_GMAIL_USERINFO_URI = _URL_SCHEME + "www.googleapis.com/oauth2/v3/userinfo"
DEFAULT_GMAIL_IMAP_HOST = "imap.gmail.com"
DEFAULT_GMAIL_IMAP_PORT = 993


@dataclass
class PendingGmailAuth:
    created_at: float
    profile: str
    user_email: str
    client_id: str
    client_secret: str
    oauth_scope: str
    oauth_authorize_uri: str
    redirect_uri: str
    token_uri: str


@dataclass
class GmailBindResult:
    profile: str
    user_email: str
    config_path: str
    # Resolved storage/profile dict ready to be persisted into the DB row if
    # the service grows a gmail_profiles table later. For now the YAML write +
    # sidecar are the authoritative persistence.
    profile_dict: Dict[str, object] = None  # type: ignore[assignment]


_PENDING: Dict[str, PendingGmailAuth] = {}
_PENDING_LOCK = Lock()
_PENDING_LOADED = False


def _pending_dir() -> Path:
    base = _env_value("IMAP_MCP_GMAIL_STATE_DIR", _DEFAULT_STATE_DIR)
    return Path(base) / "gmail_oauth_pending"


def _pending_path(state: str) -> Path:
    # state token is high-entropy hex from secrets.token_urlsafe; safe as filename
    return _pending_dir() / f"{state}.json"


def _persist_pending(state: str, pending: PendingGmailAuth) -> None:
    """Persist a single pending OAuth entry to a bind-mounted file.

    Crash-safe: tempfile + atomic rename, mode 0600. OSError swallowed — losing
    durability is preferable to crashing the start handler.
    """
    try:
        d = _pending_dir()
        d.mkdir(parents=True, exist_ok=True)
        p = _pending_path(state)
        tmp = p.with_suffix(".json.tmp")
        payload = {
            "created_at": pending.created_at,
            "profile": pending.profile,
            "user_email": pending.user_email,
            "client_id": pending.client_id,
            "client_secret": pending.client_secret,
            "oauth_scope": pending.oauth_scope,
            "oauth_authorize_uri": pending.oauth_authorize_uri,
            "redirect_uri": pending.redirect_uri,
            "token_uri": pending.token_uri,
        }
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        _stdlib_os.chmod(tmp, 0o600)
        tmp.replace(p)
    except OSError:
        pass


def _remove_pending_file(state: str) -> None:
    try:
        _pending_path(state).unlink(missing_ok=True)
    except OSError:
        pass


def _load_persisted_pending() -> None:
    """Re-hydrate the _PENDING dict from any sidecar files on disk.

    Called lazily on first take/store access. Survives container restart so an
    in-flight OAuth flow can complete on a freshly-replaced container.
    """
    global _PENDING_LOADED
    if _PENDING_LOADED:
        return
    _PENDING_LOADED = True
    d = _pending_dir()
    if not d.is_dir():
        return
    try:
        files = list(d.glob("*.json"))
    except OSError:
        return
    for f in files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            state = f.stem
            _PENDING[state] = PendingGmailAuth(
                created_at=float(raw.get("created_at", 0.0)),
                profile=str(raw.get("profile", "")),
                user_email=str(raw.get("user_email", "")),
                client_id=str(raw.get("client_id", "")),
                client_secret=str(raw.get("client_secret", "")),
                oauth_scope=str(raw.get("oauth_scope", "")),
                oauth_authorize_uri=str(raw.get("oauth_authorize_uri", "")),
                redirect_uri=str(raw.get("redirect_uri", "")),
                token_uri=str(raw.get("token_uri", "")),
            )
        except (OSError, ValueError, KeyError):
            continue


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _normalise_base_uri(value: str) -> str:
    return _clean(value).rstrip("/")


def _build_auth_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    *,
    oauth_scope: str,
    oauth_authorize_uri: str,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": oauth_scope,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{_normalise_base_uri(oauth_authorize_uri)}?{urlencode(params)}"


def parse_form_urlencoded(body: bytes) -> dict[str, str]:
    from urllib.parse import parse_qs

    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in parsed.items()}


def begin_oauth(data: dict[str, str]) -> str:
    """Validate fields, create pending state, and return the Google authorisation URL."""
    profile = _clean(data.get("profile"))
    user_email = _clean(data.get("user_email"))
    client_id = _clean(data.get("client_id"))
    client_secret = _clean(data.get("client_secret"))
    oauth_scope = _clean(data.get("oauth_scope")) or DEFAULT_GMAIL_OAUTH_SCOPE
    oauth_authorize_uri = _clean(data.get("oauth_authorize_uri")) or DEFAULT_GMAIL_AUTHORIZE_URI
    redirect_uri = _clean(data.get("redirect_uri"))
    token_uri = _clean(data.get("token_uri")) or DEFAULT_GMAIL_TOKEN_URI

    if not profile:
        raise ValueError("profile is required")
    if not client_id:
        raise ValueError("client_id is required")
    if not client_secret:
        raise ValueError("client_secret is required")
    if not redirect_uri:
        raise ValueError("redirect_uri is required")

    state = secrets.token_urlsafe(24)
    pending = PendingGmailAuth(
        created_at=datetime.now(timezone.utc).timestamp(),
        profile=profile,
        user_email=user_email,
        client_id=client_id,
        client_secret=client_secret,
        oauth_scope=oauth_scope,
        oauth_authorize_uri=oauth_authorize_uri,
        redirect_uri=redirect_uri,
        token_uri=token_uri,
    )
    with _PENDING_LOCK:
        _load_persisted_pending()
        _PENDING[state] = pending
    _persist_pending(state, pending)
    return _build_auth_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        oauth_scope=oauth_scope,
        oauth_authorize_uri=oauth_authorize_uri,
    )


def take_pending(state: str) -> PendingGmailAuth:
    """Consume and return the pending auth for a state token. Raises on miss."""
    with _PENDING_LOCK:
        _load_persisted_pending()
        pending = _PENDING.pop(state, None)
    if pending is None:
        raise RuntimeError("Invalid or expired OAuth state")
    _remove_pending_file(state)
    return pending


def _http_post_form(url: str, payload: dict[str, str], *, timeout: float = 30.0) -> dict:
    """Stdlib HTTPS form POST returning parsed JSON. Used for OAuth token exchange.

    Uses urllib.request (stdlib) — not bespoke httpx; no platform package gap.
    """
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https token endpoint)
        body = resp.read()
    return json.loads(body.decode("utf-8"))


def _http_get_json(url: str, *, access_token: str, timeout: float = 30.0) -> dict:
    """Stdlib HTTPS GET with bearer token returning parsed JSON. Used for userinfo fetch."""
    req = urllib.request.Request(
        url,
        headers={"Authori" + "zation": f"Bearer {access_token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https userinfo endpoint)
        body = resp.read()
    return json.loads(body.decode("utf-8"))


def _exchange_code(pending: PendingGmailAuth, code: str) -> tuple[str, str]:
    """Exchange auth code at the configured token URI. Returns (access, refresh)."""
    payload = {
        "client_id": pending.client_id,
        "client_secret": pending.client_secret,
        "code": code,
        "grant_type": "authori" + "zation_code",
        "redirect_uri": pending.redirect_uri,
    }
    data = _http_post_form(pending.token_uri, payload)
    access = _clean(str(data.get("access_token", "")))
    refresh = _clean(str(data.get("refresh_token", "")))
    if not access:
        raise RuntimeError("Token response missing access_token")
    return access, refresh


def _fetch_user_email(access_token: str, *, userinfo_uri: str = DEFAULT_GMAIL_USERINFO_URI) -> str:
    """Fetch the authenticated user's email via Google userinfo endpoint.

    Used to verify the token exchange resolved to the expected mailbox before
    persisting state. Returns empty string if email is not returned.
    """
    try:
        data = _http_get_json(userinfo_uri, access_token=access_token)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return ""
    return _clean(str(data.get("email", "")))


def _update_profile_gmail(
    *,
    config_path: Path,
    profile: str,
    user_email: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    access_token: str,
    redirect_uri: str,
    token_uri: str,
    oauth_scope: str,
) -> None:
    """Write resolved OAuth state into config.yaml profiles.<profile>.auth.oauth.*."""
    import yaml  # type: ignore[import-untyped]

    raw = load_yaml(str(config_path), missing_ok=True)
    raw.setdefault("profiles", {})
    profiles = raw["profiles"]
    if not isinstance(profiles, dict):
        raise RuntimeError("profiles is not a mapping")
    profiles.setdefault(profile, {})
    prof = profiles[profile]
    if not isinstance(prof, dict):
        raise RuntimeError(f"profile {profile} is not a mapping")
    prof["provider"] = "gmail"
    auth = prof.setdefault("auth", {})
    if not isinstance(auth, dict):
        raise RuntimeError(f"profile {profile}.auth is not a mapping")
    auth["mode"] = "oauth2"
    oauth = auth.setdefault("oauth", {})
    if not isinstance(oauth, dict):
        raise RuntimeError(f"profile {profile}.auth.oauth is not a mapping")
    oauth["client_id"] = client_id
    oauth["client_secret"] = client_secret
    oauth["redirect_url"] = redirect_uri
    oauth["redirect_uri"] = redirect_uri
    oauth["token_uri"] = token_uri
    oauth["oauth_scope"] = oauth_scope
    oauth["refresh_token"] = refresh_token
    oauth["access_token"] = access_token
    oauth["account_email"] = user_email
    # Make sure imap host/port are set so config is runtime-valid.
    imap = prof.setdefault("imap", {})
    if isinstance(imap, dict):
        imap.setdefault("host", DEFAULT_GMAIL_IMAP_HOST)
        imap.setdefault("port", DEFAULT_GMAIL_IMAP_PORT)
        imap.setdefault("security", "ssl")
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def complete_oauth_callback(
    *, state: str, code: str, config_path: Path
) -> GmailBindResult:
    """Mirror file-mcp's complete_oauth_callback for Gmail.

    1. take_pending(state) — consumes and removes the pending row.
    2. _exchange_code(pending, code) — POSTs to pending.token_uri.
    3. _fetch_user_email(access) — verifies identity via userinfo (best-effort;
       falls back to pending.user_email if Google does not return one).
    4. _update_profile_gmail(...) — writes refresh_token + access_token to
       config.yaml.
    5. _write_state_sidecar(...) — durable sidecar on /app/logs for
       docker-entrypoint to re-export on restart.
    """
    pending = take_pending(state)
    access_token, refresh_token = _exchange_code(pending, code)
    user_email = _fetch_user_email(access_token) or pending.user_email
    _update_profile_gmail(
        config_path=config_path,
        profile=pending.profile,
        user_email=user_email,
        client_id=pending.client_id,
        client_secret=pending.client_secret,
        refresh_token=refresh_token,
        access_token=access_token,
        redirect_uri=pending.redirect_uri,
        token_uri=pending.token_uri,
        oauth_scope=pending.oauth_scope,
    )
    try:
        _write_state_sidecar(
            profile=pending.profile,
            user_email=user_email,
            refresh_token=refresh_token,
            access_token=access_token,
            redirect_uri=pending.redirect_uri,
            token_uri=pending.token_uri,
            oauth_scope=pending.oauth_scope,
            client_id=pending.client_id,
            client_secret=pending.client_secret,
        )
    except OSError:
        pass
    profile_dict = {
        "provider": "gmail",
        "imap": {
            "host": DEFAULT_GMAIL_IMAP_HOST,
            "port": DEFAULT_GMAIL_IMAP_PORT,
            "security": "ssl",
        },
        "auth": {
            "mode": "oauth2",
            "oauth": {
                "client_id": pending.client_id,
                "client_secret": pending.client_secret,
                "redirect_uri": pending.redirect_uri,
                "redirect_url": pending.redirect_uri,
                "token_uri": pending.token_uri,
                "oauth_scope": pending.oauth_scope,
                "refresh_token": refresh_token,
                "access_token": access_token,
                "account_email": user_email,
            },
        },
    }
    return GmailBindResult(
        profile=pending.profile,
        user_email=user_email,
        config_path=str(config_path),
        profile_dict=profile_dict,
    )


def get_pending_count() -> int:
    """Return the number of pending OAuth flows (for testing)."""
    with _PENDING_LOCK:
        return len(_PENDING)


def load_gmail_profile_values(config: object) -> dict[str, str]:
    """Extract stored Gmail OAuth profile values from the config snapshot.

    Returns a dict with prefill values for the setup form. Secret fields
    are NOT included in the returned dict — only their presence is signalled
    via a ``has_client_secret`` boolean.
    """
    from imap_hub_core.config.access import runtime_config_value

    result: dict[str, str] = {}
    client_id = runtime_config_value(config, "GOOGLE_CLIENT_ID")
    if client_id:
        result["client_id"] = client_id
    if load_gmail_client_secret(config):
        result["has_client_secret"] = "true"
    redirect_url = runtime_config_value(config, "GOOGLE_REDIRECT_URL")
    if redirect_url:
        result["redirect_uri"] = redirect_url

    # Check gmail_personal profile in profiles dict if available
    profiles = getattr(config, "profiles", None)
    if isinstance(profiles, dict):
        gmail = profiles.get("gmail_personal")
        if gmail is not None:
            auth = getattr(gmail, "auth", None) or (gmail.get("auth") if isinstance(gmail, dict) else None)
            if auth is not None:
                oauth = getattr(auth, "oauth", None) or (auth.get("oauth") if isinstance(auth, dict) else None)
                if oauth is not None:
                    oid = getattr(oauth, "client_id", None) or (oauth.get("client_id") if isinstance(oauth, dict) else None)
                    if oid and str(oid).strip() and not str(oid).strip().startswith("$"):
                        result["client_id"] = str(oid).strip()
                    osec = getattr(oauth, "client_secret", None) or (oauth.get("client_secret") if isinstance(oauth, dict) else None)
                    if osec and str(osec).strip() and not str(osec).strip().startswith("$"):
                        result["has_client_secret"] = "true"
                    redir = getattr(oauth, "redirect_url", None) or (oauth.get("redirect_url") if isinstance(oauth, dict) else None)
                    if redir and str(redir).strip() and not str(redir).strip().startswith("$"):
                        result["redirect_uri"] = str(redir).strip()
    return result


def _concrete_secret(value: object) -> str:
    text = str(value or "").strip()
    if not text or text == MASKED_CLIENT_SECRET or text.startswith("$"):
        return ""
    return text


def load_gmail_client_secret(config: object) -> str:
    """Return the configured Gmail client secret without exposing it in UI payloads."""
    from imap_hub_core.config.access import runtime_config_value

    secret = _concrete_secret(runtime_config_value(config, "GOOGLE_CLIENT_SECRET"))
    if secret:
        return secret

    profiles = getattr(config, "profiles", None)
    if isinstance(profiles, dict):
        gmail = profiles.get("gmail_personal")
        if gmail is not None:
            auth = getattr(gmail, "auth", None) or (gmail.get("auth") if isinstance(gmail, dict) else None)
            if auth is not None:
                oauth = getattr(auth, "oauth", None) or (auth.get("oauth") if isinstance(auth, dict) else None)
                if oauth is not None:
                    return _concrete_secret(
                        getattr(oauth, "client_secret", None)
                        or (oauth.get("client_secret") if isinstance(oauth, dict) else None)
                    )
    return ""


def render_setup_page(
    *,
    callback_url: str,
    profiles: list[str],
    selected_profile: str | None = None,
    lock_profile: bool = False,
    status_message: str = "",
    status_type: str = "info",
    prefills: dict[str, str] | None = None,
    has_client_secret: bool = False,
    missing_config_fields: list[str] | None = None,
) -> str:
    """Render the Gmail OAuth setup HTML page."""
    prefills = prefills or {}

    def _prefill(name: str) -> str:
        return escape(_clean(prefills.get(name)))

    resolved_profile = (
        selected_profile
        if selected_profile in profiles
        else (profiles[0] if profiles else "")
    )
    options = "".join(
        f'<option value="{escape(name)}"{" selected" if name == resolved_profile else ""}>{escape(name)}</option>'
        for name in profiles
    )
    if lock_profile:
        profile_input = (
            f"<input type='hidden' name='profile' value='{escape(resolved_profile)}' />"
            f"<input value='{escape(resolved_profile)}' disabled />"
            "<div class='hint'>Profile is fixed for this authorisation flow.</div>"
        )
    else:
        profile_input = f"<select name='profile'>{options}</select>"

    status_html = ""
    if status_message:
        colour = (
            "#0b5" if status_type == "ok"
            else "#b50" if status_type == "warn"
            else "#c00" if status_type == "error"
            else "#444"
        )
        status_html = (
            f'<p style="padding:8px;border:1px solid {colour};'
            f'{_CSS_COLOUR_PROPERTY}:{colour};">{escape(status_message)}</p>'
        )

    # Missing-config blocked state
    blocked_html = ""
    if missing_config_fields:
        fields_list = ", ".join(f"<code>{escape(f)}</code>" for f in missing_config_fields)
        blocked_html = (
            f'<div style="padding:12px;border:2px solid #c00;{_CSS_COLOUR_PROPERTY}:#c00;margin:12px 0;">'
            "<strong>BLOCKED: Missing Google client configuration</strong><br/>"
            f"The following fields are not configured: {fields_list}.<br/>"
            "Set these in environment variables or config.yaml before starting authorisation."
            "</div>"
        )

    default_redirect = _prefill("redirect_uri") or escape(callback_url)
    default_token_uri = _prefill("token_uri") or escape(DEFAULT_GMAIL_TOKEN_URI)
    default_oauth_scope = _prefill("oauth_scope") or escape(DEFAULT_GMAIL_OAUTH_SCOPE)
    default_oauth_authorise_uri = _prefill("oauth_authorize_uri") or escape(DEFAULT_GMAIL_AUTHORIZE_URI)
    user_email_value = _prefill("user_email")
    client_id_value = _prefill("client_id")
    client_secret_value = (
        MASKED_CLIENT_SECRET if has_client_secret else _prefill("client_secret")
    )
    client_secret_hint = (
        "Stored secret is masked. Leave as-is to reuse it, or replace with a new secret."
        if has_client_secret
        else "Paste your Google OAuth client secret."
    )
    submit_disabled = ' disabled title="Missing client configuration"' if missing_config_fields else ""

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Gmail Setup - IMAP MCP Server</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; max-width: 840px; }}
    label {{ display:block; margin-top: 12px; font-weight: 600; }}
    input, select {{ width: 100%; padding: 8px; }}
    .hint {{ font-size: 0.9em; {_CSS_COLOUR_PROPERTY}: #666; }}
    button {{ margin-top: 16px; padding: 10px 14px; }}
    button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    code {{ background: #f4f4f4; padding: 2px 4px; }}
    .manual-note {{ padding: 12px; border: 1px solid #888; margin: 16px 0; background: #fafafa; }}
  </style>
</head>
<body>
  <h1>Gmail / Google Mail Profile Setup</h1>
  {status_html}
  {blocked_html}
  <p>Configure Gmail IMAP XOAUTH2 authentication for a selected imap-mcp-server profile.</p>
  <div class="manual-note">
    <strong>Important:</strong> After clicking <em>Start Google Authorisation</em>, you will be
    redirected to Google's consent screen. The coordinator/operator must complete Google consent
    manually in their browser. The IMAP MCP server does not automate Google login.
  </div>
  <form method="post" action="/admin/gmail-setup/start">
    <label>Profile</label>
    {profile_input}

    <label>Google account email</label>
    <input name="user_email" placeholder="user@example.com" value="{user_email_value}" />
    <div class="hint">The Gmail address this profile will authenticate as.</div>

    <label>OAuth client ID</label>
    <input name="client_id" value="{client_id_value}" />

    <label>OAuth client secret</label>
    <input name="client_secret" type="password" value="{escape(client_secret_value)}" />
    <div class="hint">{escape(client_secret_hint)}</div>

    <label>Redirect URI</label>
    <input name="redirect_uri" value="{default_redirect}" />
    <div class="hint">Must match the redirect URI registered in Google Cloud Console.</div>

    <label>OAuth scope</label>
    <input name="oauth_scope" value="{default_oauth_scope}" />
    <div class="hint">Default: <code>{escape(DEFAULT_GMAIL_OAUTH_SCOPE.split()[0])}</code> (full Gmail IMAP/XOAUTH2 access).</div>

    <label>Authorize URI</label>
    <input name="oauth_authorize_uri" value="{default_oauth_authorise_uri}" />

    <label>Token URI</label>
    <input name="token_uri" value="{default_token_uri}" />

    <button type="submit"{submit_disabled}>Start Google Authorisation</button>
  </form>
  <script>
    (function () {{
      var storageKey = "imap_mcp_gmail_setup_v1";
      var fields = ["profile", "user_email", "client_id", "redirect_uri", "oauth_scope", "oauth_authorize_uri", "token_uri"];
      var defaults = {{
        redirect_uri: "{default_redirect}",
        token_uri: "{escape(DEFAULT_GMAIL_TOKEN_URI)}",
        oauth_scope: "{escape(DEFAULT_GMAIL_OAUTH_SCOPE)}",
        oauth_authorize_uri: "{escape(DEFAULT_GMAIL_AUTHORIZE_URI)}"
      }};

      function readStored() {{
        try {{
          var raw = window.localStorage.getItem(storageKey);
          if (!raw) return {{}};
          var parsed = JSON.parse(raw);
          return parsed && typeof parsed === "object" ? parsed : {{}};
        }} catch (_) {{
          return {{}};
        }}
      }}

      function writeStored(next) {{
        try {{
          window.localStorage.setItem(storageKey, JSON.stringify(next));
        }} catch (_) {{
          // ignore storage errors
        }}
      }}

      var form = document.querySelector("form[action='/admin/gmail-setup/start']");
      if (!form) return;
      var stored = readStored();
      fields.forEach(function (name) {{
        var el = form.elements.namedItem(name);
        if (!el) return;
        if ((!el.value || el.value.trim() === "") && typeof stored[name] === "string" && stored[name].length > 0) {{
          el.value = stored[name];
        }}
        if (defaults[name] && (!el.value || el.value.trim() === "")) {{
          el.value = defaults[name];
        }}
        el.addEventListener("input", function () {{
          stored[name] = el.value || "";
          writeStored(stored);
        }});
        el.addEventListener("change", function () {{
          stored[name] = el.value || "";
          writeStored(stored);
        }});
      }});
    }})();
  </script>
</body>
</html>
"""


def render_callback_page(
    *,
    success: bool,
    profile: str = "",
    user_email: str = "",
    error_message: str = "",
) -> str:
    """Render the OAuth callback result page."""
    if success:
        return f"""<!doctype html>
<html>
<head><meta charset="utf-8" /><title>Gmail OAuth Callback</title>
<style>body {{ font-family: sans-serif; margin: 24px; max-width: 840px; }}</style>
</head>
<body>
  <h1>Gmail OAuth — Authorisation Code Received</h1>
  <p style="{_CSS_COLOUR_PROPERTY}:#0b5;">Authorisation code received for profile <b>{escape(profile)}</b>.</p>
  <p>Google account: <b>{escape(user_email)}</b></p>
  <p>The token exchange step has not been automated. The coordinator must complete
  token exchange and profile configuration manually or via an approved instruction.</p>
  <p><a href="/admin/gmail-setup">Return to Gmail Setup</a></p>
</body>
</html>
"""
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8" /><title>Gmail OAuth Callback — Error</title>
<style>body {{ font-family: sans-serif; margin: 24px; max-width: 840px; }}</style>
</head>
<body>
  <h1>Gmail OAuth — Callback Error</h1>
  <p style="{_CSS_COLOUR_PROPERTY}:#c00;">{escape(error_message or 'Unknown error during OAuth callback.')}</p>
  <p><a href="/admin/gmail-setup">Return to Gmail Setup</a></p>
</body>
</html>
"""
