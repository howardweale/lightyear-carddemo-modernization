/* Browser tests run beside the app in CI; no external preview or relaxed bind. */
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer } from 'node:net';
import { chromium, webkit } from 'playwright';

const root = fileURLToPath(new URL('../../', import.meta.url));
const output = resolve(root, 'work/browser-inspection');
await mkdir(output, { recursive: true });
const env = { ...process.env, PYTHONPATH: resolve(root, 'src') };
const python = process.env.PYTHON || 'python';
const engine = spawnSync(python, ['-m', 'lightyear_workflow.execution', 'run'], { cwd: root, env, encoding: 'utf8', timeout: 120000 });
assert.equal(engine.status, 1, engine.stdout + engine.stderr);
const execution = JSON.parse(engine.stdout);
assert.equal(execution.halt_reason, 'human-decision-required');
assert.equal(execution.summary.action_kinds_executed, 5);
const journal = resolve(root, 'work/workflow/cloudbank/events.sqlite3');
const digest = async () => createHash('sha256').update(await readFile(journal)).digest('hex');
const before = await digest();
const reservation = createServer();
await new Promise((done, reject) => { reservation.once('error', reject); reservation.listen(0, '127.0.0.1', done); });
const port = reservation.address().port;
await new Promise((done) => reservation.close(done));
const server = spawn(python, ['-m', 'lightyear_knowledge_graph', 'serve', '--port', String(port), '--no-browser'], { cwd: root, env, stdio: 'ignore' });
const base = `http://127.0.0.1:${port}`;
const observations = [];
try {
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error('Control Tower server exited before readiness');
    try { if ((await fetch(base + '/api/workflow/execution')).ok) { ready = true; break; } } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  assert(ready, 'Control Tower did not become ready');
  const observedExecution = await (await fetch(base + '/api/workflow/execution')).json();
  assert.equal(observedExecution.source, 'engine-journal');
  for (const [name, driver] of [['chromium', chromium], ['webkit', webkit]]) {
    const browser = await driver.launch({ headless: true });
    try {
      for (const [layout, viewport] of [['desktop', { width: 1440, height: 1050 }], ['mobile', { width: 390, height: 844 }]]) {
        const page = await browser.newPage({ viewport });
        const errors = [], writes = [];
        page.on('pageerror', (error) => errors.push(error.message));
        page.on('request', (request) => { if (request.url().includes('/api/workflow/') && request.method() !== 'GET') writes.push(request.method()); });
        await page.goto(base, { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(() => document.getElementById('execution-status').textContent.includes('Human decision required'), undefined, { timeout: 30000 });
        await page.locator('#convergence').getByText('No completed runs recorded yet.', { exact: false }).waitFor();
        assert.equal((await (await fetch(base + '/api/workflow/convergence')).json()).reason, 'no-runs-recorded');
        assert.equal(await page.locator('.execution-service').count(), 8);
        assert.equal(await page.locator('.execution-action').count(), 6);
        assert.equal(await page.locator('.execution-service .decision-badge.approved').count(), 8);
        assert(await page.locator('img[alt="LIGHTYEAR primary logo"]').evaluate((image) => image.complete && image.naturalWidth > 0));
        await page.screenshot({ path: resolve(output, `${name}-${layout}-overview.png`), fullPage: true });
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        if (overflow) {
          const elements = await page.evaluate(() => [...document.querySelectorAll('body *')].filter((node) => node.getBoundingClientRect().right > window.innerWidth + 1).slice(0, 20).map((node) => ({ tag: node.tagName, id: node.id, classes: node.className, right: node.getBoundingClientRect().right })));
          await writeFile(resolve(output, `${name}-${layout}-overflow.json`), JSON.stringify(elements, null, 2));
        }
        assert.equal(overflow, false, `${name}/${layout} has horizontal overflow`);
        await page.locator('[data-kind="extend-corpus"] > summary').click();
        await page.locator('[data-kind="apply-ledger-entry"] > summary').click();
        assert.match(await page.locator('[data-kind="apply-ledger-entry"]').textContent(), /Human decision required/);
        await page.locator('[data-service="account"] > summary').click();
        await page.locator('#execution-provenance > summary').click();
        const receipt = page.locator('[data-service="account"] .execution-receipt code').first();
        assert.match(await receipt.textContent(), /^[a-f0-9]{64}$/);
        assert((await receipt.boundingBox()).width > 120, 'Receipt text column collapsed');
        await page.screenshot({ path: resolve(output, `${name}-${layout}-receipts.png`), fullPage: true });
        await page.locator('#execution-filter').selectOption('unresolved');
        assert.equal(await page.locator('.execution-service').count(), 0);
        await page.locator('#execution-filter').selectOption('all');
        assert.equal(await page.locator('.execution-service').count(), 8);
        await page.route('**/api/workflow/execution', (route) => route.fulfill({ json: { status: 'invalid', reason: 'Browser test: changed evidence is rejected', items: [] } }));
        await page.locator('#execution-refresh').click();
        await page.waitForFunction(() => document.getElementById('execution-status').textContent.includes('Evidence cannot be verified'));
        assert.equal(await page.locator('.execution-service').count(), 0);
        assert.equal(await page.locator('#execution-provenance').isVisible(), false);
        assert.equal(await page.locator('.execution-action').count(), 0);
        await page.screenshot({ path: resolve(output, `${name}-${layout}-invalid.png`), fullPage: true });
        // Test-only response derived from this test's engine run; never persist an index.
        const completedActions = observedExecution.action_kinds.reduce((sum, kind) => sum + kind.executed, 0);
        await page.route('**/api/workflow/convergence', (route) => route.fulfill({ json: {
          metric_unit: 'action-events', weeks: [{ week: 'test-journal', runs: 1,
            actions_completed: completedActions, awaiting_human: observedExecution.blocks.length,
            blocked_access: 0, blocked_internal: 0 }], storage: null,
        } }));
        await page.evaluate(() => window.LightyearConvergence.reload());
        await page.locator('#convergence .convergence-table').waitFor();
        assert.match(await page.locator('#convergence').innerText(), /Completed actions/);
        assert.match(await page.locator('#convergence').innerText(), /not distinct resolved findings/);
        assert.equal(await page.locator('#convergence .convergence-card').first().locator('.convergence-figure').innerText(), String(completedActions));
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false);
        await page.unroute('**/api/workflow/convergence');
        await page.route('**/api/workflow/convergence', (route) => route.fulfill({ json: { weeks: [], reason: 'invalid-run-index' } }));
        await page.evaluate(() => window.LightyearConvergence.reload());
        await page.locator('#convergence').getByText('Run history is unavailable.', { exact: false }).waitFor();
        assert.equal(await page.locator('#convergence .convergence-card').count(), 0);
        await assert.rejects(readFile(resolve(root, 'control-tower/run-index.sqlite3')), { code: 'ENOENT' });
        assert.deepEqual(writes, []);
        assert.deepEqual(errors, []);
        observations.push({ browser: name, layout, services: 8, action_kinds: 6, executed_kinds: 5, human_approval_gated: true, logo_loaded: true, receipt_column_readable: true, horizontal_overflow: false, filter_and_invalid_state: 'passed', workflow_writes: 0, javascript_errors: [] });
        await page.close();
      }
    } finally { await browser.close(); }
  }
  assert.equal(await digest(), before, 'Browser viewing changed the engine journal');
  await writeFile(resolve(output, 'browser-inspection.json'), JSON.stringify({ status: 'passed', journal_unchanged: true, observations }, null, 2) + '\n');
  console.log('MS72_BROWSER_INSPECTION=PASSED');
} finally {
  server.kill();
}
