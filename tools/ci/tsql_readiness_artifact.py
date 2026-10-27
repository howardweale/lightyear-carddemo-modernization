"""Check public ten-pair artifact closure; never certify native execution.

This independent read-only layer checks retained bytes and selectors. It does
not connect to databases, load a provider, sign, or substitute for qualified
coverage/control provenance and comparator replay.
"""
import json
from pathlib import Path, PurePosixPath
import re

from tools.ci import tsql_readiness_ten as harness


def require(condition, reason):
    if not condition:
        raise ValueError('tsql-artifact-' + reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate-json-key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('tsql-artifact-nonfinite-json')


def verify(root, artifact, *, expected_ci, expected_harness_sha256,
           expected_bridge_sha256, expected_engine_profiles):
    """Expected bindings come from the reviewer, never from the artifact itself."""
    artifact = Path(artifact)
    require(artifact.is_dir() and not artifact.is_symlink(), 'root')
    require(all(not p.is_symlink() for p in artifact.parents), 'root-link')
    present = set()
    total = 0
    for path in artifact.rglob('*'):
        require(not path.is_symlink(), 'link')
        if path.is_dir():
            continue
        require(path.is_file(), 'regular-file')
        size = path.stat().st_size
        require(size <= 20_000_000, 'file-size')
        total += size
        require(total <= 100_000_000, 'total-size')
        present.add(path.relative_to(artifact).as_posix())
    seen = set()

    def read(name, expected=None):
        pure = PurePosixPath(name)
        require(not pure.is_absolute() and '\\' not in name and ':' not in name
                and all(p not in ('..', '.') for p in pure.parts)
                and pure.as_posix() == name, 'path')
        require(name in present and name not in seen, 'missing-or-reused-file')
        seen.add(name)
        raw = (artifact / name).read_bytes()
        require(len(raw) <= 20_000_000, 'file-size')
        if expected is not None:
            require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected)
                    and harness.sha(raw) == expected, 'hash')
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)
        require(isinstance(value, dict), 'object')
        return value, harness.sha(raw)

    ci_keys = {'GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'}
    require(set(expected_ci) == ci_keys and all(isinstance(v, str) and v for v in expected_ci.values()), 'expected-ci')
    require(re.fullmatch('[0-9a-f]{40}', expected_ci['GITHUB_SHA']) is not None, 'expected-head')
    for digest in (expected_harness_sha256, expected_bridge_sha256):
        require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), 'expected-digest')
    plan, plan_sha = read('plan.json')
    require(plan.get('schema') == 'public-tsql-ten-plan/1' and plan.get('ci') == expected_ci, 'plan-binding')
    require(plan.get('native_capture') is True and plan.get('signed') is False
            and type(plan.get('model_calls')) is int and plan['model_calls'] == 0, 'plan-scope')
    require(plan.get('harness_sha256') == expected_harness_sha256
            and plan.get('semantic_bridge_sha256') == expected_bridge_sha256
            and plan.get('configured_engine_profiles') == expected_engine_profiles, 'implementation-binding')
    selection = json.loads((Path(root) / 'docs/tsql-readiness/selection.json').read_bytes())
    require(plan.get('selection') == selection, 'selection-binding')
    items = harness.intake(root, selection)
    summary, summary_sha = read('summary.json')
    require(summary.get('schema') == 'public-tsql-ten-summary/1' and summary.get('plan_sha256') == plan_sha, 'summary-binding')
    require(summary.get('signed') is False and type(summary.get('model_calls')) is int
            and summary['model_calls'] == 0 and type(summary.get('passed')) is bool, 'summary-scope')
    entries = summary.get('procedures')
    require(isinstance(entries, list) and [r.get('procedure_id') for r in entries] == list(harness.IDS), 'procedure-inventory')
    index = 0
    verdicts = []
    for item, entry in zip(items, entries):
        receipt, unused = read(item['id'] + '.json', entry.get('receipt_sha256'))
        require(receipt.get('schema') == 'public-tsql-procedure-receipt/1'
                and receipt.get('procedure_id') == item['id'] and receipt.get('plan_sha256') == plan_sha
                and receipt.get('ci') == expected_ci, 'procedure-binding')
        require(receipt.get('assets') == item['assets'] and receipt.get('declared_cases') == item['cases']
                and receipt.get('calling_convention') == item['calling_convention'], 'public-input-binding')
        require(receipt.get('signed') is False and type(receipt.get('model_calls')) is int
                and receipt['model_calls'] == 0, 'procedure-scope')
        expected = [(variant, case['id'], repeat) for variant in ('correct', 'wrong')
                    for case in item['cases'] for repeat in range(1, case['repeated_runs'] + 1)]
        rows = receipt.get('cases')
        require(isinstance(rows, list) and len(rows) == len(expected), 'case-inventory')
        for row, selector in zip(rows, expected):
            index += 1
            require(type(row.get('repeat')) is int and
                    (row.get('variant'), row.get('case_id'), row['repeat']) == selector
                    and row.get('procedure_id') == item['id'], 'selector')
            folder = 'pair-%03d/' % index
            raw_receipt, unused = read(folder + 'receipt.json', row.get('receipt_sha256'))
            require(raw_receipt == {k: v for k, v in row.items() if k != 'receipt_sha256'}, 'case-receipt-binding')
            files = row.get('files')
            require(isinstance(files, dict) and set(files) <= {'source.json', 'target.json', 'comparison.json'}, 'case-files')
            retained = {name: read(folder + name, digest)[0] for name, digest in files.items()}
            require(type(row.get('cleanup_complete')) is bool and isinstance(row.get('cleanup_failures'), list), 'cleanup')
            require(not row['cleanup_complete'] or not row['cleanup_failures'], 'cleanup-contradiction')
            require(row.get('status') in ('compared', 'error'), 'case-status')
            if row['status'] == 'compared':
                require(set(files) == {'source.json', 'target.json', 'comparison.json'}, 'compared-files')
                require(row.get('verdict') == retained['comparison.json'].get('verdict'), 'comparison-verdict')
        outcome = harness.verdict(rows, expected)
        require(receipt.get('verdict') == entry.get('verdict') == outcome, 'procedure-verdict')
        verdicts.append(outcome)
    require(type(summary.get('native_pair_count')) is int and summary['native_pair_count'] == index, 'pair-count')
    require(summary['passed'] == all(v == 'equivalent-on-declared-public-cases' for v in verdicts), 'summary-verdict')
    require(present == seen, 'unexpected-file')
    return dict(schema='public-tsql-artifact-integrity/1', integrity_complete=True,
                plan_sha256=plan_sha, summary_sha256=summary_sha, files=len(seen),
                case_pairs=index, reported_passed=summary['passed'],
                native_execution_verified=False, comparator_replayed=False,
                coverage_qualification_verified=False, signed=False, model_calls=0,
                scope='retained byte, selector and aggregate integrity only; not native or customer equivalence')
