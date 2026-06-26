// PS-WEBUI-STYLE-COMPONENTS WSC-015 axe-core a11y audit for the imap-mcp-server
// WebUI (W28E-1803C). Scans every canonical page with axe-core
// (wcag2a + wcag2aa), EXCLUDING the embedded Swagger UI surface (`.swagger-ui`)
// which is third-party and out of the service's WebUI conformance scope.
//
// Emits an 8-column TSV: page  role  state  violations  violation_ids
//                        screenshot_path  trace_path  verdict
//
// Env:
//   IMAP_WEBUI_BASE_URL   base URL (default http://127.0.0.1:28980)
//   AXE_OUT               output TSV path
//   AXE_SHOT_DIR          screenshot output directory
//   AXE_ENV              environment label (local-docker | preprod)
//   IMAP_WEB_USERNAME / IMAP_WEB_PASSWORD  admin cookie-login creds

import { chromium } from '/opt/iac/Development/cloud-dog-ai/cloud-dog-ai-ui-monorepo/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const AXE_SRC = '/opt/iac/Development/cloud-dog-ai/cloud-dog-ai-ui-monorepo/node_modules/axe-core/axe.min.js';
const baseUrl = String(process.env.IMAP_WEBUI_BASE_URL || 'http://127.0.0.1:28980').replace(/\/$/, '');
const outPath = String(process.env.AXE_OUT || 'axe-a11y-evidence.tsv');
const shotDir = String(process.env.AXE_SHOT_DIR || 'axe-screenshots');
const envLabel = String(process.env.AXE_ENV || 'local-docker');
const adminUser = String(process.env.IMAP_WEB_USERNAME || 'admin');
const adminPass = String(process.env.IMAP_WEB_PASSWORD || 'OrangeRiverTable');
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

// page label -> { route, state }. Login is scanned unauthenticated.
const PAGES = [
  ['Login', '/login', 'anon'],
  ['Dashboard', '/', 'admin'],
  ['Channels', '/profiles', 'admin'],
  ['Mailbox-Workspace', '/mailbox-workspace', 'admin'],
  ['Mailbox', '/search-retrieve', 'admin'],
  ['Audit-Log', '/audit-log', 'admin'],
  ['Admin-Users', '/admin/users', 'admin'],
  ['Admin-Groups', '/admin/groups', 'admin'],
  ['Admin-API-Keys', '/admin/api-keys', 'admin'],
  ['Admin-Roles', '/admin/roles', 'admin'],
  ['Admin-RBAC', '/admin/rbac', 'admin'],
  ['Developer-API-Docs', '/developer/api-docs', 'admin'],
  ['Developer-MCP-Console', '/developer/mcp-console', 'admin'],
  ['Developer-A2A-Console', '/developer/a2a-console', 'admin'],
  ['System-Jobs', '/system/jobs', 'admin'],
  ['System-Settings', '/system/settings', 'admin'],
  ['System-Gmail-Settings', '/system/gmail-settings', 'admin'],
  ['System-About', '/system/about', 'admin'],
];

async function main() {
  const axeSource = await fs.readFile(AXE_SRC, 'utf-8');
  await fs.mkdir(shotDir, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  // Cookie login as admin (shared cookie jar).
  const login = await page.request.post(`${baseUrl}/auth/login`, {
    data: { username: adminUser, password: adminPass },
    headers: { 'content-type': 'application/json' },
  });
  if (!login.ok()) {
    console.error(`axe: admin login failed ${login.status()}`);
    process.exit(2);
  }

  const rows = [];
  let totalViolations = 0;
  for (const [label, route, state] of PAGES) {
    if (state === 'anon') {
      await context.clearCookies();
    }
    await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1800);
    const shot = path.join(shotDir, `axe-${label}-${state}.png`);
    await page.screenshot({ path: shot, fullPage: true }).catch(() => {});
    await page.addScriptTag({ content: axeSource });
    const result = await page.evaluate(async (tags) => {
      // eslint-disable-next-line no-undef
      const r = await axe.run(
        { exclude: [['.swagger-ui']] },
        { runOnly: { type: 'tag', values: tags }, resultTypes: ['violations'] },
      );
      return r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length }));
    }, WCAG_TAGS);
    const count = result.reduce((acc, v) => acc + v.nodes, 0);
    totalViolations += count;
    const ids = result.map((v) => `${v.id}(${v.nodes})`).join(',');
    const verdict = count === 0 ? 'PASS' : 'FAIL';
    rows.push([label, state === 'anon' ? 'anon' : 'admin', state, String(count), ids, shot, '', verdict]);
    if (state === 'anon') {
      // re-establish admin session for the remaining pages
      await page.request.post(`${baseUrl}/auth/login`, {
        data: { username: adminUser, password: adminPass },
        headers: { 'content-type': 'application/json' },
      });
    }
  }
  await browser.close();

  const header = ['page', 'role', 'state', 'violations', 'violation_ids', 'screenshot_path', 'trace_path', 'verdict'];
  await fs.mkdir(path.dirname(outPath), { recursive: true }).catch(() => {});
  await fs.writeFile(outPath, [header, ...rows].map((r) => r.join('\t')).join('\n') + '\n', 'utf-8');
  const fails = rows.filter((r) => r[7] !== 'PASS').length;
  console.log(`axe a11y audit (${envLabel}) ${baseUrl}: ${rows.length - fails}/${rows.length} pages 0-violation, ${totalViolations} total violations -> ${outPath}`);
  process.exit(fails ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(3); });
