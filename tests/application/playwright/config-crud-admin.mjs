// Covers: CFG-08
// Covers: CFG-09
// Covers: CFG-10
// Covers: CFG-11

import assert from 'node:assert/strict';
import { chromium } from 'playwright';

function text(value) {
  return (value || '').trim();
}

async function parseResult(page) {
  const raw = text(await page.locator('#result').textContent());
  return JSON.parse(raw || '{}');
}

async function waitForResult(page, previousText = 'Ready.') {
  await page.waitForFunction((prior) => {
    const node = document.querySelector('#result');
    if (!node || !node.textContent) {
      return false;
    }
    const current = node.textContent.trim();
    return current !== 'Ready.' && current !== prior;
  }, previousText);
  const raw = text(await page.locator('#result').textContent());
  return { raw, payload: JSON.parse(raw || '{}') };
}

const baseUrl = text(process.env.PLAYWRIGHT_BASE_URL) || 'http://127.0.0.1:28987';
const apiKey = text(process.env.PLAYWRIGHT_API_KEY);
if (!apiKey) {
  throw new Error('PLAYWRIGHT_API_KEY is required');
}

const suffix = `${Date.now()}`.slice(-6);
const userId = `pw_user_${suffix}`;
const groupId = `pw_group_${suffix}`;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
page.on('dialog', (dialog) => dialog.accept());
let previousResult = 'Ready.';

try {
  await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
  await page.locator('#apiKey').fill(apiKey);
  await page.locator('#role').fill('admin');

  await page.locator('#userId').fill(userId);
  await page.locator('#username').fill(userId);
  await page.locator('#userEmail').fill(`${userId}@example.com`);
  await page.locator('#userDisplayName').fill('Playwright User');
  await page.locator('#userRole').fill('viewer');
  await page.locator('#btnUserCreate').click();
  let result = await waitForResult(page, previousResult);
  previousResult = result.raw;
  let payload = result.payload;
  assert.equal(payload.status, 200);
  assert.equal(payload.response.result.user_id, userId);

  await page.locator('#btnUserList').click();
  result = await waitForResult(page, previousResult);
  previousResult = result.raw;
  payload = result.payload;
  assert.equal(payload.status, 200);
  assert.ok(JSON.stringify(payload.response).includes(userId));

  await page.locator('#groupId').fill(groupId);
  await page.locator('#groupName').fill(groupId);
  await page.locator('#groupDescription').fill('Playwright Group');
  await page.locator('#groupRoles').fill('admin');
  await page.locator('#groupMembers').fill(userId);
  await page.locator('#btnGroupCreate').click();
  result = await waitForResult(page, previousResult);
  previousResult = result.raw;
  payload = result.payload;
  assert.equal(payload.status, 200);
  assert.equal(payload.response.result.group_id, groupId);

  await page.locator('#apiKeyOwner').fill(userId);
  await page.locator('#apiKeyScopes').fill('profiles:read');
  await page.locator('#apiKeyDescription').fill('Playwright scoped key');
  await page.locator('#btnApiKeyCreate').click();
  result = await waitForResult(page, previousResult);
  previousResult = result.raw;
  payload = result.payload;
  assert.equal(payload.status, 200);
  const managedApiKeyId = payload.response.result.api_key_id;
  assert.ok(payload.response.result.raw_key);

  await page.locator('#managedApiKeyId').fill(managedApiKeyId);
  await page.locator('#btnApiKeyRevoke').click();
  result = await waitForResult(page, previousResult);
  previousResult = result.raw;
  payload = result.payload;
  assert.equal(payload.status, 200);
  assert.equal(payload.response.result.api_key_id, managedApiKeyId);

  await page.locator('#btnGroupDelete').click();
  result = await waitForResult(page, previousResult);
  previousResult = result.raw;
  payload = result.payload;
  assert.equal(payload.status, 200);
  assert.equal(payload.response.result.group_id, groupId);

  await page.locator('#btnUserDelete').click();
  result = await waitForResult(page, previousResult);
  previousResult = result.raw;
  payload = result.payload;
  assert.equal(payload.status, 200);
  assert.equal(payload.response.result.user_id, userId);

  console.log(JSON.stringify({ ok: true, user_id: userId, group_id: groupId }, null, 2));
} finally {
  await page.close();
  await browser.close();
}
