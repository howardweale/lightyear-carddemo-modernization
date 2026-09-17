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
const historyIndex = resolve(root, 'control-tower/run-index.sqlite3');
const indexBefore = await readFile(historyIndex);
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
  const observedHistory = await (await fetch(base + '/api/workflow/convergence')).json();
  assert.equal(observedHistory.metric_unit, 'action-events');
  assert(observedHistory.storage.runs >= 1, 'The terminal engine run was not recorded');
  const completedActions = observedExecution.action_kinds.reduce((sum, kind) => sum + kind.executed, 0);
  assert(observedHistory.weeks.reduce((sum, week) => sum + week.actions_completed, 0) >= completedActions);
  const latestWeek = observedHistory.weeks.at(-1);
  for (const [name, driver] of [['chromium', chromium], ['webkit', webkit]]) {
    const browser = await driver.launch({ headless: true });
    try {
      for (const [layout, viewport] of [['desktop', { width: 1440, height: 1050 }], ['mobile', { width: 390, height: 844 }]]) {
        const page = await browser.newPage({ viewport });
        const errors = [], writes = [];
        page.on('pageerror', (error) => errors.push(error.message));
        page.on('request', (request) => { if (request.url().includes('/api/workflow/') && request.method() !== 'GET') writes.push(request.method()); });
        await page.goto(base, { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(() => [...document.getElementById('customer-context').options].some(o => o.value === 'cloudbank-reference'));
        await page.locator('#estate-trigger').click();
        await page.locator('#customer-context').selectOption('cloudbank-reference');
        if (await page.locator('#close-estate').isVisible()) await page.locator('#close-estate').click();
        await page.waitForFunction(() => document.getElementById('execution-status').textContent.includes('Human decision required'), undefined, { timeout: 30000 });
        assert.equal(await page.locator('#show-queue').getAttribute('aria-pressed'), 'true');
        for (const panel of ['queue', 'run', 'convergence', 'discovery']) {
          assert.equal(await page.locator(`#show-${panel}`).isVisible(), true);
        }
        await page.locator('#workflow-campaign').selectOption('oracle26ai-alloydb-number');
        await page.locator('#campaign-view h2').waitFor();
        assert.deepEqual(await page.locator('#campaign-view .campaign-card strong').allTextContents(), ['20', '20', 'Not recorded', 'Not recorded']);
        assert.equal(await page.locator('#cloudbank-execution').isVisible(), false);
        assert.equal(await page.locator('#operator-sign-in').isEnabled(), false);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false);
        await page.screenshot({ path: resolve(output, `${name}-${layout}-campaign.png`), fullPage: true });
        await page.locator('#show-run').click();
        await page.locator('#run-view').getByText('Not run.', { exact: false }).waitFor();
        assert.equal(await page.locator('#run-view .run-figure').count(), 0);
        await page.locator('#show-convergence').click();
        await page.locator('#convergence').getByText('NUMBER campaign has no indexed runs.', { exact: false }).waitFor();
        assert.equal(await page.locator('#convergence .convergence-card').count(), 0);
        await page.locator('#workflow-campaign').selectOption('retained');
        await page.locator('#show-run').click();
        await page.locator('#run-view .run-figure').first().waitFor();
        assert.deepEqual(await page.locator('#run-view .run-figure').allTextContents(), ['19', '6', '1', '0']);
        assert.deepEqual(await page.locator('#run-view .run-step h3').allTextContents(),
          ['Round 1', 'Round 2', 'Round 3', 'Round 4', 'Round 5', 'Round 6', 'Blocked · apply-ledger-entry', 'Run halted']);
        assert.match(await page.locator('#run-view .run-step').first().innerText(), /8 × widen-observation/);
        assert.match(await page.locator('#run-view .run-step').nth(1).innerText(), /8 × escalate-lane/);
        assert.match(await page.locator('#run-view').innerText(), /unobserved → contract-verified/);
        assert.match(await page.locator('#run-view').innerText(), /contract-verified → retained-evidence-verified/);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false);
        await page.screenshot({ path: resolve(output, `${name}-${layout}-run.png`), fullPage: true });
        await page.locator('#run-view').getByRole('button', { name: 'Go to the decision' }).click();
        assert.equal(await page.locator('#decision-workspace').isVisible(), true);
        assert.equal(await page.locator('#show-queue').getAttribute('aria-pressed'), 'true');
        await page.locator('#show-convergence').click();
        await page.locator('#convergence .convergence-table').waitFor();
        assert.deepEqual(await page.locator('#convergence .convergence-figure').allTextContents(),
          [latestWeek.actions_completed, latestWeek.awaiting_human, latestWeek.blocked_access, latestWeek.blocked_internal].map(String));
        assert.match(await page.locator('#convergence').innerText(), /Runs recorded/);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false);
        await page.screenshot({ path: resolve(output, `${name}-${layout}-history.png`), fullPage: true });
        await page.locator('#show-queue').click();
        assert.deepEqual(await (await fetch(base + '/api/workflow/convergence')).json(), observedHistory);
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
        await page.route('**/api/workflow/execution?**', (route) => route.fulfill({ json: { status: 'invalid', reason: 'Browser test: changed evidence is rejected', items: [] } }));
        await page.locator('#execution-refresh').click();
        await page.waitForFunction(() => document.getElementById('execution-status').textContent.includes('Evidence cannot be verified'));
        assert.equal(await page.locator('.execution-service').count(), 0);
        assert.equal(await page.locator('#execution-provenance').isVisible(), false);
        assert.equal(await page.locator('.execution-action').count(), 0);
        await page.screenshot({ path: resolve(output, `${name}-${layout}-invalid.png`), fullPage: true });
        await page.locator('#show-run').click();
        await page.locator('#run-view').getByText('The run is unavailable.', { exact: false }).waitFor();
        assert.equal(await page.locator('#run-view .run-figure').count(), 0);
        await page.unroute('**/api/workflow/execution?**');
        await page.route('**/api/workflow/execution?**', (route) => route.fulfill({ json: { status: 'unavailable', items: [] } }));
        await page.evaluate(() => window.LightyearRun.reload());
        await page.locator('#run-view').getByText('No run recorded yet.', { exact: false }).waitFor();
        assert.equal(await page.locator('#run-view .run-figure').count(), 0);
        await page.unroute('**/api/workflow/execution?**');
        await page.locator('#show-convergence').click();
        // Empty and invalid API states remain covered without altering the real index.
        await page.route('**/api/workflow/convergence?**', (route) => route.fulfill({ json: { weeks: [], reason: 'no-runs-recorded' } }));
        await page.evaluate(() => window.LightyearConvergence.reload());
        await page.locator('#convergence').getByText('No completed runs recorded yet.', { exact: false }).waitFor();
        assert.equal(await page.locator('#convergence .convergence-card').count(), 0);
        await page.unroute('**/api/workflow/convergence?**');
        await page.evaluate(() => window.LightyearConvergence.reload());
        await page.locator('#convergence .convergence-table').waitFor();
        assert.match(await page.locator('#convergence').innerText(), /not distinct resolved findings/);
        assert.equal(await page.locator('#convergence .convergence-card').first().locator('.convergence-figure').innerText(), String(latestWeek.actions_completed));
        await page.route('**/api/workflow/convergence?**', (route) => route.fulfill({ json: { weeks: [], reason: 'invalid-run-index' } }));
        await page.evaluate(() => window.LightyearConvergence.reload());
        await page.locator('#convergence').getByText('Run history is unavailable.', { exact: false }).waitFor();
        assert.equal(await page.locator('#convergence .convergence-card').count(), 0);
        assert.deepEqual(await readFile(historyIndex), indexBefore, 'Browser viewing changed the history index');
        // A hidden graph must be fitted only after the Discovery workspace is visible.
        await page.evaluate(() => {
          window.ms75Fits = [];
          const fit = window.fitGraph;
          window.fitGraph = () => {
            const graph = document.getElementById('graph');
            window.ms75Fits.push({ visible: !document.getElementById('discovery-workspace').hidden,
              width: graph.clientWidth, height: graph.clientHeight });
            fit();
          };
        });
        await page.locator('#show-discovery').click();
        await page.waitForFunction(() => window.ms75Fits.some((fit) => fit.visible && fit.width > 0 && fit.height > 0));
        await page.evaluate(() => window.controlTowerDecisions.showQueue());
        assert.equal(await page.locator('#decision-workspace').isVisible(), true);
        assert.equal(await page.locator('#show-queue').getAttribute('aria-pressed'), 'true');
        await page.evaluate(() => window.controlTowerDecisions.showQueue(false));
        await page.waitForFunction(() => window.ms75Fits.filter((fit) => fit.visible && fit.width > 0 && fit.height > 0).length >= 2);
        await page.evaluate(() => window.controlTowerDecisions.showPanel('invalid-panel'));
        assert.equal(await page.locator('#decision-workspace').isVisible(), true);
        assert.deepEqual(writes, []);
        assert.deepEqual(errors, []);
        observations.push({ browser: name, layout, services: 8, action_kinds: 6, executed_kinds: 5, human_approval_gated: true, logo_loaded: true, receipt_column_readable: true, horizontal_overflow: false, filter_and_invalid_state: 'passed', workflow_writes: 0, javascript_errors: [] });
        await page.close();
      }
    } finally { await browser.close(); }
  }
  assert.equal(await digest(), before, 'Browser viewing changed the engine journal');
  await writeFile(resolve(output, 'browser-inspection.json'), JSON.stringify({ status: 'passed', journal_unchanged: true, history_index_unchanged: true, history: observedHistory, observations }, null, 2) + '\n');
  console.log('MS72_BROWSER_INSPECTION=PASSED');
} finally {
  server.kill();
}
