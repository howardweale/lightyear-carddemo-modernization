"""A closed diagnostic vocabulary between the independent judge and builder.

Neither raw judge output nor analyst-authored prose can enter a builder prompt.
The analyst may select verified diagnostics; it cannot invent a repair instruction.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from .contracts import canonical, read_json, require
from .journey_order import file_hash, save
from .journey_runtime import JourneySigner
from lightyear_workflow.run_store import utcnow

IDENTIFIER = re.compile(r'^[A-Za-z_$][A-Za-z0-9_.$<>?, \[\]]{0,200}$')
FORBIDDEN_ITEMS = {'command_execution', 'mcp_tool_call', 'web_search', 'file_change'}


def client_identity(executable):
    result = subprocess.run([str(executable), '--version'], capture_output=True, timeout=20, check=True)
    return {'version': result.stdout.decode().strip(), 'sha256': file_hash(executable)}


def check_client(executable, pinned):
    require(client_identity(executable) == pinned, 'Builder executable/version differs from pinned plan')


def compile_diagnostics(log):
    """Only structural compiler fields, never echoed source or arbitrary messages."""
    result = []
    for match in re.finditer(r'LightyearPartialInvoiceTest\.java:\[(\d+)(?:,(\d+))?\][ \t]*([^\r\n]*)', log):
        text = match.group(3)
        if not text.strip():
            # Tycho emits a source echo first. Discard it and find a typed diagnostic.
            messages = re.findall(r'\[ERROR\]\s+(The method [^\r\n]+|[A-Za-z_$][\w$]* cannot be resolved[^\r\n]*|Type mismatch:[^\r\n]+)',log[match.end():match.end()+2000])
            text = messages[0] if messages else ''
        item = {'category': 'compile-error', 'file': 'LightyearPartialInvoiceTest.java',
                'line': int(match.group(1)), 'column': int(match.group(2)) if match.group(2) else None}
        if text.startswith('cannot find symbol'):
            tail = log[match.end():match.end()+500]
            symbol = re.search(r'symbol:\s+(?:method|variable|class)\s+([^\r\n]+)', tail)
            item['code'] = 'cannot-find-symbol'
            if symbol:
                name = symbol.group(1).split('(')[0].strip()
                if IDENTIFIER.fullmatch(name): item['symbol'] = name
        elif text.startswith('incompatible types:'):
            types = text.removeprefix('incompatible types:').strip().split(' cannot be converted to ')
            if len(types) != 2 or not all(IDENTIFIER.fullmatch(t) for t in types): continue
            item.update(code='incompatible-types', source_type=types[0], required_type=types[1])
        elif re.match(r'The method [A-Za-z_$][\w$]*\(', text):
            item.update(code='method-signature-mismatch', symbol=re.search(r'The method (\w+)\(',text)[1])
            signature = re.match(r'The method (\w+)\(([^()]*)\) (?:in|from) the type ([\w.$]+)', text)
            if signature:
                types=[t.strip() for t in signature[2].split(',') if t.strip()]
                if all(IDENTIFIER.fullmatch(t) for t in types):
                    item.update(declaring_type=signature[3],parameter_types=types)
            supplied=re.search(r'arguments \(([^()]*)\)',text)
            if supplied:
                types=[t.strip() for t in supplied[1].split(',') if t.strip()]
                if all(IDENTIFIER.fullmatch(t) for t in types):item['argument_types']=types
            if text.endswith(' is not visible'):item['code']='method-not-visible'
            undefined=re.search(r'is undefined for the type ([\w.$]+)$',text)
            if undefined:item.update(code='method-undefined',declaring_type=undefined[1])
        elif re.match(r'method [A-Za-z_$][\w$]* in class ', text):
            item.update(code='method-signature-mismatch', symbol=re.search(r'method (\w+) in class ',text)[1])
        elif re.match(r'[A-Za-z_$][\w$]* cannot be resolved',text):
            item.update(code='cannot-find-symbol',symbol=text.split()[0])
        else: continue
        if item not in result: result.append(item)
    return result[:20]


def public_api_matches(root, symbol, api):
    """Resolve a compiler symbol from pinned upstream declarations, not repair prose."""
    result=[]
    for relative,key in [('acct/Doc.java','doc_sha256'),('acct/DocManager.java','manager_sha256'),
                         ('model/PO.java','po_sha256'),('model/MAcctSchema.java','schema_sha256')]:
        path=root/'work/idempiere-upstream/org.adempiere.base/src/org/compiere'/relative
        if not path.exists():continue
        require(file_hash(path)==api[key],'Upstream API source changed')
        source=path.read_text(encoding='utf-8')
        pattern=r'public\s+(?:(?:static|final|synchronized)\s+)*([\w.<>\[\]]+)\s+'+re.escape(symbol)+r'\s*\(([^)]*)\)'
        for match in re.finditer(pattern,source):
            types=[]
            for parameter in match[2].split(','):
                parts=parameter.strip().split()
                if not parts:continue
                types.append(' '.join(parts[:-1]).removeprefix('final '))
            if all(IDENTIFIER.fullmatch(t) for t in types):
                result.append({'declaring_type':'org.compiere.'+relative.removesuffix('.java').replace('/','.'),
                    'method':symbol,'parameter_types':types,'return_type':match[1],'source_sha256':api[key]})
    return result


def boolean_api_evidence(root, source, api):
    """Public type/representation facts, derived from the pinned source revision."""
    commit=api.get('source_commit','')
    require(re.fullmatch(r'[0-9a-f]{40}',commit) is not None,'Invalid upstream source pin')
    upstream=root/'work/idempiere-upstream'
    def model_file(name):
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) is not None,'Invalid model name')
        relative='org.adempiere.base/src/org/compiere/model/'+name+'.java'
        result=subprocess.run(['git','-C',str(upstream),'show',commit+':'+relative],
                              capture_output=True,check=True,timeout=20)
        return result.stdout.decode('utf-8'),hashlib.sha256(result.stdout).hexdigest()
    po_path=upstream/'org.adempiere.base/src/org/compiere/model/PO.java'
    require(file_hash(po_path)==api['po_sha256'],'Upstream API source changed')
    po=po_path.read_text(encoding='utf-8')
    def method(text,signature):
        match=re.search(signature+r'\s*\{.*?\n\t\}',text,re.S)
        require(match is not None,'Pinned API method not found')
        return match[0]
    string_method=method(po,r'public String get_ValueAsString\(int idx\)')
    boolean_method=method(po,r'public boolean get_ValueAsBoolean\(String columnName\)')
    require('return value.toString();' in string_method and 'oo instanceof Boolean' in boolean_method,
            'Unsupported accessor representation contract')
    models=[]
    # This is a bounded journey API surface, not arbitrary files named by a model.
    for name in ('MInvoice','MPayment','MAllocationHdr','MInOut','MInventory'):
        if not re.search(r'\b'+name+r'\b',source):continue
        model,model_hash=model_file(name)
        parent=re.search(r'\bclass\s+'+name+r'\s+extends\s+(X_\w+)\b',model)
        require(parent is not None,'Unsupported generated model ancestry')
        generated,generated_hash=model_file(parent[1])
        setter=method(generated,r'public void setPosted\s*\(boolean Posted\)')
        getter=method(generated,r'public boolean isPosted\s*\(\)')
        require('set_Value (COLUMNNAME_Posted, Boolean.valueOf(Posted))' in setter
                and 'oo instanceof Boolean' in getter,'Posted type evidence differs')
        models.append({'model_type':name,'model_sha256':model_hash,'generated_type':parent[1],
                       'generated_sha256':generated_hash,'field':'Posted','java_type':'boolean',
                       'setter_source':setter,'getter_source':getter})
    require(models,'No pinned model type evidence for this candidate')
    return {'source_commit':commit,'po_sha256':api['po_sha256'],'models':models,
            'string_accessor_source':string_method,'boolean_accessor_source':boolean_method,
            'representation_rule':'For a Boolean-backed field, Object.toString() uses Java Boolean text, not the database Y/N encoding. A String return type alone is not proof of an invalid API call.'}


def diagnostics(run, source, api):
    """Read private native artifacts; export only allowlisted structural facts."""
    from .native_reconciliation import state
    from .application_effects import TABLES
    output = []
    # At a native run, ancestors resolve to the same root used by the gate.
    from .journey_order import RUNS
    root=run.parents[len(RUNS.parts)] if len(run.parents)>len(RUNS.parts) else run
    # Case and attempt names are controlled by the native controller.
    for folder in sorted((run/'cases/partial-invoicing').glob('*')):
        for lane in ('oracle','postgresql'):
            log = folder/'execution'/lane/'maven.log'
            if log.exists():
                text = log.read_text(encoding='utf-8', errors='replace')
                output.extend(compile_diagnostics(text))
                # A failed assertion at a typed API call is distinct from a money assertion.
                lines = source.splitlines()
                for frame in re.finditer(r'LightyearPartialInvoiceTest\.java:(\d+)', text):
                    n = int(frame[1])
                    if not 0<n<=len(lines):continue
                    # Include the enclosing failing Java method: the invalid type
                    # comparison can control a later assertion or posting call.
                    start=n-1
                    while start>0 and not re.search(r'\b(?:private|public|protected)\b.*\(',lines[start]):start-=1
                    reads=[i+1 for i in range(start,n) if 'get_ValueAsString("Posted")' in lines[i]]
                    if reads:
                        output.append({'category':'api-type-mismatch', 'file':'LightyearPartialInvoiceTest.java',
                            'line':reads[0], 'failure_frame_line':n,
                            'call':'PO.get_ValueAsString', 'field':'Posted',
                            'accessor_return_type':'String','field_java_type':'boolean',
                            'typed_accessor':'PO.get_ValueAsBoolean', 'typed_accessor_return_type':'boolean',
                            'basis':'Representation mismatch in the failing method; not an assertion expected/actual value or proof of the sole failure cause',
                            'type_evidence':boolean_api_evidence(root,source,api),
                            'api_source_sha256':api['po_sha256']})
            before, after = folder/'baseline'/lane/'entry', folder/'after'/lane
            if not (before/'state.json').exists() or not (after/'state.json').exists(): continue
            a,b = state(before,lane),state(after,lane)
            outside = sorted(t for t in set(a['tables']) & set(b['tables'])
                             if t not in TABLES and a['tables'][t]['row_multiset'] != b['tables'][t]['row_multiset'])
            for table in outside:
                # A source-verified call chain, not an inferred amount or a broadened footprint.
                if table == 't_fact_acct_history' and 'Doc.postImmediate(' in source:
                    output.append({'category':'outside-footprint', 'table':table, 'call':'Doc.postImmediate',
                        'source_call_path':['Doc.postImmediate','DocManager.postDocument','Doc.post','Doc.deleteAcct'],
                        'api_source_sha256':api['doc_sha256'], 'lane':lane})
    unique = []
    for item in output:
        if item['category']=='compile-error' and item.get('symbol'):
            available=public_api_matches(root,item['symbol'],api)
            if available:item['available_public_overloads']=available
        if item not in unique: unique.append(item)
    return [{'id':f'diagnostic-{i+1}', **item} for i,item in enumerate(unique)]


REJECTION_REASONS=('insufficient-type-evidence','unrelated-to-failing-method','outside-permitted-scope')


def select_feedback(observations, proposal,require_decisions=False):
    require(not require_decisions or set(proposal)=={'decisions'},'Analyst must record a reasoned decision for every diagnostic')
    # Legacy selections remain verifiable in the immutable earlier campaign audit.
    if set(proposal)=={'decisions'}:
        decisions=proposal['decisions'];known={d['id'] for d in observations}
        require(isinstance(decisions,list),'Invalid analyst decisions')
        seen=[];ids=[]
        for decision in decisions:
            require(isinstance(decision,dict) and set(decision)=={'diagnostic_id','disposition','reason'},'Analyst decision may not add prose')
            identity=decision['diagnostic_id'];seen.append(identity)
            require(identity in known,'Analyst invented a diagnostic')
            if decision['disposition']=='forward':
                require(decision['reason']=='supported-structural-defect','Invalid forwarding reason')
                ids.append(identity)
            else:
                require(decision['disposition']=='reject' and decision['reason'] in REJECTION_REASONS,'Invalid rejection reason')
        require(len(seen)==len(set(seen)) and set(seen)==known,'Every diagnostic needs exactly one decision')
    else:
        require(set(proposal) == {'diagnostic_ids'}, 'Analyst output may only select diagnostics')
        ids = proposal['diagnostic_ids']
    require(isinstance(ids,list) and len(ids) == len(set(ids)), 'Invalid analyst selection')
    known = {item['id']:item for item in observations}
    require(all(isinstance(i,str) and i in known for i in ids), 'Analyst invented a diagnostic')
    return [known[i] for i in ids]


def analyst_schema(observations):
    return {'type':'object','properties':{'decisions':{'type':'array','items':{
        'type':'object','properties':{
            'diagnostic_id':{'type':'string','enum':[d['id'] for d in observations]},
            'disposition':{'type':'string','enum':['forward','reject']},
            'reason':{'type':'string','enum':['supported-structural-defect',*REJECTION_REASONS]}},
        'required':['diagnostic_id','disposition','reason'],'additionalProperties':False}}},
        'required':['decisions'],'additionalProperties':False}


def analyst_prompt(observations,candidate,api_reference,error):
    return {'role':'Independent failure analyst','diagnostic_contract_version':2,
        'instruction':'Assess every diagnostic independently. Forward a supported structural defect relevant to the failing method; it need not prove the sole cause or predict that the business journey will pass. For an API representation mismatch, inspect the pinned field type and accessor implementations, not just the accessor return type. Reject unsupported or unrelated diagnostics using a reason code. Never supply business values, a patch, or prose. Only forwarded diagnostics reach the builder; rejecting every diagnostic stops the factory.',
        'native_gate_status':error,'diagnostics':observations,'candidate':candidate,'api_reference':api_reference}


def invoke(root, campaign, executable, role, prompt, schema):
    """Every attempted process has a signed accounting record, even on failure."""
    plan = read_json(campaign/'plan.json')
    check_client(executable, plan['builder_client'])
    previous = sorted((campaign/'calls').glob('*/invocation.json'))
    require(len(previous) < plan['max_client_invocations'], 'Client invocation budget exhausted')
    folder = campaign/'calls'/f'{len(previous)+1:03d}-{role}'
    folder.mkdir(parents=True, exist_ok=False)
    workspace = folder/'workspace'; workspace.mkdir()
    save(folder/'prompt.json',prompt);save(folder/'schema.json',schema)
    started_at = utcnow();started = time.monotonic();error = None;code = None
    save(folder/'invocation.json',{'role':role,'started_at':started_at,'prompt_sha256':file_hash(folder/'prompt.json'),
        'plan_sha256':plan['content_sha256'],'builder_client':plan['builder_client']})
    args=[str(executable),'exec','--skip-git-repo-check','--ephemeral','--sandbox','read-only',
          '--disable','shell_tool','--disable','apps','--disable','collab','--json',
          '--config','mcp_servers={}','--config','web_search="disabled"','--config','approval_policy="never"',
          '--output-schema',str((folder/'schema.json').resolve()),'-o',str((folder/'proposal.json').resolve()),
          '-C',str(workspace.resolve()),'-']
    try:
        with (folder/'events.jsonl').open('wb') as out,(folder/'transport.log').open('wb') as err:
            process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=os.name!='nt')
            try:process.communicate(canonical(prompt),timeout=plan['client_timeout_seconds'])
            except BaseException:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                else:os.killpg(process.pid,signal.SIGKILL)
                process.wait();raise
            code=process.returncode
        require(code==0,'Agent transport failed')
        events=[json.loads(line) for line in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        require(sum(e.get('type')=='turn.completed' for e in events)==1,'Agent must complete exactly one turn')
        require(not any(e.get('item',{}).get('type') in FORBIDDEN_ITEMS for e in events),'Agent attempted a tool operation')
        require(not list(workspace.iterdir()),'Agent attempted to write its workspace')
        proposal=read_json(folder/'proposal.json')
    except BaseException as exc:
        error=type(exc).__name__
        raise
    finally:
        events=[]
        if (folder/'events.jsonl').exists():
            for line in (folder/'events.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
        usages=[e['usage'] for e in events if e.get('type')=='turn.completed' and isinstance(e.get('usage'),dict)]
        usage={k:sum(u.get(k,0) for u in usages) for k in ('input_tokens','cached_input_tokens','output_tokens')} if usages else None
        receipt=JourneySigner(root).sign({'artifact_type':'lightyear-journey-agent-call','role':role,
            'started_at':started_at,'ended_at':utcnow(),'elapsed_seconds':round(time.monotonic()-started,3),
            'exit_code':code,'error':error,'usage':usage,'usage_known':bool(usages),
            'builder_client':plan['builder_client'],'plan_sha256':plan['content_sha256'],
            'prompt_sha256':file_hash(folder/'prompt.json'),'events_sha256':file_hash(folder/'events.jsonl') if (folder/'events.jsonl').exists() else None,
            'proposal_sha256':file_hash(folder/'proposal.json') if (folder/'proposal.json').exists() else None})
        save(folder/'receipt.json',receipt)
    return folder,proposal


def cost_report(calls, attempts, elapsed):
    known=[c['usage'] for c in calls if c.get('usage') is not None]
    return {'client_invocations':len(calls),'builder_invocations':sum(c['role']=='builder' for c in calls),
        'analyst_invocations':sum(c['role']=='analyst' for c in calls),
        'input_tokens':sum(c.get('input_tokens',0) for c in known),
        'cached_input_tokens':sum(c.get('cached_input_tokens',0) for c in known),
        'output_tokens':sum(c.get('output_tokens',0) for c in known),
        'usage_complete':len(known)==len(calls),'calls_with_unknown_usage':len(calls)-len(known),
        'failed_client_invocations':sum(c.get('error') is not None for c in calls),
        'native_attempts':len(attempts),'failed_native_attempts':sum(not a['passed'] for a in attempts),
        'agent_elapsed_seconds':round(sum(c['elapsed_seconds'] for c in calls),3),
        'native_elapsed_seconds':round(sum(a['elapsed_seconds'] for a in attempts),3),
        'total_elapsed_seconds':round(elapsed,3),'billed_usd':None,
        'billing_basis':'Signed-in account; no per-call invoice is exposed. Local compute and electricity not metered.',
        'internal_provider_retries':'not exposed; client invocations are the counting unit'}
