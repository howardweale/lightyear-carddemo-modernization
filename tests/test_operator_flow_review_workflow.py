"""Disposable CI input/clone probes; native authenticated main is never invoked."""
import ast,base64,hashlib,json,os,tempfile,unittest
from pathlib import Path
import test_operator_flow_metadata as fixtures
from tools.ci.operator_flow_producer import canonical
from tools.ci.operator_flow_review_workflow import _configuration,_trust_bytes,_clone_checkout,main
from tools.ci.operator_flow_review_cli import SCALARS

class ReviewWorkflow(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.temp=Path(os.environ['RUNNER_TEMP']).resolve();self.public=b'inert public bytes, not a key'
        values=dict(executable='1'*40,metadata_head='2'*40,producer_run_id='1',artifact_id='2',
            archive_sha256='3'*64,plan_sha256='4'*64,decision_sha256='5'*64,
            journal_head_sha256='6'*64,public_key_sha256=hashlib.sha256(self.public).hexdigest(),
            nonce_sha256='8'*64,commit_epoch='1700000000')
        self.env={'OPERATOR_REVIEW_'+k.upper():v for k,v in values.items()}
        self.env['OPERATOR_REVIEW_PUBLIC_KEY_BASE64']=base64.b64encode(self.public).decode()
    def test_independent_public_values_and_fixed_paths(self):
        values,public=_configuration(self.env,self.temp)
        self.assertEqual(public,self.public);self.assertEqual(values['producer_run_id'],1)
        self.assertEqual(Path(values['metadata_root']),self.temp/'operator-publication-review-inputs/metadata')
        self.assertEqual(set(values),set(SCALARS)|{'metadata_root','trust_path'})
    def test_trust_bytes_equal_original_producer_canonical(self):
        expected=dict(scope='factory',public_key='public.pem',journal_head_sha256='6'*64)
        self.assertEqual(_trust_bytes('6'*64),canonical(expected))
    def test_missing_external_values_refuse(self):
        for key in self.env:
            env=dict(self.env);del env[key]
            with self.subTest(key=key),self.assertRaises(ValueError):_configuration(env,self.temp)
    def test_public_key_encoding_size_and_digest_refuse(self):
        for value in ('!', 'a'*87385,base64.b64encode(b'other').decode()):
            env=dict(self.env,OPERATOR_REVIEW_PUBLIC_KEY_BASE64=value)
            with self.subTest(length=len(value)),self.assertRaises(ValueError):_configuration(env,self.temp)
    def test_bad_scalar_refuses_before_preparation(self):
        env=dict(self.env,OPERATOR_REVIEW_ARTIFACT_ID='True')
        with self.assertRaisesRegex(ValueError,'integer'):_configuration(env,self.temp)
    def test_scratch_main_refuses_before_files_or_api(self):
        self.assertNotEqual(os.environ.get('GITHUB_JOB'),'operator-publication-review')
        with self.assertRaisesRegex(ValueError,'original-job-only'):main()
    def test_template_has_read_only_scope_no_secrets_or_upload(self):
        root=Path(__file__).resolve().parents[1]
        raw=(root/'tools/ci/workflow_templates/operator-flow-publication-review.yml').read_text()
        self.assertIn('    name: operator-publication-review',raw)
        self.assertIn('persist-credentials: false',raw)
        self.assertIn('operator-rehearsal-publication-review',raw)
        self.assertNotIn('secrets.',raw);self.assertNotIn('write',raw);self.assertNotIn('upload-artifact',raw)
        self.assertEqual(raw.count('run: python -B -m tools.ci.operator_flow_review_workflow'),1)
        for key in SCALARS:self.assertEqual(raw.count('vars.OPERATOR_REVIEW_'+key.upper()+' '),1)
        self.assertFalse((root/'.github/workflows/operator-flow-publication-review.yml').exists())
    def test_original_review_once_after_identity_and_clone(self):
        path=Path(__file__).resolve().parents[1]/'tools/ci/operator_flow_review_workflow.py'
        tree=ast.parse(path.read_bytes());body=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n for n in ast.walk(body) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        review=[n for n in calls if n.func.id=='review_publication'];self.assertEqual(len(review),1)
        first_identity=min(n.lineno for n in calls if n.func.id=='_review_current_identity')
        clone=next(n.lineno for n in calls if n.func.id=='_clone_checkout')
        self.assertLess(first_identity,clone);self.assertLess(clone,review[0].lineno)
    def fixture(self):
        fixture=fixtures.MetadataObjects();fixture.setUp();self.addCleanup(fixture.doCleanups)
        base=Path(fixture.tmp.name)/'workflow-inputs';base.mkdir();empty=base/'empty';empty.mkdir()
        return fixture,base/'metadata',empty
    def test_actual_detached_clone_preserves_source_and_no_hardlinks(self):
        fixture,metadata,empty=self.fixture()
        before={p.relative_to(fixture.root).as_posix():p.read_bytes() for p in fixture.root.rglob('*') if p.is_file()}
        self.assertIsNone(_clone_checkout(fixture.root,metadata,empty,fixture.head))
        self.assertEqual(fixture.git('rev-parse','HEAD',root=metadata).decode().strip(),fixture.head)
        self.assertEqual(fixture.git('rev-parse','--abbrev-ref','HEAD',root=metadata).decode().strip(),'HEAD')
        self.assertEqual(fixture.git('status','--porcelain=v1','--untracked-files=all',root=metadata),b'')
        self.assertTrue(all(p.stat().st_nlink==1 for p in (metadata/'.git').rglob('*') if p.is_file()))
        self.assertEqual(before,{p.relative_to(fixture.root).as_posix():p.read_bytes() for p in fixture.root.rglob('*') if p.is_file()})
    def test_existing_clone_is_never_reused(self):
        fixture,metadata,empty=self.fixture();metadata.mkdir();marker=metadata/'keep';marker.write_bytes(b'unchanged')
        with self.assertRaisesRegex(ValueError,'fresh-clone'):_clone_checkout(fixture.root,metadata,empty,fixture.head)
        self.assertEqual(marker.read_bytes(),b'unchanged')
