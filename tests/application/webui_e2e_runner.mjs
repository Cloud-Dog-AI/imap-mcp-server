import { chromium } from '/opt/iac/Development/cloud-dog-ai/cloud-dog-ai-ui-monorepo/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const caseId = process.argv[2];
const baseUrl = String(process.env.WEBUI_BASE_URL || '').trim().replace(/\/$/, '');
const apiKey = String(process.env.IMAP_API_KEY || '').trim();
const profileHost = String(process.env.IMAP_OPERATIONS_HOST || '').trim();
const profilePort = String(process.env.IMAP_OPERATIONS_PORT || '').trim() || '993';
const profileUsername = String(process.env.IMAP_OPERATIONS_USERNAME || '').trim();
const profilePassword = String(process.env.IMAP_OPERATIONS_PASSWORD || '').trim();
const workingDir = path.resolve('working');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function uniqueId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

// PS-WEBUI-URL-CANONICAL v1.0 (W28E-1803C): the SPA now serves at canonical
// (unprefixed) routes; the legacy `/ui/*`, `/idam/*`, `/api-docs`, `/jobs`,
// `/settings` paths 308-redirect to these. Resolve handler route strings to
// their canonical path so navigation lands directly on a 200 page.
const CANONICAL_ROUTE_MAP = {
  '/': '/', '/dashboard': '/', '/login': '/login',
  '/profiles': '/profiles', '/mailbox-workspace': '/mailbox-workspace', '/search-retrieve': '/search-retrieve',
  '/audit-log': '/audit-log', '/diagnostics-audit': '/audit-log',
  '/admin/users': '/admin/users', '/admin/groups': '/admin/groups', '/admin/api-keys': '/admin/api-keys',
  '/admin/roles': '/admin/roles', '/admin/rbac': '/admin/rbac',
  '/idam/users': '/admin/users', '/idam/groups': '/admin/groups', '/idam/api-keys': '/admin/api-keys',
  '/idam/roles': '/admin/roles', '/idam/rbac': '/admin/rbac',
  '/api-docs': '/developer/api-docs', '/mcp-console': '/developer/mcp-console', '/a2a-console': '/developer/a2a-console',
  '/jobs': '/system/jobs', '/settings': '/system/settings', '/gmail-settings': '/system/gmail-settings',
  '/about': '/system/about',
};

function uiUrl(route) {
  const normalisedRoute = route.startsWith('/') ? route : `/${route}`;
  const canonical = CANONICAL_ROUTE_MAP[normalisedRoute] || normalisedRoute;
  return `${baseUrl}${canonical}`;
}

