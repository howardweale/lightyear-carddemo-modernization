import {chromium} from 'playwright';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {dirname,resolve} from 'node:path';
async function expectedDatabase(row){
 const ref=row.database_file;assert.match(ref?.sha256??'',/^[0-9a-f]{64}$/);
 assert.equal(ref.path,'expected-database/'+ref.sha256+'.json');
 const bytes=await readFile(resolve(dirname(process.env.CARDDEMO_CASES),ref.path));
 assert.equal(createHash('sha256').update(bytes).digest('hex'),ref.sha256,'reference database hash');
 return JSON.parse(bytes.toString('utf8'));
}
const cases=JSON.parse(await readFile(process.env.CARDDEMO_CASES,'utf8'));
const out=process.env.CARDDEMO_BROWSER_OUT;await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true});const pages=new Map();const frames=[];
const remaining=new Map();for(const row of cases)remaining.set(row.session,(remaining.get(row.session)||0)+1);
let page,last,passed=false;
function attrs(frame){return Object.fromEntries(Object.entries(frame.attributes).map(([k,a])=>[k,{...a,intensity:a.intensity??(a.basic.includes('BRT')?'BRIGHT':a.hidden?'DARK':'NORMAL'),autoskip:a.autoskip??a.basic.includes('ASKIP')}]))}
function canonical(value){
 if(typeof value==='number')return {$number:String(value)};
 if(Array.isArray(value))return value.map(canonical);
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).sort().map(([k,v])=>[k,canonical(v)]));
 return value;
}
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
}

try{
 assert.ok(cases.length,'empty full-slice scenario set');
 for(const row of cases){
  if(row.aid==='INITIAL'){
   assert.ok(!pages.has(row.session),'duplicate session initial');page=await browser.newPage();pages.set(row.session,page);
   const pending=page.waitForResponse(r=>r.url().endsWith('/api/interaction'));
   await page.goto(process.env.CARDDEMO_URL||'http://127.0.0.1:8080');const response=await pending;assert.equal(response.status(),200);last=await response.json();
  }else{
   page=pages.get(row.session);assert.ok(page,'session missing');
   for(const input of await page.locator('#screen input').all())await input.fill('');
   for(const [name,value] of Object.entries(row.fields))await page.locator(`input[name="${name}"]`).fill(value.trimEnd());
   const pending=page.waitForResponse(r=>r.url().endsWith('/api/interaction'));
   // Exercise both PF buttons and keyboard shortcuts across the same source sessions.
   if(row.aid.startsWith('PF')&&frames.length%2){const n=Number(row.aid.slice(2));await page.keyboard.press((n>12?'Shift+':'')+'F'+(n>12?n-12:n));}
   else await page.locator(`[data-aid="${row.aid}"]`).click();
   const response=await pending;assert.equal(response.status(),200);last=await response.json();
  }
  await page.waitForFunction(()=>!document.querySelector('#keys').hasAttribute('aria-busy'));
  assert.equal(last.ended,row.expected.ended);assert.equal(last.screen.program,row.expected.program);
  if(row.navigation_boundary_only){assert.equal(last.screen.endpoint,'/not-in-this-slice');await compare();}
  else if(row.terminal_text_only){assert.equal(last.screen.message,row.expected.screen.message);assert.equal(await page.locator('#status').textContent(),row.expected.screen.message);assert.equal(await page.locator('#screen').textContent(),'');}
  else{
   for(const part of ['values','cursor','message'])assert.deepEqual(last.screen[part],row.expected.screen[part],row.case+' '+part);
   assert.deepEqual(attrs(last.screen),attrs(row.expected.screen),row.case+' attributes');await compare();
  }
  if(!last.ended&&!row.expected.source_fault){
   const envelope=JSON.parse(Buffer.from(last.token.split('.')[0],'base64url').toString('utf8'));
   assert.equal(envelope.program,row.expected.program);
   assert.equal(Buffer.from(envelope.commarea,'base64').toString('hex'),row.expected.commarea,row.case+' returned COMMAREA');
  }
  const meta=JSON.parse(execFileSync('python',['-B','factory/carddemo-web/runtime/snapshot.py','--out',out+'/database'],{encoding:'utf8'}));
  const state=JSON.parse(await readFile(out+'/database/'+meta.path,'utf8'));
  for(const item of state.authfrds)item.auth_ts=item.auth_ts.replace(' ','T');
  const normalized=Object.fromEntries(Object.entries(state).map(([table,rows])=>[table,rows.map(canonical).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)))]));
  // Compare row multisets without relying on locale-dependent sorting order.
  const wanted=await expectedDatabase(row);
  assert.deepEqual(Object.keys(normalized).sort(),Object.keys(wanted).sort());
  for(const table of Object.keys(normalized))assert.deepEqual(normalized[table].map(JSON.stringify).sort(),wanted[table].map(v=>JSON.stringify(canonical(v))).sort(),row.case+' '+table);
  frames.push({case:row.case,session:row.session,aid:row.aid,screen:last.screen,database_after:meta});
  remaining.set(row.session,remaining.get(row.session)-1);if(!remaining.get(row.session)){await page.close();pages.delete(row.session);}
 }
 passed=true;
}finally{
 await writeFile(out+'/frames.json',JSON.stringify(frames,null,2));
 await writeFile(out+'/summary.json',JSON.stringify({schema:'carddemo-browser-proof/1',head:process.env.GITHUB_SHA,passed,interactions_compared:frames.length,interactions_required:cases.length,programs_compared:[...new Set(frames.map(f=>f.screen.program))],full_slice_screen_equivalence:passed},null,2));
 await browser.close();
}
