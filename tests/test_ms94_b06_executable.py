import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import seal, canonical
from lightyear_calibration.journey_order import RUNS, file_hash
from tools.ms94_b06_executable import assemble_slot, freeze, verify_snapshot, window, POLICY


class ExecutableTests(unittest.TestCase):
    def test_running_guard_and_full_pair_window_are_distinct(self):
        from tools.ms94_b06_native import group_window_guard
        p = {'execution_admission_version': 3, 'docker_run_window': {
            'not_before_utc': '2026-10-18T16:00:00Z', 'deadline_utc': '2026-10-18T18:00:00Z'},
            'declaration': {'policy': {'max_elapsed_seconds': 7190}}}
        group_window_guard(p, '2026-10-18T16:00:00Z', starting=True)
        group_window_guard(p, '2026-10-18T17:00:00Z')
        with self.assertRaisesRegex(ValueError, 'no-full-pair-window'):
            group_window_guard(p, '2026-10-18T17:00:00Z', starting=True)
        for t in ('2026-10-18T15:59:59Z', '2026-10-18T18:00:00Z'):
            with self.assertRaisesRegex(ValueError, 'outside-approved-group-window'): group_window_guard(p, t)

    def test_window_refuses_month_crossing_and_excess_budget(self):
        c = seal({'period_start_utc': '2026-10-01T00:00:00Z',
                  'period_end_exclusive_utc': '2026-11-01T00:00:00Z', 'maximum_seconds': 96*3600})
        self.assertFalse(window(c, '2026-10-18T00:00:00Z', '2026-10-19T00:00:00Z')['docker_approved'])
        for a, b in [('2026-10-28T00:00:00Z', '2026-10-29T00:00:00Z'),
                     ('2026-10-18T00:00:00Z', '2026-10-23T00:00:00Z'),
                     ('2026-10-18T00:00:00Z', '2026-10-17T00:00:00Z')]:
            with self.subTest(a=a, b=b), self.assertRaises(ValueError): window(c, a, b)

    def test_incomplete_native_bundle_never_creates_slot(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); run = root / RUNS / 'j2-001'
            base = {'journey': 'J2', 'model_calls': 0, 'qualification_only': True,
                    'declaration': {'policy': {'max_model_calls': 1}}}
            with self.assertRaisesRegex(ValueError, 'declaration-model-budget'):
                assemble_slot(root, run, base, {}, {})
            self.assertFalse(run.exists())

    def test_snapshot_copy_is_exact_append_only_and_rechecked(self):
        # Assembly validation is tested elsewhere; this fixture tests real I/O,
        # closure, exclusive creation and post-freeze corruption detection.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'source'; root.mkdir()
            (root / 'impl.py').write_bytes(b'no model transport')
            (root / POLICY).parent.mkdir(parents=True)
            (root / POLICY).write_bytes(b'unchanged policy fixture')
            p = root / RUNS / 'j2-001' / 'plan.json'; p.parent.mkdir(parents=True)
            plan = seal({'implementation_sha256': {'impl.py': file_hash(root / 'impl.py')},
                         'inputs_sha256': {}, 'posting_observer': {'target_class_files_sha256': {},
                          'classes_directory': 'classes', 'class_files_sha256': {}}})
            p.write_bytes(canonical(plan)); name = p.relative_to(root).as_posix()
            out = Path(d) / 'b06-execution-snapshots' / 'test'
            files = {n: file_hash(root / n) for n in ('impl.py', name, POLICY)}
            with patch('tools.ms94_b06_executable.verify_inputs'):
                with self.assertRaisesRegex(ValueError, 'freeze-input-closure'):
                    freeze(root, out, {name: files[name]}, {name: plan['content_sha256']})
                self.assertFalse(out.exists())
                m = freeze(root, out, files, {name: plan['content_sha256']})
                self.assertEqual(verify_snapshot(out, m['content_sha256']), m)
                with self.assertRaisesRegex(ValueError, 'freeze-existing-or-empty'):
                    freeze(root, out, files, {name: plan['content_sha256']})
            (out / 'impl.py').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'bound-file-changed'):
                verify_snapshot(out, m['content_sha256'])


if __name__ == '__main__': unittest.main()
