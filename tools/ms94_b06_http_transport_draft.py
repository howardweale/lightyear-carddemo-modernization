"""Review-only B06 argv construction. No process, socket, credential or model I/O.

This is not admission evidence and is deliberately not wired to Controller.launch.
The existing pinned transport proof remains unchanged; a new proof is required.
"""
from pathlib import PureWindowsPath
from tools.ms94_b06_pinned_transport import PATH, SHA
from tools.ms94_tool_policy_v5 import capability_arguments
from tools.ms94_builder_mcp_v5 import TOOLS, SERVER
from tools.qualification_transport_policy import toml

TOKEN_ENV = 'B06_MCP_TOKEN'


def draft(port, empty_workspace):
    """Only a numeric host-assigned loopback port and an absolute workspace vary.

    Existence, emptiness, ACLs, account authentication and the bound CLI hash
    must be checked by the future host adapter, not inferred from this draft.
    """
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Expected an unprivileged numeric loopback port')
    if (not isinstance(empty_workspace, str) or
            any(ord(c) < 32 for c in empty_workspace) or
            not PureWindowsPath(empty_workspace).is_absolute() or
            empty_workspace.startswith(('\\\\', '//'))):
        raise ValueError('Expected an absolute local Windows workspace')
    server = {
        'url': f'http://127.0.0.1:{port}/mcp',
        'bearer_token_env_var': TOKEN_ENV,
        'enabled': True, 'required': True, 'enabled_tools': list(TOOLS),
        'startup_timeout_sec': 30, 'tool_timeout_sec': 660,
        'default_tools_approval_mode': 'approve',
    }
    argv = ['exec', *capability_arguments(), '--ignore-rules', '--strict-config',
            '--model', 'gpt-6-astra', '--config', 'model_reasoning_effort="high"',
            '--config', 'mcp_servers=' + toml({SERVER: server}),
            '--json', '--ephemeral', '--skip-git-repo-check',
            '--sandbox', 'read-only', '--cd', empty_workspace, '-']
    return {
        'artifact_type': 'ms94-b06-http-exec-draft/1',
        'status': 'draft-not-admitted', 'executable': PATH,
        'executable_sha256': SHA, 'argv': argv,
        'environment_names': ['CODEX_HOME', TOKEN_ENV],
        'stdin': 'exact bound builder request; no argv prompt',
        'model_calls_authorized': False,
        'requires_new_transport_proof': True,
    }
