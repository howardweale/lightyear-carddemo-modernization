"""Verified, shared APPL-RESULT selection for status, guide and decision packet."""
from hashlib import sha256
import json
from pathlib import Path
from lightyear_control_tower.decisions import digest
from lightyear_control_tower.factory_supersessions import CURRENT, identity, normalized_hash

PATH = 'docs/factory/appl-result-contract-selection-2026-10-18.json'

def load(root):
    path=Path(root)/PATH
    if not path.exists():return None
    value=json.loads(path.read_bytes())
    if value['schema']!='appl-result-contract-selection/1':raise ValueError('appl-selection-schema')
    if {r['program'] for r in value['records']}!={'INTCALC','POSTTRAN'} or len(value['records'])!=2:
        raise ValueError('appl-selection-programs')
    for row in value['records']:
        raw=(Path(root)/row['path']).read_bytes();contract=json.loads(raw)
        actual=dict(file_sha256=sha256(raw).hexdigest(),template_queue_sha256=digest(contract),
                    normalized_contract_sha256=normalized_hash(contract),item_set_sha256=identity(contract),
                    members=len(contract['details']['items']),class_proof_sha256=contract['details']['class_proof_sha256'],
                    program=contract['program'])
        if any(row[k]!=v for k,v in actual.items()):raise ValueError('appl-selection-binding')
        if CURRENT[identity(contract)]['selected']!=normalized_hash(contract):raise ValueError('appl-selection-importer')
    return value


def markdown(value):
    if value is None:return 'No current APPL-RESULT contract selection is recorded.'
    lines=['APPL-RESULT selection as of '+value['prepared_on']+'. Unsigned; no authority inferred.', '',
           '| Program | Selected contract | Members | Template queue ID | Class proof | Re-review required |',
           '|---|---|---:|---|---|---|']
    for r in value['records']:
        lines.append(f"| {r['program']} | [{Path(r['path']).name}]({r['path'].removeprefix('docs/factory/')}) | {r['members']} | `factory-{r['template_queue_sha256']}` | `{r['class_proof_sha256']}` | {r['review_required']} |")
    lines+=['', 'INTCALC position 2 is a template: binding the verified position-1 decision changes its final queue hash. The final bound hash must be checked before import.', '',
            *[r['program']+': '+r['reason'] for r in value['records']]]
    return '\n'.join(lines)
