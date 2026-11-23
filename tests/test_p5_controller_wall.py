"""CI-only real controller wall refusal and evidence corruption negatives."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.orchestrator import FactoryOrchestrator
from tools.ci.p5_controller_wall import CASES, observe_case, validate


class ControllerWallTests(unittest.TestCase):
    def test_controller_wall_refusal_and_retained_accounting(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        with tempfile.TemporaryDirectory(prefix='p5-wall-ci-') as temp:
            for case in CASES:
                with self.subTest(case=case):
                    row = observe_case(Path(temp)/case, Path(__file__).resolve().parents[1], case)
                    self.assertTrue(validate(json.loads(json.dumps(row))))
                    self.assertEqual(row['transport_roles'], ['planner', 'builder'] if case == 'clean' else ['planner'])
                    self.assertIs(row['controller_refused'], case == 'past-wall')
                    self.assertEqual(row['real_model_calls'], 0)
                    self.assertEqual(row['actual_spend'], 0)
                    if case == 'past-wall':
                        self.assertEqual(row['failure_causes'], ['Factory exceeded max_elapsed_seconds'])
                        receipt = json.loads(row['receipt_utf8'])
                        self.assertEqual(receipt['attempts'], 0)
                        self.assertFalse(receipt['qualifies_for_factory_receipt'])
                        self.assertFalse(receipt['failure_accounting']['billing_final'])
                        self.assertEqual(receipt['failure_accounting']['calls'], 1)

    def test_wall_evidence_rejects_corruption_and_self_rehashed_false_claims(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        with tempfile.TemporaryDirectory(prefix='p5-wall-corruption-') as temp:
            row = observe_case(Path(temp)/'past-wall', Path(__file__).resolve().parents[1], 'past-wall')
        for field, value in [('controller_refused', False), ('transport_roles', ['planner', 'builder']),
                             ('failure_causes', ['unrelated']), ('plan_created_count', 0),
                             ('clock_delta_seconds', 0), ('receipt_sha256', '0'*64)]:
            bad = copy.deepcopy(row); bad[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, '^p5-wall-evidence-invalid$'):
                validate(bad)
        for field, value in [('status', 'passed'), ('qualifies_for_factory_receipt', True),
                             ('attempts', 1), ('factory_build_receipt', {})]:
            bad = copy.deepcopy(row); doc = json.loads(bad['receipt_utf8']); doc[field] = value
            doc['content_sha256'] = canonical_hash(doc, {'content_sha256'})
            raw = json.dumps(doc, sort_keys=True, separators=(',', ':'))
            bad['receipt_utf8'], bad['receipt_sha256'] = raw, hashlib.sha256(raw.encode()).hexdigest()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, '^p5-wall-evidence-invalid$'):
                validate(bad)

    def test_unrelated_controller_refusal_cannot_pass_as_timeout(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        with tempfile.TemporaryDirectory(prefix='p5-wall-wrong-reason-') as temp:
            with patch.object(FactoryOrchestrator, '_validate_plan', side_effect=ContractError('unrelated refusal')):
                with self.assertRaisesRegex(ValueError, '^p5-wall-wrong-underlying-refusal$'):
                    observe_case(Path(temp)/'wrong', Path(__file__).resolve().parents[1], 'past-wall')


if __name__ == '__main__':
    unittest.main()
