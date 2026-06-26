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

import os


def listener_port(env_name: str) -> int:
    """Return a configured listener port from the active test env."""
    raw_value = os.environ.get(env_name, "").strip()
    if not raw_value:
        raise RuntimeError(f"Missing required listener port env: {env_name}")
    return int(raw_value)


def listener_host(env_name: str) -> str:
    """Return a loopback-safe listener host from the active test env."""
    raw_value = os.environ.get(env_name, "").strip()
    if not raw_value or raw_value == "0.0.0.0":
        return "127.0.0.1"
    return raw_value
