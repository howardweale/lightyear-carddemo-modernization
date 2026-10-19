"""Verified account group status and additive dated publication, generated in CI."""
import json
from pathlib import Path
from tools.carddemo_account_evidence import json_document
from tools.carddemo_account_group import load_account_group
from tools.carddemo_account_proof import GROUPS

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'docs/modernization/carddemo-account-publication-index.json'


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def _proof(root):
    root = Path(root)
    if not (root/INDEX).exists(): return None
    return load_account_group(root, None, json_document((root/INDEX).read_bytes()))


def _record(proof):
    identity, scope, mutation = proof['identity'], proof['scope'], proof['mutation']
    return {'schema': 'carddemo-account-publication/1', **identity, **scope,
        'measurement_run_url': 'https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/' + str(identity['run_id']),
        'measurement_date': identity['measurement_date'], 'original_receipt_date': identity['original_receipt_date'],
        'tested_parents': proof['git_sources']['tested_parents'], 'tested_tree': proof['git_sources']['tree'],
        'measurement_base_note': 'Run began before retargeting; tested tree equals the integrated source tree. Final current-main validation is a separate exact-head audit.',
        'hash_closure': proof['hash_closure'], 'descriptor': proof['descriptor'],
        'scope_binding': proof['scope_binding'], 'scenarios': proof['scenarios'],
        'observations': proof['observations'],
        'mutation': {key: mutation[key] for key in ('killed', 'total', 'percent', 'status_counts', 'denominator')},
        'classes': {name: mutation[group][name] for group, names in GROUPS.items() for name in names},
        'merge_approved': False, 'activation_authorized': False, 'phase2_authorized': False}


def paragraph(record):
    if record is None: return 'Account group proof has not been published.'
    score = record['mutation']
    return (f"COACTUPC: {record['validation_paragraph_count']} validation paragraphs in {len(record['groups'])} groups; "
        f"120 journeys and 678 interactions per API, browser and mutation-reference run. "
        f"Strict mutation result {score['killed']}/{score['total']} ({score['percent']:.8f}%), KILLED only. "
        f"Measured source {record['source_head']}, run {record['run_id']}; publication {record['publication_date']}. "
        'Whole account screen remains incomplete. Statement engines remain for ' +
        ', '.join(record['remaining_statement_engine_programs']) + '. No merge or execution authority.')


def outputs(record):
    stem = 'docs/modernization/carddemo-account-' + record['publication_date']
    text = '# COACTUPC group proof\n\n' + paragraph(record) + '\n\n'
    text += f"Measurement date: {record['measurement_date']}; original receipt date: {record['original_receipt_date']}.\n\n"
    text += record['measurement_base_note'] + '\n\n| Class | Killed / all |\n| --- | ---: |\n'
    for name, row in record['classes'].items(): text += f"| {name} | {row['killed']} / {row['total']} |\n"
    text += '\n' + record['observations']['commarea'] + '\n'
    result = {stem+'.json': encoded(record), stem+'.md': text.encode()}
    for group, scope in record['groups'].items():
        name = group.removeprefix('account_').removesuffix('_java').replace('_', '-')
        row = {**record, 'schema': 'carddemo-account-group-publication/1', 'group': group,
               'group_scope': scope, 'group_classes': {n: record['classes'][n] for n in GROUPS[group]}}
        result[f'docs/modernization/carddemo-account-{name}-{record["publication_date"]}.json'] = encoded(row)
    return result


def load(root=ROOT):
    proof = _proof(root)
    if proof is None: return None
    record = _record(proof)
    for path, raw in outputs(record).items():
        if (Path(root)/path).exists() and (Path(root)/path).read_bytes() != raw:
            raise ValueError('account-publication-record-mismatch')
    return record


def inputs(root=ROOT):
    proof = _proof(root)
    if proof is None: return []
    record = _record(proof)
    return [INDEX, *proof['inputs'], *[p for p in outputs(record) if (Path(root)/p).is_file()]]


def publish_ci(output, root=ROOT):
    record = load(root)
    if record is None: raise ValueError('account-publication-input-missing')
    for path, raw in outputs(record).items():
        target = Path(output)/path; target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw: raise ValueError('account-publication-overwrite')
        target.write_bytes(raw)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True)
    publish_ci(parser.parse_args().out)
