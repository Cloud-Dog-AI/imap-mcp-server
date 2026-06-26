// Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

const ENDPOINTS = {
  health: { method: "GET", path: "/api/v1/health" },
  tools: { method: "GET", path: "/api/v1/tools" },
  profileList: { method: "GET", path: "/api/v1/admin/profiles" },
  profileGet: { method: "GET", path: "/api/v1/admin/profiles/{profile_id}" },
  profilePut: { method: "PUT", path: "/api/v1/admin/profiles/{profile_id}" },
  profileDelete: { method: "DELETE", path: "/api/v1/admin/profiles/{profile_id}" },
  userList: { method: "GET", path: "/api/v1/admin/users" },
  userGet: { method: "GET", path: "/api/v1/admin/users/{user_id}" },
  userCreate: { method: "POST", path: "/api/v1/admin/users" },
  userUpdate: { method: "PUT", path: "/api/v1/admin/users/{user_id}" },
  userDelete: { method: "DELETE", path: "/api/v1/admin/users/{user_id}" },
  groupList: { method: "GET", path: "/api/v1/admin/groups" },
  groupGet: { method: "GET", path: "/api/v1/admin/groups/{group_id}" },
  groupCreate: { method: "POST", path: "/api/v1/admin/groups" },
  groupUpdate: { method: "PUT", path: "/api/v1/admin/groups/{group_id}" },
  groupDelete: { method: "DELETE", path: "/api/v1/admin/groups/{group_id}" },
  groupAddMember: { method: "POST", path: "/api/v1/admin/groups/{group_id}/members" },
  groupRemoveMember: {
    method: "DELETE",
    path: "/api/v1/admin/groups/{group_id}/members/{user_id}",
  },
  apiKeyList: { method: "GET", path: "/api/v1/admin/api-keys" },
  apiKeyCreate: { method: "POST", path: "/api/v1/admin/api-keys" },
  apiKeyDelete: { method: "DELETE", path: "/api/v1/admin/api-keys/{api_key_id}" },
  rbacGet: { method: "GET", path: "/api/v1/admin/rbac/policies" },
  rbacPut: { method: "PUT", path: "/api/v1/admin/rbac/policies" },
  probe: { method: "POST", path: "/api/v1/tools/mail_probe" },
  audit: { method: "GET", path: "/api/v1/admin/audit/events" },
  archiveExport: { method: "POST", path: "/api/v1/admin/archive/export" },
  search: { method: "POST", path: "/api/v1/tools/mail_search" },
  getMessage: { method: "POST", path: "/api/v1/tools/mail_get_message" },
  extract: { method: "POST", path: "/api/v1/tools/mail_extract_message" },
  listAttachments: { method: "POST", path: "/api/v1/tools/mail_list_attachments" },
  downloadAttachment: { method: "POST", path: "/api/v1/tools/mail_download_attachment" },
  setSeen: { method: "POST", path: "/api/v1/tools/mail_set_seen" },
  moveDuplicates: { method: "POST", path: "/api/v1/tools/mail_move_duplicates_since_last_search" },
  moveMessages: { method: "POST", path: "/api/v1/tools/mail_move_messages" },
  deleteMessages: { method: "POST", path: "/api/v1/tools/mail_delete_messages" },
  a2aTools: { method: "GET", path: "/a2a/tools" },
  a2aCall: { method: "POST", path: "/a2a/tools/{tool_name}" },
  a2aEvents: { method: "WS", path: "/a2a/events" },
};

window.IMAP_WEB_ENDPOINTS = ENDPOINTS;

document.getElementById("endpointMap").textContent = JSON.stringify(ENDPOINTS, null, 2);

function value(id) {
  return document.getElementById(id).value.trim();
}

function apiHeaders() {
  const key = value("apiKey");
  const role = value("role") || "admin";
  const headers = {
    "Content-Type": "application/json",
    "x-api-key": key,
    Authorization: `Bearer ${key}`,
    "x-role": role,
  };
  return headers;
}

function result(payload) {
  document.getElementById("result").textContent = JSON.stringify(payload, null, 2);
}

