"""imap-mcp-server module."""

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

# Covers: FR-02

import inspect
from collections.abc import Mapping, Sequence
from typing import Any

from cloud_dog_config import GlobalConfig, load_config

from imap_hub_core.config.models import GlobalConfigModel


def load_global_config(
    env_files: Sequence[str] | None = None,
    config_yaml: str = "config.yaml",
    defaults_yaml: str = "defaults.yaml",
) -> GlobalConfigModel:
    """Load and validate runtime configuration using cloud_dog_config."""
    snapshot = load_raw_config(
        env_files=env_files, config_yaml=config_yaml, defaults_yaml=defaults_yaml
    )
    return bind_global_config(snapshot)


def load_raw_config(
    env_files: Sequence[str] | None = None,
    config_yaml: str = "config.yaml",
    defaults_yaml: str = "defaults.yaml",
    unresolved_policy: str = "warn",
) -> GlobalConfig:
    """Return the raw config snapshot provided by cloud_dog_config.

    Delegates file, environment, and default loading to
    `cloud_dog_config.load_config(...)`.
    """
    kwargs: dict[str, Any] = {
        "env_files": list(env_files) if env_files else None,
        "config_yaml": config_yaml,
        "defaults_yaml": defaults_yaml,
    }
    if "unresolved_policy" in inspect.signature(load_config).parameters:
        kwargs["unresolved_policy"] = unresolved_policy
    return load_config(**kwargs)


def bind_global_config(snapshot: GlobalConfig | Mapping[str, Any]) -> GlobalConfigModel:
    """Validate a cloud_dog_config snapshot into the project's typed model."""
    if isinstance(snapshot, Mapping):
        tree: dict[str, Any] = dict(snapshot)
    else:
        tree = dict(snapshot.data)
    return GlobalConfigModel.model_validate(tree)
