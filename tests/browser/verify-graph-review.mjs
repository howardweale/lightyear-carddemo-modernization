import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const root=fileURLToPath(new URL("../../",import.meta.url));
const server=spawn(process.env.PYTHON || "python",["tests/browser/verify_graph_review_fixture.py"],{cwd:root,stdio:["ignore","pipe","pipe"]});
let errors=""; server.stderr.on("data",data=>errors+=data);
try {
  const config=await new Promise((resolve,reject)=>{
    let text=""; const timer=setTimeout(()=>reject(Error(errors||"Fixture timeout")),60000);
    server.stdout.on("data",data=>{text+=data;if(text.includes("\n")){clearTimeout(timer);resolve(JSON.parse(text.split("\n")[0]));}});
    server.once("exit",()=>{clearTimeout(timer);reject(Error(errors));});
  });
  const browser=await chromium.launch({headless:true});
  try {
    for (const width of [1280,390]) {
      const page=await browser.newPage({viewport:{width,height:900}});
      const pageErrors=[]; page.on("pageerror",e=>pageErrors.push(e.message));
      await page.goto(`http://127.0.0.1:${config.port}/`);
      await page.locator("#login input").fill(config.credential); await page.locator("#login button").click();
      await page.getByRole("button",{name:"Work queue",exact:true}).click();
      await page.getByRole("button",{name:"Review and decide",exact:true}).click();
      await page.getByRole("heading",{name:"Public graph projection review"}).waitFor();
      await page.getByText(/Expiry is 00:00 UTC/).waitFor();
      assert.equal(await page.locator('#drawer code').filter({hasText:config.acknowledgment}).count(),1);
      await page.locator('#drawer textarea').fill("Reviewed without the required acknowledgment");
      await page.locator('#drawer input').nth(0).fill("Test reviewer");
      await page.locator('#drawer input[type=date]').fill(new Date(Date.now()+86400000*7).toISOString().slice(0,10));
      await page.getByRole("button",{name:"Record decision",exact:true}).click();
      await page.locator('#message').getByText(/Acknowledge every/).waitFor();
      await page.locator('#drawer textarea').fill("Reviewed public source " + config.acknowledgment);
      await page.getByRole("button",{name:"Record decision",exact:true}).click();
      await page.getByRole("heading",{name:"Decision recorded",exact:true}).waitFor();
      assert.deepEqual(pageErrors,[]);
      await page.close();
    }
    console.log("Desktop/mobile graph review: public-only scope, UTC expiry, refused missing acknowledgment, signed test approval. Zero models.");
  } finally {await browser.close();}
} finally {server.kill();}
