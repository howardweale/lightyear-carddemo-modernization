"""Pinned Codex CLI transport; organization API deferred by user."""
import json
import os
import signal
import sys
from tools.ms94_tool_policy_v4 import arguments,verify_events
from tools.ms94_builder_mcp_v4 import transcript
import subprocess
import time
from lightyear_calibration.contracts import read_json, require, canonical
from lightyear_calibration.journey_order import save, file_hash
from lightyear_calibration.journey_repair import check_client, FORBIDDEN_ITEMS
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_workflow.run_store import utcnow

def invoke(root, campaign, executable, role, prompt, schema, remaining_seconds):
    """Every attempted process has a signed accounting record, even on failure."""
    from tools.ms94_controller_v4 import frozen
    plan = frozen(root,campaign,live=True)
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
    require(remaining_seconds>0,'Campaign elapsed budget exhausted')
    session_id=plan['tool_session_id']
    before_tools=transcript(root,session_id)
    capability_args=arguments(root,sys.executable,session_id,plan['max_compilations']) if role=='builder' else [
        '--ignore-user-config','--disable','shell_tool','--disable','apps','--disable','collab',
        '--config','mcp_servers={}','--config','web_search="disabled"','--config','approval_policy="never"']
    args=[str(executable),'exec','--model',plan['requested_model'],'--config','model_reasoning_effort='+json.dumps(plan['reasoning_effort']),
          '--skip-git-repo-check','--ephemeral','--sandbox','read-only','--json',*capability_args,
          '--output-schema',str((folder/'schema.json').resolve()),'-o',str((folder/'proposal.json').resolve()),
          '-C',str(workspace.resolve()),'-']

    try:
        with (folder/'events.jsonl').open('wb') as out,(folder/'transport.log').open('wb') as err:
            process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=os.name!='nt')
            try:process.communicate(canonical(prompt),timeout=min(plan['client_timeout_seconds'],remaining_seconds))
            except BaseException:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                else:os.killpg(process.pid,signal.SIGKILL)
                process.wait();raise
            code=process.returncode
        require(code==0,'Agent transport failed')
        events=[json.loads(line) for line in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        require(sum(e.get('type')=='turn.completed' for e in events)==1,'Agent must complete exactly one turn')
        records=transcript(root,session_id)[len(before_tools):]
        verify_events(events,role,records)
        save(folder/'tool-transcript.json',records)
        require(not list(workspace.iterdir()),'Agent attempted to write its workspace')
        frozen(root,campaign)
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
        try:
            records=transcript(root,session_id)[len(before_tools):]
            transcript_error=None
        except Exception as exc:
            records=[];transcript_error=type(exc).__name__
            error=error or 'IncompleteToolTranscript'
        save(folder/'tool-transcript.json',records)
        receipt=JourneySigner(root).sign({'artifact_type':'lightyear-journey-agent-call','role':role,
            'started_at':started_at,'ended_at':utcnow(),'elapsed_seconds':round(time.monotonic()-started,3),
            'exit_code':code,'error':error,'usage':usage,'usage_known':bool(usages),
            'tool_transcript_error':transcript_error,
            'builder_client':plan['builder_client'],'requested_model':plan['requested_model'],
            'reasoning_effort':plan['reasoning_effort'],'provider_resolved_model':None,'plan_sha256':plan['content_sha256'],
            'tool_transcript_sha256':file_hash(folder/'tool-transcript.json'),
            'prompt_sha256':file_hash(folder/'prompt.json'),'events_sha256':file_hash(folder/'events.jsonl') if (folder/'events.jsonl').exists() else None,
            'proposal_sha256':file_hash(folder/'proposal.json') if (folder/'proposal.json').exists() else None})
        save(folder/'receipt.json',receipt)
    return folder,proposal
