export {}; // Keep browser declarations in module scope.
type Field = {name:string|null;data_offset:number;length:number;initial:string;attributes:string[];protected:boolean;hidden:boolean;color:string;highlight:string};
type Attributes = {protected:boolean;hidden:boolean;color:string;highlight:string;modified?:boolean;intensity?:string;autoskip?:boolean};
type Frame = {program:string;transaction:string;model:{rows:number;columns:number;fields:Field[]};values:Record<string,string>;attributes:Record<string,Attributes>;cursor:string;message:string;endpoint:string};
type Reply = {token:string|null;screen:Frame;ended:boolean;sourceHash:string};
const form=document.querySelector<HTMLFormElement>('#screen')!;
const status=document.querySelector<HTMLElement>('#status')!;
const keys=document.querySelector<HTMLElement>('#keys')!;
let token:string|null=null, current:Frame|null=null, busy=false, ended=false;
const colors:Record<string,string>={BLUE:'#6daaff',RED:'#ff7373',GREEN:'#74e59a',YELLOW:'#ffe382',TURQUOISE:'#69dbdf',PINK:'#ed9fe6',NEUTRAL:'#eeeeee'};

function style(node:HTMLElement,f:Field,a:Attributes,offset:number,width:number):void {
  const columns=current!.model.columns;
  node.style.left=`${offset%columns}ch`;node.style.top=`${Math.floor(offset/columns)*1.25}em`;node.style.width=`${width}ch`;
  const color=a.color==='DEFAULT'?(a.protected?((a.intensity==='BRIGHT'||(!a.intensity&&f.attributes.includes('BRT')))?'NEUTRAL':'BLUE'):((a.intensity==='BRIGHT'||(!a.intensity&&f.attributes.includes('BRT')))?'RED':'GREEN')):a.color;
  if(!(color in colors))throw new Error('Unsupported screen color');
  node.style.color=colors[color];if((a.intensity==='BRIGHT'||(!a.intensity&&f.attributes.includes('BRT'))))node.classList.add('bright');
  if(a.highlight==='UNDERLINE')node.classList.add('underline');
  else if(a.highlight==='REVERSE')node.classList.add('reverse');
  else if(a.highlight==='BLINK')node.classList.add('blink');
  else if(a.highlight!=='OFF')throw new Error('Unsupported screen highlight');
}
function render(frame:Frame):void {
  current=frame;form.replaceChildren();form.style.width=`${frame.model.columns}ch`;form.style.height=`${frame.model.rows*1.25}em`;
  form.dataset.program=frame.program;form.dataset.transaction=frame.transaction;
  for(const f of frame.model.fields){
    const a=f.name?frame.attributes[f.name]:f;const value=(f.name?frame.values[f.name]:f.initial).padEnd(f.length,' ').slice(0,f.length);
    if(f.name&&!a.protected){
      const input=document.createElement('input');input.name=f.name;input.setAttribute('aria-label',f.name);input.maxLength=f.length;
      input.type=a.hidden?'password':'text';input.value=value.trimEnd();input.autocomplete='off';input.spellcheck=false;
      input.dataset.value=value;style(input,f,a,f.data_offset,f.length);form.append(input);
    }else{
      let at=f.data_offset,remaining=value;
      while(remaining.length){const width=Math.min(remaining.length,frame.model.columns-at%frame.model.columns);
        const label=document.createElement('span');label.textContent=a.hidden?' '.repeat(width):remaining.slice(0,width);
        if(f.name)label.dataset.field=f.name;label.dataset.hidden=String(a.hidden);label.dataset.value=remaining.slice(0,width);
        style(label,f,a,at,width);form.append(label);at+=width;remaining=remaining.slice(width);}
    }
  }
  if(frame.cursor){const field=Array.from(form.elements).find(e=>e instanceof HTMLInputElement&&e.name===frame.cursor) as HTMLInputElement|undefined;field?.focus();field?.setSelectionRange(0,0);}
  status.textContent=frame.endpoint?'This option is not in slice 1.':frame.message;
}
async function interact(aid:string):Promise<void>{
  if(busy||ended)return;busy=true;keys.setAttribute('aria-busy','true');
  const fields:Record<string,string>={};if(aid!=='INITIAL')for(const control of Array.from(form.elements))if(control instanceof HTMLInputElement)fields[control.name]=control.value;
  try{
    const response=await fetch('/api/interaction',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'omit',body:JSON.stringify({token,aid,fields}),cache:'no-store'});
    if(!response.ok){const failure=await response.json() as {error?:string};throw new Error(failure.error??'The interaction could not be completed.');}
    const next=await response.json() as Reply;token=next.token;ended=next.ended;render(next.screen);
    document.body.dataset.sourceHash=next.sourceHash;
    if(ended){form.replaceChildren();keys.replaceChildren();status.textContent=next.screen.message;}
  }catch(error){status.textContent=error instanceof Error?error.message:'Connection unavailable.';}
  finally{busy=false;keys.removeAttribute('aria-busy');}
}
form.addEventListener('submit',event=>{event.preventDefault();void interact('ENTER');});
// All PF keys are sent to the program; its source decides whether to reject, remap or act.
for(const aid of ['ENTER',...Array.from({length:24},(_,i)=>`PF${i+1}`)]){
  const button=document.createElement('button');button.type='button';button.textContent=aid;button.dataset.aid=aid;
  button.addEventListener('click',()=>void interact(aid));keys.append(button);
}
document.addEventListener('keydown',event=>{
  if(event.altKey||event.ctrlKey||event.metaKey)return;
  const match=/^F([1-9]|1[0-2])$/.exec(event.key);
  if(match){event.preventDefault();void interact(`PF${Number(match[1])+(event.shiftKey?12:0)}`);}
});
void interact('INITIAL');
