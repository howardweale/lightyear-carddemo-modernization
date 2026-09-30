"""B04 closed runtime projection. No exception prose or private values escape.

The legacy projection is called unchanged. This module is a prospective input,
never a replacement exporter for earlier signed campaigns.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from lightyear_calibration.contracts import read_json, verify
from lightyear_calibration.journey_repair import public_api_matches
from tools.qualification_feedback import export as legacy_export

VERSION = 'qualified-feedback-v4-runtime'
EXCEPTIONS = frozenset(('NullPointerException', 'IllegalStateException',
    'IllegalArgumentException', 'IndexOutOfBoundsException', 'ClassCastException',
    'ArithmeticException', 'UnsupportedOperationException', 'AssertionError',
    'AssertionFailedError', 'ComparisonFailure', 'AdempiereException',
    'DBException', 'AdempiereUserError', 'AdempiereSystemError'))
PACKAGES = ('java.lang.', 'org.opentest4j.', 'org.junit.', 'junit.framework.',
            'org.assertj.', 'org.adempiere.exceptions.', 'org.compiere.util.')
FRAME = re.compile(r'^\s*at ([A-Za-z_$][\w.$]*)\.([\w$<>]+)\(([^():]+):(\d+)\)\s*$')
HEADER = re.compile(r'^(?:Caused by: )?([A-Za-z_$][\w.$]*(?:Exception|Error|Failure))(?::.*)?$')
# The source file combines candidate and support. Bounds, not filename alone,
# decide ownership. XML Properties entry order is explicitly not chronology.
STAGES = (
    ('customer', ('customer.id',)), ('product', ('product.id',)),
    ('order', ('order.id',)), ('shipment', ('firstShipment.id', 'shipment.id')),
    ('invoice', ('invoice.id',)), ('payment allocation', ('payment.id',)),
    ('credit', ('credit.id',)),
    ('reversal allocation', ('creditReversal.id', 'credit.reversalId', 'credit.finalStatus')),
    ('recovery', ('recoveryCustomer.id',)),
    ('concurrency', ('concurrency.firstValue', 'concurrency.secondValue')),
)


def masked_source(source):
    source = re.sub(r'\\u+([0-9a-fA-F]{4})', lambda m: chr(int(m[1], 16)), source)
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)


def stage(path, declaration):
    """Last declared lifecycle checkpoint, not a guess based on XML entry order.

    Omit missing, malformed, duplicate or undeclared traces. Values are ignored.
    This reports a public checkpoint stage, not a proof of execution chronology.
    """
    path = Path(path)
    if not path.exists(): return None
    raw = path.read_bytes()
    if len(raw) > 65536 or b'<!ENTITY' in raw.upper(): return None
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError:
        return None
    if tree.tag != 'properties': return None
    names = [e.attrib.get('key') for e in tree.findall('entry')]
    if len(names) != len(set(names)) or set(names)-set(declaration['trace_fields']): return None
    found = [label for label, fields in STAGES if any(f in names for f in fields)]
    return found[-1] if found else None


def stacks(log):
    """Only exception headers immediately followed by Java frames qualify.

    Ignore suppressed exceptions and log summaries. Repeated surefire copies
    deduplicate later. For chained exceptions retain the innermost complete
    stack, so application failures cannot be disguised as candidate throws.
    """
    blocks = []
    lines = log.splitlines()
    for i, line in enumerate(lines):
        header = HEADER.fullmatch(line)
        if not header: continue
        frames = []
        for text in lines[i+1:]:
            m = FRAME.fullmatch(text)
            if not m: break
            frames.append((m[1], m[2], m[3], int(m[4])))
        if frames: blocks.append((header[1], frames))
    return blocks


def locate(block, source):
    exception, frames = block
    masked = masked_source(source)
    boundary = re.search(r'\b(?:final\s+)?class\s+JourneySupport\b', masked)
    if boundary is None: return None, 'unresolved'
    end = masked[:boundary.start()].count('\n')+1
    top = frames[0]
    if top[0].split('.')[-1].split('$')[0] == 'JourneySupport': return None, 'support'
    candidate = next((f for f in frames if f[2] == 'LightyearOperationsTest.java'
                      and f[0].split('.')[-1].split('$')[0] == 'LightyearOperationsTest'
                      and 0 < f[3] < end), None)
    if candidate is None: return None, 'outside-candidate'
    if any(f[0].split('.')[-1].split('$')[0] == 'JourneySupport' for f in frames[:frames.index(candidate)]):
        return None, 'support'
    # The stack's method is candidate-owned text, but must also exist in source.
    method = candidate[1]
    declared = method if not method.startswith('lambda$') else method.split('$')[1]
    if declared not in ('<init>', '<clinit>') and not re.search(r'\b'+re.escape(declared)+r'\s*\(', masked[:boundary.start()]):
        return None, 'unresolved'
    if top == candidate or top[0].startswith(('org.junit.', 'org.opentest4j.', 'org.assertj.', 'junit.framework.')):
        origin = 'candidate'
    elif top[0].startswith(('org.compiere.', 'org.adempiere.')):
        origin = 'application'
    elif top[0].startswith('java.'):
        origin = 'candidate'
    else:
        return None, 'outside-candidate'
    simple = exception.rsplit('.', 1)[-1]
    label = simple if simple in EXCEPTIONS and exception.startswith(PACKAGES) else 'other'
    return {'category':'candidate-runtime-exception', 'exception_class':label,
            'thrown_by':origin, 'candidate_frame':{'method':method,'line':candidate[3]}}, None


def runtime(run, declaration, *, root, api):
    run = Path(run)
    source = (run/'inputs/operations.java').read_text(encoding='utf-8')
    result = []; suspects = []
    for lane in ('oracle', 'postgresql'):
        folder = run/'cases/operations/1/execution'/lane
        execution = read_json(folder/'execution.json'); verify(execution)
        if execution['exit_code'] == 0: continue
        log = folder/'maven.log'
        blocks = stacks(log.read_text(encoding='utf-8', errors='replace')) if log.exists() else []
        # Ambiguous roots never produce a partially guessed diagnostic.
        located = [locate(b, source) for b in blocks]
        values = []; reasons = []
        for value, reason in located:
            if reason: reasons.append(reason)
            elif value not in values: values.append(value)
        if reasons:
            suspects.append(lane); continue
        if len(values) != 1: continue
        value = values[0]
        checkpoint = stage(folder/'journey.xml', declaration)
        if checkpoint: value['public_stage'] = checkpoint
        line = masked_source(source).splitlines()[value['candidate_frame']['line']-1]
        # Export an API name only when the exact throwing line uniquely resolves
        # against the existing pinned public API index. Never invent a caller.
        resolved = []
        for symbol in re.findall(r'\b([A-Za-z_$][\w$]*)\s*\(', line):
            for match in public_api_matches(Path(root), symbol, api):
                name = match['declaring_type']+'.'+match['method']
                if name not in resolved: resolved.append(name)
        if len(resolved) == 1: value['api_call'] = resolved[0]
        result.append((lane, value))
    if suspects: return [], True
    unique = []
    for lane, value in result:
        if value in [v for _, v in unique]: continue
        unique.append((lane, value))
    return [{**v, 'lanes':'both' if sum(other == v for _, other in result) == 2 else 'one'} for _, v in unique], False


def export(run, declaration, *, root, api):
    out = legacy_export(run, declaration, root=root, api=api)
    gate = read_json(Path(run)/'gate.json'); verify(gate)
    if gate['status'] == 'contract-violation':
        # Only these declared structural codes/field names may leave the gate.
        codes = {'invalid-public-identifier','missing-public-rollback-witness','missing-public-lock-witness'}
        for findings in gate.get('checks',{}).get('public_contract',{}).values():
            for item in findings:
                if item.get('category') != 'trace-contract' or item.get('code') not in codes: continue
                value = {'category':'trace-contract','code':item['code']}
                if 'field' in item:
                    if item['field'] not in declaration['trace_fields']: continue
                    value['field'] = item['field']
                if value not in [{k:v for k,v in x.items() if k != 'id'} for x in out]:
                    out.append({'id':'structural-'+str(len(out)+1),**value})
        return out
    if gate['status'] != 'execution-failure': return out
    values, suspect = runtime(run, declaration, root=root, api=api)
    # A support/outside throw halts the whole attempt; even unrelated legacy
    # feedback must not hide it. Controller receives the separate local flag.
    if suspect: return []
    return out + [{'id':'runtime-'+str(i), **v} for i, v in enumerate(values, 1)]


def equipment_suspect(run, declaration, *, root, api):
    gate = read_json(Path(run)/'gate.json'); verify(gate)
    return gate['status'] == 'execution-failure' and runtime(run, declaration, root=root, api=api)[1]