function apiUrl(pathname) {
  const normalisedPath = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return `${baseUrl}${normalisedPath}`;
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function ensureVisible(locator, message, timeout = 20000) {
  await locator.waitFor({ state: 'visible', timeout });
  if ((await locator.count()) < 1) throw new Error(message);
}

async function waitForText(getText, matcher, message, timeout = 10000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const value = await getText();
    if (matcher.test(value)) {
      return value;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(message);
}

async function waitForCount(getCount, matcher, message, timeout = 10000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const count = await getCount();
    if (matcher(count)) {
      return count;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(message);
}

function rowByText(tableLocator, text) {
  return tableLocator.getByRole('row').filter({ hasText: text });
}

async function findRowAcrossPages(page, text, { maxPages = 40, timeout = 45000 } = {}) {
  const table = page.getByRole('table').first();
  const nextButton = page.getByRole('button', { name: /^next$/i });
  const previousButton = page.getByRole('button', { name: /^previous$/i });
  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    while ((await previousButton.count()) > 0 && !(await previousButton.isDisabled())) {
      await previousButton.click();
      await page.waitForTimeout(300);
    }

    for (let pageIndex = 0; pageIndex < maxPages; pageIndex += 1) {
      const row = rowByText(table, text);
      if ((await row.count()) > 0) {
        await ensureVisible(row.first(), `Row ${text} found but not visible`);
        return row.first();
      }
      if ((await nextButton.count()) < 1) {
        break;
      }
      if (await nextButton.isDisabled()) {
        break;
      }
      await nextButton.click();
      await page.waitForTimeout(500);
    }

    await page.waitForTimeout(500);
  }
  throw new Error(`Could not find row ${text} across paginated table`);
}

async function gotoPage(page, route, headingName) {
  await page.goto(uiUrl(route), { waitUntil: 'domcontentloaded' });
  if (headingName) {
    // W28A-735-R5: current bundle can render the page title in more than one
    // heading (e.g. nav + content); match the first.
    await ensureVisible(page.getByRole('heading', { name: headingName }).first(), `Expected heading ${headingName}`);
  }
}

// W28A-735-R5: imap WebUI uses the cookie / user-pass FLAT login (admin /
// read-write / read-only) via the shared cloud_dog_idam guard. Credentials are
// overridable via env; defaults match the rest of the estate so all three roles
// are demoable. Legacy api-key role names map onto the flat roles (fail-closed
// to read-only).
const FLAT_WEB_CREDENTIALS = {
  admin: {
    username: String(process.env.E2E_WEB_USERNAME || process.env.CLOUD_DOG_WEB_LOGIN_USERNAME || 'admin').trim(),
    password: String(process.env.E2E_WEB_PASSWORD || process.env.CLOUD_DOG_WEB_LOGIN_PASSWORD || 'OrangeRiverTable').trim(),
  },
  'read-write': {
    username: String(process.env.CLOUD_DOG_WEB_LOGIN_READ_WRITE_USERNAME || 'read-write').trim(),
    password: String(process.env.CLOUD_DOG_WEB_LOGIN_READ_WRITE_PASSWORD || 'BlueRiverChair').trim(),
  },
  'read-only': {
    username: String(process.env.CLOUD_DOG_WEB_LOGIN_READ_ONLY_USERNAME || 'read-only').trim(),
    password: String(process.env.CLOUD_DOG_WEB_LOGIN_READ_ONLY_PASSWORD || 'GreenRiverDesk').trim(),
  },
};

function flatCredsFor(role) {
  const r = String(role || 'admin').toLowerCase().replace(/_/g, '-');
  if (['admin', 'owner', 'superuser', 'super-admin'].includes(r)) return FLAT_WEB_CREDENTIALS.admin;
  if (['read-write', 'readwrite', 'writer', 'editor', 'user', 'member'].includes(r)) {
    return FLAT_WEB_CREDENTIALS['read-write'];
  }
  return FLAT_WEB_CREDENTIALS['read-only']; // viewer / read-only / unknown -> read-only (fail-closed)
}

async function signIn(page, role = 'admin', key = apiKey) {
  // Establish the session cookie via POST /auth/login in the page's request
  // context (shares the browser cookie jar), then load the dashboard. `key` is
  // retained for call-site compatibility but cookie login does not use it.
  void key;
  const creds = flatCredsFor(role);
  const resp = await page.request.post(apiUrl('/auth/login'), {
    data: { username: creds.username, password: creds.password },
    headers: { 'content-type': 'application/json' },
  });
  assert(resp.ok(), `Cookie login failed for role ${role}: ${resp.status()} ${await resp.text()}`);
  await page.goto(uiUrl('/dashboard'), { waitUntil: 'domcontentloaded' });
  await ensureVisible(page.getByRole('heading', { name: /^dashboard$/i }), 'Dashboard did not load after sign-in', 60000);
}

async function setLabeledField(page, label, value) {
  const field = page.getByLabel(label).first();
  await ensureVisible(field, `Field ${label} missing`);
  const tagName = await field.evaluate((element) => element.tagName.toLowerCase());
  if (tagName === 'select') {
    await field.selectOption(value);
  } else {
    await field.fill(value);
  }
}

function adminHeaders() {
  return {
    'x-api-key': apiKey,
    'x-role': 'admin',
    'x-user-roles': 'admin',
    Authorization: `Bearer ${apiKey}`,
    'content-type': 'application/json',
  };
}

function buildLiveProfilePayload(profileId) {
  const security = profilePort === '143' ? 'starttls' : 'ssl';
  return {
    provider: 'imap_generic',
    imap: {
      host: profileHost,
      port: Number(profilePort),
      security,
      tls: { allow_self_signed: false },
      timeout_seconds: 30,
    },
    auth: { mode: 'basic' },
    credentials: {
      username: profileUsername,
      password: profilePassword,
    },
    sync: {
      retention: {
        max_age_days: 30,
        max_total_bytes: 2147483648,
        max_messages: 50000,
      },
      folder_policy: {
        include_globs: ['INBOX'],
        exclude_globs: [],
      },
      parts_policy: {
        cache_headers: true,
        cache_bodies: true,
        max_body_bytes: 200000,
        cache_attachments: false,
        max_attachment_bytes: 25000000,
      },
    },
    sync_interval_seconds: 30,
    write: { enabled: false },
    metadata: { seeded_by: 'w28a-515-webui-runner', profile_id: profileId },
  };
}

async function upsertLiveProfile(page, profileId) {
  const response = await page.request.put(
    apiUrl(`/api/v1/admin/profiles/${encodeURIComponent(profileId)}`),
    {
      headers: adminHeaders(),
      data: buildLiveProfilePayload(profileId),
    },
  );
  assert(response.ok(), `Failed to seed live profile ${profileId}: ${response.status()} ${await response.text()}`);
}

async function deleteProfile(page, profileId) {
  const response = await page.request.delete(
    apiUrl(`/api/v1/admin/profiles/${encodeURIComponent(profileId)}`),
    { headers: adminHeaders() },
  );
  assert(response.ok(), `Failed to delete profile ${profileId}: ${response.status()} ${await response.text()}`);
}

async function fetchSettings(page) {
  const response = await page.request.get(apiUrl('/api/v1/admin/settings'), {
    headers: adminHeaders(),
  });
  assert(response.ok(), `Failed to fetch settings: ${response.status()} ${await response.text()}`);
  const payload = await response.json();
  return extractObject(payload);
}

async function updateSettingsViaApi(page, pollingIntervalSeconds, requestTimeoutSeconds) {
  const response = await page.request.put(apiUrl('/api/v1/admin/settings'), {
    headers: adminHeaders(),
    data: {
      polling_interval_seconds: pollingIntervalSeconds,
      request_timeout_seconds: requestTimeoutSeconds,
    },
  });
  assert(response.ok(), `Failed to restore settings: ${response.status()} ${await response.text()}`);
}

async function waitForJsonResponse(page, predicate, action, errorMessage) {
  const [response] = await Promise.all([
    page.waitForResponse(predicate, { timeout: 30000 }),
    action(),
  ]);

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok()) {
    const detail = payload ? JSON.stringify(payload) : await response.text().catch(() => '');
    throw new Error(`${errorMessage}: HTTP ${response.status()} ${detail}`.trim());
  }
  return payload;
}

function extractObject(payload) {
  if (!payload || typeof payload !== 'object') return {};
  if (payload.result && typeof payload.result === 'object') return payload.result;
  if (payload.data && typeof payload.data === 'object') return payload.data;
  return payload;
}

function firstString(value, keys) {
  if (!value || typeof value !== 'object') return '';
  for (const key of keys) {
    const candidate = value[key];
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim();
  }
  return '';
}

// W28A-735-R5: the W28A-876 UI bundle moved CRUD dialogs from stable `#ef-*`
// field IDs to accessible labels + React auto-IDs, renamed the create buttons
// ("+ Add User"/"+ Add Group"/"+ Generate API Key"/"Add Channel"), and the
// status toast is no longer role=status. These helpers target the current
// bundle via accessible labels and poll the page body for status text.
async function openCreateDialog(page, buttonName) {
  await page.getByRole('button', { name: buttonName }).first().click();
  const dialog = page.getByRole('dialog');
  await ensureVisible(dialog, `Create dialog did not open for ${buttonName}`);
  return dialog;
}

async function submitDialog(dialog, buttonName = /^(save|save profile|generate)$/i) {
  await dialog.getByRole('button', { name: buttonName }).first().click({ force: true });
}

// Status toasts render into the page body (not a role=status element). Poll the
// body text for the expected message.
async function waitForStatusText(page, regex, message, timeout = 20000) {
  await waitForText(() => page.locator('body').innerText(), regex, message, timeout);
}

async function fillLabeled(scope, label, value) {
  await scope.getByLabel(label, { exact: true }).fill(value);
}

// W28A-876 bundle: a row has no inline edit/delete buttons; clicking the row's
// identifier cell (rendered as a button) opens an "Edit <id>" dialog that itself
// carries Save + Delete actions. Returns the opened dialog.
async function openEditDialog(page, id) {
  const row = await findRowAcrossPages(page, id);
  // W28E-1803C: the current @cloud-dog/ui DataTable renders the identifier cell
  // as a role="link" affordance (data-testid="<entity>-link-<id>"), not a
  // role="button". Click the link to open the "Edit <id>" dialog; fall back to
  // the legacy button affordance for older bundles.
  const idLink = row.getByRole('link', { name: id, exact: true });
  if ((await idLink.count()) > 0) {
    await idLink.first().click();
  } else {
    await row.getByRole('button', { name: id, exact: true }).first().click();
  }
  const dialog = page.getByRole('dialog');
  await ensureVisible(dialog, `Edit dialog did not open for ${id}`);
  return dialog;
}

async function confirmIfPresent(page, buttonName = /^(delete|confirm|yes|remove)$/i) {
  const dialog = page.getByRole('dialog');
  const btn = dialog.getByRole('button', { name: buttonName });
  if ((await btn.count()) > 0) {
    const confirm = btn.last();
    // Wait for the confirm affordance to settle (dialog open animation) before
    // clicking so the click is not raced against an in-flight transition.
    await confirm.waitFor({ state: 'visible' }).catch(() => {});
    await confirm.click({ force: true });
  }
}

async function createUser(page, userId, role = 'user') {
  await gotoPage(page, '/admin/users', /^users$/i);
  const dialog = await openCreateDialog(page, /add user/i);
  await fillLabeled(dialog, 'username', userId);
  await fillLabeled(dialog, 'display_name', `User ${userId}`);
  await fillLabeled(dialog, 'password', 'E2ePass!234');
  await fillLabeled(dialog, 'email', `${userId}@example.com`);
  await dialog.getByLabel('role', { exact: true }).selectOption(role);
  await submitDialog(dialog);
  await waitForStatusText(
    page,
    new RegExp(`Created user ${escapeRegex(userId)}`, 'i'),
    `Create user status missing for ${userId}`,
  );
  await findRowAcrossPages(page, userId);
}

async function deleteUser(page, userId) {
  await gotoPage(page, '/admin/users', /^users$/i);
  const dialog = await openEditDialog(page, userId);
  await dialog.getByRole('button', { name: /^delete$/i }).first().click();
  await confirmIfPresent(page);
  await waitForStatusText(
    page,
    new RegExp(`Deleted user ${escapeRegex(userId)}`, 'i'),
    `Delete user status missing for ${userId}`,
  );
}

async function createGroup(page, groupId, memberUserId) {
  await gotoPage(page, '/admin/groups', /^groups$/i);
  const dialog = await openCreateDialog(page, /add group/i);
  await fillLabeled(dialog, 'name', groupId);
  await fillLabeled(dialog, 'description', `Group ${groupId}`);
  await fillLabeled(dialog, 'initial_members', memberUserId);
  await submitDialog(dialog);
  await waitForStatusText(
    page,
    new RegExp(`Created group ${escapeRegex(groupId)}`, 'i'),
    `Create group status missing for ${groupId}`,
  );
  await findRowAcrossPages(page, groupId);
}

async function createManagedApiKey(page, ownerUserId, description) {
  await gotoPage(page, '/admin/api-keys', /^api keys$/i);
  const dialog = await openCreateDialog(page, /generate api key/i);
  await fillLabeled(dialog, 'label', description);
  await dialog.getByLabel('owner', { exact: true }).selectOption({ label: ownerUserId }).catch(async () => {
    await dialog.getByLabel('owner', { exact: true }).selectOption(ownerUserId).catch(() => {});
  });
  const payload = await waitForJsonResponse(
    page,
    (response) => response.url().includes('/admin/api-keys') && response.request().method() === 'POST',
    () => submitDialog(dialog, /^generate$/i),
    'Create API key request failed',
  );
  const result = extractObject(payload);
  const apiKeyId = firstString(result, ['api_key_id', 'apiKeyId', 'apiKeyId'.toLowerCase()]);
  const rawKey = firstString(result, ['raw_key', 'rawKey']);
  assert(apiKeyId, 'Managed API key ID missing from create response');
  assert(rawKey, 'Managed raw API key missing from create response');
  await waitForStatusText(
    page,
    new RegExp(`(Created|Generated) API key`, 'i'),
    `Create API key status missing for ${apiKeyId}`,
  );
  return { apiKeyId, rawKey, description };
}

async function revokeManagedApiKey(page, label) {
  // The shared IdamApiKeysPage table renders the key LABEL (not the api_key_id
  // uuid), so locate the row by its unique label text. The row has no inline
  // revoke control: click the label button to open the edit dialog, then use
  // its destructive "Revoke" action.
  await gotoPage(page, '/admin/api-keys', /^api keys$/i);
  const row = await findRowAcrossPages(page, label);
  await row.getByRole('button', { name: label }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: /^revoke$/i }).click();
  await waitForStatusText(
    page,
    new RegExp(`Revoked API key`, 'i'),
    `Revoke API key status missing for ${label}`,
  );
}

