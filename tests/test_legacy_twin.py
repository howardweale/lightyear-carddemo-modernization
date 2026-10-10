import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_mainframe import legacy_twin as twin


class TwinTests(unittest.TestCase):
    def test_public_inputs_are_complete_and_hash_verified(self):
        for scenario in twin.PUBLIC_SCENARIOS:
            job, _, images, hashes = twin.public_inputs(scenario)
            self.assertEqual(set(images), set(twin.FILES[job]))
            self.assertEqual(set(images), set(hashes))
            for dd, raw in images.items():
                n = twin.FILES[job][dd][0]
                self.assertEqual(twin.frame(twin.unframe(raw, n), n), raw)

    def test_unknown_scenario_never_opens_a_path(self):
        with self.assertRaises(KeyError):
            twin.public_inputs('../../customer')

    def test_fixed_framing_preserves_spaces_and_rejects_partial(self):
        self.assertEqual(twin.frame(b'a b ', 2), b'a \nb \n')
        self.assertEqual(twin.unframe(b'a \nb \n', 2), b'a b ')
        for raw in (b'a', b'ab\r\n', b'abcd'):
            with self.assertRaises(ValueError):
                twin.unframe(raw, 2)
        with self.assertRaises(ValueError):
            twin.frame(b'a', 2)

    def test_windows_build_is_refused_before_writes(self):
        with patch.object(twin.platform, 'system', return_value='Windows'):
            with self.assertRaisesRegex(ValueError, 'Windows'):
                twin.build(Path('must-not-be-created'))
        self.assertFalse(Path('must-not-be-created').exists())

    def test_only_intcalc_xref_has_alternate_key(self):
        self.assertIn('alternate record key', twin.indexed_adapter('INTCALC', 'XREFFILE'))
        self.assertNotIn('alternate record key', twin.indexed_adapter('POSTTRAN', 'XREFFILE'))
        with self.assertRaises(ValueError):
            twin.indexed_adapter('POSTTRAN', 'DALYTRAN')

    def test_digest_and_artifact_tamper_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'binary').write_bytes(b'original')
            twin.receipt(root/'build-receipt.json', source_commit=twin.SOURCE_COMMIT,
                         files={'binary': twin.sha(b'original')})
            twin.verify_build(root)
            (root/'binary').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'artifact'):
                twin.verify_build(root)
            d = (root/'build-receipt.json').read_text().replace('engineering', 'evidence')
            (root/'build-receipt.json').write_text(d)
            with self.assertRaisesRegex(ValueError, 'digest'):
                twin.verify_build(root)

    def test_runtime_environment_does_not_inherit_overrides(self):
        with patch.dict(twin.os.environ, {'COB_CURRENT_DATE':'1999', 'DD_ACCTFILE':'secret'}):
            self.assertNotIn('COB_CURRENT_DATE', twin.clean_env())
            self.assertNotIn('DD_ACCTFILE', twin.clean_env())


if __name__ == '__main__':
    unittest.main()
