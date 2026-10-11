import json
from pathlib import Path
import tempfile
import unittest
from lightyear_mainframe.legacy_twin import receipt
from tools.legacy_twin.mixed_key_probe import KEYS, EXPECTED_CP037, program
from tools.legacy_twin.reproducible_build import BASE_IMAGE, compare, expected_binaries


class TwinFollowupTests(unittest.TestCase):
    def test_fixture_discriminates_digits_lowercase_uppercase_and_suffixes(self):
        self.assertEqual(EXPECTED_CP037, sorted(KEYS, key=lambda k: k.encode('cp037')))
        self.assertNotEqual(EXPECTED_CP037, sorted(KEYS))
        self.assertTrue(all(len(k) == 4 for k in KEYS))
        self.assertLess(EXPECTED_CP037.index('A00z'), EXPECTED_CP037.index('A000'))
        self.assertIn("call 'LYKEY'", program('cp037'))
        self.assertNotIn("call 'LYKEY'", program('ascii'))

    def make_receipt(self, path, *, kind='github-hosted', machine='first', binary='a'*64, commit='b'*40):
        return receipt(path, phase='independent-machine-build', host_kind=kind, machine_id=machine,
                       repository_commit=commit, base_image=BASE_IMAGE, platform='linux/amd64',
                       installer_sha256='c'*64, binaries={name:binary for name in expected_binaries()})

    def test_same_host_does_not_become_second_machine(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); self.make_receipt(p/'a.json'); self.make_receipt(p/'b.json', machine='second')
            with self.assertRaisesRegex(ValueError, 'independent-github'):
                compare(p/'a.json',p/'b.json',p/'out.json')

    def test_different_head_is_not_reproducibility(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); self.make_receipt(p/'a.json')
            self.make_receipt(p/'b.json', kind='operator-machine', machine='second', commit='d'*40)
            with self.assertRaisesRegex(ValueError, 'binding-mismatch'):
                compare(p/'a.json',p/'b.json',p/'out.json')

    def test_binary_mismatch_is_recorded_and_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); self.make_receipt(p/'a.json')
            self.make_receipt(p/'b.json', kind='operator-machine', machine='second', binary='e'*64)
            with self.assertRaisesRegex(ValueError, 'hashes-differ'):
                compare(p/'a.json',p/'b.json',p/'out.json')
            self.assertFalse(json.loads((p/'out.json').read_text())['matched'])

    def test_matching_receipts_and_tamper_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); self.make_receipt(p/'a.json')
            self.make_receipt(p/'b.json', kind='operator-machine', machine='second')
            self.assertTrue(compare(p/'a.json',p/'b.json',p/'out.json')['matched'])
            altered=json.loads((p/'b.json').read_text());altered['machine_id']='invented'
            (p/'b.json').write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'seal-mismatch'):
                compare(p/'a.json',p/'b.json',p/'bad.json')

    def test_matching_partial_manifests_are_not_full_reproduction(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for name,kind,machine in [('a','github-hosted','first'),('b','operator-machine','second')]:
                receipt(p/(name+'.json'), phase='independent-machine-build', host_kind=kind, machine_id=machine,
                        repository_commit='b'*40, base_image=BASE_IMAGE, platform='linux/amd64',
                        installer_sha256='c'*64, binaries={'ascii/INTCALC/bin/twin':'a'*64})
            with self.assertRaisesRegex(ValueError, 'artifact-set-mismatch'):
                compare(p/'a.json',p/'b.json',p/'out.json')
