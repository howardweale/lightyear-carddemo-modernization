"""CI-only refusal/parser coverage; no fabricated passed proof or execution."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_human_dispatch import (
    dispatch_configured_human,review_configured_human_dispatch,_independent_source)


class ConfiguredDispatchBoundaryTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_local_dispatch_stops_before_trust_or_nonce(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}),patch(
                'lightyear_factory.model_admission.FactoryModelAdmission.from_external_trust') as trust:
            with self.assertRaisesRegex(ContractError,'ci-only'):
                dispatch_configured_human(SimpleNamespace())
            trust.assert_not_called()

    def test_review_also_refuses_non_ci_before_reading_inputs(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            with self.assertRaisesRegex(ContractError,'ci-only'):
                review_configured_human_dispatch(SimpleNamespace())

    def test_relative_source_is_refused(self):
        with self.assertRaisesRegex(ContractError,'independent-source'):
            _independent_source(Path('relative-source'))

    def test_parser_requires_explicit_runtime_and_trust(self):
        from lightyear_factory.cli import build_parser
        for command in ('human-configured-proof-review','human-configured-execute'):
            with self.subTest(command=command),self.assertRaises(SystemExit):
                build_parser().parse_args([command])

    def test_parser_rejects_stub_output_and_resume_options(self):
        from lightyear_factory.cli import build_parser
        args=['human-configured-proof-review','--source-root','unused','--work-order','unused',
            '--execution-policy','unused','--factory-plan','unused','--factory-approval','unused',
            '--factory-contract','unused','--factory-trust','unused','--model-config','unused',
            '--public-isolation-plan','unused','--execution-runtime','docker']
        for extra in (['--public-output-plan','unused'],['--resume'],['--model-conf','unused']):
            with self.subTest(extra=extra),self.assertRaises(SystemExit):
                build_parser().parse_args(args+extra)

    def test_parser_keeps_review_separate_from_execution_root(self):
        from lightyear_factory.cli import build_parser
        parser=build_parser()
        args=['human-configured-proof-review','--source-root','unused','--work-order','unused',
            '--execution-policy','unused','--factory-plan','unused','--factory-approval','unused',
            '--factory-contract','unused','--factory-trust','unused','--model-config','unused',
            '--public-isolation-plan','unused','--execution-runtime','docker']
        parsed=parser.parse_args(args)
        self.assertFalse(hasattr(parsed,'runs_root'))
        with self.assertRaises(SystemExit):parser.parse_args(args+['--runs-root','unused'])
