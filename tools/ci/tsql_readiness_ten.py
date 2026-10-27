"""CI-only unsigned native public-pair harness. Provisioning is a separate boundary.

Uses supplied NativeEngine instances, never credentials, Docker, keys or signing.
Unit-test stubs do not count as native execution evidence.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

IDS = ('len', 'integer-division', 'isnull-length', 'datediff-day',
       'datediff-year', 'round-negative', 'money-scale', 'bit',
       'uuid-case', 'trailing-varchar')
CORPUS = 'data-modernization/tsql-procedures/typed-corpus-r1/corpus.json'
CORPUS_SHA256 = '57861a00427bc73d813c702016cc4087f8d31d222ce742c3436e644fee6725d4'
PREFIX = 'data-modernization/tsql-procedures/'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def ci_boundary():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('tsql-readiness-ci-only')
    now = datetime.now(timezone.utc)
    if datetime(2026, 10, 30, 15, tzinfo=timezone.utc) <= now < datetime(2026, 10, 31, 3, tzinfo=timezone.utc):
        raise ValueError('friday-run-ci-blackout')


def asset(root, descriptor):
    relative = descriptor['path']
    if (not isinstance(relative, str) or not relative.startswith(PREFIX)
            or '\\' in relative or '..' in Path(relative).parts):
        raise ValueError('public-asset-path')
    root = Path(root).resolve()
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise ValueError('public-asset-link')
    if not path.resolve().is_relative_to(root):
        raise ValueError('public-asset-escape')
    raw = path.read_bytes().replace(b'\r\n', b'\n')
    if len(raw) > 1_000_000 or sha(raw) != descriptor['sha256']:
        raise ValueError('public-asset-hash')
    return raw.decode('utf-8')


def intake(root, selection):
    if (selection.get('schema') != 'public-tsql-readiness-ten/1'
            or selection.get('ids') != list(IDS)
            or selection.get('corpus', {}).get('path') != CORPUS
            or selection.get('corpus', {}).get('sha256') != CORPUS_SHA256):
        raise ValueError('ten-pair-selection')
    corpus = json.loads(asset(root, selection['corpus']))
    if corpus.get('public_fixture') is not True or corpus.get('authored_original') is not True:
        raise ValueError('public-corpus-required')
    rows = corpus['procedures']
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('duplicate-procedure')
    known = {r['id']: r for r in rows}
    if not set(IDS) <= set(known):
        raise ValueError('public-procedure-missing')
    selected = [deepcopy(known[key]) for key in IDS]
    for item in selected:
        if not item['cases'] or item['expected']['policy_required'] or item.get('coverage_scenarios'):
            raise ValueError('public-case-or-policy')
        if (len({c['id'] for c in item['cases']}) != len(item['cases']) or any(
                type(c['repeated_runs']) is not int or not 1 <= c['repeated_runs'] <= 20 for c in item['cases'])):
            raise ValueError('public-case-inventory')
        # Every byte is checked before the first database operation.
        for descriptor in item['assets'].values():
            asset(root, descriptor)
    return selected


def verdict(rows, expected_cases):
    selectors = [(r['variant'], r['case_id'], r['repeat']) for r in rows]
    if sorted(selectors) != sorted(expected_cases) or len(set(selectors)) != len(selectors):
        return 'insufficient-evidence'
    if any(r.get('cleanup_complete') is not True or r.get('status') == 'error' for r in rows):
        return 'execution-error'
    correct = [r for r in rows if r['variant'] == 'correct']
    wrong = [r for r in rows if r['variant'] == 'wrong']
    if any(r['verdict'] == 'divergent' for r in correct):
        return 'divergent'
    if not wrong or any(r['verdict'] != 'divergent' for r in wrong):
        return 'insufficient-evidence'
    return 'equivalent-on-declared-public-cases' if correct and all(
        r['verdict'] == 'equivalent' for r in correct) else 'insufficient-evidence'


def run_suite(root, output, source_engine, target_engine, bridge, selection, qualification=None):
    ci_boundary()
    from lightyear_data.tsql_procedures.native import NativeEngine
    from lightyear_data.tsql_procedures.inventory import parse
    from lightyear_data.tsql_procedures.semantics import contract
    from lightyear_data.tsql_procedures.policy import profile
    from lightyear_data.tsql_procedures.comparison_v9 import compare
    if (type(source_engine) is not NativeEngine or type(target_engine) is not NativeEngine
            or source_engine.engine != 'sqlserver' or target_engine.engine != 'postgresql'
            or source_engine.owned or target_engine.owned):
        raise ValueError('fresh-native-engine-pair-required')
    root = Path(root).resolve(); output = Path(output).resolve()
    if output.is_relative_to(root / 'data-modernization'):
        raise ValueError('evidence-must-not-overwrite-inputs')
    items = intake(root, selection)
    # Bind the actual parser contract for every source before provisioning.
    for item in items:
        source = asset(root, item['assets']['source'])
        syntax = parse(source, ('dotnet', str(bridge)), allow_sqlglot=False)
        if syntax['status'] != 'parsed':
            raise ValueError('native-source-syntax-required')
        semantic = contract(syntax)
        if len(semantic['procedures']) != 1:
            raise ValueError('one-procedure-per-intake')
        item['source_syntax'] = syntax['ast']
        item['procedure_contract'] = semantic['procedures'][0]
    output.mkdir(parents=True, exist_ok=False)
    def write(path, value):
        raw = canonical(value)
        with path.open('xb') as stream:
            stream.write(raw)
        return sha(raw)
    ci = {key: os.environ.get(key) for key in ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')}
    if any(not value for value in ci.values()):
        raise ValueError('ci-identity-required')
    plan = dict(schema='public-tsql-ten-plan/1', ci=ci, selection=selection,
                native_capture=True, signed=False, model_calls=0,
                qualification_supplied=qualification is not None,
                semantic_bridge_sha256=sha(Path(bridge).read_bytes()),
                harness_sha256=sha(Path(__file__).read_bytes().replace(b'\r\n', b'\n')),
                configured_engine_profiles=dict(source=source_engine.engine_profile, target=target_engine.engine_profile))
    plan_sha = write(output / 'plan.json', plan)
    engines = {'source': source_engine, 'target': target_engine}
    receipts = []; index = 0
    for item in items:
        rows = []; expected = []
        for variant in ('correct', 'wrong'):
            for case in item['cases']:
                for repeat in range(1, case['repeated_runs'] + 1):
                    ci_boundary(); index += 1
                    expected.append((variant, case['id'], repeat))
                    folder = output / ('pair-%03d' % index); folder.mkdir()
                    row = dict(procedure_id=item['id'], variant=variant, case_id=case['id'], repeat=repeat,
                               status='error', verdict='insufficient-evidence', cleanup_complete=False, files={})
                    try:
                        lanes = {}
                        for lane, engine in engines.items():
                            setup = 'source-setup' if lane == 'source' else ('target-setup' if variant == 'correct' else 'wrong-setup')
                            proc = 'source' if lane == 'source' else variant
                            baseline = engine.provision('b%03d' % index, asset(root, item['assets'][setup]), asset(root, item['assets'][proc]))
                            reset = engine.reset(baseline, 'r%03d' % index)
                            execution = deepcopy(item); execution['cases'] = [case]
                            execution['case_binding'] = dict(parameters=case['parameters'], case_sha256=sha(canonical(case['parameters'])))
                            if lane == 'target': execution['target_source'] = asset(root, item['assets'][proc])
                            lanes[lane] = engine.call(reset, execution)
                            lanes[lane]['baseline'] = baseline
                            row['files'][lane+'.json'] = write(folder / (lane+'.json'), lanes[lane])
                        comparison = compare(lanes['source'], lanes['target'], profile(item), qualification)
                        row['files']['comparison.json'] = write(folder / 'comparison.json', comparison)
                        # Recompute from retained bytes, never trust a claimed verdict alone.
                        again = compare(json.loads((folder/'source.json').read_bytes()),
                                        json.loads((folder/'target.json').read_bytes()), profile(item), qualification)
                        if canonical(again) != canonical(comparison): raise ValueError('replay-mismatch')
                        row.update(status='compared', verdict=comparison['verdict'])
                    except Exception as error:
                        # Raw exception text may contain connector information; retain type only.
                        row['error_type'] = type(error).__name__
                    finally:
                        failures = []
                        for lane, engine in engines.items():
                            for database in sorted(engine.owned):
                                try: engine.drop(database)
                                except Exception as error: failures.append(dict(lane=lane, error_type=type(error).__name__))
                        row['cleanup_complete'] = not failures and not any(e.owned for e in engines.values())
                        row['cleanup_failures'] = failures
                    row['receipt_sha256'] = write(folder / 'receipt.json', row)
                    rows.append(row)
                    if not row['cleanup_complete']:
                        raise RuntimeError('owned-database-cleanup-incomplete')
        receipt = dict(schema='public-tsql-procedure-receipt/1', procedure_id=item['id'],
            assets=item['assets'], calling_convention=item['calling_convention'],
            declared_cases=item['cases'], plan_sha256=plan_sha, ci=ci, signed=False,
            verdict=verdict(rows, expected), cases=rows, model_calls=0,
            scope='declared authored public fixtures; not customer admission or independent attestation')
        receipts.append(dict(procedure_id=item['id'], verdict=receipt['verdict'],
            receipt_sha256=write(output / (item['id']+'.json'), receipt)))
    result = dict(schema='public-tsql-ten-summary/1', plan_sha256=plan_sha,
        procedures=receipts, native_pair_count=index, signed=False, model_calls=0,
        passed=len(receipts)==10 and all(r['verdict']=='equivalent-on-declared-public-cases' for r in receipts))
    write(output/'summary.json', result)
    return result
