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

from fnmatch import fnmatch


def filter_folders(
    folders: list[str], include_globs: list[str], exclude_globs: list[str]
) -> list[str]:
    """Apply include then exclude glob policies to IMAP folder names."""
    includes = include_globs or ["*"]
    selected = [name for name in folders if any(fnmatch(name, pattern) for pattern in includes)]
    return [
        name for name in selected if not any(fnmatch(name, pattern) for pattern in exclude_globs)
    ]
