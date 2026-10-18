import {chromium} from 'playwright';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const fixture=JSON.parse(await readFile(process.env.CARDDEMO_FIXTURE,'utf8'));
const out=process.env.CARDDEMO_BROWSER_OUT;await mkdir(out,{recursive:true});
let previousState;
const browser=await chromium.launch({headless:true});const page=await browser.newPage();let last;const frames=[];
page.on('response',async response=>{if(response.url().endsWith('/api/interaction')&&response.ok())last=await response.json();});
async function compare(){
  await page.waitForFunction(()=>!document.querySelector('#keys').hasAttribute('aria-busy'));
  assert.ok(last?.screen);const frame=last.screen;
  assert.equal(await page.locator('#screen').getAttribute('data-program'),frame.program);
  for(const field of frame.model.fields){if(!field.name)continue;
    const attr=frame.attributes[field.name];
    if(!attr.protected){const input=page.locator(`input[name="${field.name}"]`);assert.equal(await input.inputValue(),frame.values[field.name].trimEnd());assert.equal(await input.getAttribute('maxlength'),String(field.length));assert.equal(await input.getAttribute('type'),attr.hidden?'password':'text');}
    else {const spans=page.locator(`[data-field="${field.name}"]`);assert.equal((await spans.evaluateAll(nodes=>nodes.map(n=>n.dataset.value))).join(''),frame.values[field.name]);}
  }
  if(frame.cursor)assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('name')||document.activeElement?.getAttribute('data-field')),frame.cursor);
  const state=JSON.parse(execFileSync('python',['-B','factory/carddemo-web/runtime/snapshot.py','--out',out+'/database'],{encoding:'utf8'}));
  if(previousState)assert.deepEqual(state.tables,previousState.tables,'Read-only browser journey changed database state');
  previousState=state;frames.push({screen:frame,database_after:state});
}
async function aid(name){const response=page.waitForResponse(r=>r.url().endsWith('/api/interaction'));await page.locator(`[data-aid="${name}"]`).click();const r=await response;assert.equal(r.status(),200);last=await r.json();await compare();}
try{
  const initial=page.waitForResponse(r=>r.url().endsWith('/api/interaction'));await page.goto(process.env.CARDDEMO_URL||'http://127.0.0.1:8080');last=await(await initial).json();await compare();
  await page.locator('[name=USERID]').fill(fixture.user);await page.locator('[name=PASSWD]').fill(fixture.password);await aid('ENTER');assert.equal(last.screen.program,'COMEN01C');
  for(const option of ['1','2','11']){
    await page.locator('[name=OPTION]').fill(option);await aid('ENTER');
    await page.locator(`[name=${option==='11'?'ACCTID':'ACCTSID'}]`).fill(fixture.account);await aid('ENTER');
    if(option==='11'){
      const selection=last.screen.model.fields.find(f=>f.name&&f.length===1&&!last.screen.attributes[f.name].protected);assert.ok(selection);
      await page.locator(`[name=${selection.name}]`).fill('S');await aid('ENTER');assert.equal(last.screen.program,'COPAUS1C');await aid('PF3');
    }
    await aid('PF3');assert.equal(last.screen.program,'COMEN01C');
  }
  await page.screenshot({path:out+'/screen.png',fullPage:true});
  await writeFile(out+'/summary.json',JSON.stringify({passed:true,interactions:frames.length,comparison:'DOM versus service response; not independent COBOL proof'},null,2));
}finally{await writeFile(out+'/frames.json',JSON.stringify(frames,null,2));await browser.close();}
