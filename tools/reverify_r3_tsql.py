"""CI-only public R3 re-verification; never reissues historical native receipts."""
import argparse
import datetime
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class Results(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.completed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.completed.append(test.id())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or not os.environ.get('TSQL_BRIDGE'):
        raise SystemExit('CI with built ScriptDom bridge required')
    if version('pglast') != '7.20':
        raise SystemExit('pglast 7.20 required')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'tests'))
    from lightyear_data.tsql_procedures import postgresql_syntax, postgresql_syntax_v8
    from lightyear_data.tsql_procedures.typed_corpus import build
    generated = build(root)
    corpus_path = 'data-modernization/tsql-procedures/typed-corpus-r1/corpus.json'
    corpus = json.loads(generated[corpus_path])
    if len(corpus['procedures']) != 43:
        raise SystemExit('R3 public corpus cardinality changed; review required')
    contracts = []
    # Re-run both current parser modules over every correct and wrong target.
    # Policy obligations remain visible; a parsed contract is not equivalence.
    for item in corpus['procedures']:
        for variant in ('correct', 'wrong'):
            asset = item['assets'][variant]
            raw = generated[asset['path']]
            if digest(raw) != asset['sha256'] or (root / asset['path']).read_bytes().replace(b'\r\n', b'\n') != raw:
                raise SystemExit('R3 corpus asset/hash drift')
            for module in (postgresql_syntax, postgresql_syntax_v8):
                value = module.contract(raw.decode('utf-8'))
                if value['parser'] != 'pglast-7.20' or value['source_sha256'] != digest(raw):
                    raise SystemExit('R3 parser provenance mismatch')
                contracts.append(dict(procedure=item['id'], variant=variant,
                    module=module.__name__, source=asset, contract=value))
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_tsql*.py')
    result = unittest.TextTestRunner(verbosity=2, resultclass=Results).run(suite)
    passed = (result.wasSuccessful() and result.testsRun > 0 and not result.skipped
              and not result.expectedFailures and not result.unexpectedSuccesses)
    # Bind all public implementation, tests and input assets; never read VM captures.
    files = subprocess.check_output(['git', 'ls-files', 'src/lightyear_data/tsql_procedures',
        'tests/test_tsql*.py', 'data-modernization/tsql-procedures', 'tools/tsql_scriptdom',
        'pyproject.toml', 'tools/reverify_r3_tsql.py', 'tools/export_tsql_r9.py',
        '.github/workflows/tsql-procedures.yml'], cwd=root).decode().splitlines()
    inputs = {p: digest(subprocess.check_output(['git', 'show', 'HEAD:' + p], cwd=root)) for p in files}
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()
    report = dict(schema='r3-pglast-public-reverification/1',
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_commit=head, pr_head=os.environ.get('R3_PR_HEAD'),
        ci=dict(run_id=os.environ.get('GITHUB_RUN_ID'), attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
                os=os.environ.get('RUNNER_OS')), pglast=version('pglast'), passed=passed,
        public_procedures=43, target_variants=86, parser_contracts=contracts,
        tests=dict(run=result.testsRun, passed_ids=result.completed,
            failures=[t.id() for t, _ in result.failures], errors=[t.id() for t, _ in result.errors],
            skipped=[t.id() for t, _ in result.skipped],
            expected_failures=[t.id() for t, _ in result.expectedFailures],
            unexpected_successes=[t.id() for t in result.unexpectedSuccesses]),
        inputs=inputs, native_capture_pairs_reverified=0,
        historical_native_result_reissued=False, full_r3_reverification_complete=False,
        model_calls=0, database_connections=0)
    args.out.mkdir(parents=True, exist_ok=False)
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    (args.out / 'report.json').write_bytes(raw)
    note = ('# R3 public re-verification — ' + report['generated_at'][:10] + '\n\n'
        + 'pglast 7.20; checkout `' + head + '`. Public regression verdict: **'
        + ('PASS' if passed else 'FAIL') + '**. ' + str(result.testsRun) + ' tests ran.\n\n'
        + '43 public procedures, 86 correct/wrong target variants, both parser modules. '
        + 'Every policy obligation is retained in report.json. No database or model calls.\n\n'
        + 'Historical revision-9 evidence measured with the earlier parser reported '
        + '86/86 expected outcomes over 108 native pairs '
        + '(55 matches, 53 divergences). This run re-verifies zero historical native pairs; '
        + 'it does not reissue their receipts or claim 108 equivalence certificates.\n\n'
        + 'Report SHA-256: `' + digest(raw) + '`.\n')
    (args.out / 'dated-note.md').write_text(note, encoding='utf-8')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