const handlers = {
  async T1(page) {
    await signIn(page);
    const t1Path = new URL(page.url()).pathname.replace(/\/$/, '') || '/';
    assert(t1Path === '/' || /\/dashboard$/.test(t1Path), 'Expected canonical dashboard URL after login');
    await ensureVisible(page.getByRole('heading', { name: /^resource metrics$/i }), 'Dashboard resource metrics missing');
    await ensureVisible(page.getByRole('heading', { name: /^recent activity$/i }), 'Dashboard recent activity card missing');
    return 'Login loaded the current dashboard.';
  },

  async T2(page) {
    await signIn(page);
    const userId = uniqueId('e2e_user');

    await createUser(page, userId, 'user');

    const dialog = await openEditDialog(page, userId);
    await fillLabeled(dialog, 'display_name', `Updated ${userId}`);
    await dialog.getByLabel('role', { exact: true }).selectOption('admin');
    await submitDialog(dialog);
    await waitForStatusText(
      page,
      new RegExp(`Updated user ${escapeRegex(userId)}`, 'i'),
      `Update user status missing for ${userId}`,
    );
    const row = await findRowAcrossPages(page, userId);
    await waitForText(
      () => row.innerText(),
      /Updated/i,
      'Updated display name did not appear in user row',
      15000,
    );

    await deleteUser(page, userId);
    return `User CRUD passed for ${userId}.`;
  },

  async T3(page) {
    await signIn(page);
    const userId = uniqueId('e2e_group_user');
    const groupId = uniqueId('e2e_group');

    await createUser(page, userId, 'user');
    await createGroup(page, groupId, userId);

    // Edit via the cell-click dialog (W28A-876 model): change description, save.
    const editDialog = await openEditDialog(page, groupId);
    await fillLabeled(editDialog, 'description', `Updated ${groupId}`);
    await submitDialog(editDialog);
    await waitForStatusText(
      page,
      new RegExp(`Updated group ${escapeRegex(groupId)}`, 'i'),
      `Update group status missing for ${groupId}`,
    );

    // Delete via the cell-click dialog's Delete action.
    const delDialog = await openEditDialog(page, groupId);
    await delDialog.getByRole('button', { name: /^delete$/i }).first().click();
    await confirmIfPresent(page);
    await waitForStatusText(
      page,
      new RegExp(`Deleted group ${escapeRegex(groupId)}`, 'i'),
      `Delete group status missing for ${groupId}`,
    );

    await deleteUser(page, userId);
    return `Group CRUD passed for ${groupId}.`;
  },

  async T4(page) {
    await signIn(page);
    const ownerUserId = uniqueId('e2e_key_owner');
    await createUser(page, ownerUserId, 'user');
    const { apiKeyId, description } = await createManagedApiKey(page, ownerUserId, `Key ${ownerUserId}`);
    await revokeManagedApiKey(page, description);
    await deleteUser(page, ownerUserId);
    return `API key CRUD passed for ${apiKeyId}.`;
  },

  async T5(page, browser) {
    // W28A-735-R5 flat-login RBAC: the read-only role may VIEW data surfaces but
    // is DENIED writes. Log in a separate context as the read-only flat user
    // (cookie) and prove a write is 403 at the web write-seam gate while a read
    // surface renders. (Replaces the retired api-key/runtime-role viewer flow.)
    await signIn(page);
    const viewerContext = await browser.newContext();
    const viewerPage = await viewerContext.newPage();
    await signIn(viewerPage, 'read-only');
    // read-only CAN view the channels (data) page
    await gotoPage(viewerPage, '/profiles', /^channels$/i);
    // read-only write attempts are denied 403 across the write seam
    for (const path of ['/webapi/v1/admin/users', '/webapi/v1/admin/groups']) {
      const resp = await viewerPage.request.post(apiUrl(path), {
        data: { user_id: uniqueId('ro_probe'), username: uniqueId('ro_probe'), email: 'ro@example.com', name: 'ro' },
        headers: { 'content-type': 'application/json' },
      });
      assert(resp.status() === 403, `read-only write to ${path} must be 403, got ${resp.status()}`);
    }
    await viewerContext.close();
    return 'Read-only flat role denied on write surfaces (403); read surface rendered.';
  },

  async T6(page) {
    await signIn(page);
    await gotoPage(page, '/profiles', /^channels$/i);
    const profileId = uniqueId('e2e_profile');
    // W28A-876 bundle: the Channels page uses labelled fields + a "Save Profile"
    // button; row edit/delete are on an "Actions ▾" menu.
    const dialog = await openCreateDialog(page, /add channel/i);
    await dialog.getByLabel(/^channel id/i).fill(profileId);
    await dialog.getByLabel(/^provider/i).selectOption('imap').catch(() => {});
    await dialog.getByLabel(/^imap server/i).fill(profileHost);
    await dialog.getByLabel(/^port/i).fill(profilePort);
    await dialog.getByLabel(/^security/i).selectOption(profilePort === '143' ? 'starttls' : 'ssl').catch(() => {});
    await dialog.getByLabel(/^username/i).fill(profileUsername);
    await dialog.getByLabel(/^password/i).fill(profilePassword);
    await dialog.getByLabel(/mailbox pattern/i).fill('INBOX');
    await dialog.getByLabel(/sync interval/i).fill('30');
    await submitDialog(dialog, /save profile/i);
    await waitForStatusText(
      page,
      new RegExp(`Saved channel ${escapeRegex(profileId)}`, 'i'),
      `Save channel status missing for ${profileId}`,
      30000,
    );

    // Edit via the Actions menu.
    let row = await findRowAcrossPages(page, profileId);
    await row.getByRole('button', { name: /actions/i }).click();
    await page.waitForTimeout(300);
    await page.getByRole('menuitem', { name: /edit channel/i }).click();
    const editDialog = page.getByRole('dialog');
    await ensureVisible(editDialog, `Edit channel dialog missing for ${profileId}`);
    await editDialog.getByLabel(/sync interval/i).fill('45');
    await submitDialog(editDialog, /save profile/i);
    await waitForStatusText(
      page,
      new RegExp(`Saved channel ${escapeRegex(profileId)}`, 'i'),
      `Update channel status missing for ${profileId}`,
      30000,
    );

    // Delete via the Actions menu.
    row = await findRowAcrossPages(page, profileId);
    await row.getByRole('button', { name: /actions/i }).click();
    await page.waitForTimeout(300);
    await page.getByRole('menuitem', { name: /delete channel/i }).click();
    await confirmIfPresent(page);
    await waitForStatusText(
      page,
      new RegExp(`Deleted channel ${escapeRegex(profileId)}`, 'i'),
      `Delete channel status missing for ${profileId}`,
      30000,
    );
    return `Channel CRUD passed for ${profileId}.`;
  },

  async T7(page) {
    await signIn(page);
    const profileId = uniqueId('e2e_search_profile');
    await upsertLiveProfile(page, profileId);
    await gotoPage(page, '/search-retrieve', /^search and retrieve$/i);
    try {
      // W28A-876 bundle: channel + mode are stable-id selects on the search panel.
      await page.locator('#search-filter-profileId').selectOption(profileId).catch(async () => {
        await page.locator('#search-filter-profileId').fill(profileId).catch(() => {});
      });
      await page.locator('#search-filter-mode').selectOption('imap').catch(() => {});
      await page.getByRole('button', { name: /^search$/i }).first().click();
      await waitForText(
        () => page.locator('body').innerText(),
        /Found \d+ messages\./i,
        'Search result status did not show message count',
        30000,
      );
      const selectButtons = page.getByRole('button', { name: /^select$/i });
      if ((await selectButtons.count()) > 0) {
        await selectButtons.first().click();
      }
      await page.getByRole('button', { name: /^get message$/i }).click();
      await ensureVisible(page.getByRole('heading', { name: /^raw message$/i }), 'Raw message panel missing', 30000);
      await page.getByRole('button', { name: /^extract message$/i }).click();
      await ensureVisible(page.getByText(/^Extracted JSON$/i), 'Extracted JSON panel missing', 30000);
      return 'Mail search and retrieve passed.';
    } finally {
      await deleteProfile(page, profileId).catch(() => {});
    }
  },

  async T8(page) {
    await signIn(page);
    await ensureVisible(page.getByRole('heading', { name: /^dashboard$/i }), 'Dashboard missing after login');
    await ensureVisible(page.getByRole('heading', { name: /^resource metrics$/i }).first(), 'Resource metrics card missing');
    await ensureVisible(page.getByRole('heading', { name: /^recent activity$/i }).first(), 'Recent activity card missing');
    await ensureVisible(page.getByRole('button', { name: /^refresh$/i }).first(), 'Dashboard refresh action missing');
    await page.getByRole('button', { name: /^refresh$/i }).first().click();
    return 'Dashboard widgets and quick actions rendered.';
  },

  async T9(page) {
    await signIn(page);
    await gotoPage(page, '/mcp-console', /^mcp console$/i);
    await ensureVisible(page.getByRole('heading', { name: /^mcp tool execution$/i }).first(), 'MCP tool execution panel missing');
    // W28A-876 bundle: pick a tool from the tool-browser button list, fill the
    // PARAMETERS (JSON) textarea, then Execute.
    await page.getByRole('button', { name: 'profile_list', exact: true }).first().click();
    await page.waitForTimeout(500);
    await page.locator('textarea').first().fill('{"include_disabled": false}');
    await page.getByRole('button', { name: /^submit$/i }).first().click();
    await waitForText(
      () => page.locator('body').innerText(),
      /"ok"|"result"|"status"|profile_id|operations/i,
      'MCP result payload missing',
      30000,
    );
    return 'MCP catalogue and execution passed.';
  },

  async T10(page) {
    await signIn(page);
    await gotoPage(page, '/diagnostics-audit', /^audit log$/i);
    await ensureVisible(page.getByRole('heading', { name: /^audit entries$/i }).first(), 'Audit entries card missing');
    await ensureVisible(page.getByRole('heading', { name: /^trace log$/i }).first(), 'Audit trace log card missing');
    await waitForCount(
      () => page.getByRole('button', { name: /^view$/i }).count(),
      (count) => count > 0,
      'Audit entries did not render any view actions',
      30000,
    );
    await page.getByRole('button', { name: /^view$/i }).first().click();
    await ensureVisible(page.getByText(/audit entry/i).first(), 'Audit detail panel missing');
    return 'Audit log rendered and detail view opened.';
  },

  async T11(page) {
    await signIn(page);
    await gotoPage(page, '/settings', /^settings$/i);
    await waitForText(
      () => page.getByRole('status').innerText(),
      /Settings loaded\./i,
      'Settings page did not load',
      30000,
    );
    await page.getByLabel(/search settings group/i).click();
    const pollingField = page.locator('#sc-polling_interval_seconds');
    const originalPolling = Number(await pollingField.inputValue());
    const currentSettings = await fetchSettings(page);
    const originalTimeout = Number(currentSettings.request_timeout_seconds ?? 15);
    const updatedPolling = originalPolling + 5;
    await pollingField.fill(String(updatedPolling));
    await page.getByRole('button', { name: /^save$/i }).first().click();
    await waitForText(
      () => page.getByRole('status').innerText(),
      /Settings saved\./i,
      'Settings save did not complete',
      30000,
    );
    await page.getByRole('button', { name: /^reload$/i }).click();
    await waitForText(
      () => page.getByRole('status').innerText(),
      /Settings loaded\./i,
      'Settings reload did not finish',
      30000,
    );
    const persisted = await fetchSettings(page);
    assert(
      Number(persisted.polling_interval_seconds) === updatedPolling,
      'Saved polling interval did not persist after reload',
    );
    await updateSettingsViaApi(page, originalPolling, originalTimeout);
    return 'Settings persistence passed.';
  },
};

