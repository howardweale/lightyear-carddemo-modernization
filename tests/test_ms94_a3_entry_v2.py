import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from lightyear_calibration.contracts import seal, read_json, CalibrationError
from lightyear_control_tower.decisions import verify_envelope
from lightyear_workflow.campaign_engine import Signer
from tools.ms94_a3_entry_v2 import admit
from tools.ms94_a3_qualification_v2 import schedule
from tools.ms94_a3_qualification import schedule as original_schedule


def test_signer():
    signer = Signer.__new__(Signer)
    signer.key = Ed25519PrivateKey.generate()
    signer.public = signer.key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return signer


class EntrySigningBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name); self.signer = test_signer()
        self.checked = seal({'artifact_type':'ms94-a3-full-entry-admission',
            'checkpoint_profile':'admitted','checkpoint_sha256':'checkpoint',
            'preparation_verification_sha256':'preparation',
            'native_entry_checks':{'oracle':{'passed':True},'postgresql':{'passed':True}},
            'restore_sha256':{},'passed':True})
        self.mock = patch('tools.ms94_a3_entry_v2.check', return_value=self.checked)
        self.mock.start(); self.addCleanup(self.mock.stop)

    def test_original_nested_seal_signature_is_rejected(self):
        self.assertFalse(verify_envelope(self.signer.sign(self.checked),self.signer.public))

    def test_real_signer_roundtrip_preserves_every_checked_field(self):
        for profile in ('admitted','perturbed'):
            with self.subTest(profile=profile):
                value={k:v for k,v in self.checked.items() if k!='content_sha256'}
                value['checkpoint_profile']=profile
                value['restore_sha256']={} if profile=='admitted' else {'oracle':'a','postgresql':'b'}
                checked=seal(value)
                with patch('tools.ms94_a3_entry_v2.check',return_value=checked):
                    envelope=admit(self.run,self.signer)
                self.assertTrue(verify_envelope(envelope,self.signer.public))
                self.assertEqual(envelope['content_sha256'],checked['content_sha256'])
                self.assertEqual({k:v for k,v in envelope.items() if k!='signature'},checked)
                self.assertEqual(read_json(self.run/'a3-entry-admission.json'),envelope)
                (self.run/'a3-entry-admission.json').unlink()

    def test_real_verifier_rejects_tampering_and_wrong_key(self):
        envelope=admit(self.run,self.signer)
        bad=copy.deepcopy(envelope);bad['native_entry_checks']['oracle']['passed']=False
        self.assertFalse(verify_envelope(bad,self.signer.public))
        self.assertFalse(verify_envelope(envelope,test_signer().public))

    def test_invalid_source_seal_cannot_be_signed(self):
        self.checked['checkpoint_sha256']='tampered'
        with self.assertRaises(CalibrationError):admit(self.run,self.signer)
        self.assertFalse((self.run/'a3-entry-admission.json').exists())

    def test_invalid_signer_output_blocks_persistence(self):
        with patch.object(self.signer,'sign',return_value=self.signer.sign(self.checked)):
            with self.assertRaisesRegex(CalibrationError,'Invalid new entry'):admit(self.run,self.signer)
        self.assertFalse((self.run/'a3-entry-admission.json').exists())

    def test_valid_signature_over_changed_body_is_rejected(self):
        original=self.signer.sign
        def changed(body):return original({**body,'checkpoint_sha256':'different'})
        with patch.object(self.signer,'sign',side_effect=changed):
            with self.assertRaisesRegex(CalibrationError,'Signer changed'):admit(self.run,self.signer)
        self.assertFalse((self.run/'a3-entry-admission.json').exists())

    def test_persisted_tampering_blocks_return_to_execution(self):
        from lightyear_calibration.journey_order import save
        def tamper(path,body):save(path,{**body,'checkpoint_sha256':'different'})
        with patch('tools.ms94_a3_entry_v2.save',side_effect=tamper):
            with self.assertRaisesRegex(CalibrationError,'Persisted entry'):admit(self.run,self.signer)

    def test_existing_entry_is_never_overwritten(self):
        path=self.run/'a3-entry-admission.json';path.write_bytes(b'preserve')
        with self.assertRaisesRegex(CalibrationError,'Preserve existing'):admit(self.run,self.signer)
        self.assertEqual(path.read_bytes(),b'preserve')

    def test_revision_requalifies_the_entire_original_schedule(self):
        self.assertEqual(schedule(),original_schedule());self.assertEqual(len(schedule()),14)


if __name__=='__main__':unittest.main()
