import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const root = fileURLToPath(new URL("../../", import.meta.url));
const server = spawn(process.env.PYTHON || "python", ["tests/browser/carddemo_zos_fixture.py"], {
  cwd: root, env: { ...process.env, PYTHONPATH: resolve(root, "src"), PYTHONUTF8: "1" },
  stdio: ["pipe", "pipe", "pipe"],
});
let errors = "";
server.stderr.on("data", (v) => { errors += v; });
try {
  const config = await new Promise((done, reject) => {
    let data = "";
    const timer = setTimeout(() => reject(Error("Fixture timeout: " + errors)), 30000);
    server.stdout.on("data", (v) => {
      data += v;
      if (data.includes("\n")) { clearTimeout(timer); done(JSON.parse(data.split("\n")[0])); }
    });
    server.once("exit", () => { clearTimeout(timer); reject(Error("Fixture exited: " + errors)); });
  });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const pageErrors = [], external = [];
    page.on("pageerror", (e) => pageErrors.push(e.message));
    const url = `http://127.0.0.1:${config.port}/`;
    page.on("request", (r) => { if (!r.url().startsWith(url)) external.push(r.url()); });
    await page.goto(url);
    await page.locator("#login input").fill(config.credential);
    await page.locator("#login button").click();
    await page.locator('[data-tab="workspace"]').click();
    await page.getByRole("heading", { name: "CardDemo z/OS arrivals" }).waitFor();
    assert.match(await page.locator("#content").innerText(), /3 runs · 50 files · 0 findings/);
    assert.equal(await page.locator("#content button, #content input").count(), 0);
    const output = resolve(root, "work/carddemo-zos-browser");
    await mkdir(output, { recursive: true });
    await page.screenshot({ path: resolve(output, "arrivals.png"), fullPage: true });
    await page.locator('[data-tab="queue"]').click();
    const item = page.locator("#content article").filter({ hasText: "normalization:" });
    await item.getByRole("button", { name: "Review and decide" }).click();
    assert.equal(await page.locator('#drawer input[readonly]').inputValue(), "howard-weale");
    assert.match(await page.locator("#drawer").innerText(), /hash commitments/);
    assert.deepEqual(pageErrors, []);
    assert.deepEqual(external, []);
    console.log("CardDemo arrival view and Howard review form passed; no decision submitted.");
  } finally { await browser.close(); }
} finally {
  const exit = once(server, "exit");
  server.stdin.end("stop\n");
  await exit;
  if (errors) process.stderr.write(errors);
}
