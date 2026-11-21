"""CI-only disposable Ed25519 component checks; never production authority."""
import base64,copy,hashlib,json,os,tempfile,unittest
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_control_tower.decisions import canonical,digest
from lightyear_factory.contracts import ContractError
from tools.ci.p5_drills import DRILLS,EXPECTED,qualify
from tools.ci.configured_outcome_inventory import check_outcome_inventory_bytes,read_outcome_inventory

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only disposable cryptography')
class OutcomeInventoryBindings(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        self.public=self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        self.expected={name:dict(public_key=self.public,commit='a'*40,run_id='123',run_attempt='1',source_sha256={'public-source.py':'b'*64}) for name in DRILLS}
        self.bodies={name:dict(schema='p5-disposable-observation/1',id=name,expected=EXPECTED[name],observed={},expectation_met=False,
            gaps=['Disposable fixture, not production controller evidence.'],production_controller_receipt=False,
            commit='a'*40,run_id='123',run_attempt='1',source_sha256={'public-source.py':'b'*64}) for name in DRILLS}
    def pack(self,bodies=None,key=None,public=None):
        bodies=self.bodies if bodies is None else bodies;key=self.key if key is None else key;public=self.public if public is None else public
        raw={};rows=[]
        for name in DRILLS:
            body=bodies[name];envelope={**body,'content_sha256':digest(body),'signature':dict(algorithm='Ed25519',key_id=hashlib.sha256(public).hexdigest(),value=base64.b64encode(key.sign(canonical(body))).decode())}
            raw[name+'.json']=canonical(envelope);raw[name+'.public.pem']=public
            rows.append(dict(id=name,expectation_met=body['expectation_met'],gaps=body['gaps'],harness_error=False,receipt_file=name+'.json',public_key_file=name+'.public.pem',receipt_sha256=hashlib.sha256(raw[name+'.json']).hexdigest()))
        raw['summary.json']=canonical(dict(schema='p5-drills/1',complete=True,drills=rows,go=False,production_authority=False))
        return raw
    def test_real_fixture_signatures_bind_but_never_qualify(self):
        raw=self.pack();self.assertIsNone(check_outcome_inventory_bytes(raw,self.expected))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,value in raw.items():(root/name).write_bytes(value)
            self.assertEqual(read_outcome_inventory(root,self.expected),raw)
            self.assertFalse(qualify(root))
    def test_self_supplied_replacement_key_and_signatures_refused(self):
        key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        with self.assertRaises(ContractError):check_outcome_inventory_bytes(self.pack(key=key,public=public),self.expected)
    def test_valid_signatures_with_wrong_external_bindings_refused(self):
        for field,value in (('commit','c'*40),('run_id','124'),('run_attempt','2'),('source_sha256',{'public-source.py':'d'*64})):
            with self.subTest(field=field):
                bodies=copy.deepcopy(self.bodies);bodies[DRILLS[0]][field]=value
                with self.assertRaises(ContractError):check_outcome_inventory_bytes(self.pack(bodies),self.expected)
    def test_tampered_signature_even_with_updated_summary_hash_refused(self):
        raw=self.pack();name=DRILLS[0];envelope=json.loads(raw[name+'.json']);envelope['signature']['value']=base64.b64encode(bytes(64)).decode()
        raw[name+'.json']=canonical(envelope);summary=json.loads(raw['summary.json']);summary['drills'][0]['receipt_sha256']=hashlib.sha256(raw[name+'.json']).hexdigest();raw['summary.json']=canonical(summary)
        with self.assertRaises(ContractError):check_outcome_inventory_bytes(raw,self.expected)
    def test_inventory_missing_extra_duplicate_and_path_changes_refused(self):
        for mode in ('missing','extra','duplicate','path'):
            with self.subTest(mode=mode):
                raw=self.pack();summary=json.loads(raw['summary.json'])
                if mode=='missing':del raw[DRILLS[0]+'.public.pem']
                elif mode=='extra':raw['unexpected.json']=b'{}'
                elif mode=='duplicate':summary['drills'][1]=summary['drills'][0]
                else:summary['drills'][0]['receipt_file']='../outside.json'
                raw['summary.json']=canonical(summary)
                with self.assertRaises(ContractError):check_outcome_inventory_bytes(raw,self.expected)
    def test_unsigned_summary_cannot_change_signed_expectation_or_gaps(self):
        for field,value in (('expectation_met',True),('gaps',[])):
            with self.subTest(field=field):
                raw=self.pack();summary=json.loads(raw['summary.json']);summary['drills'][0][field]=value;raw['summary.json']=canonical(summary)
                with self.assertRaises(ContractError):check_outcome_inventory_bytes(raw,self.expected)
    def test_duplicate_wire_keys_refused_before_relationships(self):
        raw=self.pack();raw['summary.json']=b'{"complete":true,'+raw['summary.json'][1:]
        with self.assertRaises(ContractError):check_outcome_inventory_bytes(raw,self.expected)
