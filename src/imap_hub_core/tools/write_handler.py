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

class WriteToolHandlers(ImapToolHandlersBase):
    def mail_move_duplicates_since_last_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Find duplicate candidates from live search and plan or execute move operations."""
        try:
            request = MailMoveDuplicatesInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_move_duplicates_since_last_search", payload)
        try:
            profile = self._profile(request.profile_id)
        except KeyError as exc:
            return self._error_envelope("profile_not_found", str(exc))

        try:
            messages, _, _ = self._search_live_messages(
                profile_id=request.profile_id,
                query=request.query,
                folder="INBOX",
                limit=100,
            )
        except Exception as exc:
            if request.dry_run:
                messages = []
            else:
                return self._error_envelope("imap_search_failed", str(exc))

        candidates: list[DuplicateCandidate] = []
        for item in messages:
            subject = str(item.get("subject", ""))
            sender = str(item.get("from", ""))
            date_utc = str(item.get("date_utc", ""))
            content_hash = hashlib.sha256(
                f"{subject}|{sender}|{date_utc}".encode("utf-8")
            ).hexdigest()
            received_at = self._parse_received_at(date_utc)
            uid = str(item.get("uid", ""))
            candidates.append(
                DuplicateCandidate(
                    message_id=uid,
                    header_message_id=item.get("header_message_id"),
                    content_hash=content_hash,
                    sender=sender,
                    subject=subject,
                    received_at_utc=received_at,
                    size_bytes=len(subject.encode("utf-8")),
                )
            )

        groups = group_duplicates(candidates, strategy=request.strategy)
        kept_ids: list[str] = []
        moved_ids: list[str] = []
        for group in groups:
            keeper = choose_keeper(group, policy=request.policy)
            kept_ids.append(keeper.message_id)
            moved_ids.extend(
                [entry.message_id for entry in group if entry.message_id != keeper.message_id]
            )

        if not request.dry_run:
            write_enabled = bool((profile.get("write", {}) or {}).get("enabled"))
            if not write_enabled:
                self._audit(
                    "mail_move_duplicates_since_last_search",
                    "denied",
                    request.profile_id,
                    payload,
                )
                return self._write_disabled()

            client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
            try:
                client, _ = self._open_imap_client(
                    profile_id=request.profile_id,
                    folder="INBOX",
                    readonly=False,
                )
                for uid in moved_ids:
                    copy_status, _ = client.copy(uid, request.destination_folder)
                    if copy_status != "OK":
                        continue
                    client.store(uid, "+FLAGS.SILENT", "\\Deleted")
                client.expunge()
            except Exception as exc:
                self._audit(
                    "mail_move_duplicates_since_last_search",
                    "failure",
                    request.profile_id,
                    {"error": str(exc), **payload},
                )
                return self._error_envelope("imap_move_failed", str(exc))
            finally:
                self._logout(client)

        response = self._ok_envelope(
            result={
                "dry_run": request.dry_run,
                "moved": sorted(set(moved_ids)),
                "kept": sorted(set(kept_ids)),
            }
        )
        self._audit("mail_move_duplicates_since_last_search", "success", request.profile_id, payload)
        return response

    def mail_set_seen(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose: Implement `mail_set_seen` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        try:
            request = MailSetSeenInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_set_seen", payload)
        try:
            profile = self._profile(request.profile_id)
        except KeyError as exc:
            self._audit(
                "mail_set_seen", "failure", request.profile_id, {"error": str(exc), **payload}
            )
            return self._error_envelope("profile_not_found", str(exc))

        write_enabled = bool((profile.get("write", {}) or {}).get("enabled"))
        if not write_enabled:
            self._audit("mail_set_seen", "denied", request.profile_id, payload)
            return self._write_disabled()

        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        updated: list[str] = []
        failed: list[dict[str, str]] = []
        try:
            client, _ = self._open_imap_client(
                profile_id=request.profile_id,
                folder=request.folder,
                readonly=False,
            )
            action = "+FLAGS.SILENT" if request.seen else "-FLAGS.SILENT"
            for uid in request.uids:
                status, _ = self._uid_command(client, "STORE", uid, action, "\\Seen")
                if status == "OK":
                    updated.append(uid)
                else:
                    failed.append({"uid": uid, "status": status})
            if updated:
                client.expunge()
        except Exception as exc:
            self._audit(
                "mail_set_seen", "failure", request.profile_id, {"error": str(exc), **payload}
            )
            return self._error_envelope("imap_set_seen_failed", str(exc))
        finally:
            self._logout(client)

        status = "success" if not failed else "failure"
        self._audit("mail_set_seen", status, request.profile_id, payload)
        warnings = [f"Failed to update flags for {len(failed)} message(s)."] if failed else []
        return self._ok_envelope(
            result={
                "profile_id": request.profile_id,
                "folder": request.folder,
                "seen": request.seen,
                "updated": updated,
                "failed": failed,
            },
            warnings=warnings,
        )

    def mail_move_messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose: Implement `mail_move_messages` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        try:
            request = MailMoveMessagesInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_move_messages", payload)
        try:
            profile = self._profile(request.profile_id)
        except KeyError as exc:
            self._audit(
                "mail_move_messages", "failure", request.profile_id, {"error": str(exc), **payload}
            )
            return self._error_envelope("profile_not_found", str(exc))

        write_enabled = bool((profile.get("write", {}) or {}).get("enabled"))
        if not write_enabled:
            self._audit("mail_move_messages", "denied", request.profile_id, payload)
            return self._write_disabled()

        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        moved: list[str] = []
        failed: list[dict[str, str]] = []
        try:
            client, _ = self._open_imap_client(
                profile_id=request.profile_id,
                folder=request.folder,
                readonly=False,
            )
            for uid in request.uids:
                copy_status, _ = self._uid_command(client, "COPY", uid, request.destination_folder)
                if copy_status != "OK":
                    failed.append({"uid": uid, "status": copy_status, "step": "copy"})
                    continue
                store_status, _ = self._uid_command(client, "STORE", uid, "+FLAGS.SILENT", "\\Deleted")
                if store_status != "OK":
                    failed.append({"uid": uid, "status": store_status, "step": "delete-flag"})
                    continue
                moved.append(uid)
            if moved:
                client.expunge()
        except Exception as exc:
            self._audit(
                "mail_move_messages", "failure", request.profile_id, {"error": str(exc), **payload}
            )
            return self._error_envelope("imap_move_failed", str(exc))
        finally:
            self._logout(client)

        status = "success" if moved and not failed else "failure" if failed else "success"
        self._audit("mail_move_messages", status, request.profile_id, payload)
        warnings = [f"Failed to move {len(failed)} message(s)."] if failed else []
        return self._ok_envelope(
            result={
                "profile_id": request.profile_id,
                "folder": request.folder,
                "destination_folder": request.destination_folder,
                "moved": moved,
                "failed": failed,
            },
            warnings=warnings,
        )

    def mail_delete_messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose: Implement `mail_delete_messages` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        try:
            request = MailDeleteMessagesInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_delete_messages", payload)
        try:
            profile = self._profile(request.profile_id)
        except KeyError as exc:
            self._audit(
                "mail_delete_messages",
                "failure",
                request.profile_id,
                {"error": str(exc), **payload},
            )
            return self._error_envelope("profile_not_found", str(exc))

        write_enabled = bool((profile.get("write", {}) or {}).get("enabled"))
        if not write_enabled:
            self._audit("mail_delete_messages", "denied", request.profile_id, payload)
            return self._write_disabled()

        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        deleted: list[str] = []
        failed: list[dict[str, str]] = []
        try:
            client, _ = self._open_imap_client(
                profile_id=request.profile_id,
                folder=request.folder,
                readonly=False,
            )
            for uid in request.uids:
                status, _ = self._uid_command(client, "STORE", uid, "+FLAGS.SILENT", "\\Deleted")
                if status == "OK":
                    deleted.append(uid)
                else:
                    failed.append({"uid": uid, "status": status})
            if deleted:
                client.expunge()
        except Exception as exc:
            self._audit(
                "mail_delete_messages",
                "failure",
                request.profile_id,
                {"error": str(exc), **payload},
            )
            return self._error_envelope("imap_delete_failed", str(exc))
        finally:
            self._logout(client)

        status = "success" if deleted and not failed else "failure" if failed else "success"
        self._audit("mail_delete_messages", status, request.profile_id, payload)
        warnings = [f"Failed to delete {len(failed)} message(s)."] if failed else []
        return self._ok_envelope(
            result={
                "profile_id": request.profile_id,
                "folder": request.folder,
                "deleted": deleted,
                "failed": failed,
            },
            warnings=warnings,
        )



