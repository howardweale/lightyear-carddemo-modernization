import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const root = fileURLToPath(new URL("../../", import.meta.url));
const server = spawn(process.env.PYTHON || "python", ["tests/browser/b06_fixture.py"], {
  cwd: root, env: { ...process.env, PYTHONPATH: resolve(root, "src"), PYTHONUTF8: "1" },
  stdio: ["pipe", "pipe", "pipe"],
});
let errors = "";
server.stderr.on("data", v => { errors += v; });
try {
  const config = await new Promise((done, reject) => {
    let data = "";
    const timer = setTimeout(() => reject(Error("B06 fixture timeout: " + errors)), 30000);
    server.stdout.on("data", v => {
      data += v;
      if (data.includes("\n")) { clearTimeout(timer); done(JSON.parse(data.split("\n")[0])); }
    });
    server.once("exit", () => { clearTimeout(timer); reject(Error("B06 fixture exited: " + errors)); });
  });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const pageErrors = [], external = [];
    page.on("pageerror", e => pageErrors.push(e.message));
    const url = `http://127.0.0.1:${config.port}/`;
    page.on("request", r => { if (!r.url().startsWith(url)) external.push(r.url()); });
    await page.goto(url);
    await page.locator("#login input").fill(config.credential);
    await page.locator("#login button").click();
    await page.getByRole("button", { name: "Review campaign" }).click();
    await page.getByText("FIXTURE — zero-model integration rehearsal; not a measured B06 result.", { exact: true }).waitFor();
    const content = await page.locator("#content").innerText();
    assert.match(content, /FIXTURE/);
    assert.match(content, /J1: 1\/1/); assert.match(content, /J2: 1\/1/); assert.match(content, /J3: 1\/1/);
    assert.match(content, /equipment-suspect/); assert.match(content, /Latest launch/);
    assert.match(content, /B06 controller consumes verified/);
    assert.doesNotMatch(content, /this controller does not read/);
    const out = resolve(root, "work/browser-inspection"); await mkdir(out, { recursive: true });
    await page.screenshot({ path: resolve(out, "b06-cockpit.png"), fullPage: true });
    await page.locator('[data-tab="queue"]').click();
    const item = page.locator("#content article").filter({ hasText: "b06-pause" });
    await item.getByRole("button", { name: "Review and decide" }).click();
    await page.locator("#drawer select").waitFor({ state: "visible" });
    const options = await page.locator("#drawer select option").allTextContents();
    assert.deepEqual(options, ["continue", "stop", "void"]);
    assert.match(await page.locator("#drawer").innerText(), /pause/);
    assert.deepEqual(pageErrors, []); assert.deepEqual(external, []);
    console.log("B06 fixture cockpit and pause review passed; no decision submitted by browser.");
  } finally { await browser.close(); }
} finally {
  const ended = once(server,"exit"); server.stdin.end("stop\n"); await ended;
  if (errors) process.stderr.write(errors);
}
