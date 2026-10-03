import base64
import copy
import hashlib
import json
import unittest
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_control_tower.decisions import canonical, digest
from tools.ms94_b06_attribution import project


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.policy = json.loads(Path('docs/calibration/idempiere-ms94/stage-b-06/preparation/template-r1/diagnostic-policy.json').read_bytes())
        self.binding = {'run_id': 'fixture-native-run', 'snapshot_sha256': 'a'*64,
                        'candidate_sha256': 'b'*64, 'observer_sha256': 'c'*64,
                        'execution_sha256': {'oracle': 'd'*64, 'postgresql': 'e'*64}}

    def sign(self, body):
        value = {**body, 'content_sha256': digest(body)}
        value['signature'] = {'algorithm': 'Ed25519', 'key_id': hashlib.sha256(self.public).hexdigest(),
                              'value': base64.b64encode(self.key.sign(canonical(body))).decode()}
        return value

    def evidence(self, kind='posted'):
        proofs, replays = {}, {}
        for lane in ('oracle', 'postgresql'):
            bind = {**self.binding, 'lane': lane}
            body = {'artifact_type': 'ms94-b06-posting-origin-proof/1', 'binding': bind,
                    'observer_complete': True, 'non_candidate_fault_checks_passed': True,
                    'document_label': 'invoice',
                    'events': [{'sequence': 1, 'kind': kind, 'origin': 'candidate',
                                'document_key': [318, 123456], 'execution_sha256': self.binding['execution_sha256'][lane]},
                               {'sequence': 2, 'kind': 'native-readback'},
                               {'sequence': 3, 'kind': 'posting-failed', 'origin': 'support',
                                'document_key': [318, 123456], 'step': 'JourneySupport.postOnce'}],
                    'pre_support_native_readback': {'document_key': [318, 123456], 'after_event_sequence': 2,
                        'capture_sha256': 'f'*64, 'posted': True, 'accounting_facts_present': True,
                        'lock_owner_execution_sha256': self.binding['execution_sha256'][lane], 'lock_still_held': True}}
            proofs[lane] = self.sign(body)
            replays[lane] = {'full_entry_replayed': True, 'observer_replayed': True,
                             'proof_sha256': proofs[lane]['content_sha256'], 'binding': bind,
                             'verified_capture_hashes': ['f'*64]}
        return proofs, replays

    def call(self, proofs, replays):
        return project(proofs, public_key=self.public, binding=self.binding, policy=self.policy,
                       replayed_native_evidence=replays)

    def test_candidate_prior_post_or_lock_direct_no_private_values(self):
        for kind in ('posted', 'lock-held'):
            proofs, replays = self.evidence(kind)
            value = self.call(proofs, replays)
            self.assertFalse(value['equipment_suspect'])
            self.assertEqual('builder-direct', value['route'])
            self.assertEqual({'id', 'category', 'document', 'posting_step', 'lanes'}, set(value['diagnostics'][0]))
            self.assertNotIn('123456', json.dumps(value))

    def test_support_outside_fault_wrong_document_and_missing_proof_send_nothing(self):
        for mutation in ('support', 'outside', 'equipment', 'other-document', 'missing', 'gap', 'no-readback'):
            with self.subTest(mutation=mutation):
                proofs, replays = self.evidence()
                if mutation == 'missing': del proofs['oracle']
                else:
                    body = {k:copy.deepcopy(v) for k,v in proofs['oracle'].items() if k not in ('signature','content_sha256')}
                    if mutation in ('support', 'outside'): body['events'][0]['origin'] = mutation
                    elif mutation == 'equipment': body['non_candidate_fault_checks_passed'] = False
                    elif mutation == 'other-document': body['events'][0]['document_key'] = [318, 9]
                    elif mutation == 'gap': body['events'][0]['sequence'] = 0
                    else: body['pre_support_native_readback']['posted'] = False
                    proofs['oracle'] = self.sign(body)
                    replays['oracle']['proof_sha256'] = proofs['oracle']['content_sha256']
                value = self.call(proofs,replays)
                self.assertTrue(value['equipment_suspect'])
                self.assertEqual([], value['diagnostics'])
                self.assertEqual('pause',value['route'])

    def test_signature_alone_does_not_replace_independent_native_replay(self):
        proofs, replays = self.evidence()
        replays['oracle']['observer_replayed'] = False
        self.assertEqual([], self.call(proofs,replays)['diagnostics'])
        proofs, replays = self.evidence()
        proofs['oracle']['events'][0]['document_key'] = [318, 7]
        self.assertTrue(self.call(proofs,replays)['equipment_suspect'])


if __name__ == '__main__': unittest.main()
