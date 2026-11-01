"""CI-only parser boundary tests. No proof verification, signing or execution."""
import contextlib
import io
import os
import unittest
from lightyear_factory.cli import build_parser


class HumanDrillReviewCLITests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.args=['human-drill-public-proof-review','--source-root','public-source','--work-order','public-order.json',
            '--execution-policy','public-policy.json','--factory-plan','plan.json','--factory-approval','proof.json',
            '--factory-contract','contract.json','--factory-trust','external-public-trust.json',
            '--public-output-plan','tests/fixtures/p5_public/outputs.json']

    def test_public_proof_review_has_no_execution_or_provider_options(self):
        args=build_parser().parse_args(self.args)
        self.assertEqual(args.command,'human-drill-public-proof-review')
        for name in ('execution_runtime','provider','signed_work_order','model_config'):
            self.assertFalse(hasattr(args,name))

    def test_execution_secret_or_abbreviated_flags_refuse(self):
        for extra in (['--provider','openai'],['--execution-runtime','docker'],['--signed-work-order','x'],
                      ['--execute'],['--factory-pl','x'],['--api-key','synthetic']):
            with self.subTest(extra=extra),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                build_parser().parse_args(self.args+extra)


if __name__=='__main__':unittest.main()