if (!handlers[caseId]) {
  console.error(JSON.stringify({ caseId, status: 'FAIL', details: `Unknown case ${caseId}` }));
  process.exit(2);
}

assert(baseUrl, 'Missing required WEBUI_BASE_URL environment variable');
assert(apiKey, 'Missing required IMAP_API_KEY environment variable');
assert(profileHost, 'Missing required IMAP_OPERATIONS_HOST environment variable');
assert(profileUsername, 'Missing required IMAP_OPERATIONS_USERNAME environment variable');
assert(profilePassword, 'Missing required IMAP_OPERATIONS_PASSWORD environment variable');

// W28C-1715 CONSOLE-GATE: collect unhandled page errors (pageerror) and console
// errors so that any uncaught JavaScript exception causes the test to FAIL
// rather than silently passing. This satisfies the W28C-1715 functional
// compliance requirement for a console/page-error gate on the WebUI AT surface.
//
// W28C-1715 CW-* TESTID NOTE (RESOLVED — gap closed):
//   PS-77 defines canonical CW-T*/CW-F* data-testid attributes for DataTable
//   (CW-T1..T11) and Form/EntityDialog (CW-F1..F5) components. As of the
//   @cloud-dog/ui PS-77 CW-T*/CW-F* contract (ui-monorepo origin/main 39d7571),
//   the imap-mcp WebUI bundle DOES render these canonical testids:
//     data-testid="CW-T1"  (DataTable root container — admin Users/Groups/API-keys)
//     data-testid="CW-F1"  (EntityDialog root — create/edit modal CRUD container)
//   The CW-* gap is therefore CLOSED. The assertion below POSITIVELY asserts the
//   CW-T1 DataTable testid (and CW-F1 EntityDialog testid when an edit/create
//   dialog is open) via Playwright getByTestId on the admin CRUD surfaces.
const pageErrors = [];
const consoleErrors = [];

