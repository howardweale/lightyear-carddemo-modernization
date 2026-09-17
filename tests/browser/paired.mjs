import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const root = fileURLToPath(new URL('../../', import.meta.url));
const server = spawn(process.env.PYTHON || 'python', ['tests/browser/paired_fixture.py'], {cwd:root, env:{...process.env,PYTHONPATH:resolve(root,'src'),PYTHONUTF8:'1'}, stdio:['ignore','pipe','pipe']});
let errors = '';
server.stderr.on('data', data => { errors += data; });
try {
  const config = await new Promise((done,reject) => {
    let data = '';
    const timer = setTimeout(() => reject(new Error('Fixture startup timeout: ' + errors)), 60000);
    server.stdout.on('data', chunk => { data += chunk; if (data.includes('\n')) {clearTimeout(timer); done(JSON.parse(data.split('\n')[0]));} });
    server.once('exit', () => {clearTimeout(timer); reject(new Error('Fixture exited: ' + errors));});
  });
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const pageErrors = []; page.on('pageerror',error => pageErrors.push(error.message));
    await page.goto(`http://127.0.0.1:${config.port}/`);
    await page.waitForFunction(() => [...document.querySelector('#customer-context').options].some(o=>o.value==='cloudbank-reference'));
    await page.locator('#estate-trigger').click();
    await page.locator('#customer-context').selectOption('cloudbank-reference');
    await page.locator('#workflow-campaign').selectOption('oracle26ai-alloydb-number');
    await page.locator('#campaign-controls form').waitFor();
    await page.locator('#campaign-controls input[type=password]').fill(config.credential);
    await page.locator('#campaign-controls textarea').fill('Browser test: explicitly simulated run, no cloud resources.');
    await page.locator('#campaign-controls input[type=checkbox]').check();
    await page.locator('#campaign-controls button[type=submit]').click();
    await page.locator('#run-view').getByText('passed-simulated', {exact:false}).first().waitFor({timeout:60000});
    assert.deepEqual(await page.locator('#run-view .run-figure').allTextContents(), ['20 / 20','20 / 20','20 / 20','20 / 20']);
    assert.match(await page.locator('#run-view').innerText(), /unclassified-or-simulated/);
    assert.match(await page.locator('#workflow-run option:checked').innerText(), /20 equivalent pairs.*passed-simulated/);
    await page.locator('#run-view summary').getByText('Signed campaign authorization', {exact:true}).click();
    assert.match(await page.locator('#run-view').innerText(), /Browser test: explicitly simulated run, no cloud resources/);
    assert.equal((await page.locator('#run-view').innerText()).includes(config.credential), false);
    await page.locator('#run-view summary').getByText('Signed campaign authorization', {exact:true}).click();
    await page.locator('#run-view .paired-case summary').first().click();
    await page.waitForTimeout(3500);
    assert.equal(await page.locator('#run-view .paired-case').first().getAttribute('open'), '');
    await mkdir(resolve(root,'work/browser-inspection'),{recursive:true});
    await page.screenshot({path:resolve(root,'work/browser-inspection/paired-simulated-run.png'),fullPage:true});
    await page.reload();
    await page.waitForFunction(() => [...document.querySelector('#customer-context').options].some(o=>o.value==='cloudbank-reference'));
    await page.locator('#estate-trigger').click();
    await page.locator('#customer-context').selectOption('cloudbank-reference');
    await page.locator('#workflow-campaign').selectOption('oracle26ai-alloydb-number');
    await page.locator('#show-run').click();
    await page.locator('#run-view').getByText('passed-simulated', {exact:false}).first().waitFor();
    await page.locator('#show-convergence').click();
    await page.locator('#convergence').getByText('passed-simulated', {exact:true}).waitFor();
    assert.deepEqual(pageErrors,[]);
  } finally {await browser.close();}
  console.log('PAIRED_BROWSER_SIMULATION=PASSED (no native evidence or cloud operations)');
} finally {server.kill();}
