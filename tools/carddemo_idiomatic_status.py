"""Verified dated screen-group receipt; historical measurements remain immutable."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize

PATH = 'docs/modernization/carddemo-cosgn00-2026-10-18.json'
INPUT = 'docs/modernization/carddemo-cosgn00-evidence-2026-10-18/publication-input.json'
CLASSES = ('SignonService', 'SignonRules')


def bound(root, reference):
    path = Path(reference['path'])
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('idiomatic-path')
    raw = (Path(root)/path).read_bytes()
    if sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('idiomatic-evidence-hash')
    return raw


def inputs(root):
    root = Path(root)
    if not (root/PATH).exists():
        return []
    group = json.loads((root/PATH).read_bytes())
    manifest = json.loads(bound(root, group['manifest']))
    return [PATH, *[group[k]['path'] for k in ('receipt', 'mutations', 'scope', 'baseline', 'manifest')], *manifest]


def load(root, path=PATH):
    root = Path(root)
    if not (root/path).exists():
        return None
    group = json.loads((root/path).read_bytes())
    if group['schema'] != 'carddemo-idiomatic-group/1' or group['unsigned'] is not True:
        raise ValueError('idiomatic-group-shape')
    for name, expected in json.loads(bound(root, group['manifest'])).items():
        bound(root, dict(path=name, sha256=expected))
    receipt = json.loads(bound(root, group['receipt']))
    scope = json.loads(bound(root, group['scope']))
    nodes = ET.fromstring(bound(root, group['mutations'])).findall('mutation')
    old_nodes = ET.fromstring(bound(root, group['baseline'])).findall('mutation')
    current = summarize(nodes, CLASSES)
    previous = summarize(old_nodes, ('SignonService',))
    counts = dict(Counter(n.attrib['status'] for n in nodes))
    old_counts = dict(Counter(n.attrib['status'] for n in old_nodes))
    gates = receipt['gates']; m = gates['mutation']; idiomatic = m['idiomatic_java']
    expected = {'api-reference', 'browser-reference', 'mutation-reference', 'browser', 'mutation', 'ci-jobs'}
    if (receipt['unsigned'] is not True or receipt['acceptance_complete'] is not True
        or receipt['status'] != 'proved-in-ci' or receipt['remaining_evidence_gaps']
        or set(gates) != expected or any(g.get('passed') is not True for g in gates.values())
        or group['date'] != receipt['date'] or group['program'] != scope['program'] or idiomatic['program'] != scope['program']
        or set(receipt['scope']['programs']) != {'COSGN00C','COMEN01C','COACTVWC','COACTUPC','COPAUS0C','COPAUS1C'}
        or counts != m['status_counts'] or len(nodes) != m['total'] or counts.get('KILLED',0) != m['killed']
        or not nodes or 10*m['killed'] < 9*m['total'] or m['threshold'] != 90 or m['missing_screen_handlers']
        or abs(m['percent']-100*m['killed']/m['total']) > 1e-9
        or m['report']['sha256'] != group['mutations']['sha256']
        or idiomatic['previous']['sha256'] != group['baseline']['sha256'] or idiomatic['passed'] is not True
        or current != idiomatic['current'] or previous != idiomatic['previous']['classes']
        or not all(row['passed'] for row in current.values()) or idiomatic['threshold'] != 90
        or scope['remaining_statement_engine_programs'] != idiomatic['remaining_statement_engine_programs']):
        raise ValueError('idiomatic-proof-denominator')
    browser = gates['browser']; api = gates['api-reference']
    if (browser['interactions'] != browser['required'] or browser['interactions'] <= 0
        or any(gates[k]['interactions'] != browser['interactions']
            or gates[k]['completed_cases'] != gates[k]['planned_cases'] or gates[k]['completed_cases'] <= 0
            or gates[k]['programs_compared'] != 6 or gates[k]['programs_required'] != 6
            for k in ('api-reference','browser-reference','mutation-reference'))):
        raise ValueError('idiomatic-scenario-denominator')
    return dict(date=group['date'],program=group['program'],run_id=receipt['run_id'],
        source_head=receipt['source_head'],tested_commit=receipt['tested_commit'],
        cases=api['completed_cases'],interactions=browser['interactions'],
        total=len(nodes),killed=counts['KILLED'],status_counts=counts,
        previous_total=len(old_nodes),previous_killed=old_counts['KILLED'],
        current=current,previous=previous,
        remaining_statement_engine_programs=scope['remaining_statement_engine_programs'],
        other_handwritten_programs=scope['other_handwritten_programs'],
        remaining_evidence_gaps=group['remaining_evidence_gaps'],path=PATH,unsigned=True)


def paragraph(value):
    if value is None:
        return 'No dated idiomatic screen-group proof is published.'
    ratio = lambda killed,total: f'{killed}/{total} ({100*killed/total:.2f}%)'
    rows = '; '.join(name+': '+ratio(row['killed'],row['total']) for name,row in value['current'].items())
    return (f"As of {value['date']}, {value['program']} idiomatic Java passed CI run {value['run_id']}: "
        f"{value['cases']} journeys and {value['interactions']}/{value['interactions']} API/browser interactions. "
        'Strict full-scope KILLED/all-generated: '+ratio(value['killed'],value['total'])+
        '; historical baseline '+ratio(value['previous_killed'],value['previous_total'])+'. '+rows+'. '
        'Remaining statement-engine programs: '+', '.join(value['remaining_statement_engine_programs'])+'. '
        'Other existing hand-written orchestration: '+', '.join(value['other_handwritten_programs'])+'. '
        'Open gaps: '+'; '.join(value['remaining_evidence_gaps'])+'. '
        'No survivor, uncovered mutant or timeout is waived. Final publication CI and merge approval are separate. '
        'Unsigned; no signing, import, activation, Phase 2 or release authority.')


def render(value):
    lines = ['# CardDemo idiomatic screen-group receipt - '+value['date'], '', paragraph(value), '',
        'Source head: `'+value['source_head']+'`; tested commit: `'+value['tested_commit']+'`.', '',
        '| Class | Previous KILLED / all | Current KILLED / all |', '|---|---|---|']
    for name,row in value['current'].items():
        old = value['previous'].get(name)
        baseline = f"{old['killed']}/{old['total']}" if old else 'new class'
        lines.append(f"| {name} | {baseline} | {row['killed']}/{row['total']} |")
    lines += ['', 'Non-killed mutants in the completed group:']
    for name,row in value['current'].items():
        for mutant in row['non_killed']:
            lines.append(f"- {name}.{mutant['method']} line {mutant['line']}: {mutant['status']}; {mutant['description']}.")
    lines += ['', 'Surviving sign-on mutations remove intermediate COMMAREA assignments; later routing can overwrite these values. They remain unproved distinctions, not equivalence waivers.',
        '', '[Original receipt, all seven CI archives, full mutant inventory and hashes](carddemo-cosgn00-evidence-2026-10-18/).',
        'This supersedes the implementation classification for COSGN00C only. Earlier dated receipts and their measurements remain unchanged.', '']
    return '\n'.join(lines)


def publish_ci(root):
    root = Path(root)
    raw = (root/INPUT).read_bytes()
    if (root/PATH).exists() and (root/PATH).read_bytes() != raw:
        raise ValueError('idiomatic-publication-already-different')
    (root/PATH).write_bytes(raw)
    value = load(root)
    (root/Path(PATH).with_suffix('.md')).write_text(render(value),encoding='utf-8',newline='\n')
    readme = root/'factory/carddemo-web/README.md'
    text = readme.read_text(encoding='utf-8')
    start, end = '<!-- idiomatic-group-status:start -->', '<!-- idiomatic-group-status:end -->'
    if start not in text:
        text += '\n'+start+'\n'+end+'\n'
    before, rest = text.split(start,1); _, after = rest.split(end,1)
    text = before+start+'\n'+paragraph(value)+'\n'+end+after
    readme.write_text(text,encoding='utf-8',newline='\n')


if __name__ == '__main__':
    publish_ci(Path(__file__).resolve().parents[1])
