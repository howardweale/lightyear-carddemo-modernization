import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {fileURLToPath} from "node:url";
import {resolve} from "node:path";
import {mkdir} from "node:fs/promises";
import {createRequire} from "node:module";
const require=createRequire(process.env.PLAYWRIGHT_PACKAGE || import.meta.url);
const {chromium}=require("playwright");
const root=fileURLToPath(new URL("../../",import.meta.url));
const server=spawn(process.env.PYTHON || "python",["-B","tests/browser/factory_console_fixture.py"],{cwd:root,env:{...process.env,PYTHONPATH:[resolve(root,"src"),root].join(process.platform==="win32"?";":":"),PYTHONUTF8:"1"},stdio:["ignore","pipe","pipe"]});
let errors="";server.stderr.on("data",v=>errors+=v);
try{
 const config=await new Promise((done,reject)=>{let data="";const timeout=setTimeout(()=>reject(Error("Fixture startup: "+errors)),30000);server.stdout.on("data",v=>{data+=v;if(data.includes("\n")){clearTimeout(timeout);done(JSON.parse(data.split("\n")[0]));}});server.on("exit",code=>{if(code)reject(Error(errors));});});
 const browser=await chromium.launch({headless:true,...(process.env.FACTORY_BROWSER_EXECUTABLE ? {executablePath:process.env.FACTORY_BROWSER_EXECUTABLE} : {})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}});const pageErrors=[],external=[];
  page.on("pageerror",e=>pageErrors.push(e.message));
  const base="http://127.0.0.1:"+config.port;
  await page.route("**/*",route=>{if(!route.request().url().startsWith(base)){external.push(route.request().url());return route.abort();}return route.continue();});
  await page.goto(base);await page.locator('input[name="credential"]').fill(config.credential);await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await page.getByRole("button",{name:"Programs",exact:true}).click();
  await mkdir(resolve(root,"work/browser-inspection/factory"),{recursive:true});
  for(const program of ["INTCALC","POSTTRAN"]){
   await page.getByRole("button",{name:program,exact:true}).click();
   await page.getByRole("heading",{name:program,exact:true}).waitFor();
   assert.match(await page.locator("#content").innerText(),program==="INTCALC"?/308\/421/:/360\/483/);
   assert.match(await page.locator("#content").innerText(),/Not releasable/);
   await page.screenshot({path:resolve(root,`work/browser-inspection/factory/${program}.png`),fullPage:true});
  }
  assert.deepEqual(pageErrors,[]);assert.deepEqual(external,[]);
  assert.equal(await page.evaluate(()=>Object.keys(localStorage).length),0);
  assert.equal(await page.locator('script:not([src]),style,[style]:not([style=""])').count(),0);
  console.log("Factory Programs screenshots and CSP/browser checks passed.");
 }finally{await browser.close();}
}finally{server.kill();}