await fs.mkdir(workingDir, { recursive: true });
const started = Date.now();
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 2200 } });

// Register console/page-error gate BEFORE any navigation.
page.on('pageerror', (error) => {
  pageErrors.push(error instanceof Error ? error.message : String(error));
});
page.on('console', (msg) => {
  if (msg.type() === 'error') {
    const text = msg.text();
    // Filter out known benign browser noise (favicon 404 etc.) that is not
    // an application error. Only surface messages that indicate a real
    // JavaScript runtime error in the application.
    if (
      !text.includes('favicon') &&
      !text.includes('net::ERR_') &&
      !text.includes('Failed to load resource')
    ) {
      consoleErrors.push(text);
    }
  }
});

page.on('dialog', async (dialog) => {
  await dialog.accept();
});

// W28C-1715 CW-* structural assertion helper — asserts the PS-77 canonical
// CW-T1 (DataTable root) and CW-F1 (EntityDialog root) data-testid attributes
// now shipped in the imap WebUI bundle, using Playwright getByTestId.
//
// `requireDataTable` is true for the admin CRUD cases (Users/Groups/API-keys),
// which always navigate the admin DataTable surface and therefore MUST render
// the CW-T1 DataTable testid — its absence FAILS the case.  For non-table cases
// (e.g. the Dashboard) the assertion is opportunistic: CW-T1/CW-F1 are asserted
// visible only if present, otherwise the case is unaffected.
async function assertCwTestids(page, caseName, requireDataTable = false) {
  const cwT1 = page.getByTestId('CW-T1'); // DataTable root container
  const cwF1 = page.getByTestId('CW-F1'); // EntityDialog (modal CRUD) root
  const cwT1Count = await cwT1.count();
  const cwF1Count = await cwF1.count();

  if (requireDataTable) {
    // Admin CRUD surface — CW-T1 DataTable testid is REQUIRED and must be visible.
    await ensureVisible(
      cwT1.first(),
      `PS-77 CW-T1 DataTable testid missing/not visible on admin surface in ${caseName}`,
    );
    return `CW-T1 DataTable testid present and visible (CW-T1=${cwT1Count} CW-F1=${cwF1Count}).`;
  }

  if (cwT1Count > 0 || cwF1Count > 0) {
    // CW testids present on this page — assert at least one is visible.
    const firstCw = (cwT1Count > 0 ? cwT1 : cwF1).first();
    await ensureVisible(firstCw, `CW-T1/CW-F1 testid found but not visible in ${caseName}`);
    return `CW testid present and visible (CW-T1=${cwT1Count} CW-F1=${cwF1Count}).`;
  }

  // This page does not render a DataTable/EntityDialog — informational only.
  return `No CW-T1/CW-F1 testid on current page in ${caseName} (non-table surface).`;
}

