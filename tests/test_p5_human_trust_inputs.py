"""Configuration-only negative tests; synthetic plans grant no authority."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.ci.p5_human_trust_inputs import validate_public_configuration, prepare, PUBLIC_KEY, PLAN, REPOSITORY


class PublicHumanTrustInputTests(unittest.TestCase):
    def fixture(self):
        plan = dict(schema='factory-build-plan/1', test_fixture_only=True)
        seal = sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        plan['content_sha256'] = seal
        environment = dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='pull_request',
            GITHUB_RUN_ATTEMPT='1', GITHUB_REPOSITORY=REPOSITORY,
            P5_HUMAN_CLEAN_APPROVED_HEAD='a' * 40, P5_HUMAN_CLEAN_APPROVED_PLAN=seal,
            P5_HUMAN_CLEAN_JOURNAL_HEAD='b' * 64)
        return plan, environment

    def test_only_configuration_is_returned_and_journal_is_independent(self):
        plan, env = self.fixture()
        value = validate_public_configuration(env, 'a' * 40, plan)
        self.assertEqual(value, dict(scope='factory', public_key='factory-authority.public.pem',
                                    journal_head_sha256='b' * 64))
        self.assertNotIn('execution_authorized', value)
        self.assertNotIn('proof_verified', value)

    def test_wrong_event_attempt_repository_or_non_ci_refuses(self):
        plan, env = self.fixture()
        for key, value in [('GITHUB_ACTIONS', ''), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                           ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REPOSITORY', 'someone/else')]:
            with self.subTest(key=key):
                changed = dict(env)
                changed[key] = value
                with self.assertRaisesRegex(ValueError, 'human-trust-ci-scope'):
                    validate_public_configuration(changed, 'a' * 40, plan)

    def test_missing_malformed_or_changed_independent_head_refuses(self):
        plan, env = self.fixture()
        for value in ['', 'a' * 39, 'A' * 40, 'c' * 40]:
            with self.subTest(value=value):
                changed = dict(env, P5_HUMAN_CLEAN_APPROVED_HEAD=value)
                with self.assertRaisesRegex(ValueError, 'human-trust-approved-head'):
                    validate_public_configuration(changed, 'a' * 40, plan)

    def test_absent_independent_journal_does_not_use_claim_from_plan(self):
        plan, env = self.fixture()
        plan['journal_head_sha256'] = 'b' * 64
        for value in ['', 'b' * 63, 'B' * 64]:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'human-trust-independent-config'):
                    validate_public_configuration(dict(env, P5_HUMAN_CLEAN_JOURNAL_HEAD=value), 'a' * 40, plan)

    def test_changed_or_resealed_plan_cannot_change_operator_approved_seal(self):
        plan, env = self.fixture()
        changed = deepcopy(plan)
        changed['test_fixture_only'] = False
        for reseal in [False, True]:
            if reseal:
                changed['content_sha256'] = sha256(json.dumps(
                    {k: v for k, v in changed.items() if k != 'content_sha256'},
                    sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            with self.subTest(reseal=reseal), self.assertRaisesRegex(ValueError, 'human-trust-approved-plan'):
                validate_public_configuration(env, 'a' * 40, changed)

    def git_fixture(self, temporary):
        root = Path(temporary) / 'source'
        root.mkdir()
        plan, env = self.fixture()
        public = (Path(__file__).resolve().parents[1] / PUBLIC_KEY).read_bytes()
        for relative, raw in [(PUBLIC_KEY, public), (PLAN, json.dumps(plan).encode()),
                              ('docs/factory/p5-human-clean-control/proof.json', b'{}'),
                              ('docs/factory/p5-human-clean-control/contract.json', b'{}')]:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        command = ['git', '-C', str(root)]
        subprocess.run(command + ['init', '--quiet'], check=True, capture_output=True)
        subprocess.run(command + ['add', '.'], check=True, capture_output=True)
        subprocess.run(command + ['-c', 'commit.gpgsign=false', '-c', 'user.name=Public fixture',
            '-c', 'user.email=public-fixture@example.invalid', 'commit', '--quiet', '-m', 'Unsigned parser fixture'],
            check=True, capture_output=True)
        env['P5_HUMAN_CLEAN_APPROVED_HEAD'] = subprocess.check_output(command + ['rev-parse', 'HEAD']).decode().strip()
        return root, env

    def test_real_git_public_config_does_not_authorize_synthetic_proof(self):
        from lightyear_factory.model_admission import FactoryModelAdmission
        from lightyear_factory.contracts import WorkOrder
        with tempfile.TemporaryDirectory() as temp:
            root, env = self.git_fixture(temp)
            output = Path(temp) / 'trust'
            result = prepare(root, output, env)
            self.assertFalse(result['execution_authorized'])
            self.assertFalse(result['proof_verified'])
            admission = FactoryModelAdmission.from_external_trust(root, PLAN,
                'docs/factory/p5-human-clean-control/proof.json',
                'docs/factory/p5-human-clean-control/contract.json', output / 'trust.json')
            order = WorkOrder.from_dict(dict(schema_version='1.0', id='parser-fixture',
                title='Unsigned parser fixture', goal='Reject an unsigned proof',
                scope=dict(allowed_paths=['public.py']),
                acceptance=dict(gates=[dict(id='unused', command=['python3', 'public.py'])])))
            with self.assertRaisesRegex(ValueError, 'factory-model-plan-binding'):
                admission.verify_plan(order)
            self.assertEqual(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain']), b'')

    def test_real_git_dirty_source_refuses_before_writing_trust(self):
        with tempfile.TemporaryDirectory() as temp:
            root, env = self.git_fixture(temp)
            (root / 'unexpected.txt').write_text('dirty', encoding='utf-8')
            output = Path(temp) / 'trust'
            with self.assertRaisesRegex(ValueError, 'human-trust-dirty-source'):
                prepare(root, output, env)
            self.assertFalse(output.exists())

    def test_real_git_uncommitted_public_key_change_refuses(self):
        with tempfile.TemporaryDirectory() as temp:
            root, env = self.git_fixture(temp)
            (root / PUBLIC_KEY).write_text('not the pinned public key', encoding='utf-8')
            output = Path(temp) / 'trust'
            with self.assertRaisesRegex(ValueError, 'human-trust-dirty-source'):
                prepare(root, output, env)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
