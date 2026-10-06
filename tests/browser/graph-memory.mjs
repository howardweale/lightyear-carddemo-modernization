import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const root=fileURLToPath(new URL("../../",import.meta.url));
const server=spawn(process.env.PYTHON || "python",["tests/browser/graph_memory_fixture.py"],{cwd:root,stdio:["ignore","pipe","pipe"]});
let errors=""; server.stderr.on("data",data=>errors+=data);
try {
  const config=await new Promise((resolve,reject)=>{
    let text=""; const timer=setTimeout(()=>reject(Error(errors||"Fixture timeout")),30000);
    server.stdout.on("data",data=>{text+=data;if(text.includes("\n")){clearTimeout(timer);resolve(JSON.parse(text.split("\n")[0]));}});
    server.once("exit",()=>{clearTimeout(timer);reject(Error(errors));});
  });
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage(); const pageErrors=[]; const outside=[];
    page.on("pageerror",e=>pageErrors.push(e.message));
    page.on("request",r=>{if(!r.url().startsWith(`http://127.0.0.1:${config.port}/`)) outside.push(r.url());});
    await page.goto(`http://127.0.0.1:${config.port}/`);
    await page.locator("#login input").fill(config.credential); await page.locator("#login button").click();
    await page.getByRole("button",{name:"Graph memory",exact:true}).click();
    await page.getByRole("heading",{name:"Annotation health",exact:true}).waitFor();
    await page.getByRole("button",{name:"Review anchors and evidence"}).click();
    await page.locator("#drawer").getByText(/Use the approved rounding convention/).waitFor();
    assert.equal(await page.locator('#drawer a[href*="node="]').count(),1);
    await page.getByRole("button",{name:"Close",exact:true}).click();
    await page.getByRole("checkbox",{name:"Select "+config.request_id}).check();
    await page.getByRole("button",{name:"Review selected decisions"}).click();
    await page.locator('#drawer input').nth(0).fill("Synthetic browser review");
    await page.locator('#drawer input').nth(1).fill("Howard");
    const expiry=new Date(Date.now()+86400000*5).toISOString().slice(0,10);
    await page.locator('#drawer input').nth(2).fill(expiry);
    await page.getByRole("button",{name:"Record selected decisions"}).click();
    await page.locator('#drawer').waitFor({state:"hidden"});
    assert.deepEqual(pageErrors,[]); assert.deepEqual(outside,[]);
    assert.equal(await page.locator('#message').innerText(),"");
    console.log("Graph memory health, safe review, graph links and bulk signed decision passed; no external requests.");
  } finally {await browser.close();}
} finally {server.kill();}
