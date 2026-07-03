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

# imap-mcp-server — Live IMAP tool verification
# Description: Executes API tool flow against live operations IMAP profile.

set -euo pipefail

set -a
source /path/to/cloud-dog-ai/env-public
set +a

PYTHONPATH=src python3 - <<'PY'
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from fastapi.testclient import TestClient

from imap_hub_server.api_server import create_api_app

req = Request(
    f"{os.environ['VAULT_ADDR']}/v1/{os.environ['VAULT_MOUNT_POINT']}/data/{os.environ['VAULT_CONFIG_PATH']}",
    headers={"X-Vault-Token": os.environ['VAULT_TOKEN']},
)
with urlopen(req, timeout=20) as resp:
    payload = json.loads(resp.read().decode('utf-8'))
content = json.loads(payload['data']['data']['content'])
imap_cfg = content['dev']['email']['imap_operations_cloud_dog_net']

live_env = Path('/tmp/imap-live-tool.env')
live_env.write_text('\n'.join([
    'CA_BUNDLE_PATH=/etc/ssl/certs/ca-certificates.crt',
    'GOOGLE_CLIENT_ID=test-google-client-id',
    'GOOGLE_CLIENT_SECRET=test-google-client-secret',
    'MS_CLIENT_ID=test-ms-client-id',
    'MS_CLIENT_SECRET=test-ms-client-secret',
    f"IMAP_OPERATIONS_HOST={imap_cfg['host']}",
    f"IMAP_OPERATIONS_PORT={imap_cfg['port']}",
    f"IMAP_OPERATIONS_USERNAME={imap_cfg['username']}",
    f"IMAP_OPERATIONS_PASSWORD={imap_cfg['password']}",
]), encoding='utf-8')

app = create_api_app(env_files=[str(live_env)])
client = TestClient(app)
headers = {'x-api-key': app.state.seed_api_key}

search = client.post('/api/v1/tools/mail_search', headers=headers, json={
    'profile_id': 'operations_cloud_dog',
    'mode': 'imap',
    'query': '',
    'filters': {},
})
search.raise_for_status()
search_body = search.json()['result']
assert search_body['ok'] is True
messages = search_body['result']['messages']
print(f"LIVE_TOOL_SEARCH_COUNT={len(messages)}")

if messages:
    uid = messages[-1]['uid']
    msg = client.post('/api/v1/tools/mail_get_message', headers=headers, json={
        'profile_id': 'operations_cloud_dog',
        'uid': uid,
        'folder': 'INBOX',
    })
    msg.raise_for_status()
    msg_body = msg.json()['result']
    assert msg_body['ok'] is True
    print(f"LIVE_TOOL_MESSAGE_UID={uid}")

    att = client.post('/api/v1/tools/mail_list_attachments', headers=headers, json={
        'profile_id': 'operations_cloud_dog',
        'uid': uid,
        'folder': 'INBOX',
    })
    att.raise_for_status()
    att_body = att.json()['result']
    assert att_body['ok'] is True
    print(f"LIVE_TOOL_ATTACHMENT_COUNT={len(att_body['result']['attachments'])}")

live_env.unlink(missing_ok=True)
print('LIVE_TOOL_IMAP_VERIFIED=1')
PY
