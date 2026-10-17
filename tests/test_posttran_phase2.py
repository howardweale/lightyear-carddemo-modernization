"""Authorization tests never compile or run a candidate or twin."""
import copy
import unittest
from tools.prepare_posttran_phase2 import digest
from tools.run_posttran_phase2 import authorize, returncodes_agree, comparison_status


class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(generation_attempt=1, model_calls=0, retries=0)
        self.plan['content_sha256'] = digest(self.plan)
        self.head = 'a' * 40
        self.env = dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='pull_request', GITHUB_RUN_ATTEMPT='1',
            POSTTRAN_PHASE2_APPROVED_PLAN=self.plan['content_sha256'], POSTTRAN_PHASE2_APPROVED_HEAD=self.head)

    def test_equal_abends_remain_divergent_after_invariant_failures(self):
        for code in (8, 12):
            for valid in (False, True):
                self.assertEqual('divergent', comparison_status(True, code, code, 'public:posttran-public', invariants_passed=valid))
        self.assertEqual('equivalent', comparison_status(True, 999, 12, 'generated:posttran-duplicate-id'))
        self.assertEqual('divergent', comparison_status(True, 999, 12, 'public:posttran-public'))

    def test_no_authorization_no_execution(self):
        for key in self.env:
            env = self.env.copy(); del env[key]
            with self.subTest(key=key), self.assertRaises(ValueError): authorize(self.plan, env, self.head)

    def test_stale_plan_head_retry_or_wrong_event_refuses(self):
        for key, value in [('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_EVENT_NAME', 'push'),
            ('POSTTRAN_PHASE2_APPROVED_PLAN', 'b' * 64), ('POSTTRAN_PHASE2_APPROVED_HEAD', 'c' * 40)]:
            env = {**self.env, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError): authorize(self.plan, env, self.head)
        changed = copy.deepcopy(self.plan); changed['retries'] = 1
        with self.assertRaises(ValueError): authorize(changed, self.env, self.head)

    def test_exact_authorization_and_strict_abend_scope(self):
        self.assertEqual(self.plan, authorize(self.plan, self.env, self.head))
        self.assertTrue(returncodes_agree(999, 12, 'generated:posttran-duplicate-id'))
        self.assertFalse(returncodes_agree(999, 12, 'public:posttran-public'))
        self.assertFalse(returncodes_agree(12, 12, 'generated:posttran-duplicate-id'))
        self.assertFalse(returncodes_agree(999, 999, 'generated:posttran-duplicate-id'))
        self.assertTrue(returncodes_agree(4, 4, 'public:posttran-public'))


if __name__ == '__main__': unittest.main()
