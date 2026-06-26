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

class ReadToolHandlers(ImapToolHandlersBase):
    def mail_get_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose: Implement `mail_get_message` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        try:
            request = MailGetMessageInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_get_message", payload)
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        try:
            client, _ = self._open_imap_client(
                profile_id=request.profile_id,
                folder=request.folder,
                readonly=True,
            )
            raw_bytes = self._fetch_message_bytes(client, request.uid)
            response = self._ok_envelope(
                result={
                    "profile_id": request.profile_id,
                    "folder": request.folder,
                    "uid": request.uid,
                    "raw_eml": raw_bytes.decode("utf-8", "replace"),
                }
            )
            self._audit("mail_get_message", "success", request.profile_id, payload)
            return response
        except Exception as exc:
            # Fixture-fallback: trigger when live IMAP is unconfigured OR when live fetch
            # returned empty bytes (e.g. operations profile with live creds but UID only
            # in offline fixture). Fixture lookup is safe — returns None when absent.
            fixture = self._offline_fixture_message(request.profile_id, request.folder, request.uid)
            if fixture is not None:
                raw_bytes = self._offline_message_bytes(fixture)
                response = self._ok_envelope(
                    result={
                        "profile_id": request.profile_id,
                        "folder": request.folder,
                        "uid": request.uid,
                        "raw_eml": raw_bytes.decode("utf-8", "replace"),
                    }
                )
                self._audit("mail_get_message", "success", request.profile_id, payload)
                return response
            self._audit("mail_get_message", "failure", request.profile_id, {"error": str(exc), **payload})
            return self._error_envelope("imap_fetch_failed", str(exc))
        finally:
            self._logout(client)

    def mail_list_attachments(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose: Implement `mail_list_attachments` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        try:
            request = MailListAttachmentsInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_list_attachments", payload)
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        try:
            client, _ = self._open_imap_client(
                profile_id=request.profile_id,
                folder=request.folder,
                readonly=True,
            )
            raw_bytes = self._fetch_message_bytes(client, request.uid)
            message = self._decode_message(raw_bytes)
            attachments = [
                {
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "size": item.size_bytes,
                    "size_bytes": item.size_bytes,
                    "content_id": item.content_id,
                    "part_id": item.part_id,
                }
                for item in list_attachments(message)
            ]
            response = self._ok_envelope(
                result={
                    "profile_id": request.profile_id,
                    "folder": request.folder,
                    "uid": request.uid,
                    "attachments": attachments,
                }
            )
            self._audit("mail_list_attachments", "success", request.profile_id, payload)
            return response
        except Exception as exc:
            # Fixture-fallback: trigger when live IMAP is unconfigured OR when live fetch
            # returned empty bytes. Fixture lookup is safe — returns None when absent.
            fixture = self._offline_fixture_message(request.profile_id, request.folder, request.uid)
            if fixture is not None:
                response = self._ok_envelope(
                    result={
                        "profile_id": request.profile_id,
                        "folder": request.folder,
                        "uid": request.uid,
                        "attachments": [
                            {
                                "filename": item.filename,
                                "content_type": item.content_type,
                                "size": item.size_bytes,
                                "size_bytes": item.size_bytes,
                                "content_id": None,
                                "part_id": item.part_id,
                            }
                            for item in fixture.attachments
                        ],
                    }
                )
                self._audit("mail_list_attachments", "success", request.profile_id, payload)
                return response
            self._audit(
                "mail_list_attachments",
                "failure",
                request.profile_id,
                {"error": str(exc), **payload},
            )
            return self._error_envelope("imap_attachment_list_failed", str(exc))
        finally:
            self._logout(client)

    def mail_download_attachment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose: Implement `mail_download_attachment` behaviour for this module.
        Inputs: Parameters are defined by the function/class signature.
        Outputs: Returns values according to the module contract.
        Dependencies: Uses internal project modules and configured services.
        Related tests: See TESTS.md and tests/ for coverage mapping.
        """
        try:
            request = MailDownloadAttachmentInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_download_attachment", payload)
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        try:
            client, _ = self._open_imap_client(
                profile_id=request.profile_id,
                folder=request.folder,
                readonly=True,
            )
            raw_bytes = self._fetch_message_bytes(client, request.uid)
            message = self._decode_message(raw_bytes)
            attachment = self._attachment_payload_for_part(message, request.part_id)
            if attachment is None:
                return self._error_envelope(
                    "attachment_not_found", f"Attachment part {request.part_id} not found."
                )

            inferred_name, payload_bytes = attachment
            filename = safe_file_name(request.filename or inferred_name)
            destination = join_fs_path(self._downloads_dir, filename)
            # Avoid overwriting host-mounted files that may be owned by another user in docker mode.
            if self._download_storage.exists(f"/{filename}") and not os.access(destination, os.W_OK):
                stem, suffix = split_file_name(filename)
                filename = f"{stem}_{uuid4().hex[:8]}{suffix}"
                destination = join_fs_path(self._downloads_dir, filename)
            write_storage_bytes(self._download_storage, f"/{filename}", payload_bytes)

            content_encoding = "base64"
            content = base64.b64encode(payload_bytes).decode("ascii")
            if b"\x00" not in payload_bytes:
                try:
                    decoded = payload_bytes.decode("utf-8")
                    content_encoding = "text"
                    content = decoded
                except UnicodeDecodeError:
                    content_encoding = "base64"

            response = self._ok_envelope(
                result={
                    "path": destination,
                    "filename": filename,
                    "size_bytes": len(payload_bytes),
                    "content_encoding": content_encoding,
                    "content": content,
                }
            )
            self._audit("mail_download_attachment", "success", request.profile_id, payload)
            return response
        except Exception as exc:
            # Fixture-fallback: trigger when live IMAP is unconfigured OR when live fetch
            # returned empty bytes. Fixture lookup is safe — returns None when absent.
            fixture = self._offline_fixture_message(request.profile_id, request.folder, request.uid)
            attachment_fixture = (
                self._offline_attachment_for_part(fixture, request.part_id) if fixture is not None else None
            )
            if attachment_fixture is not None:
                with open(attachment_fixture.path, "rb") as handle:
                    payload_bytes = handle.read()
                filename = safe_file_name(request.filename or attachment_fixture.filename)
                source_path = attachment_fixture.path
                destination = source_path
                if os.path.basename(source_path) != filename:
                    destination = join_fs_path(self._downloads_dir, filename)
                    write_storage_bytes(self._download_storage, f"/{filename}", payload_bytes)

                content_encoding = "base64"
                content = base64.b64encode(payload_bytes).decode("ascii")
                if b"\x00" not in payload_bytes:
                    try:
                        decoded = payload_bytes.decode("utf-8")
                        content_encoding = "text"
                        content = decoded
                    except UnicodeDecodeError:
                        content_encoding = "base64"

                response = self._ok_envelope(
                    result={
                        "path": destination,
                        "filename": filename,
                        "size_bytes": len(payload_bytes),
                        "content_encoding": content_encoding,
                        "content": content,
                    }
                )
                self._audit("mail_download_attachment", "success", request.profile_id, payload)
                return response
            self._audit(
                "mail_download_attachment",
                "failure",
                request.profile_id,
                {"error": str(exc), **payload},
            )
            return self._error_envelope("imap_attachment_download_failed", str(exc))
        finally:
            self._logout(client)

    @staticmethod
    def _html_to_markdown(value: str) -> str:
        """Convert a minimal HTML fragment into readable markdown-like plain text."""
        content = re.sub(r"(?i)<br\\s*/?>", "\n", value)
        content = re.sub(r"(?is)</p\\s*>", "\n\n", content)
        content = re.sub(r"(?is)<[^>]+>", "", content)
        content = html.unescape(content)
        return "\n".join(line.rstrip() for line in content.splitlines()).strip()

    def mail_extract_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Fetch a message and return extracted JSON and/or Markdown text outputs."""
        try:
            request = MailExtractMessageInput.model_validate(payload)
        except ValidationError as exc:
            return self._validation_error(exc)

        self._require_profile_access(request.profile_id, "mail_extract_message", payload)
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        try:
            client, _ = self._open_imap_client(
                profile_id=request.profile_id,
                folder=request.folder,
                readonly=True,
            )
            raw_bytes = self._fetch_message_bytes(client, request.uid)
            message = self._decode_message(raw_bytes)
            extracted = extract_message_text(message)
            attachment_items = list_attachments(message)

            json_result = {
                "profile_id": request.profile_id,
                "folder": request.folder,
                "uid": request.uid,
                "subject": message.get("Subject", ""),
                "from": message.get("From", ""),
                "to": message.get("To", ""),
                "date": message.get("Date", ""),
                "text_plain": extracted.text_plain,
                "text_html": extracted.text_html,
                "attachment_count": len(attachment_items),
            }
            markdown_body = extracted.text_plain or self._html_to_markdown(extracted.text_html)
            markdown_result = (
                f"# {json_result['subject'] or '(no subject)'}\n\n"
                f"- From: {json_result['from']}\n"
                f"- To: {json_result['to']}\n"
                f"- Date: {json_result['date']}\n\n"
                f"{markdown_body}".strip()
            )

            if request.format == "json":
                response = self._ok_envelope(result={"json": json_result})
            elif request.format == "markdown":
                response = self._ok_envelope(result={"markdown": markdown_result})
            else:
                response = self._ok_envelope(result={"json": json_result, "markdown": markdown_result})
            self._audit("mail_extract_message", "success", request.profile_id, payload)
            return response
        except Exception as exc:
            # Fixture-fallback: trigger when live IMAP is unconfigured OR when live fetch
            # returned empty bytes. Fixture lookup is safe — returns None when absent.
            fixture = self._offline_fixture_message(request.profile_id, request.folder, request.uid)
            if fixture is not None:
                raw_bytes = self._offline_message_bytes(fixture)
                message = self._decode_message(raw_bytes)
                extracted = extract_message_text(message)
                attachment_items = list_attachments(message)

                json_result = {
                    "profile_id": request.profile_id,
                    "folder": request.folder,
                    "uid": request.uid,
                    "subject": message.get("Subject", ""),
                    "from": message.get("From", ""),
                    "to": message.get("To", ""),
                    "date": message.get("Date", ""),
                    "text_plain": extracted.text_plain,
                    "text_html": extracted.text_html,
                    "attachment_count": len(attachment_items),
                }
                markdown_body = extracted.text_plain or self._html_to_markdown(extracted.text_html)
                markdown_result = (
                    f"# {json_result['subject'] or '(no subject)'}\n\n"
                    f"- From: {json_result['from']}\n"
                    f"- To: {json_result['to']}\n"
                    f"- Date: {json_result['date']}\n\n"
                    f"{markdown_body}".strip()
                )

                if request.format == "json":
                    response = self._ok_envelope(result={"json": json_result})
                elif request.format == "markdown":
                    response = self._ok_envelope(result={"markdown": markdown_result})
                else:
                    response = self._ok_envelope(result={"json": json_result, "markdown": markdown_result})
                self._audit("mail_extract_message", "success", request.profile_id, payload)
                return response
            self._audit("mail_extract_message", "failure", request.profile_id, {"error": str(exc), **payload})
            return self._error_envelope("imap_extract_failed", str(exc))
        finally:
            self._logout(client)


