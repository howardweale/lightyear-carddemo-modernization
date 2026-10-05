"""B06 model-facing capability boundary; no model transport or filesystem tool.

The host broker may import tools/. The builder receives only closed results.
Read-only CLI sandbox mode alone does not establish filesystem confidentiality.
"""
import re
from lightyear_calibration.contracts import require
from tools.ms94_tool_policy_v5 import capability_arguments, verify_events

ARGUMENTS = {'public_contract': {'scenario'}, 'public_api': {'class_name', 'method'},
             'deterministic_support': set(), 'check_structure': {'source'}, 'compile': {'source'}}


def dispatch(broker, name, arguments):
    require(name in ARGUMENTS and isinstance(arguments, dict), 'Undeclared B06 builder capability')
    args = dict(arguments)
    if name == 'public_api': args.setdefault('method', '')
    require(set(args) == ARGUMENTS[name], 'B06 builder argument schema differs')
    if name == 'public_api':
        require(isinstance(args['class_name'], str) and
                re.fullmatch(r'(?:org\.(?:compiere|adempiere|idempiere)\.)[A-Za-z0-9_.$]+', args['class_name']),
                'B06 API identifier is not an application class')
        require(isinstance(args['method'], str) and re.fullmatch(r'[A-Za-z0-9_$]*', args['method']),
                'B06 API method is not an identifier')
    if name == 'public_contract':
        require(args['scenario'] in ('operations', 'procure-to-pay', 'materials'), 'Unknown B06 public scenario')
    if name in ('compile', 'check_structure'):
        require(isinstance(args['source'], str) and len(args['source'].encode('utf-8')) <= 60000,
                'B06 source bound exceeded')
    return broker.call(name, args)


def admit_transport(flags, available_tools, workspace_files, *, root, probe_binding, public_key, transport,
                    process_probe_binding=None):
    """Require a signed actual OS record bound by hash, never an asserted bool."""
    required = capability_arguments()
    require(flags == required, 'B06 CLI capability policy differs')
    require(set(available_tools) == set(ARGUMENTS) and not workspace_files,
            'B06 builder exposes additional inputs or tools')
    from tools.ms94_b06_os_probe import admit
    record = admit(root, probe_binding, public_key, transport)
    require(record.get('method') == 'windows-local-account' and
            record.get('account_sid') == transport.get('account_sid'),
            'B06 Codex transport requires the admitted local account SID')
    from tools.ms94_b06_codex_transport import admit_process
    admit_process(root, process_probe_binding, public_key, transport, record)
    return True
