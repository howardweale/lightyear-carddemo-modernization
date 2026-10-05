"""Synthetic signature fixtures exercise admission, never OS qualification."""
import tempfile
import unittest
from pathlib import Path
from lightyear_calibration.contracts import canonical, digest, seal
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_measurement_admission import builder_gate, preflight_builder_gate


def builder_fixture(root):
    root = Path(root); (root / 'tools').mkdir(exist_ok=True)
    for name in ('tools/target.py', 'launcher.exe', 'runtime.dll'):
        (root / name).write_bytes(name.encode())
    signer = test_signer()
    transport = {'appcontainer_sid': 'synthetic-unit-fixture', 'policy_sha256': 'policy',
                 'launcher_sha256': file_hash(root / 'launcher.exe'), 'launcher_path': 'launcher.exe',
                 'runtime_sha256': file_hash(root / 'runtime.dll'), 'runtime_path': str(root / 'runtime.dll')}
    record = signer.sign({'artifact_type': 'ms94-b06-os-builder-denial/1', 'status': 'passed',
              'evidence_kind': 'actual-host-process', 'appcontainer_sid': transport['appcontainer_sid'],
              'policy_sha256': 'policy', 'launcher_sha256': transport['launcher_sha256'],
              'runtime_sha256': transport['runtime_sha256'], 'capabilities': [], 'inherited_handles': False,
              'child_exit_code': 0, 'token_is_appcontainer': True, 'denial_win32_error': 5,
              'positive_control_opened': True,
              'target': {'path': 'tools/target.py', 'sha256': file_hash(root / 'tools/target.py')}})
    (root / 'probe.json').write_bytes(canonical(record))
    spec = {'probe': {'path': 'probe.json', 'sha256': file_hash(root / 'probe.json')},
            'transport_sha256': digest(transport)}
    context = {'root': root, 'public_key': signer.public, 'transport': transport}
    return spec, context


class MeasurementAdmissionTests(unittest.TestCase):
    def test_both_boundaries_require_actual_bound_signed_file_not_boolean(self):
        with tempfile.TemporaryDirectory() as d:
            spec, context = builder_fixture(d)
            plan = seal({'builder_boundary': spec})
            for gate in (builder_gate, preflight_builder_gate):
                self.assertEqual(spec['probe']['sha256'], gate(plan, context)['probe_file_sha256'])
                for changed, ctx in ((seal({}), context), (plan, None), (plan, True)):
                    with self.assertRaisesRegex(ValueError, 'measurement-builder-probe-required'):
                        gate(changed, ctx)
                with self.assertRaisesRegex(ValueError, 'measurement-builder-transport-changed'):
                    gate(plan, {**context, 'transport': {**context['transport'], 'policy_sha256': 'changed'}})
            self.assertFalse(preflight_builder_gate(plan, context)['complete_preflight_passed'])
            (Path(d) / 'probe.json').write_bytes(b'corrupt')
            for gate in (builder_gate, preflight_builder_gate):
                with self.assertRaisesRegex(ValueError, 'bound-file-changed'): gate(plan, context)


if __name__ == '__main__': unittest.main()
