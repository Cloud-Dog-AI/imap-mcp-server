#!/usr/bin/env bash
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

# imap-mcp-server — Local mail verification
# Description: Verifies live IMAP login/list/search using Vault-managed operations mailbox credentials.

set -euo pipefail

set -a
source /path/to/cloud-dog-ai/env-public
set +a

python3 - <<'PY'
import json
import imaplib
import ssl
from urllib.request import Request, urlopen
import os

req = Request(
    f"{os.environ['VAULT_ADDR']}/v1/{os.environ['VAULT_MOUNT_POINT']}/data/{os.environ['VAULT_CONFIG_PATH']}",
    headers={"X-Vault-Token": os.environ['VAULT_TOKEN']},
)
with urlopen(req, timeout=20) as resp:
    payload = json.loads(resp.read().decode('utf-8'))

content_blob = payload['data']['data']['content']
content = json.loads(content_blob)
imap_cfg = content['dev']['email']['imap_operations_cloud_dog_net']

host = imap_cfg['host']
port = int(imap_cfg['port'])
username = imap_cfg['username']
password = imap_cfg['password']
use_ssl = bool(imap_cfg.get('ssl'))
use_starttls = bool(imap_cfg.get('starttls'))

if use_ssl:
    client = imaplib.IMAP4_SSL(host=host, port=port, timeout=15)
else:
    client = imaplib.IMAP4(host=host, port=port, timeout=15)
    if use_starttls:
        client.starttls(ssl_context=ssl.create_default_context())

typ, _ = client.login(username, password)
if typ != 'OK':
    raise RuntimeError('IMAP login failed')

typ, mailboxes = client.list()
if typ != 'OK':
    raise RuntimeError('IMAP LIST failed')

typ, _ = client.select('INBOX', readonly=True)
if typ != 'OK':
    raise RuntimeError('IMAP SELECT INBOX failed')

typ, ids = client.search(None, 'ALL')
if typ != 'OK':
    raise RuntimeError('IMAP SEARCH failed')
count = len(ids[0].split()) if ids and ids[0] else 0

print('LOCAL_MAIL_VERIFIED=1')
print(f'MAILBOX_COUNT={len(mailboxes or [])}')
print(f'INBOX_MESSAGE_COUNT={count}')

client.logout()
PY
