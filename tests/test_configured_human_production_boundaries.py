"""CI-only negative production boundaries; no proof-verifier mocking."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_human_runtime import verify_configured_human_runtime
from lightyear_execution.configured_human_scopes import (
    reserve_configured_human_plan,verify_configured_human_role)


class ConfiguredHumanProductionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_fabricated_passed_review_cannot_reach_reservation_api(self):
        fake={'status':'verified-plan-only','execution_authorized':False,
              'nonce_consumed':False,'verified_model_admission':{'passed':True}}
        with patch('lightyear_execution.tower_drill_reservation._GitHubAPI.request',
                   side_effect=AssertionError('API must not be reached')) as api:
            with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
                reserve_configured_human_plan(fake,object(),object())
            api.assert_not_called()

    def test_provider_role_name_alone_cannot_authorize_a_secret_lease(self):
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            verify_configured_human_role({'status':'passed'},object(),object(),
                                        'provider','secret:lease:OPENAI_API_KEY')

    def test_runtime_paths_are_unread_until_genuine_proof_type_boundary(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('no path reads')) as read:
            with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
                verify_configured_human_runtime(object(),object(),object(),source_root='.',
                    input_paths={'scope':'untrusted.json'},read_manifest={})
            read.assert_not_called()

    def test_resume_receipt_and_environment_claims_cannot_bypass_real_proof(self):
        claims={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'howardweale/lightyear-carddemo-modernization',
                'GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_ID':'123','GITHUB_JOB':'configured-build-control'}
        with patch.dict(os.environ,claims):
            for value in ({'status':'consumed-only'},{'status':'passed','resume':True}):
                with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
                    reserve_configured_human_plan(value,object(),object())

    def test_production_reservation_has_no_api_or_review_injection_argument(self):
        with self.assertRaises(TypeError):
            reserve_configured_human_plan(object(),object(),object(),api=object())
        with self.assertRaises(TypeError):
            reserve_configured_human_plan(object(),object(),object(),review={'passed':True})

    def test_role_scope_has_no_caller_clock_or_credential_argument(self):
        with self.assertRaises(TypeError):
            verify_configured_human_role(object(),object(),object(),'builder','factory:build',now='old')
        with self.assertRaises(TypeError):
            verify_configured_human_role(object(),object(),object(),'provider','secret:lease:OPENAI_API_KEY',token='untrusted')

    def test_plan_review_cannot_accept_a_caller_frozen_clock(self):
        from lightyear_execution.configured_human_admission import verify_configured_human_plan
        with self.assertRaises(TypeError):
            verify_configured_human_plan(object(),object(),object(),now='previously-valid-window')

    def test_runtime_boundary_cannot_accept_cached_review_or_clock(self):
        with self.assertRaises(TypeError):
            verify_configured_human_runtime(object(),object(),object(),source_root='.',
                input_paths={},read_manifest={},review={'status':'passed'})
        with self.assertRaises(TypeError):
            verify_configured_human_runtime(object(),object(),object(),source_root='.',
                input_paths={},read_manifest={},now='previously-valid-window')
