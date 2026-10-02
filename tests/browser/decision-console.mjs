import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const root = fileURLToPath(new URL("../../", import.meta.url));
const server = spawn(
  process.env.PYTHON || "python",
  ["tests/browser/decision_console_fixture.py"],
  {
    cwd: root,
    env: { ...process.env, PYTHONPATH: resolve(root, "src"), PYTHONUTF8: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
let errors = "";
server.stderr.on("data", (v) => {
  errors += v;
});
try {
  const config = await new Promise((done, reject) => {
    let data = "";
    const timer = setTimeout(
      () => reject(Error("Fixture startup timeout: " + errors)),
      30000,
    );
    server.stdout.on("data", (v) => {
      data += v;
      if (data.includes("\n")) {
        clearTimeout(timer);
        done(JSON.parse(data.split("\n")[0]));
      }
    });
    server.once("exit", () => {
      clearTimeout(timer);
      reject(Error("Fixture failed: " + errors));
    });
  });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    const pageErrors = [];
    page.on("pageerror", (e) => pageErrors.push(e.message));
    const external = [];
    page.on("request", (r) => {
      if (!r.url().startsWith(`http://127.0.0.1:${config.port}/`))
        external.push(r.url());
    });
    await page.goto(`http://127.0.0.1:${config.port}/`);
    await page.locator("#login input").fill(config.credential);
    await page.locator("#login button").click();
    await page.getByRole("button", { name: "Review campaign" }).click();
    await page
      .getByText("repeated-cause · accounting_cache cohort-01, cohort-03", {
        exact: true,
      })
      .waitFor();
    assert.match(
      await page.locator("#content").innerText(),
      /gate-decline-pattern/,
    );
    await mkdir(resolve(root, "work/browser-inspection"), { recursive: true });
    await page.screenshot({
      path: resolve(
        root,
        "work/browser-inspection/decision-console-campaign.png",
      ),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Work queue", exact: true }).click();
    await page.getByRole("button", { name: "Review and decide" }).click();
    await page
      .locator("#drawer textarea")
      .fill("Browser fixture: operator review only, no engine launch.");
    await page
      .getByRole("button", { name: "Record decision", exact: true })
      .click();
    await page.getByText("Decision recorded", { exact: true }).waitFor();
    assert.match(await page.locator("#drawer").innerText(), /operator-review/);
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await page.getByRole("button", { name: "Catalogue", exact: true }).click();
    await page
      .getByText(
        /Lane Adapter Standard catalogue is not installed|Catalogue adapter not installed/,
      )
      .waitFor();
    await page
      .getByRole("button", { name: "Customer workspace", exact: true })
      .click();
    await page.getByText(/No customer workspace configured/).waitFor();
    assert.equal(
      await page.evaluate(() => Object.keys(localStorage).length),
      0,
    );
    assert.equal(
      (await page.locator("body").innerText()).includes(config.credential),
      false,
    );
    assert.deepEqual(external, []);
    assert.deepEqual(pageErrors, []);
    console.log("Decision console browser flow passed; no external requests.");
  } finally {
    await browser.close();
  }
} finally {
  server.kill();
}
