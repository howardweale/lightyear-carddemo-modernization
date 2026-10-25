"""Validate additive survivor accounting; never turn an argument into a kill."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import subprocess

RECORD = 'docs/factory/intcalc-m1-triage-2026-10-23.json'
PLAN = 'docs/factory/posttran-phase2-plan-2026-10-16.json'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def safe_path(value):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value,
            'unsafe-binding-path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(p not in ('', '.', '..') for p in value.split('/')),
            'unsafe-binding-path')
    return value


def validate(record, read):
    require(record['schema'] == 'intcalc-m1-triage/1' and record['program'] == 'INTCALC', 'triage-schema')
    require(record['raw_counts'] == dict(all=424, killed=311, survivors=113, kill_rate='311/424',
            required_kills=382, additional_kills_needed=71), 'raw-counts-changed')
    require(record['triage_complete'] is True and record['m1_complete'] is False, 'scope-overclaim')
    for key in ('measurement_credit', 'release_authorized', 'native_equivalence_claim'):
        require(record[key] is False, 'scope-overclaim')
    require(record['sites_removed'] == 0, 'survivors-removed')
    bindings = {**record['source_bindings'], **record['supporting_records']}
    require(len(bindings) == len(record['source_bindings']) + len(record['supporting_records']), 'duplicate-binding')
    for path, digest in bindings.items():
        require(sha256(read(safe_path(path))).hexdigest() == digest, 'triage-source-drift')
    arguments = record['arguments']
    ids = {item['id'] for item in arguments}
    require(len(arguments) == len(ids) == 22 and all(item['argument'].strip() and item['scope'].strip()
            for item in arguments), 'argument-inventory')
    rows = record['mutants']
    require(len(rows) == len({item['id'] for item in rows}) == 113, 'survivor-inventory')
    for item in rows:
        require(item['argument_id'] in ids and item['category'] == 'equivalent', 'unbound-argument')
        require(item['counted_as_kill'] is False and item['raw_status'] == 'evidence-gap', 'argument-is-not-kill')
        require(item['source_path'] in record['source_bindings'] and
                item['source_sha256'] == record['source_bindings'][item['source_path']], 'mutant-source-binding')
        lines = read(item['source_path']).decode('utf-8').splitlines()
        require(type(item['line']) is int and type(item['end_line']) is int and
                1 <= item['line'] <= item['end_line'] <= len(lines), 'mutant-source-span')
        require(item['paragraph'] and item['operator'] and len(item['retained_record_sha256']) == 64, 'mutant-record')
    require(dict(Counter(item['paragraph'] for item in rows)) == record['paragraph_counts'], 'paragraph-counts')
    require(record['category_counts'] == {'equivalent': 113, 'missing-scenario': 0, 'timeout': 0, 'error': 0}, 'category-counts')
    require(sum(item['targeted_cases'] or 0 for item in rows) == 6000, 'targeted-counts')
    require(sum(item['fresh_compiler_identity'] for item in rows) == 2, 'compiler-counts')
    require(sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest() ==
            '512d4d313b9b8d0d381a4f44d024f1d4d1707194fee3c840fde41addcc4c2bdb', 'reviewed-record-content-changed')
    return dict(schema='intcalc-m1-triage-validation/1', survivors=113, arguments=22,
                raw_killed=311, denominator=424, additional_kills_claimed=0,
                record_sha256=sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                m1_complete=False, release_authorized=False)


def posttran_paths(plan, names):
    require(isinstance(plan['bound_files'], dict) and len(plan['bound_files']) == 182, 'posttran-bound-inventory')
    require(isinstance(plan['candidate_files'], dict) and len(plan['candidate_files']) == 2, 'posttran-candidate-inventory')
    return {safe_path(p) for p in (*plan['bound_files'], *plan['candidate_files'], PLAN)} | {
        p for p in names if p.startswith(('docs/factory/posttran-', 'spec/mainframe/posttran-independent/'))}


def check_posttran(repo, base, head):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    base = git('rev-parse', '--verify', base + '^{commit}').decode().strip()
    head = git('rev-parse', '--verify', head + '^{commit}').decode().strip()
    names = git('ls-tree', '-r', '--name-only', base).decode().splitlines()
    protected = posttran_paths(json.loads(git('show', base + ':' + PLAN)), names)
    changed = set(filter(None, git('diff', '--no-renames', '--name-only', '-z', base, head).decode().split('\0')))
    require(not changed & protected, 'posttran-bound-path-changed')
    return dict(base=base, head=head, protected_paths=len(protected), blocked_paths=[], automatic_expiry=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--base')
    parser.add_argument('--head', default='HEAD')
    args = parser.parse_args()
    result = validate(json.loads((args.root / RECORD).read_bytes()), lambda p: (args.root / p).read_bytes())
    if args.base:
        result['posttran_fence'] = check_posttran(args.root, args.base, args.head)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
