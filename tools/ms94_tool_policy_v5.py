"""Closed capabilities and output provenance for the controller-v2 transport."""
import json,os
from pathlib import Path
from lightyear_calibration.contracts import require
from tools.qualification_transport_policy import toml
from tools.ms94_builder_mcp_v5 import TOOLS,SERVER

# Exact non-executable diagnostic emitted by the pinned CLI's legacy alias.
# Do not accept arbitrary error items or infer safety from a message prefix.
LEGACY_COLLAB_WARNING = (
    '`[features].collab` is deprecated. Use `[features].multi_agent` instead. '
    '(Enable it with `--enable multi_agent` or `[features].multi_agent` in config.toml. '
    'See https://developers.openai.com/codex/config-basic#feature-flags for details.)'
)


def capability_arguments():
    return ['--ignore-user-config','--disable','shell_tool','--disable','apps','--disable','multi_agent',
            '--config','web_search="disabled"','--config','approval_policy="never"']


def arguments(root,python,session_id,maximum):
    root=Path(root).resolve()
    server={'command':str(Path(python).resolve()),'args':['-m','tools.ms94_builder_mcp_v5','--root',str(root),
        '--maximum',str(maximum),'--session-id',session_id],'cwd':str(root),
        'env':{'PYTHONPATH':os.pathsep.join((str(root/'src'),str(root))),'PYTHONUTF8':'1'},
        'enabled':True,'required':True,'enabled_tools':list(TOOLS),'startup_timeout_sec':30,
        'tool_timeout_sec':660,'default_tools_approval_mode':'approve'}
    return capability_arguments()+['--config','mcp_servers='+toml({SERVER:server})]


def closed_output(result):
    require(isinstance(result,dict),'Missing MCP result')
    if result.get('structured_content') is not None:return result['structured_content']
    if result.get('structuredContent') is not None:return result['structuredContent']
    content=result.get('content',[])
    require(len(content)==1 and content[0].get('type')=='text','Unexpected MCP output content')
    return json.loads(content[0]['text'])


def verify_events(events,role,records):
    # Unknown executable capabilities fail closed, not merely known bad tools.
    allowed={'reasoning','agent_message','mcp_tool_call'}
    completed=[];started={}
    for event in events:
        require(event.get('type') not in ('error','turn.failed'),'Agent reported a transport failure')
        item=event.get('item')
        if item is None:continue
        if item.get('type')=='error':
            require(event.get('type')=='item.completed' and set(event)=={'type','item'}
                    and set(item)=={'id','type','message'} and isinstance(item.get('id'),str)
                    and bool(item['id']) and item.get('message')==LEGACY_COLLAB_WARNING,
                    'Unrecognized CLI diagnostic')
            continue
        kind=item.get('type');require(kind in allowed,'Undeclared agent capability')
        if kind!='mcp_tool_call':continue
        require(role=='builder' and item.get('server')==SERVER and item.get('tool') in TOOLS,'Undeclared MCP call')
        identity=item.get('id');require(identity,'Missing tool event identity')
        if event['type']=='item.started':require(identity not in started,'Duplicate tool start');started[identity]=item
        if event['type']=='item.completed':completed.append(item)
    require(len(completed)==len(records),'Unrecorded/incomplete MCP tool operation')
    require(len({x['id'] for x in completed})==len(completed),'Repeated tool completion')
    remaining=list(records)
    for item in completed:
        args=item.get('arguments') or {}
        if isinstance(args,str):args=json.loads(args)
        if item['tool']=='public_api':args.setdefault('method','')
        require(item.get('error') is None,'MCP transport failed')
        output=closed_output(item.get('result'))
        match=next((r for r in remaining if item['tool']==r['invocation']['tool'] and
                    args==r['invocation']['arguments'] and output==r['result']['output']),None)
        require(match is not None,'Tool arguments/output differ from broker record')
        remaining.remove(match)
    require(not set(started)-{x['id'] for x in completed},'Unfinished tool call')
    return {'verified':True,'tool_calls':len(records),'candidate_basis':'frozen prompt plus recorded public tool outputs and permitted structural feedback'}
