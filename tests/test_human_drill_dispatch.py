"""CI-only public dispatch boundaries; no admission, consumption or signing."""
import contextlib
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_factory.cli import build_parser
from lightyear_factory.contracts import ContractError
from lightyear_execution.human_drill_dispatch import validate_public_domain,dispatch_human_drill


class HumanDrillDispatchTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.path='tests/fixtures/p5_public/source.txt'
        self.order=SimpleNamespace(allowed_paths=(self.path,),allow_network=False,max_attempts=1,
                                   metadata={},graph_node_ids=())
        self.manifest={self.path:'a'*64}
        self.args=['human-drill-execute','--source-root','public-source','--work-order','public-order.json',
            '--execution-policy','public-policy.json','--factory-plan','plan.json','--factory-approval','proof.json',
            '--factory-contract','contract.json','--factory-trust','external-public-trust.json',
            '--public-output-plan','tests/fixtures/p5_public/outputs.json',
            '--public-isolation-plan','tests/fixtures/p5_public/isolation.json',
            '--runs-root','public-run-evidence','--execution-runtime','docker']

    def validate(self):
        return validate_public_domain(self.order,self.manifest,
            'tests/fixtures/p5_public/outputs.json','tests/fixtures/p5_public/isolation.json')

    def test_cli_explicit_public_inputs_no_provider_or_signer(self):
        args=build_parser().parse_args(self.args)
        self.assertEqual(args.command,'human-drill-execute')
        self.assertEqual(args.execution_runtime,'docker')
        self.assertEqual(args.runs_root,Path('public-run-evidence'))
        for name in ('provider','model_config','candidate_signing_key','signed_work_order','factory_private_expected_values'):
            self.assertFalse(hasattr(args,name))

    def test_cli_refuses_provider_secret_private_and_abbreviated_flags(self):
        for extra in (['--provider','openai'],['--model-config','x'],['--api-key','synthetic'],
                      ['--factory-private-expected-values','x'],['--signed-work-order','x'],['--factory-pl','x']):
            with self.subTest(extra=extra),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                build_parser().parse_args(self.args+extra)

    def test_dispatch_refuses_outside_ci_before_reading_inputs(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}),self.assertRaisesRegex(ContractError,'ci-only'):
            dispatch_human_drill(SimpleNamespace())

    def test_public_domain_accepts_only_explicit_public_fixture_scope(self):
        self.assertIsNone(self.validate())
        for path in ('src/product.py','tests/fixtures/p5_public/../secret.txt',
                     'tests/fixtures/p5_public//source.txt','C:/private.txt',12):
            with self.subTest(path=path):
                self.manifest={path:'a'*64};self.order.allowed_paths=(path,)
                with self.assertRaises(ContractError):self.validate()

    def test_output_and_isolation_files_cannot_enter_worker_manifest(self):
        for name in ('outputs.json','isolation.json'):
            with self.subTest(name=name):
                self.manifest={self.path:'a'*64,'tests/fixtures/p5_public/'+name:'b'*64}
                with self.assertRaises(ContractError):self.validate()

    def test_network_retries_and_graph_routes_refuse(self):
        for field,value in (('allow_network',True),('max_attempts',2),('max_attempts',True),
                            ('graph_node_ids',('a',)),('metadata',{'context_schema':'1.1'}),
                            ('metadata',{'graph_policy':{'enabled':True}})):
            with self.subTest(field=field,value=value):
                original=getattr(self.order,field);setattr(self.order,field,value)
                try:
                    with self.assertRaises(ContractError):self.validate()
                finally:setattr(self.order,field,original)


if __name__=='__main__':unittest.main()
