"""Qualification needs exact native inputs, but has no builder to isolate."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import canonical, seal, CalibrationError
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_executable import window
from tools.ms94_b06_qualification_plan import convert


class ConversionTests(unittest.TestCase):
    def test_missing_snapshot_cannot_promote_draft(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CalibrationError):
                convert(Path(d), seal({'journey': 'J1'}), 'missing', '', '')

    def test_conversion_ignores_builder_probe_but_binds_native_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cal = seal({'period_start_utc': '2026-10-01T00:00:00Z',
                        'period_end_exclusive_utc': '2026-11-01T00:00:00Z',
                        'maximum_seconds': 345600, 'scenario_date': '2026-10-01',
                        'frozen_at_utc': '2026-10-05T00:00:00Z'})
            start, end = '2026-10-18T00:00:00Z', '2026-10-19T00:00:00Z'
            images = {'application': 'a', 'oracle': 'o', 'postgresql': 'p'}
            plan = seal({'journey': 'J1', 'slot_id': 'j1-001', 'execution_admission_version': 3,
                         'docker_run_window': window(cal, start, end), 'calendar': cal,
                         'local': {'runner_image': 'a'}, 'declaration': {'environment': {'engines': {
                             k: {'image_digest': images[k]} for k in ('oracle', 'postgresql')}}},
                         'harness_sha256': 'source', 'control': 'retained-reference', 'expected': {'status': 'passed'}})
            (root / 'plan.json').write_bytes(canonical(plan))
            manifest = seal({'files_sha256': {'plan.json': file_hash(root / 'plan.json')},
                             'slot_plans_sha256': {'plan.json': plan['content_sha256']}})
            (root / 'b06-executable-snapshot.json').write_bytes(canonical(manifest))
            body = {'journey': 'J1', 'model_calls': 0, 'measurement_authorized': False,
                    'slot_count': 1, 'images': images, 'schedule': [{'id': 'j1-001',
                    'source': {'sha256': 'source'}, 'control': plan['control'], 'expected': plan['expected']}]}
            # Only native private-input checking is mocked; snapshot hashing and
            # slot/source/image/calendar validation use real files and code.
            with patch('tools.ms94_b06_qualification_plan.verify_inputs') as inputs, patch(
                    'tools.ms94_b06_os_probe.admit', side_effect=AssertionError('no builder')):
                result = convert(root, seal(body), manifest['content_sha256'], start, end,tower_public_key_sha256='a'*64)
                inputs.assert_called_once()
                self.assertFalse(result['builder_present'])
                self.assertFalse(result['docker_authorized'])
                self.assertNotIn('os_probe_sha256', result)
                for field, value in [('model_calls', 1), ('measurement_authorized', True)]:
                    with self.assertRaisesRegex(ValueError, 'qualification-only-no-builder'):
                        convert(root, seal({**body, field: value}), manifest['content_sha256'], start, end,tower_public_key_sha256='a'*64)
                changed = {**body, 'images': {**images, 'oracle': 'other'}}
                with self.assertRaisesRegex(ValueError, 'qualification-image-binding'):
                    convert(root, seal(changed), manifest['content_sha256'], start, end,tower_public_key_sha256='a'*64)
            (root / 'plan.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'bound-file-changed'):
                convert(root, seal(body), manifest['content_sha256'], start, end,tower_public_key_sha256='a'*64)


if __name__ == '__main__': unittest.main()
