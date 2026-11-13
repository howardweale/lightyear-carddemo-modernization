"""CI-only actual Git serialization checks. No fake API or admitted proof."""
from base64 import b64decode
from datetime import datetime
import copy,os,unittest
import test_operator_flow_metadata as fixtures
from tools.ci.operator_flow_metadata import object_id,PREFIX
from tools.ci.operator_flow_publication_objects import ANCESTORS,object_requests,tree_entries,tree_bytes

class PublicationObjects(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.fixture=fixtures.MetadataObjects()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.candidate=self.fixture.build();self.metadata=dict(self.fixture.raw)
        self.base={}
        for path in ANCESTORS:
            spec=self.fixture.head+(':'+path.rstrip('/') if path else '^{tree}')
            oid=self.fixture.git('rev-parse',spec).decode().strip()
            self.base[path]=(oid,self.fixture.git('cat-file','tree',oid))
    def requests(self):
        return object_requests(self.candidate,self.metadata,self.base,
            expected_executable=self.fixture.head,expected_candidate=self.candidate['commit'])
    def test_original_git_reconstructs_every_rest_body_and_exact_commit(self):
        original=copy.deepcopy((self.candidate,self.metadata,self.base))
        rows=self.requests();self.assertEqual(len(rows),8)
        for endpoint,oid,body in rows:
            if endpoint=='blobs':
                self.assertEqual(body['encoding'],'base64')
                raw=b64decode(body['content'],validate=True);kind='blob'
            elif endpoint=='trees':
                self.assertEqual(set(body),{'tree'})
                raw=tree_bytes([(r['path'].encode(),r['mode'].lstrip('0'),r['sha']) for r in body['tree']])
                kind='tree'
            else:
                self.assertEqual(endpoint,'commits')
                self.assertEqual(body['parents'],[self.fixture.head])
                self.assertEqual(body['author'],body['committer'])
                who=body['author'];epoch=int(datetime.fromisoformat(who['date']).timestamp())
                identity=who['name']+' <'+who['email']+'> '+str(epoch)+' +0000'
                raw=('tree '+body['tree']+'\nparent '+body['parents'][0]+'\nauthor '+identity+
                    '\ncommitter '+identity+'\n\n'+body['message']).encode();kind='commit'
            self.assertEqual(self.fixture.git('hash-object','-t',kind,'--stdin',data=raw).decode().strip(),oid)
            self.assertEqual(self.candidate['objects'][oid],(kind,raw))
        self.assertEqual((self.candidate,self.metadata,self.base),original)
        self.assertEqual(rows[-1][1],self.candidate['commit'])
        self.assertFalse(self.candidate['publication_authorized'])
        self.assertFalse(self.candidate['publish_ready'])
    def test_independent_expected_head_mismatch_refuses(self):
        for e,m in [('0'*40,self.candidate['commit']),(self.fixture.head,'0'*40)]:
            with self.assertRaisesRegex(ValueError,'expected-E-M'):
                object_requests(self.candidate,self.metadata,self.base,expected_executable=e,expected_candidate=m)
    def test_changed_original_metadata_refuses(self):
        self.metadata[PREFIX+'proof.json']+=b' '
        with self.assertRaisesRegex(ValueError,'missing-or-changed-object'):self.requests()
    def test_missing_and_extra_original_objects_refuse(self):
        saved=dict(self.candidate['objects'])
        self.candidate['objects'].pop(self.candidate['commit'])
        with self.assertRaisesRegex(ValueError,'missing-or-changed-object'):self.requests()
        self.candidate['objects']=saved
        self.candidate['objects'][object_id('blob',b'extra')]=('blob',b'extra')
        with self.assertRaisesRegex(ValueError,'object-inventory'):self.requests()
    def test_tampered_object_under_original_digest_refuses(self):
        oid=self.candidate['commit'];kind,raw=self.candidate['objects'][oid]
        self.candidate['objects'][oid]=(kind,raw+b' ')
        with self.assertRaisesRegex(ValueError,'object-digest'):self.requests()
    def test_base_bytes_and_ancestor_substitution_refuse(self):
        saved=dict(self.base);oid,raw=self.base[PREFIX]
        self.base[PREFIX]=(oid,raw+b' ')
        with self.assertRaisesRegex(ValueError,'base-tree-digest'):self.requests()
        self.base=saved
        self.base[PREFIX]=(object_id('tree',b''),b'')
        with self.assertRaisesRegex(ValueError,'base-ancestor-link'):self.requests()
    def test_original_tree_names_modes_and_order_are_not_normalized(self):
        raw_oid=b'1'*20
        for raw in (b'100644 a\0'+raw_oid+b'100644 a\0'+raw_oid,
                    b'100644 b\0'+raw_oid+b'100644 a\0'+raw_oid,
                    b'100644 ../a\0'+raw_oid,b'100644 \xff\0'+raw_oid,
                    b'040000 dir\0'+raw_oid,b'100644 a\0'+raw_oid[:-1]):
            with self.subTest(raw=raw),self.assertRaises(ValueError):tree_entries(raw)
        rows=[(b'a','100755','1'*40),(b'dir','40000','2'*40),
            ('file-\u00e9'.encode(),'100644','3'*40),(b'link','120000','4'*40),
            (b'submodule','160000','5'*40)]
        self.assertEqual(tree_entries(tree_bytes(rows)),rows)
    def test_prepared_epoch_and_candidate_tree_substitution_refuse(self):
        epoch=self.candidate['commit_epoch'];self.candidate['commit_epoch']=True
        with self.assertRaisesRegex(ValueError,'prepared-epoch'):self.requests()
        self.candidate['commit_epoch']=epoch;self.candidate['tree']='0'*40
        with self.assertRaisesRegex(ValueError,'candidate-tree'):self.requests()
