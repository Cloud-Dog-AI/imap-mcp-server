"""Config snapshot access helpers for runtime compatibility values."""

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

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import cloud_dog_config
from cloud_dog_config import GlobalConfig
from cloud_dog_config.naming import env_to_path


def resolve_env_files(explicit: Sequence[str] | None = None) -> list[str] | None:
    """Resolve runtime env-file list through cloud_dog_config."""
    files = cloud_dog_config.resolve_runtime_env_files(explicit)
    return files or None


def runtime_config_value(config: Any, *names_or_paths: str) -> str:
    """Return the first non-empty value from a config snapshot/model.

    Inputs may be dotted config paths or environment-style names. Env-style
    names are translated using cloud_dog_config's naming rules; raw legacy keys
    are also checked when they are explicitly present in the config snapshot.
    """
    for name_or_path in names_or_paths:
        for candidate in _candidate_paths(name_or_path):
            value = _get_path(config, candidate)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
    return ""


def _candidate_paths(name_or_path: str) -> tuple[str, ...]:
    raw = name_or_path.strip()
    if not raw:
        return ()
    candidates: list[str] = [raw]
    prefixed = env_to_path(raw, prefix="CLOUD_DOG")
    if prefixed:
        candidates.append(prefixed)
    unprefixed = env_to_path(raw)
    if unprefixed:
        candidates.append(unprefixed)
    return tuple(dict.fromkeys(candidates))


def _get_path(config: Any, path: str) -> Any:
    if config is None or not path:
        return None
    if isinstance(config, GlobalConfig):
        return config.get(path)
    if isinstance(config, Mapping):
        return _get_mapping_path(config, path)
    model_extra = getattr(config, "model_extra", None)
    if path in (model_extra or {}):
        return model_extra[path]
    if "." not in path and hasattr(config, path):
        return getattr(config, path)
    node: Any = config
    for part in path.split("."):
        if isinstance(node, Mapping):
            if part not in node:
                return None
            node = node[part]
            continue
        extra = getattr(node, "model_extra", None)
        if isinstance(extra, Mapping) and part in extra:
            node = extra[part]
            continue
        if not hasattr(node, part):
            return None
        node = getattr(node, part)
    return node


def _get_mapping_path(config: Mapping[str, Any], path: str) -> Any:
    if path in config:
        return config[path]
    node: Any = config
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node
