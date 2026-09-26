"""Bounded builder transport; only the existing PatchBroker writes generated code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import time
from .contracts import canonical, read_json, require
from .journey_order import save, file_hash
from .journey_runtime import JourneySigner
from lightyear_factory.agents import BUILDER_SCHEMA
from lightyear_factory.contracts import WorkOrder
from lightyear_factory.patches import PatchBroker
from lightyear_factory.workspace import IsolatedWorkspace

ORDER=Path('factory/idempiere/partial-invoicing/work-order.json')
PLACEHOLDER='// LIGHTYEAR_BUILDER_JOURNEY\n'


def build(root, output, executable, prompt_file):
    declaration=read_json(root/ORDER);order=WorkOrder.from_dict(declaration)
    prompt=read_json(prompt_file)
    require(prompt['declaration']==declaration,'Reviewed prompt differs from declaration')
    repair=prompt.get('single_call_repair')
    if repair is not None:
        original=repair['source']
        require(hashlib.sha256(original.encode('utf-8')).hexdigest()==repair['source_sha256'],'Repair source hash differs')
        require(repair['find'] and original.count(repair['find'])==1,'Repair must replace exactly one source occurrence')
        expected=original.replace(repair['find'],repair['replace'])
        require(hashlib.sha256(expected.encode('utf-8')).hexdigest()==repair['expected_sha256'],'Repair expectation hash differs')
    require(order.allowed_paths==('LightyearPartialInvoiceTest.java',), 'Unexpected builder scope')
    require(not output.exists(), 'Builder output already exists')
    previous=list(output.parent.glob('build-*/invocation.json'))
    require(len(previous)<declaration['policy']['max_builder_invocations'],'Builder invocation budget exhausted')
    prior=[]
    for path in sorted(previous):
        transcript=path.parent/'events.jsonl'
        events=[json.loads(line) for line in transcript.read_text(encoding='utf-8').splitlines() if line.strip()] if transcript.exists() else []
        prior.append({'directory':path.parent.relative_to(root).as_posix(),'invocation_sha256':file_hash(path),
                      'events':events,'events_sha256':file_hash(transcript) if transcript.exists() else None,
                      'completed_turns':sum(e.get('type')=='turn.completed' for e in events)})
    output.mkdir(parents=True);workspace=output/'workspace';workspace.mkdir()
    (workspace/'LightyearPartialInvoiceTest.java').write_text(PLACEHOLDER,encoding='utf-8',newline='\n')
    save(output/'prompt.json',prompt);save(output/'schema.json',BUILDER_SCHEMA)
    save(output/'invocation.json',{'approved_prompt_sha256':file_hash(prompt_file),'prompt_sha256':file_hash(output/'prompt.json'),'declaration_sha256':file_hash(root/ORDER)})
    args=[str(executable),'exec','--skip-git-repo-check','--ephemeral','--sandbox','read-only',
          '--disable','shell_tool','--disable','apps','--disable','collab','--json',
          '--config','mcp_servers={}','--config','web_search="disabled"','--config','approval_policy="never"',
          '--output-schema',str((output/'schema.json').resolve()),'-o',str((output/'proposal.json').resolve()),
          '-C',str(workspace.resolve()),'-']
    started=time.monotonic()
    with (output/'events.jsonl').open('wb') as out, (output/'transport.log').open('wb') as err:
        process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=os.name!='nt')
        try:process.communicate(canonical(prompt),timeout=declaration['policy']['builder_timeout_seconds'])
        except subprocess.TimeoutExpired:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            else:os.killpg(process.pid,signal.SIGKILL)
            process.wait();raise ValueError('Builder elapsed budget exceeded')
    require(process.returncode==0,'Builder transport failed; diagnostics retained')
    events=[json.loads(line) for line in (output/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    turns=[e for e in events if e.get('type')=='turn.completed']
    require(len(turns)==1,'Builder must complete exactly one bounded turn')
    require(not any(e.get('item',{}).get('type') in ('command_execution','mcp_tool_call','web_search','file_change') for e in events),'Builder attempted tool operations')
    proposal=read_json(output/'proposal.json');require(proposal['blocked_reason'] is None,'Builder declined')
    require((workspace/'LightyearPartialInvoiceTest.java').read_text(encoding='utf-8')==PLACEHOLDER,'Builder bypassed patch broker')
    isolated=IsolatedWorkspace(workspace,workspace,order.allowed_paths)
    patch=PatchBroker().apply(order,isolated,proposal['edits'])
    code=(workspace/'LightyearPartialInvoiceTest.java').read_text(encoding='utf-8')
    if repair is not None:
        require(file_hash(workspace/'LightyearPartialInvoiceTest.java')==repair['expected_sha256'],'Builder changed source outside the approved single-call repair')
    require('class LightyearPartialInvoiceTest extends AbstractTestCase' in code,'Unexpected test class')
    require(all(term not in code for term in ('ProcessBuilder','Runtime.getRuntime','java.net.','System.getenv','/output/','/verifier/','ALTER USER','DROP TABLE')),'Generated harness requests out-of-scope capabilities')
    receipt=JourneySigner(root).sign({'artifact_type':'lightyear-journey-builder',
      'declaration_sha256':file_hash(root/ORDER),'provider':'authenticated-codex-cli','executable_sha256':file_hash(executable),
      'provider_invocations':len(previous)+1,'completed_turns':len(turns)+sum(p['completed_turns'] for p in prior),
      'completed_turns_current':len(turns),'prior_invocations':prior,
      'model_calls_accounting':'all Codex builder invocations including failed transport attempts; internal provider retries are not exposed',
      'usage':turns[0].get('usage'),'usage_scope':'current successful generation','elapsed_seconds':round(time.monotonic()-started,1),
      'prompt_sha256':file_hash(output/'prompt.json'),'events_sha256':file_hash(output/'events.jsonl'),
      'proposal_sha256':file_hash(output/'proposal.json'),'patch':patch,'harness_sha256':file_hash(workspace/'LightyearPartialInvoiceTest.java'),
      'single_call_repair':{'source_sha256':repair['source_sha256'],'expected_sha256':repair['expected_sha256']} if repair is not None else None,
      'agent_generated':True,'native_execution_verified':False,'gate_output_exposed':False,
      'independently_attested':False,'cloud_resources_started':False})
    save(output/'receipt.json',receipt);return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('.'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--prompt',type=Path,required=True)
    args=parser.parse_args();result=build(args.root.resolve(),args.output.resolve(),args.executable.resolve(),args.prompt.resolve())
    print(json.dumps({k:result[k] for k in ('agent_generated','harness_sha256','native_execution_verified','usage')}))

if __name__=='__main__':main()
