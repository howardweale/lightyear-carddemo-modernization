"""CI-only synthetic artifact contracts; no native execution or qualification."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.ci import tsql_readiness_artifact as checker
from tools.ci import tsql_readiness_ten as h

ROOT = Path(__file__).resolve().parents[1]


class PublicArtifactIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.temp = tempfile.TemporaryDirectory(prefix='public-tsql-integrity-')
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.selection = json.loads((ROOT/'docs/tsql-readiness/selection.json').read_bytes())
        self.items = h.intake(ROOT, self.selection)
        self.ci = dict(GITHUB_REPOSITORY='public/synthetic-contract', GITHUB_SHA='a'*40,
                       GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='1')
        self.pins = dict(expected_ci=self.ci, expected_harness_sha256=h.sha(Path(h.__file__).read_bytes().replace(b'\r\n', b'\n')),
                         expected_bridge_sha256='b'*64, expected_engine_profiles=dict(source={'fixture': 'sqlserver'}, target={'fixture': 'postgresql'}))

    def write(self, name, value):
        raw = h.canonical(value)
        p = self.output/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        return h.sha(raw)

    def fixture(self):
        plan = dict(schema='public-tsql-ten-plan/1', ci=self.ci, selection=self.selection,
                    native_capture=True, signed=False, model_calls=0, qualification_supplied=True,
                    harness_sha256=self.pins['expected_harness_sha256'],
                    semantic_bridge_sha256=self.pins['expected_bridge_sha256'],
                    configured_engine_profiles=self.pins['expected_engine_profiles'])
        plan_sha = self.write('plan.json', plan)
        entries = []
        index = 0
        for item in self.items:
            rows = []
            for variant in ('correct', 'wrong'):
                for case in item['cases']:
                    for repeat in range(1, case['repeated_runs'] + 1):
                        index += 1
                        folder = 'pair-%03d/' % index
                        outcome = 'equivalent' if variant == 'correct' else 'divergent'
                        files = {name: self.write(folder+name, {'synthetic_contract_only': True}) for name in ('source.json', 'target.json')}
                        files['comparison.json'] = self.write(folder+'comparison.json', dict(verdict=outcome, synthetic_contract_only=True))
                        row = dict(procedure_id=item['id'], variant=variant, case_id=case['id'], repeat=repeat,
                                   status='compared', verdict=outcome, cleanup_complete=True, cleanup_failures=[], files=files)
                        row['receipt_sha256'] = self.write(folder+'receipt.json', row)
                        rows.append(row)
            receipt = dict(schema='public-tsql-procedure-receipt/1', procedure_id=item['id'],
                           assets=item['assets'], declared_cases=item['cases'], calling_convention=item['calling_convention'],
                           plan_sha256=plan_sha, ci=self.ci, signed=False, model_calls=0,
                           verdict='equivalent-on-declared-public-cases', cases=rows)
            entries.append(dict(procedure_id=item['id'], verdict=receipt['verdict'], receipt_sha256=self.write(item['id']+'.json', receipt)))
        self.write('summary.json', dict(schema='public-tsql-ten-summary/1', plan_sha256=plan_sha,
                                       procedures=entries, native_pair_count=index, signed=False, model_calls=0, passed=True))

    def rebind_first(self, change, case_index=None):
        receipt = json.loads((self.output/'len.json').read_bytes())
        change(receipt)
        if case_index is not None:
            row = receipt['cases'][case_index]
            row['receipt_sha256'] = self.write('pair-%03d/receipt.json' % (case_index+1),
                                               {k:v for k,v in row.items() if k!='receipt_sha256'})
        digest = self.write('len.json', receipt)
        summary = json.loads((self.output/'summary.json').read_bytes())
        summary['procedures'][0]['receipt_sha256'] = digest
        self.write('summary.json', summary)

    def test_synthetic_closed_artifact_never_becomes_native_proof(self):
        self.fixture()
        result = checker.verify(ROOT, self.output, **self.pins)
        self.assertTrue(result['integrity_complete'])
        self.assertTrue(result['reported_passed'])
        self.assertFalse(result['native_execution_verified'])
        self.assertFalse(result['coverage_qualification_verified'])
        self.assertFalse(result['comparator_replayed'])
        self.assertFalse(result['signed'])
        self.assertGreater(result['case_pairs'], 10)

    def test_hash_drift_missing_extra_and_duplicate_json_are_refused(self):
        for mode in ('drift', 'missing', 'extra', 'duplicate-json'):
            with self.subTest(mode=mode):
                self.fixture()
                p = self.output/'pair-001/source.json'
                original = p.read_bytes()
                if mode=='drift': p.write_bytes(b'{}')
                elif mode=='missing': p.unlink()
                elif mode=='extra': (self.output/'unexpected.json').write_bytes(b'{}')
                else: (self.output/'summary.json').write_bytes(b'{"schema":1,"schema":2}')
                with self.assertRaises(ValueError): checker.verify(ROOT, self.output, **self.pins)
                p.write_bytes(original)
                if mode=='extra': (self.output/'unexpected.json').unlink()

    def test_external_ci_bridge_and_profile_pins_are_required(self):
        self.fixture()
        for field in ('expected_ci', 'expected_bridge_sha256', 'expected_engine_profiles'):
            pins = copy.deepcopy(self.pins)
            if field=='expected_ci': pins[field]['GITHUB_RUN_ID']='2'
            elif field=='expected_bridge_sha256': pins[field]='c'*64
            else: pins[field]['source']={'fixture': 'changed'}
            with self.subTest(field=field), self.assertRaises(ValueError): checker.verify(ROOT, self.output, **pins)

    def test_rehashed_wrong_twin_match_still_refuses_success(self):
        self.fixture()
        first = json.loads((self.output/'len.json').read_bytes())
        i = next(i for i,row in enumerate(first['cases']) if row['variant']=='wrong')
        digest = self.write('pair-%03d/comparison.json' % (i+1), dict(verdict='equivalent', synthetic_contract_only=True))
        def change(receipt):
            receipt['cases'][i]['verdict']='equivalent'
            receipt['cases'][i]['files']['comparison.json']=digest
        self.rebind_first(change, i)
        with self.assertRaisesRegex(ValueError, 'procedure-verdict'): checker.verify(ROOT, self.output, **self.pins)

    def test_rehashed_selectors_cleanup_assets_and_scope_do_not_bypass_checks(self):
        for mode in ('bool-repeat', 'cleanup', 'assets', 'scope', 'path'):
            with self.subTest(mode=mode):
                self.fixture()
                def change(receipt):
                    row=receipt['cases'][0]
                    if mode=='bool-repeat': row['repeat']=True
                    elif mode=='cleanup': row['cleanup_complete']=False
                    elif mode=='assets': receipt['assets']['source']['sha256']='d'*64
                    elif mode=='scope': receipt['model_calls']=True
                    else: row['files']['../source.json']=row['files'].pop('source.json')
                self.rebind_first(change, 0)
                with self.assertRaises(ValueError): checker.verify(ROOT, self.output, **self.pins)


if __name__ == '__main__':
    unittest.main()
