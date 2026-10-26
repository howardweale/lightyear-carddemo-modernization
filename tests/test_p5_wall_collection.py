"""CI-only collector contracts; no key, Tower, signature or model creation."""
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.ci import p5_controller_wall as wall


class WallCollectionTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def test_collector_retains_both_ordered_observations_without_rewriting_them(self):
        rows = [dict(case=case, retained=dict(marker=case)) for case in wall.CASES]
        original = copy.deepcopy(rows)
        with tempfile.TemporaryDirectory(prefix='p5-wall-collection-') as temp:
            fixture = SimpleNamespace(parent=Path(temp))
            repository = Path(__file__).resolve().parents[1]
            with patch.object(wall, 'observe_case', side_effect=rows) as observe, \
                 patch.object(wall, 'validate', return_value=True) as validate:
                result = wall.observe(fixture, repository)
            self.assertEqual(result, original)
            self.assertEqual(json.loads(json.dumps(result)), original)
            self.assertEqual([call.args[2] for call in observe.call_args_list], list(wall.CASES))
            self.assertEqual([call.args[0] for call in observe.call_args_list],
                [Path(temp)/'wall-controller-probes'/case for case in wall.CASES])
            self.assertEqual([call.args[0] for call in validate.call_args_list], original)

    def test_collection_refuses_missing_duplicate_reordered_and_extra_cases(self):
        clean, stopped = dict(case='clean'), dict(case='past-wall')
        for rows in ([], [clean], [clean, clean], [stopped, clean],
                     [clean, stopped, stopped], None, [clean, None]):
            with self.subTest(rows=rows), patch.object(wall, 'validate', return_value=True) as validate:
                with self.assertRaisesRegex(ValueError, '^p5-wall-collection-invalid$'):
                    wall.validate_collection(rows)
                validate.assert_not_called()

    def test_collection_requires_real_case_validation_and_explicit_true(self):
        rows = [dict(case=case) for case in wall.CASES]
        with self.assertRaisesRegex(ValueError, '^p5-wall-evidence-invalid$'):
            wall.validate_collection(rows)
        for answer in (False, None, 1):
            with self.subTest(answer=answer), patch.object(wall, 'validate', return_value=answer):
                with self.assertRaisesRegex(ValueError, '^p5-wall-collection-invalid$'):
                    wall.validate_collection(rows)


if __name__ == '__main__':
    unittest.main()
