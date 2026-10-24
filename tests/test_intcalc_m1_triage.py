"""CI-only record binding and refusal cases; no twin or mutation campaign."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from tools.check_intcalc_m1_triage import RECORD, posttran_paths, validate


class IntcalcM1TriageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.record = json.loads((self.root / RECORD).read_bytes())

    def check(self, record):
        return validate(record, lambda p: (self.root / p).read_bytes())

    def test_complete_retained_inventory_has_no_new_kill_credit(self):
        result = self.check(self.record)
        self.assertEqual((113, 22, 311, 424, 0), tuple(result[k] for k in
            ('survivors', 'arguments', 'raw_killed', 'denominator', 'additional_kills_claimed')))
        self.assertFalse(result['m1_complete'])
        self.assertFalse(result['release_authorized'])

    def test_kill_promotion_dropped_survivor_and_scope_overclaim_refuse(self):
        cases = []
        bad = deepcopy(self.record); bad['mutants'][0]['counted_as_kill'] = True; cases.append(bad)
        bad = deepcopy(self.record); bad['mutants'].pop(); cases.append(bad)
        bad = deepcopy(self.record); bad['raw_counts']['killed'] += 1; cases.append(bad)
        for field in ('m1_complete', 'measurement_credit', 'native_equivalence_claim', 'release_authorized'):
            bad = deepcopy(self.record); bad[field] = True; cases.append(bad)
        for bad in cases:
            with self.subTest(record=bad['raw_counts']), self.assertRaises(ValueError):
                self.check(bad)

    def test_source_drift_unbound_argument_and_duplicate_id_refuse(self):
        for change in ('source', 'argument', 'duplicate', 'span', 'paragraph'):
            bad = deepcopy(self.record)
            if change == 'source':
                bad['source_bindings'][next(iter(bad['source_bindings']))] = '0' * 64
            elif change == 'argument':
                bad['mutants'][0]['argument_id'] = 'absent'
            elif change == 'duplicate':
                bad['mutants'][0]['id'] = bad['mutants'][1]['id']
            elif change == 'span':
                bad['mutants'][0]['line'] = 0
            else:
                bad['paragraph_counts']['invented'] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check(bad)

    def test_posttran_fence_uses_all_bound_candidate_and_control_paths(self):
        plan = {'bound_files': {f'src/{i}': 'a' * 64 for i in range(182)},
                'candidate_files': {f'candidate/{i}': 'b' * 64 for i in range(2)}}
        names = ['docs/factory/posttran-retained.json', 'spec/mainframe/posttran-independent/a', 'safe.txt']
        fenced = posttran_paths(plan, names)
        self.assertTrue(set(plan['bound_files']) | set(plan['candidate_files']) <= fenced)
        self.assertIn(names[0], fenced)
        self.assertIn(names[1], fenced)
        self.assertNotIn('safe.txt', fenced)
        plan['candidate_files']['../escape'] = plan['candidate_files'].pop('candidate/0')
        with self.assertRaises(ValueError):
            posttran_paths(plan, names)
