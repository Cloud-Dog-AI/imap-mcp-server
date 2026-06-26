"""Shared helpers for configurable server base paths."""

from __future__ import annotations

from typing import Any

from imap_hub_core.config.access import runtime_config_value

DEFAULT_API_BASE_PATH = "/api/v1"
DEFAULT_WEB_BASE_PATH = ""
DEFAULT_MCP_BASE_PATH = "/mcp"
DEFAULT_A2A_BASE_PATH = "/a2a"
LEGACY_API_BASE_PATH = "/app/v1"


def normalise_base_path(value: str | None, default: str = "") -> str:
    """Return a canonical base path string for route registration."""
    candidate = str(value or default).strip()
    if not candidate or candidate == "/":
        return ""
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    return candidate.rstrip("/")


def join_base_path(base_path: str, suffix: str = "/") -> str:
    """Join a normalised base path with a route suffix."""
    base = normalise_base_path(base_path)
    tail = str(suffix or "").strip()
    if not tail or tail == "/":
        return base or "/"
    if not tail.startswith("/"):
        tail = f"/{tail}"
    return f"{base}{tail}" if base else tail


def strip_base_path(path: str, base_path: str) -> str:
    """Remove a matching base path prefix from a request path."""
    candidate = str(path or "").strip() or "/"
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    base = normalise_base_path(base_path)
    if not base:
        return candidate
    if candidate == base:
        return "/"
    if candidate.startswith(f"{base}/"):
        return candidate[len(base) :]
    return candidate


def rewrite_base_path(
    path: str,
    *,
    source_base_paths: tuple[str, ...],
    target_base_path: str,
) -> str:
    """Rewrite a path from one published base path to another."""
    candidate = str(path or "").strip() or "/"
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    for source_base_path in source_base_paths:
        source = normalise_base_path(source_base_path)
        if candidate == source or candidate.startswith(f"{source}/"):
            tail = strip_base_path(candidate, source)
            return join_base_path(target_base_path, tail)
    return candidate


def resolve_surface_base_path(
    config: Any,
    *,
    surface_name: str,
    default: str,
    env_files: list[str] | None = None,
    service_prefix: str = "IMAP",
) -> str:
    """Resolve a surface base path from config with env override support."""
    _ = env_files
    override = runtime_config_value(
        config,
        f"CLOUD_DOG__{service_prefix}__{surface_name.upper()}__BASE_PATH",
        f"CLOUD_DOG__{surface_name.upper()}__BASE_PATH",
    )
    configured = getattr(getattr(config, surface_name), "base_path", "")
    return normalise_base_path(override or configured, default)
