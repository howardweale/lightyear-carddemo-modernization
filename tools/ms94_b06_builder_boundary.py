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


def admit_transport(flags, available_tools, workspace_files, *, os_read_probe_passed):
    """Future executable must supply actual zero-model OS denial-probe evidence."""
    required = capability_arguments()
    require(flags == required, 'B06 CLI capability policy differs')
    require(set(available_tools) == set(ARGUMENTS) and not workspace_files,
            'B06 builder exposes additional inputs or tools')
    require(os_read_probe_passed is True, 'B06 tools filesystem denial not demonstrated')
    return True
