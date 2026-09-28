"""Public structural contract. No monetary oracle or private captures belong here."""
from pathlib import Path
import xml.etree.ElementTree as ET
from .contracts import read_json, seal

VERSION = 'idempiere-public-journey-contract-v1'
AREA = Path('factory/idempiere/qualification')


def contract(root, scenario):
    if scenario not in ('operations', 'procure-to-pay'):
        raise ValueError('Unknown public scenario')
    return read_json(Path(root)/AREA/'public'/(scenario+'.json'))


def trace_diagnostics(path, declaration):
    """Only contract-owned field names and closed codes can leave this function."""
    allowed = set(declaration['trace_fields'])
    if not Path(path).exists():
        return [{'category':'trace-contract', 'code':'missing-trace-artifact'}]
    raw = Path(path).read_bytes()
    if len(raw) > 65536:
        return [{'category':'trace-contract', 'code':'oversized-trace-artifact'}]
    # Properties.storeToXML emits a standard DOCTYPE; ElementTree does not fetch it.
    if b'<!ENTITY' in raw.upper():
        return [{'category':'trace-contract', 'code':'invalid-trace-format'}]
    try:
        tree = ET.fromstring(raw)
        if tree.tag != 'properties': raise ValueError()
    except (ET.ParseError, ValueError):
        return [{'category':'trace-contract', 'code':'invalid-trace-format'}]
    names = [x.attrib.get('key') for x in tree.findall('entry')]
    out = []
    if any(x.tag not in ('comment','entry') or (x.tag=='entry' and list(x)) for x in tree):
        out.append({'category':'trace-contract','code':'invalid-trace-format'})
    for name in sorted(allowed):
        count = names.count(name)
        if count == 0 and name not in declaration['optional_trace_fields']:
            out.append({'category':'trace-contract','code':'missing-field','field':name})
        if count > 1:
            out.append({'category':'trace-contract','code':'duplicate-field','field':name})
        if any(x.attrib.get('key')==name and x.text is None for x in tree.findall('entry')):
            out.append({'category':'trace-contract','code':'missing-field-value','field':name})
    if any(name not in allowed for name in names):
        out.append({'category':'trace-contract','code':'undeclared-field'})
    return out


def structural_result(run, root, scenario):
    declaration = contract(root, scenario)
    checks = {}
    for lane in ('oracle','postgresql'):
        path = Path(run)/'cases/operations/1/execution'/lane/'journey.xml'
        checks[lane] = trace_diagnostics(path, declaration)
    return seal({'contract_version':VERSION, 'scenario':scenario, 'lanes':checks,
                 'passed':not any(checks.values())})
