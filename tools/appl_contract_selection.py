"""Verified, shared APPL-RESULT selection for status, guide and decision packet."""
from hashlib import sha256
import json
from pathlib import Path
from lightyear_control_tower.factory_selection import load_selection, selection_path

# Historical compatibility name; current selection is resolved from dated data.
PATH = 'docs/factory/appl-result-contract-selection-2026-10-18.json'

def load(root):
    return load_selection(root)


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