async function send(path, method = "GET", body = null) {
  const options = { method, headers: apiHeaders() };
  if (body !== null) {
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const text = await response.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (_err) {
    parsed = { raw: text };
  }
  result({ status: response.status, path, method, body, response: parsed });
}

function splitUids() {
  return value("mutUids")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function confirmDestructive(action, scope) {
  return window.confirm(`Confirm ${action}?\n\nAffected scope:\n${scope}`);
}

function profileId() {
  return encodeURIComponent(value("profileId"));
}

function userId() {
  return encodeURIComponent(value("userId"));
}

function groupId() {
  return encodeURIComponent(value("groupId"));
}

function apiKeyId() {
  return encodeURIComponent(value("managedApiKeyId"));
}

function splitCsv(id) {
  return value(id)
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function mailProfile() {
  return value("mailProfile") || "operations";
}

function mailFolder() {
  return value("mailFolder") || "INBOX";
}

function mailUid() {
  return value("mailUid") || "1";
}

document.getElementById("btnHealth").onclick = () => send(ENDPOINTS.health.path);
document.getElementById("btnTools").onclick = () => send(ENDPOINTS.tools.path);
document.getElementById("btnProfileList").onclick = () => send(ENDPOINTS.profileList.path);
document.getElementById("btnProfileGet").onclick = () =>
  send(ENDPOINTS.profileGet.path.replace("{profile_id}", profileId()));
document.getElementById("btnProfilePut").onclick = () =>
  send(
    ENDPOINTS.profilePut.path.replace("{profile_id}", profileId()),
    "PUT",
    JSON.parse(value("profilePayload") || "{}"),
  );
document.getElementById("btnProfileDelete").onclick = () => {
  const scope = `profile=${value("profileId")}`;
  if (!confirmDestructive("delete profile", scope)) {
    return;
  }
  send(ENDPOINTS.profileDelete.path.replace("{profile_id}", profileId()), "DELETE");
};

document.getElementById("btnUserList").onclick = () => send(ENDPOINTS.userList.path);
document.getElementById("btnUserGet").onclick = () =>
  send(ENDPOINTS.userGet.path.replace("{user_id}", userId()));
document.getElementById("btnUserCreate").onclick = () =>
  send(ENDPOINTS.userCreate.path, "POST", {
    user_id: value("userId") || undefined,
    username: value("username"),
    email: value("userEmail"),
    display_name: value("userDisplayName"),
    role: value("userRole") || "viewer",
  });
document.getElementById("btnUserUpdate").onclick = () =>
  send(ENDPOINTS.userUpdate.path.replace("{user_id}", userId()), "PUT", {
    username: value("username"),
    email: value("userEmail"),
    display_name: value("userDisplayName"),
    role: value("userRole") || "viewer",
  });
document.getElementById("btnUserDelete").onclick = () => {
  const scope = `user=${value("userId") || value("username")}`;
  if (!confirmDestructive("delete user", scope)) {
    return;
  }
  send(ENDPOINTS.userDelete.path.replace("{user_id}", userId()), "DELETE");
};

document.getElementById("btnGroupList").onclick = () => send(ENDPOINTS.groupList.path);
document.getElementById("btnGroupGet").onclick = () =>
  send(ENDPOINTS.groupGet.path.replace("{group_id}", groupId()));
document.getElementById("btnGroupCreate").onclick = () =>
  send(ENDPOINTS.groupCreate.path, "POST", {
    group_id: value("groupId") || undefined,
    name: value("groupName"),
    description: value("groupDescription"),
    roles: splitCsv("groupRoles"),
    members: splitCsv("groupMembers"),
  });
document.getElementById("btnGroupUpdate").onclick = () =>
  send(ENDPOINTS.groupUpdate.path.replace("{group_id}", groupId()), "PUT", {
    name: value("groupName"),
    description: value("groupDescription"),
    roles: splitCsv("groupRoles"),
  });
document.getElementById("btnGroupDelete").onclick = () => {
  const scope = `group=${value("groupId") || value("groupName")}`;
  if (!confirmDestructive("delete group", scope)) {
    return;
  }
  send(ENDPOINTS.groupDelete.path.replace("{group_id}", groupId()), "DELETE");
};
document.getElementById("btnGroupAddMember").onclick = () =>
  send(ENDPOINTS.groupAddMember.path.replace("{group_id}", groupId()), "POST", {
    user_id: value("groupMemberUserId"),
  });
document.getElementById("btnGroupRemoveMember").onclick = () =>
  send(
    ENDPOINTS.groupRemoveMember.path
      .replace("{group_id}", groupId())
      .replace("{user_id}", encodeURIComponent(value("groupMemberUserId"))),
    "DELETE",
  );

document.getElementById("btnApiKeyList").onclick = () => send(ENDPOINTS.apiKeyList.path);
document.getElementById("btnApiKeyCreate").onclick = () =>
  send(ENDPOINTS.apiKeyCreate.path, "POST", {
    owner_user_id: value("apiKeyOwner"),
    scopes: splitCsv("apiKeyScopes"),
    description: value("apiKeyDescription"),
    ttl_days: value("apiKeyTtlDays") ? Number(value("apiKeyTtlDays")) : null,
  });
document.getElementById("btnApiKeyRevoke").onclick = () => {
  const scope = `api_key=${value("managedApiKeyId")}`;
  if (!confirmDestructive("revoke api key", scope)) {
    return;
  }
  send(ENDPOINTS.apiKeyDelete.path.replace("{api_key_id}", apiKeyId()), "DELETE");
};

document.getElementById("btnRbacGet").onclick = () => send(ENDPOINTS.rbacGet.path);
document.getElementById("btnRbacPut").onclick = () =>
  send(ENDPOINTS.rbacPut.path, "PUT", JSON.parse(value("rbacPayload") || "{}"));

document.getElementById("btnProbe").onclick = () =>
  send(ENDPOINTS.probe.path, "POST", {
    profile_id: value("probeProfile") || "operations",
    folder: "INBOX",
  });

document.getElementById("btnAudit").onclick = () => {
  const filter = encodeURIComponent(value("auditContains"));
  send(`${ENDPOINTS.audit.path}?limit=100&contains=${filter}`);
};

document.getElementById("btnA2ATools").onclick = () => send(ENDPOINTS.a2aTools.path);
document.getElementById("btnA2AEvents").onclick = () => {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const key = encodeURIComponent(value("apiKey"));
  const socket = new WebSocket(
    `${scheme}://${window.location.host}${ENDPOINTS.a2aEvents.path}?api_key=${key}`,
  );
  socket.onopen = () => result({ status: "connected", path: ENDPOINTS.a2aEvents.path });
  socket.onmessage = (event) => {
    let parsed;
    try {
      parsed = JSON.parse(event.data);
    } catch (_err) {
      parsed = { raw: event.data };
    }
    result({ event: parsed });
  };
  socket.onerror = () => result({ status: "error", path: ENDPOINTS.a2aEvents.path });
};
document.getElementById("btnArchiveExport").onclick = () =>
  send(ENDPOINTS.archiveExport.path, "POST", {
    profile_id: mailProfile(),
    message_id: value("archiveMessageId"),
    raw_eml: `Subject: ${value("archiveSubject")}\n\nWebUI archive export sample.`,
    metadata: { source: "webui" },
    force: true,
  });

document.getElementById("btnSearch").onclick = () =>
  send(ENDPOINTS.search.path, "POST", {
    profile_id: mailProfile(),
    mode: "imap",
    query: value("mailQuery") || "ALL",
    filters: { folder: mailFolder() },
  });

document.getElementById("btnGet").onclick = () =>
  send(ENDPOINTS.getMessage.path, "POST", {
    profile_id: mailProfile(),
    folder: mailFolder(),
    uid: mailUid(),
  });

document.getElementById("btnExtract").onclick = () =>
  send(ENDPOINTS.extract.path, "POST", {
    profile_id: mailProfile(),
    folder: mailFolder(),
    uid: mailUid(),
    format: "both",
  });

document.getElementById("btnListAttachments").onclick = () =>
  send(ENDPOINTS.listAttachments.path, "POST", {
    profile_id: mailProfile(),
    folder: mailFolder(),
    uid: mailUid(),
  });

document.getElementById("btnDownloadAttachment").onclick = () =>
  send(ENDPOINTS.downloadAttachment.path, "POST", {
    profile_id: mailProfile(),
    folder: mailFolder(),
    uid: mailUid(),
    part_id: "2",
  });

document.getElementById("btnSetSeen").onclick = () => {
  const scope = `profile=${mailProfile()} folder=${mailFolder()} uids=${splitUids().join(",")}`;
  if (!confirmDestructive("set seen", scope)) {
    return;
  }
  send(ENDPOINTS.setSeen.path, "POST", {
    profile_id: mailProfile(),
    folder: mailFolder(),
    uids: splitUids(),
    seen: value("mutSeen").toLowerCase() === "true",
  });
};

document.getElementById("btnMoveDuplicates").onclick = () => {
  const scope = `profile=${mailProfile()} folder=${mailFolder()} destination=${value("mutDestFolder")}`;
  if (!confirmDestructive("move duplicates", scope)) {
    return;
  }
  send(ENDPOINTS.moveDuplicates.path, "POST", {
    profile_id: mailProfile(),
    query: value("mailQuery") || "ALL",
    destination_folder: value("mutDestFolder"),
    strategy: "heuristic",
    policy: "newest",
    dry_run: false,
  });
};

document.getElementById("btnMove").onclick = () => {
  const scope = `profile=${mailProfile()} folder=${mailFolder()} destination=${value("mutDestFolder")} uids=${splitUids().join(",")}`;
  if (!confirmDestructive("move messages", scope)) {
    return;
  }
  send(ENDPOINTS.moveMessages.path, "POST", {
    profile_id: mailProfile(),
    folder: mailFolder(),
    destination_folder: value("mutDestFolder"),
    uids: splitUids(),
  });
};

document.getElementById("btnDelete").onclick = () => {
  const scope = `profile=${mailProfile()} folder=${mailFolder()} uids=${splitUids().join(",")}`;
  if (!confirmDestructive("delete messages", scope)) {
    return;
  }
  send(ENDPOINTS.deleteMessages.path, "POST", {
    profile_id: mailProfile(),
    folder: mailFolder(),
    uids: splitUids(),
  });
};
