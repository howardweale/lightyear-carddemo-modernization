"""CI-only actual Git fixture construction, never proof/admission authority."""
from pathlib import Path
import os,subprocess,tempfile,unittest
from tools.ci.operator_flow_metadata import prepare_candidate,PREFIX,LIMITS,object_id

class MetadataObjects(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'source';self.root.mkdir()
        self.env=dict(os.environ,GIT_AUTHOR_NAME='Fixture',GIT_AUTHOR_EMAIL='fixture@example.invalid',
            GIT_COMMITTER_NAME='Fixture',GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init');self.git('config','core.autocrlf','false')
        parent=self.root/PREFIX;parent.mkdir(parents=True)
        (parent/'retained.txt').write_bytes(b'original retained fixture\n')
        (self.root/'executable.py').write_bytes(b'# inert fixture source\n')
        self.git('add','.');self.git('commit','-m','fixture E')
        self.head=self.git('rev-parse','HEAD').decode().strip()
        # These bytes are intentionally NOT a valid proof or admission packet.
        self.raw={path:('{"fixture_path":"'+path+'"}\n').encode() for path in LIMITS}
    def git(self,*args,data=None,root=None):
        return subprocess.check_output(['git','-C',str(root or self.root),*args],input=data,env=self.env,stderr=subprocess.DEVNULL)
    def build(self):return prepare_candidate(self.root,self.head,self.raw,1700000000)
    def test_actual_git_independently_verifies_three_path_candidate(self):
        before=self.git('status','--porcelain=v1');candidate=self.build()
        copy=Path(self.tmp.name)/'verification'
        subprocess.run(['git','clone','--no-hardlinks',str(self.root),str(copy)],check=True,capture_output=True,env=self.env)
        for oid,(kind,body) in candidate['objects'].items():
            actual=self.git('hash-object','-w','-t',kind,'--stdin',data=body,root=copy).decode().strip()
            self.assertEqual(actual,oid)
        commit=candidate['commit']
        self.assertEqual(self.git('rev-list','--parents','-n','1',commit,root=copy).decode().split(),[commit,self.head])
        paths=self.git('diff','--name-only',self.head,commit,root=copy).decode().splitlines()
        self.assertEqual(set(paths),set(LIMITS))
        for path,raw in self.raw.items():self.assertEqual(self.git('show',commit+':'+path,root=copy),raw)
        self.assertEqual(self.git('show',commit+':executable.py',root=copy),b'# inert fixture source\n')
        self.assertEqual(self.git('status','--porcelain=v1'),before)
        self.assertEqual(self.git('rev-parse','HEAD').decode().strip(),self.head)
        self.assertFalse(candidate['publish_ready']);self.assertFalse(candidate['native_proof_verified'])
    def test_same_prepared_inputs_give_same_commit(self):
        self.assertEqual(self.build()['commit'],self.build()['commit'])
    def test_dirty_source_refuses(self):
        (self.root/'executable.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'clean-E'):self.build()
    def test_existing_metadata_is_never_overwritten(self):
        (self.root/(PREFIX+'proof.json')).write_bytes(b'retained')
        self.git('add','.');self.git('commit','-m','existing metadata');self.head=self.git('rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(ValueError,'already-exists'):self.build()
    def test_extra_path_or_nonbytes_refuses(self):
        self.raw['other.txt']=b'x'
        with self.assertRaisesRegex(ValueError,'three-paths'):self.build()
        del self.raw['other.txt'];self.raw[PREFIX+'proof.json']='text'
        with self.assertRaisesRegex(ValueError,'original-bytes'):self.build()
    def test_wrong_head_or_boolean_epoch_refuses(self):
        with self.assertRaises(ValueError):prepare_candidate(self.root,'0'*40,self.raw,1700000000)
        with self.assertRaises(ValueError):prepare_candidate(self.root,self.head,self.raw,True)
    def test_oversized_metadata_refuses_before_git(self):
        self.raw[PREFIX+'plan.json']=b'x'*(LIMITS[PREFIX+'plan.json']+1)
        with self.assertRaisesRegex(ValueError,'original-bytes'):self.build()
