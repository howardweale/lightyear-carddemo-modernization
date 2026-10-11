import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_calibration.contracts import seal
from lightyear_control_tower.decisions import canonical,digest
from tools.b06_host_probe.alternatives_partition import classify,partition

class AlternativesPartitionTests(unittest.TestCase):
    def test_caller_is_not_generation_input(self):
        self.assertEqual(classify({'stack':[{'class':'App','class_object_id':1,'loader':'9'}]})[0], 'unresolved-no-class-input-witness')
    def test_bootstrap_input_is_only_a_candidate(self):
        self.assertEqual(classify({'lambda_factory':{'implClass':{'class':'java.lang.String','class_object_id':1,'loader':'bootstrap'}}})[0], 'bootstrap-only-captured-input-candidate')
    def test_direct_application_class_input_is_witness(self):
        self.assertEqual(classify({'definer':{'lookup':{'class':'example.App','class_object_id':1,'loader':'9'}}})[0], 'application-derived-input')
    def test_nonbootstrap_platform_type_stays_unresolved(self):
        self.assertEqual(classify({'lambda_factory':{'implClass':{'class':'javax.sql.DataSource','class_object_id':1,'loader':'9'}}})[0], 'unresolved-platform-loader-input')
    def test_class_name_alone_is_not_runtime_identity(self):
        self.assertEqual(classify({'lambda_form_graph':{'nodes':{'1':{'class':'example.App'}}}})[0], 'unresolved-no-class-input-witness')
    def test_signed_partition_binds_stream_and_exports_no_values(self):
        # Ephemeral synthetic key only, never a campaign/engineering authority.
        key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        def sign(body):
            return dict(body,content_sha256=digest(body),signature=dict(algorithm='Ed25519',key_id=hashlib.sha256(public).hexdigest(),value=base64.b64encode(key.sign(canonical(body))).decode()))
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            record=seal(dict(previous_sha256=None,event=dict(sequence=1,kind='generation-entry',record=dict(entry_method='synthetic',lambda_factory={'class':'PRIVATE-TEST-INPUT','class_object_id':4,'loader':'9'}))))
            raw=(json.dumps(record)+'\n').encode();(folder/'events.jsonl').write_bytes(raw)
            body=dict(complete=False,event_count=1,last_event_sha256=record['content_sha256'],event_file_sha256=hashlib.sha256(raw).hexdigest(),plan_sha256='0'*64,lane='oracle')
            for name in ('frame-census.json','failure.json'):(folder/name).write_text(json.dumps(sign(body)))
            result=partition(folder,public)
            self.assertEqual(result['counts'],{'application-derived-input':1});self.assertEqual(result['image_independent_proven'],0)
            self.assertNotIn('PRIVATE-TEST-INPUT',json.dumps(result));self.assertEqual(result['signatures_verified'],2)
            (folder/'events.jsonl').write_bytes(raw.replace(b'PRIVATE-TEST-INPUT',b'TAMPERED'))
            with self.assertRaises(ValueError):partition(folder,public)
            (folder/'events.jsonl').write_bytes(raw)
            bad=dict(sign(body));bad['signature']['value']=base64.b64encode(b'wrong').decode();(folder/'failure.json').write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'classification-signature-or-scope'):partition(folder,public)

if __name__=='__main__':unittest.main()
