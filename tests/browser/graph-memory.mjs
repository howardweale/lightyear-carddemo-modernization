import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const root=fileURLToPath(new URL("../../",import.meta.url));
const server=spawn(process.env.PYTHON || "python",["tests/browser/graph_memory_fixture.py"],{cwd:root,stdio:["ignore","pipe","pipe"]});
let errors=""; let serverExit=null;
server.stderr.on("data",data=>{errors=(errors+data).slice(-8000);});
server.once("exit",(code,signal)=>{serverExit={code,signal};});
try {
  const config=await new Promise((resolve,reject)=>{
    let text=""; const timer=setTimeout(()=>reject(Error(errors||"Fixture timeout")),30000);
    server.stdout.on("data",data=>{text+=data;if(text.includes("\n")){clearTimeout(timer);resolve(JSON.parse(text.split("\n")[0]));}});
    server.once("exit",()=>{clearTimeout(timer);reject(Error(errors));});
  });
  const browser=await chromium.launch({headless:true});
  const failedRequests=[]; const failedResponses=[]; const pageErrors=[];
  let stage="login";
  try {
    const page=await browser.newPage(); const outside=[];
    page.on("pageerror",e=>pageErrors.push(e.message));
    // Only transport metadata: never headers, bodies, query strings or tokens.
    page.on("requestfailed",r=>{
      if(failedRequests.length<32) failedRequests.push({method:r.method(),
        path:new URL(r.url()).pathname,error:r.failure()?.errorText});
    });
    page.on("response",r=>{
      if(r.status()>=400 && failedResponses.length<32)
        failedResponses.push({path:new URL(r.url()).pathname,status:r.status()});
    });
    page.on("request",r=>{if(!r.url().startsWith(`http://127.0.0.1:${config.port}/`)) outside.push(r.url());});
    await page.goto(`http://127.0.0.1:${config.port}/`);
    await page.locator("#login input").fill(config.credential); await page.locator("#login button").click();
    await page.getByRole("button",{name:"Graph memory",exact:true}).click();
    await page.getByRole("heading",{name:"Annotation health",exact:true}).waitFor();
    stage="overlapping queue responses";
    // Force two queue responses to overlap. One atomic render must win.
    await page.evaluate(async () => {
      clearTimeout(timer);
      const original = api; const pending = [];
      api = async (...args) => {
        const value = await original(...args);
        if (args[0] === "queue") await new Promise(resolve => {
          pending.push(resolve); if (pending.length === 2) pending.forEach(done => done());
        });
        return value;
      };
      try { await Promise.all([knowledge(), knowledge()]); }
      finally { api = original; }
    });
    assert.equal(await page.getByRole("checkbox",{name:"Select "+config.request_id,exact:true}).count(),1);
    stage="review anchors";
    await page.getByRole("button",{name:"Review anchors and evidence"}).click();
    await page.locator("#drawer").getByText(/Use the approved rounding convention/).waitFor();
    assert.equal(await page.locator('#drawer a[href*="node="]').count(),1);
    await page.getByRole("button",{name:"Close",exact:true}).click();
    await page.getByRole("checkbox",{name:"Select "+config.request_id}).check();
    stage="synthetic bulk review";
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
  } catch(error) {
    const fixtureStderr=errors.split(config.credential).join("[REDACTED]");
    console.error("Graph memory failure diagnostics: "+JSON.stringify({stage,
      failedRequests,failedResponses,pageErrors,serverExit,fixtureStderr}));
    throw error;
  } finally {await browser.close();}
} finally {server.kill();}
