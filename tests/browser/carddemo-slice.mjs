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
    const nodes=page.locator(attr.protected?`[data-field="${field.name}"]`:`input[name="${field.name}"]`);
    assert.equal(await nodes.count(),attr.protected?Math.ceil(((field.data_offset%frame.model.columns)+field.length)/frame.model.columns):1);
    const bright=attr.intensity==='BRIGHT'||(!attr.intensity&&field.attributes.includes('BRT'));
    const color=attr.color==='DEFAULT'?(attr.protected?(bright?'NEUTRAL':'BLUE'):(bright?'RED':'GREEN')):attr.color;
    const rgb={BLUE:'rgb(109, 170, 255)',RED:'rgb(255, 115, 115)',GREEN:'rgb(116, 229, 154)',YELLOW:'rgb(255, 227, 130)',TURQUOISE:'rgb(105, 219, 223)',PINK:'rgb(237, 159, 230)',NEUTRAL:'rgb(238, 238, 238)'};
    assert.ok(rgb[color],'Unknown BMS color');
    for(const node of await nodes.all()){
      assert.equal(await node.evaluate(n=>getComputedStyle(n).color),rgb[color],field.name+' color');
      assert.equal(await node.evaluate(n=>n.classList.contains('bright')),bright,field.name+' intensity');
      for(const [highlight,css] of [['UNDERLINE','underline'],['REVERSE','reverse'],['BLINK','blink']])assert.equal(await node.evaluate((n,c)=>n.classList.contains(c),css),attr.highlight===highlight,field.name+' '+highlight);
      if(attr.protected&&attr.hidden)assert.equal((await node.textContent()).trim(),'');
    }
    if(!attr.protected){const input=page.locator(`input[name="${field.name}"]`);assert.equal(await input.inputValue(),frame.values[field.name].trimEnd());assert.equal(await input.getAttribute('maxlength'),String(field.length));assert.equal(await input.getAttribute('type'),attr.hidden?'password':'text');}
    else {const spans=page.locator(`[data-field="${field.name}"]`);assert.equal((await spans.evaluateAll(nodes=>nodes.map(n=>n.dataset.value))).join(''),frame.values[field.name]);}
  }
  assert.equal(await page.locator('#status').textContent(),frame.endpoint?'This option is not in slice 1.':frame.message);
  if(frame.cursor)assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('name')||document.activeElement?.getAttribute('data-field')),frame.cursor);
  const state=JSON.parse(execFileSync('python',['-B','factory/carddemo-web/runtime/snapshot.py','--out',out+'/database'],{encoding:'utf8'}));
  if(previousState)assert.deepEqual(state.tables,previousState.tables,'Read-only browser journey changed database state');
  previousState=state;frames.push({screen:frame,database_after:state});
}
async function aid(name){const response=page.waitForResponse(r=>r.url().endsWith('/api/interaction'));await page.locator(`[data-aid="${name}"]`).click();const r=await response;assert.equal(r.status(),200);last=await r.json();await compare();}
try{
  if(process.env.CARDDEMO_REFERENCE_SIGNON){
    const cases=JSON.parse(await readFile(process.env.CARDDEMO_REFERENCE_SIGNON,'utf8'));assert.ok(cases.length);
    for(const scenario of cases){
      const opened=page.waitForResponse(r=>r.url().endsWith('/api/interaction'));
      await page.goto(process.env.CARDDEMO_URL||'http://127.0.0.1:8080');last=await(await opened).json();await compare();
      if(scenario.login){
        for(const part of ['values','attributes','cursor','message'])assert.deepEqual(last.screen[part],scenario.signon.screen[part],scenario.id+' signon '+part);
        for(const [name,value] of Object.entries(scenario.login))await page.locator(`[name="${name}"]`).fill(value.trimEnd());
        await aid('ENTER');
      }
      for(const part of ['values','attributes','cursor','message'])assert.deepEqual(last.screen[part],scenario.initial.screen[part],scenario.id+' initial '+part);
      for(const [name,value] of Object.entries(scenario.fields))await page.locator(`[name="${name}"]`).fill(value.trimEnd());
      await aid(scenario.aid);
      for(const part of ['values','attributes','cursor','message'])assert.deepEqual(last.screen[part],scenario.expected.screen[part],scenario.id+' '+part);
    }
  }
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
  await writeFile(out+'/summary.json',JSON.stringify({passed:true,interactions:frames.length,comparison:'DOM versus service response for six-screen smoke; raw-COBOL sign-on and menu cases compared separately',independent_programs_compared:process.env.CARDDEMO_REFERENCE_SIGNON?['COSGN00C','COMEN01C']:[],required_programs:6,full_slice_screen_equivalence:false},null,2));
}finally{await writeFile(out+'/frames.json',JSON.stringify(frames,null,2));await browser.close();}