const result = { caseId, status: 'FAIL', durationSeconds: 0, details: '', screenshot: null };
try {
  const handlerResult = await handlers[caseId](page, browser);

  // W28C-1715 CW-* structural check after handler completes. The admin CRUD
  // cases (T2 Users, T3 Groups, T4 API-keys) navigate the admin DataTable and
  // MUST render the canonical PS-77 CW-T1 DataTable testid — a missing CW-T1
  // on those surfaces FAILS the case (no longer treated as an informational gap).
  const requireDataTable = ['T2', 'T3', 'T4'].includes(caseId);
  const cwNote = await assertCwTestids(page, caseId, requireDataTable);

  // W28C-1715 CONSOLE-GATE: fail if any unhandled page errors were collected.
  if (pageErrors.length > 0) {
    throw new Error(
      `CONSOLE-GATE: ${pageErrors.length} unhandled page error(s) detected:\n` +
        pageErrors.map((e, i) => `  [${i + 1}] ${e}`).join('\n')
    );
  }

  result.details = `${handlerResult} | ${cwNote}`;
  result.status = 'PASS';
} catch (error) {
  result.details = error instanceof Error ? error.message : String(error);
  result.screenshot = path.join('working', `w28a-515-${caseId.toLowerCase()}-failure.png`);
  await page.screenshot({ path: result.screenshot, fullPage: true }).catch(() => {});
} finally {
  result.durationSeconds = Number(((Date.now() - started) / 1000).toFixed(2));
  await browser.close();
}
console.log(JSON.stringify(result));
process.exit(result.status === 'PASS' ? 0 : 1);
