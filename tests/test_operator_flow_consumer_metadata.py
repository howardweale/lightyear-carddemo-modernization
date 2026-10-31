"""CI-only real Git byte/ancestry checks and untrusted report relationships.

No fixture below is a valid proof, public key, native review or admission. A
matching untrusted report is deliberately insufficient to authenticate anything.
No API replacement, fake live context, signature, nonce, model or network call.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,os,subprocess,tempfile,unittest
from tools.ci.operator_flow_consumer import check_metadata,check_public_expectations,METADATA,WORKFLOW

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only metadata boundary checks')
class ConsumerMetadataGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP'])
        self.addCleanup(self.tmp.cleanup)
        self.root=(Path(self.tmp.name)/'source').resolve();self.root.mkdir()
        self.env=dict(os.environ,GIT_AUTHOR_NAME='Metadata fixture',GIT_AUTHOR_EMAIL='fixture@example.invalid',
            GIT_COMMITTER_NAME='Metadata fixture',GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init');self.git('config','core.autocrlf','false')
        (self.root/'source.txt').write_bytes(b'inert executable fixture\n')
        self.git('add','.');self.git('commit','-m','fixture E')
        self.executable=self.git('rev-parse','HEAD').decode().strip()
        # Deliberately not a signed plan/contract/proof. These exercise only
        # original Git/file boundary checks, never the native admission path.
        self.files={name:json.dumps({'inert_filename':name}).encode()+b'\n' for name in METADATA}
    def git(self,*args):
        return subprocess.check_output(['git','--no-optional-locks','-C',str(self.root),
            '-c','commit.gpgsign=false','-c','core.hooksPath='+str(Path(self.tmp.name)/'no-hooks'),*args],
            env=self.env,stderr=subprocess.DEVNULL)
    def metadata_commit(self,*,omit=None,extra=False):
        for name,relative in METADATA.items():
            if name==omit:continue
            path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(self.files[name])
        if extra:(self.root/'source.txt').write_bytes(b'unapproved source delta\n')
        self.git('add','.');self.git('commit','-m','fixture M')
        return dict(executable=self.executable,metadata_head=self.git('rev-parse','HEAD').decode().strip())
    def test_exact_three_path_bytes_pass_only_structural_check(self):
        approval=self.metadata_commit()
        self.assertIsNone(check_metadata(self.root,approval,self.files))
        self.assertEqual(self.git('rev-parse','HEAD').decode().strip(),approval['metadata_head'])
        self.assertEqual(self.git('status','--porcelain=v1','--untracked-files=all'),b'')
    def test_different_checked_out_head_refuses(self):
        approval=self.metadata_commit();approval['metadata_head']='0'*40
        with self.assertRaisesRegex(ValueError,'consumer-exact-M'):
            check_metadata(self.root,approval,self.files)
    def test_wrong_independent_parent_refuses(self):
        approval=self.metadata_commit();approval['executable']='0'*40
        with self.assertRaisesRegex(ValueError,'consumer-single-metadata-parent-E'):
            check_metadata(self.root,approval,self.files)
    def test_extra_committed_source_change_refuses(self):
        approval=self.metadata_commit(extra=True)
        with self.assertRaisesRegex(ValueError,'consumer-only-three-metadata-paths'):
            check_metadata(self.root,approval,self.files)
    def test_missing_metadata_path_refuses(self):
        approval=self.metadata_commit(omit='proof.json')
        with self.assertRaisesRegex(ValueError,'consumer-only-three-metadata-paths'):
            check_metadata(self.root,approval,self.files)
    def test_different_handoff_bytes_refuse_without_changing_originals(self):
        approval=self.metadata_commit()
        for name in METADATA:
            with self.subTest(name=name):
                changed=dict(self.files);changed[name]+=b' '
                with self.assertRaisesRegex(ValueError,'consumer-byte-exact-published-handoff'):
                    check_metadata(self.root,approval,changed)
                self.assertEqual((self.root/METADATA[name]).read_bytes(),self.files[name])
        self.assertEqual(self.git('status','--porcelain=v1','--untracked-files=all'),b'')
    def test_dirty_tracked_or_untracked_source_refuses(self):
        approval=self.metadata_commit()
        source=self.root/'source.txt';original=source.read_bytes();source.write_bytes(b'dirty\n')
        with self.assertRaisesRegex(ValueError,'consumer-clean-source'):
            check_metadata(self.root,approval,self.files)
        source.write_bytes(original);(self.root/'untracked.txt').write_bytes(b'untracked\n')
        with self.assertRaisesRegex(ValueError,'consumer-clean-source'):
            check_metadata(self.root,approval,self.files)
    def test_second_metadata_commit_is_not_sole_parent_E(self):
        approval=self.metadata_commit()
        path=self.root/METADATA['proof.json'];path.write_bytes(self.files['proof.json']+b' ')
        self.git('add','.');self.git('commit','-m','second metadata change')
        approval['metadata_head']=self.git('rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(ValueError,'consumer-single-metadata-parent-E'):
            check_metadata(self.root,approval,self.files)

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only untrusted relationship checks')
class ConsumerCandidateClaimTests(unittest.TestCase):
    def setUp(self):
        self.public=b'NOT A PUBLIC KEY; inert relationship fixture\n'
        self.approval=dict(executable='a'*40,metadata_head='b'*40,plan_sha256='c'*64,
            decision_sha256='d'*64,journal_head_sha256='e'*64,nonce_sha256='f'*64,
            public_key_sha256=sha256(self.public).hexdigest())
        # This is an untrusted claim with no valid proof, not a passed native
        # verification result. The pure predicate has no signature authority.
        self.claim=dict(parent=self.approval['executable'],commit=self.approval['metadata_head'],
            native_candidate_verified=True,**{k:self.approval[k] for k in
                ('plan_sha256','decision_sha256','journal_head_sha256','nonce_sha256')})
        self.report=dict(decision_sha256=self.approval['decision_sha256'],nonce_sha256=self.approval['nonce_sha256'],
            consumer_workflow=WORKFLOW,metadata_candidate=self.claim)
    def files(self,report):
        return {'public.pem':self.public,'trust.json':json.dumps(dict(scope='factory',public_key='public.pem',
            journal_head_sha256=self.approval['journal_head_sha256'])).encode(),
            'producer.json':json.dumps(report).encode()}
    def test_matching_untrusted_claims_supply_no_proof_or_admission(self):
        files=self.files(self.report)
        self.assertNotIn('proof.json',files)
        self.assertIsNone(check_public_expectations(self.approval,files))
    def test_independent_E_and_M_cannot_be_replaced_by_claim(self):
        for key in ('parent','commit'):
            with self.subTest(key=key):
                report=deepcopy(self.report);report['metadata_candidate'][key]='0'*40
                with self.assertRaisesRegex(ValueError,'consumer-original-candidate-binding'):
                    check_public_expectations(self.approval,self.files(report))
    def test_each_candidate_case_binding_must_match_independent_expectation(self):
        for key in ('plan_sha256','decision_sha256','journal_head_sha256','nonce_sha256'):
            with self.subTest(key=key):
                report=deepcopy(self.report);report['metadata_candidate'][key]='0'*64
                with self.assertRaisesRegex(ValueError,'consumer-original-candidate-binding'):
                    check_public_expectations(self.approval,self.files(report))
    def test_candidate_verified_claim_requires_exact_boolean(self):
        for value in (False,1,'true',None):
            with self.subTest(value=value):
                report=deepcopy(self.report);report['metadata_candidate']['native_candidate_verified']=value
                with self.assertRaisesRegex(ValueError,'consumer-original-candidate-binding'):
                    check_public_expectations(self.approval,self.files(report))
    def test_absent_or_nonmapping_candidate_claim_refuses(self):
        for value in (None,[],False,'candidate'):
            with self.subTest(value=value):
                report=deepcopy(self.report);report['metadata_candidate']=value
                with self.assertRaisesRegex(ValueError,'consumer-original-candidate-binding'):
                    check_public_expectations(self.approval,self.files(report))
        report=deepcopy(self.report);del report['metadata_candidate']
        with self.assertRaisesRegex(ValueError,'consumer-original-candidate-binding'):
            check_public_expectations(self.approval,self.files(report))
    def test_outer_case_claims_cannot_override_independent_expectations(self):
        for key in ('decision_sha256','nonce_sha256','consumer_workflow'):
            with self.subTest(key=key):
                report=deepcopy(self.report);report[key]='wrong'
                with self.assertRaisesRegex(ValueError,'consumer-producer-exact-case'):
                    check_public_expectations(self.approval,self.files(report))
