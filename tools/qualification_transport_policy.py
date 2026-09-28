"""Explicit local-tool policy for a future qualified campaign. Does not invoke a model.

Configuration reference: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
"""
import json
from pathlib import Path
from lightyear_calibration.contracts import require

TOOLS=('public_contract','public_api','deterministic_support','check_structure','compile_candidate_source')
SERVER='qualified_journey_public'


def toml(value):
    if isinstance(value,str):return json.dumps(value)
    if type(value) is bool:return 'true' if value else 'false'
    if type(value) is int:return str(value)
    if isinstance(value,list):return '['+','.join(toml(x) for x in value)+']'
    if isinstance(value,dict):return '{'+','.join(toml(k)+'='+toml(v) for k,v in value.items())+'}'
    raise TypeError('Unsupported configuration value')


def builder_arguments(root, python, session_id, max_compilations):
    root=Path(root).resolve()
    server={'command':str(Path(python).resolve()),
        'args':['-m','tools.journey_builder_mcp','--root',str(root),
                '--session-id',session_id,'--max-compilations',str(max_compilations)],
        'cwd':str(root),'env':{'PYTHONPATH':str(root/'src')+';'+str(root),'PYTHONUTF8':'1'},
        'enabled':True,'required':True,'enabled_tools':list(TOOLS),
        'startup_timeout_sec':30,'tool_timeout_sec':660,'default_tools_approval_mode':'approve'}
    # These settings apply only to the child builder, never to the user's global config.
    return ['--ignore-user-config','--disable','shell_tool','--disable','apps','--disable','collab',
            '--config','web_search="disabled"','--config','approval_policy="never"',
            '--config','mcp_servers='+toml({SERVER:server})]


def verify_events(events, role):
    calls=[]
    for event in events:
        item=event.get('item',{});kind=item.get('type')
        require(kind not in ('command_execution','web_search','file_change'),'Undeclared agent capability')
        if kind=='mcp_tool_call':
            require(role=='builder' and item.get('server')==SERVER and item.get('tool') in TOOLS,
                    'Agent used an undeclared MCP tool')
            calls.append(item)
    return {'allowed_mcp_event_count':len(calls),'policy':'local-public-journey-tools-only'}
