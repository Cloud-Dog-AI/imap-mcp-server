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

from __future__ import annotations

from imap_hub_core.tools.base_handler import *  # noqa: F403

class SearchToolHandlers(ImapToolHandlersBase):
    def profile_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return available profile IDs."""
        try:
            request = ProfileListInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        current_profiles = self._current_profiles()
        profiles = sorted(current_profiles.keys())
        if not request.include_disabled:
            profiles = [
                profile_id
                for profile_id in profiles
                if bool((current_profiles.get(profile_id) or {}).get("enabled", True))
            ]
        profiles = [profile_id for profile_id in profiles if self._check_profile_access(profile_id)]
        return self._ok_envelope(result={"profiles": profiles})

    def mail_probe(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Probe IMAP connectivity for a configured profile."""
        try:
            request = MailProbeInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_probe", payload)
        try:
            profile = self._profile(request.profile_id)
            settings = self._resolve_connection(profile)
            result = probe_imap_connectivity(
                IMAPConnectionConfig(
                    host=settings.host,
                    port=settings.port,
                    security=settings.security,
                    timeout_seconds=settings.timeout_seconds,
                    ca_bundle_path=settings.ca_bundle_path,
                    allow_self_signed=settings.allow_self_signed,
                )
            )
            response = self._ok_envelope(
                result={
                    "profile_id": request.profile_id,
                    "folder": request.folder,
                    "connected": result.get("status") == "ok",
                    "mode": result.get("mode"),
                    "host": settings.host,
                    "port": settings.port,
                }
            )
            self._audit("mail_probe", "success", request.profile_id, payload)
            return response
        except KeyError as exc:
            self._audit("mail_probe", "failure", request.profile_id, {"error": str(exc), **payload})
            return self._error_envelope("profile_not_found", str(exc))
        except Exception as exc:
            self._audit("mail_probe", "failure", request.profile_id, {"error": str(exc), **payload})
            return self._error_envelope("imap_probe_failed", str(exc))

    def mail_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute live IMAP search, record ledger state, and return message summaries."""
        try:
            request = MailSearchInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_search", payload)
        try:
            self._profile(request.profile_id)
        except KeyError as exc:
            return self._error_envelope("profile_not_found", str(exc))

        effective_query = self._effective_search_query(request.profile_id, request.query)
        similarity_key, canonical = build_similarity_key(
            profile_id=request.profile_id,
            mode=request.mode,
            query=effective_query,
            filters=request.filters,
            similarity_pins=request.similarity_pins,
        )

        folder = str(request.filters.get("folder", "INBOX"))
        limit = self._effective_search_limit(request.profile_id, request.limit, fallback=50)
        if request.mode == "cache":
            messages, high_water_mark, result_ids = self._offline_search_messages(
                profile_id=request.profile_id,
                folder=folder,
                query=effective_query,
                limit=limit,
            )
        else:
            try:
                messages, high_water_mark, result_ids = self._search_live_messages(
                    profile_id=request.profile_id,
                    query=effective_query,
                    folder=folder,
                    limit=limit,
                )
            except Exception as exc:
                self._audit(
                    "mail_search", "failure", request.profile_id, {"error": str(exc), **payload}
                )
                return self._error_envelope("imap_search_failed", str(exc))

        now = datetime.now(timezone.utc)
        search_id = f"search-{uuid4().hex[:12]}"
        self._ledger.append(
            LedgerEntry(
                search_id=search_id,
                actor_id="system",
                profile_id=request.profile_id,
                similarity_key=similarity_key,
                created_at=now,
                high_water_mark=high_water_mark,
                result_ids=result_ids,
            )
        )
        self._audit("mail_search", "success", request.profile_id, payload)

        return self._ok_envelope(
            result={
                "search_id": search_id,
                "similarity_key": similarity_key,
                "canonical": canonical,
                "effective_query": effective_query,
                "effective_limit": limit,
                "high_water_mark": high_water_mark,
                "messages": messages,
            }
        )

    def mail_search_since_last(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run live search and return messages that are new since the last similar baseline."""
        try:
            request = MailSearchSinceLastInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_search_since_last", payload)
        try:
            self._profile(request.profile_id)
        except KeyError as exc:
            return self._error_envelope("profile_not_found", str(exc))

        similarity_key, canonical = build_similarity_key(
            profile_id=request.profile_id,
            mode=request.mode,
            query=request.query,
            filters=request.filters,
        )
        baseline_entry = self._ledger.find_last_similar(
            actor_id="system",
            profile_id=request.profile_id,
            similarity_key=similarity_key,
        )

        folder = str(request.filters.get("folder", "INBOX"))
        if request.mode == "cache":
            messages, high_water_mark, result_ids = self._offline_search_messages(
                profile_id=request.profile_id,
                folder=folder,
                query=request.query,
                limit=self._effective_search_limit(request.profile_id, request.limit, fallback=200),
            )
        else:
            try:
                messages, high_water_mark, result_ids = self._search_live_messages(
                    profile_id=request.profile_id,
                    query=request.query,
                    folder=folder,
                )
            except Exception as exc:
                self._audit(
                    "mail_search_since_last",
                    "failure",
                    request.profile_id,
                    {"error": str(exc), **payload},
                )
                return self._error_envelope("imap_search_failed", str(exc))

        baseline_ids = set(baseline_entry.result_ids) if baseline_entry is not None else set()
        new_messages = [item for item in messages if str(item.get("uid", "")) not in baseline_ids]

        now = datetime.now(timezone.utc)
        search_id = f"search-{uuid4().hex[:12]}"
        self._ledger.append(
            LedgerEntry(
                search_id=search_id,
                actor_id="system",
                profile_id=request.profile_id,
                similarity_key=similarity_key,
                created_at=now,
                high_water_mark=high_water_mark,
                result_ids=result_ids,
            )
        )

        baseline: dict[str, Any] | None = None
        if baseline_entry is not None:
            resolved = self._ledger.resolve_high_water_mark(baseline_entry)
            baseline = {
                "search_id": baseline_entry.search_id,
                "created_at": baseline_entry.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "high_water_mark": baseline_entry.high_water_mark,
                "resolved": {"kind": resolved[0], "value": resolved[1]}
                if resolved is not None
                else None,
            }

        self._audit("mail_search_since_last", "success", request.profile_id, payload)
        return self._ok_envelope(
            result={
                "search_id": search_id,
                "similarity_key": similarity_key,
                "canonical": canonical,
                "baseline": baseline,
                "new_messages": new_messages,
            }
        )

    def mail_headlines(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run a search and return compact headline items for recent messages."""
        try:
            request = MailHeadlinesInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_headlines", payload)
        try:
            self._profile(request.profile_id)
        except KeyError as exc:
            return self._error_envelope("profile_not_found", str(exc))

        folder = str(request.filters.get("folder", "INBOX"))
        effective_query = self._effective_search_query(request.profile_id, request.query)
        limit = self._effective_search_limit(request.profile_id, request.limit, fallback=200)
        try:
            messages, _, _ = self._search_live_messages(
                profile_id=request.profile_id,
                query=effective_query,
                folder=folder,
                limit=limit,
            )
        except Exception as exc:
            self._audit(
                "mail_headlines", "failure", request.profile_id, {"error": str(exc), **payload}
            )
            return self._error_envelope("imap_search_failed", str(exc))

        headlines: list[dict[str, Any]] = []
        for item in messages:
            subject = str(item.get("subject", "")).strip()
            sender = str(item.get("from", "")).strip()
            headlines.append(
                {
                    "uid": str(item.get("uid", "")),
                    "headline": subject or "(no subject)",
                    "from": sender,
                    "date_utc": item.get("date_utc"),
                }
            )

        self._audit("mail_headlines", "success", request.profile_id, payload)
        return self._ok_envelope(
            result={
                "profile_id": request.profile_id,
                "query": effective_query,
                "effective_limit": limit,
                "count": len(headlines),
                "headlines": headlines,
            }
        )

    def mail_list_folders(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Enumerate live IMAP folders and cache the result for a bounded TTL."""
        try:
            request = MailListFoldersInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_list_folders", payload)
        ttl_seconds = self._folder_list_cache_ttl_seconds(request.profile_id)
        now = _time.monotonic()
        cached = self._folder_list_cache.get(request.profile_id)
        if cached is not None and cached.expires_at > now:
            response = self._ok_envelope(
                result={
                    "profile_id": request.profile_id,
                    "folders": cached.folders,
                    "cached": True,
                    "ttl_seconds": ttl_seconds,
                    "retrieved_at": cached.retrieved_at,
                }
            )
            self._audit(
                "mail_list_folders",
                "success",
                request.profile_id,
                {"cached": True, **payload},
            )
            return response

        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        try:
            client, _ = self._connect_imap_client(request.profile_id)
            status, entries = client.list("", "*")
            if status != "OK":
                raise RuntimeError(f"IMAP LIST failed: {status}")

            folders = [
                parsed
                for parsed in (
                    self._parse_list_response_line(entry)
                    for entry in (entries or [])
                    if isinstance(entry, bytes)
                )
                if parsed is not None and str(parsed.get("name", "")).strip()
            ]
            folders.sort(key=lambda item: str(item.get("name", "")).lower())
            retrieved_at = self._to_utc_iso(datetime.now(timezone.utc))
            self._folder_list_cache[request.profile_id] = FolderListCacheEntry(
                expires_at=now + ttl_seconds,
                retrieved_at=retrieved_at,
                folders=folders,
            )
            response = self._ok_envelope(
                result={
                    "profile_id": request.profile_id,
                    "folders": folders,
                    "cached": False,
                    "ttl_seconds": ttl_seconds,
                    "retrieved_at": retrieved_at,
                }
            )
            self._audit("mail_list_folders", "success", request.profile_id, payload)
            return response
        except Exception as exc:
            self._audit(
                "mail_list_folders",
                "failure",
                request.profile_id,
                {"error": str(exc), **payload},
            )
            return self._error_envelope("imap_folder_list_failed", str(exc))
        finally:
            self._logout(client)


