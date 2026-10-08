"""Offline handoff guards: a successful practice is never launch authorization."""
import copy
import unittest
from lightyear_calibration.contracts import seal
from tools.b06_image_artifacts import build_once_handoff as h


def reseal(value, **updates):
    return seal({**{k:v for k,v in value.items() if k != 'content_sha256'}, **updates})


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.common = seal(dict(source_commit='a'*40, snapshot_sha256='b'*64))
        self.practice = seal(dict(source_commit='a'*40, snapshot_sha256='b'*64,
            common_plan_sha256=self.common['content_sha256'], image='sha256:'+'c'*64,
            manifest_sha256='d'*64, report_sha256='e'*64, model_calls=0,
            native_pairs=0, native_admission=False))

    def test_practice_does_not_create_an_executable_request(self):
        plan = h.prospective(self.common, self.practice)
        self.assertFalse(plan['native_admission'])
        self.assertFalse(plan['executable'])
        self.assertIsNone(plan['window'])
        self.assertEqual(plan['builder_runs'], 0)
        with self.assertRaisesRegex(ValueError, 'evidence-driver-not-ready'):
            h.request(plan, 'f'*40)

    def test_wrong_source_or_snapshot_or_plan_refuses(self):
        for field in ('source_commit', 'snapshot_sha256', 'common_plan_sha256'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'common-plan-binding'):
                h.prospective(self.common, reseal(self.practice, **{field:'0'*64}))

    def test_admission_or_model_scope_cannot_be_inherited(self):
        for field, value in (('native_admission', True), ('model_calls', 1), ('native_pairs', 1)):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'practice-scope'):
                h.prospective(self.common, reseal(self.practice, **{field:value}))

    def test_tampered_hash_refuses(self):
        practice = copy.deepcopy(self.practice)
        practice['image'] = 'sha256:'+'0'*64
        with self.assertRaises(ValueError):
            h.prospective(self.common, practice)

    def test_window_and_rebuild_guards(self):
        plan = reseal(h.prospective(self.common, self.practice), executable=True, driver_sha256='1'*64)
        with self.assertRaisesRegex(ValueError, 'fresh-evidence-window-required'):
            h.request(plan, 'f'*40)
        window = dict(not_before_utc='2026-10-09T00:00:00Z', latest_start_utc='2026-10-09T00:05:00Z', deadline_utc='2026-10-09T00:44:59Z')
        with self.assertRaisesRegex(ValueError, 'evidence-window-reserve'):
            h.request(reseal(plan, window=window), 'f'*40)
        with self.assertRaisesRegex(ValueError, 'evidence-consumers-only'):
            h.request(reseal(plan, builder_runs=1), 'f'*40)