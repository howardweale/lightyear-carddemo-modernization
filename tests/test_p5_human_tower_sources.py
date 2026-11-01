"""CI-only installed-Tower source-shape tests; no key, proof or signing."""
import copy
import os
import unittest
from lightyear_control_tower.factory_policy import validate_contract
from lightyear_execution.public_drill_outputs import require_public_contract_source


class PublicTowerSourceTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.binding = {'path': 'docs/factory/p5-human-clean-control/public-outputs.json', 'sha256': 'b'*64}
        self.contract = dict(schema='factory-contract/1', kind='engineering-run-approval', program='factory',
            sources=[dict(self.binding, commit='a'*40)], details=dict(executable_commit='a'*40,
            request_seal='c'*64, observer_sha256='d'*64, class_hashes={'PublicControl': 'e'*64},
            window={'start': '2026-10-28T00:00:00+00:00', 'end': '2026-10-29T00:00:00+00:00'},
            caps={'max_attempts': 1}))

    def test_native_tower_accepts_three_fields_and_projection_matches(self):
        self.assertEqual(validate_contract(self.contract, check_evidence=False), self.contract)
        self.assertIsNone(require_public_contract_source(self.contract, self.binding))
        self.assertNotIn('execution_authorized', self.contract)

    def test_two_field_source_and_test_fixture_path_reproduce_original_refusal(self):
        bad = copy.deepcopy(self.contract); del bad['sources'][0]['commit']
        with self.assertRaises(ValueError): validate_contract(bad, check_evidence=False)
        bad = copy.deepcopy(self.contract); bad['sources'][0]['path'] = 'tests/fixtures/p5_public/outputs.json'
        with self.assertRaises(ValueError): validate_contract(bad, check_evidence=False)

    def test_wrong_executable_commit_hash_or_missing_source_refuses(self):
        for field, value in [('commit', 'f'*40), ('sha256', 'f'*64), ('path', 'docs/factory/other.json')]:
            with self.subTest(field=field):
                bad = copy.deepcopy(self.contract); bad['sources'][0][field] = value
                with self.assertRaises(ValueError): require_public_contract_source(bad, self.binding)

    def test_binding_shape_and_nonpublic_prefix_refuse(self):
        for bad in [dict(self.binding, commit='a'*40), {'path': self.binding['path']},
                    dict(self.binding, path='docs/factory/other.json'), dict(self.binding, sha256='bad')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                require_public_contract_source(self.contract, bad)

    def test_same_content_at_other_path_cannot_substitute(self):
        bad = copy.deepcopy(self.contract)
        bad['sources'][0]['path'] = 'docs/factory/p5-human-clean-control/public-isolation.json'
        with self.assertRaises(ValueError): require_public_contract_source(bad, self.binding)


if __name__ == '__main__': unittest.main()
