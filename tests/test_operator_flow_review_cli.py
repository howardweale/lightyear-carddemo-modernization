"""CI-only public argument/source probes; no API or native proof invocation."""
import hashlib,os,subprocess,tempfile,unittest
from pathlib import Path
from tools.ci.operator_flow_review_cli import _parse_args,_caller_source,main,SCALARS,PATHS

class ReviewCLI(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        root=Path(os.environ['RUNNER_TEMP']).resolve()
        self.values=dict(executable='1'*40,metadata_head='2'*40,producer_run_id='1',artifact_id='2',
            archive_sha256='3'*64,plan_sha256='4'*64,decision_sha256='5'*64,
            journal_head_sha256='6'*64,public_key_sha256='7'*64,nonce_sha256='8'*64,
            commit_epoch='1700000000',metadata_root=str(root/'inert-M'),trust_path=str(root/'public'/'trust.json'))
    def args(self,values=None):
        return [v for key,value in (values or self.values).items() for v in ('--'+key.replace('_','-'),value)]
    def test_exact_public_scalars_preserved_without_authority(self):
        result=_parse_args(self.args());self.assertEqual(set(result),set(SCALARS+PATHS))
        self.assertEqual(result['commit_epoch'],1700000000)
        self.assertEqual(result['executable'],self.values['executable'])
        self.assertEqual(result['trust_path'],self.values['trust_path'])
    def test_duplicate_flag_refuses(self):
        args=self.args();args[-2]=args[0]
        with self.assertRaisesRegex(ValueError,'duplicate'):_parse_args(args)
    def test_missing_unknown_and_extra_refuse(self):
        unknown=self.args();unknown[0]='--caller-api'
        for args in (self.args()[:-2],self.args()+['--extra','x'],unknown):
            with self.subTest(args=args),self.assertRaises(ValueError):_parse_args(args)
    def test_integer_encodings_refuse(self):
        for value in ('0','01','+1','True',' 1','1.0','9'*21):
            values=dict(self.values,artifact_id=value)
            with self.subTest(value=value),self.assertRaises(ValueError):_parse_args(self.args(values))
    def test_hash_and_relative_path_refuse(self):
        for key,value in (('metadata_head','1'*40),('nonce_sha256','bad'),('trust_path','trust.json')):
            values=dict(self.values,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):_parse_args(self.args(values))
    def test_scratch_job_refuses_before_arguments_or_api(self):
        self.assertNotEqual(os.environ.get('GITHUB_JOB'),'operator-publication-review')
        with self.assertRaisesRegex(ValueError,'review-cli-original-job-only'):main()
    def test_actual_loaded_caller_matches_committed_source(self):
        root=Path(__file__).resolve().parents[1]
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip()
        expected=hashlib.sha256((root/'tools/ci/operator_flow_review_cli.py').read_bytes()).hexdigest()
        self.assertEqual(_caller_source(root,head),expected)
    def test_other_root_refuses_original_module_without_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'review-cli-original-module'):
                _caller_source(Path(tmp).resolve(),'1'*40)
