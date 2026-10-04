import tempfile
import unittest
from pathlib import Path
from lightyear_calibration.contracts import canonical
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_os_probe import admit


class OSProbeTests(unittest.TestCase):
    def test_signature_hash_transport_and_real_access_denial_are_all_required(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'tools').mkdir()
            for name in ('tools/target.py', 'launcher.exe', 'runtime.dll'):
                (root / name).write_bytes(name.encode())
            signer = test_signer()
            transport = {'appcontainer_sid': 'fixture-only', 'policy_sha256': 'policy',
                         'launcher_sha256': file_hash(root / 'launcher.exe'), 'launcher_path': 'launcher.exe',
                         'runtime_sha256': file_hash(root / 'runtime.dll'), 'runtime_path': str(root / 'runtime.dll')}
            record = {'artifact_type': 'ms94-b06-os-builder-denial/1', 'status': 'passed',
                      'evidence_kind': 'actual-host-process', 'appcontainer_sid': 'fixture-only',
                      'policy_sha256': 'policy', 'launcher_sha256': transport['launcher_sha256'],
                      'runtime_sha256': transport['runtime_sha256'], 'capabilities': [],
                      'inherited_handles': False, 'child_exit_code': 0, 'token_is_appcontainer': True,
                      'denial_win32_error': 5, 'positive_control_opened': True,
                      'target': {'path': 'tools/target.py', 'sha256': file_hash(root / 'tools/target.py')}}
            def saved(body):
                (root / 'probe.json').write_bytes(canonical(signer.sign(body)))
                return {'path': 'probe.json', 'sha256': file_hash(root / 'probe.json')}
            binding = saved(record); admit(root, binding, signer.public, transport)
            for key, value in [('status', 'blocked-before-child'), ('evidence_kind', 'synthetic'),
                               ('denial_win32_error', 2), ('positive_control_opened', False),
                               ('appcontainer_sid', 'other'), ('capabilities', ['network']),
                               ('inherited_handles', True), ('token_is_appcontainer', False)]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    admit(root, saved({**record, key: value}), signer.public, transport)
            binding = saved(record)
            (root / 'probe.json').write_bytes(b'changed')
            with self.assertRaises(ValueError): admit(root, binding, signer.public, transport)


if __name__ == '__main__': unittest.main()
