"""CI-only retention of real-controller synthetic budget/fallback evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import canonical_hash
from tools.ci.p5_budget_evidence import validate
from tools.ci.p5_controller_budgets import CASES, observe_case
from tools.ci.p5_fallback_probe import observe as observe_fallback
from tools.ci import p5_drills as drills


class BudgetEvidenceTests(unittest.TestCase):
    def test_real_controller_retains_all_budget_and_fallback_cases(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        repository = Path(__file__).resolve().parents[1]
        retained = []
        with tempfile.TemporaryDirectory(prefix='p5-budget-retention-ci-') as temp:
            root = Path(temp)
            for case in CASES:
                row = observe_case(root/case, repository, case)
                value = row['retained_budget_evidence']
                self.assertEqual(value['receipt_utf8'].encode(),
                    (root/case/'runs'/value['run_id']/'receipt.json').read_bytes())
                retained.append(value)
            for changed in (False, True):
                parent = root/('fallback-'+str(changed))
                row = observe_fallback(parent, repository, changed_fallback_model=changed)
                value = row['retained_budget_evidence']
                self.assertEqual(value['receipt_utf8'].encode(),
                    (parent/'runs/fallback-probe/receipt.json').read_bytes())
                retained.append(value)
        self.assertEqual(len(retained), 8)
        for value in retained:
            args = {key: value[key] for key in ('case', 'run_id', 'work_order_sha256')}
            self.assertTrue(validate(value, **args))
            for field in ('receipt_utf8', 'identity_utf8', 'calls_utf8', 'case', 'run_id', 'work_order_sha256'):
                bad = copy.deepcopy(value)
                bad[field] += 'changed'
                with self.subTest(case=value['case'], corruption=field), self.assertRaises(ValueError):
                    validate(bad, **args)
            calls = json.loads(value['calls_utf8'])
            if not calls:
                continue
            for mutation in ('missing', 'duplicate', 'sequence', 'hash', 'aggregate'):
                bad = copy.deepcopy(value)
                changed_calls = copy.deepcopy(calls)
                if mutation == 'missing':
                    changed_calls.pop()
                elif mutation == 'duplicate':
                    changed_calls.append(copy.deepcopy(changed_calls[0]))
                elif mutation == 'sequence':
                    changed_calls[0]['call_sequence'] = 99
                    changed_calls[0]['content_sha256'] = canonical_hash(changed_calls[0], {'content_sha256'})
                elif mutation == 'hash':
                    changed_calls[0]['content_sha256'] = '0'*64
                else:
                    changed_calls[0]['input_tokens'] += 1
                    changed_calls[0]['content_sha256'] = canonical_hash(changed_calls[0], {'content_sha256'})
                bad['calls_utf8'] = json.dumps(changed_calls, sort_keys=True)
                bad['calls_sha256'] = hashlib.sha256(bad['calls_utf8'].encode()).hexdigest()
                with self.subTest(case=value['case'], corruption=mutation), self.assertRaises(ValueError):
                    validate(bad, **args)

    def test_collector_keeps_budget_bytes_and_gaps_without_qualification(self):
        # Plumbing control only; the integration test above uses the real controller.
        class FakeFixture:
            def __init__(self, *args): pass
            def close(self): pass
        value = {'receipt_utf8': '{"synthetic": true}', 'calls_utf8': '[]'}
        def measured(fixture):
            return {'controller_cases': [{'retained_budget_evidence': value}]}, True, ['final billing unmeasured']
        with tempfile.TemporaryDirectory(prefix='p5-budget-collector-') as temp:
            root = Path(temp)/'public'
            with patch.object(drills, 'Fixture', FakeFixture), patch.object(drills, 'FUNCTIONS',
                    {name: measured for name in drills.DRILLS}):
                self.assertTrue(drills.collect(Path(__file__).resolve().parents[1], root))
            for name in drills.DRILLS:
                receipt = json.loads((root/(name+'.json')).read_bytes())
                self.assertEqual(receipt['observed']['controller_cases'][0]['retained_budget_evidence'], value)
                self.assertEqual(receipt['gaps'], ['final billing unmeasured'])
                self.assertFalse(receipt['production_controller_receipt'])
                self.assertIn('tools/ci/p5_budget_evidence.py', receipt['source_sha256'])
            with patch.object(drills, 'verify_envelope', return_value=True):
                self.assertFalse(drills.qualify(root))
