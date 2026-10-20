"""Read and verify the newest dated public selection; never infer approval."""
from datetime import date
from hashlib import sha256
from pathlib import Path
import json
import re
import subprocess
from .decisions import digest
from .requests import confined, read_bytes, read_json

PATTERN = re.compile(r'appl-result-contract-selection-(\d{4}-\d{2}-\d{2})\.json')


def selection_path(root):
    folder = confined(root, 'docs/factory')
    candidates = []
    for path in folder.glob('appl-result-contract-selection-*.json'):
        match = PATTERN.fullmatch(path.name)
        if match is None:
            raise ValueError('appl-selection-filename')
        candidates.append((date.fromisoformat(match[1]), path.name))
    if not candidates:
        return None
    return 'docs/factory/' + max(candidates)[1]


def load_selection(root, *, committed_only=False):
    from .factory_supersessions import identity, normalized_hash
    name = selection_path(root)
    # Intake additionally checks the Git selection inventory, including deletion
    # of every selected record. A plain queue fixture without Git or selection
    # has no selected-record baseline; its live/journal overlap guards still run.
    commit = None
    if committed_only and (name is not None or (Path(root) / '.git').exists()):
        from .factory_import import committed
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        tracked = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit, '--', 'docs/factory/'],
                                          cwd=root, text=True).splitlines()
        dated = [p for p in tracked if PATTERN.fullmatch(Path(p).name)]
        if name != (max(dated) if dated else None):
            raise ValueError('appl-selection-uncommitted')
    if name is None:
        return None
    selected_raw = read_bytes(confined(root, name))
    if committed_only and committed(root, commit, name) != selected_raw:
        raise ValueError('appl-selection-uncommitted')
    value = json.loads(selected_raw)
    if (value.get('schema') != 'appl-result-contract-selection/1'
            or value.get('prepared_on') != PATTERN.fullmatch(Path(name).name)[1]
            or value.get('signed') is not False or value.get('execution_authorized') is not False):
        raise ValueError('appl-selection-schema')
    rows = value.get('records', [])
    if len(rows) != 2 or {r['program'] for r in rows} != {'INTCALC', 'POSTTRAN'}:
        raise ValueError('appl-selection-programs')
    for row in rows:
        if not row['path'].startswith('docs/factory/'):
            raise ValueError('appl-selection-path')
        raw = read_bytes(confined(root, row['path']))
        if committed_only and committed(root, commit, row['path']) != raw:
            raise ValueError('appl-selection-uncommitted')
        contract = json.loads(raw)
        if contract.get('kind') != 'equivalence-review':
            raise ValueError('appl-selection-kind')
        actual = dict(file_sha256=sha256(raw).hexdigest(), template_queue_sha256=digest(contract),
                      normalized_contract_sha256=normalized_hash(contract), item_set_sha256=identity(contract),
                      members=len(contract['details']['items']), class_proof_sha256=contract['details']['class_proof_sha256'],
                      program=contract['program'])
        if any(row[k] != v for k, v in actual.items()):
            raise ValueError('appl-selection-binding')
    return value
