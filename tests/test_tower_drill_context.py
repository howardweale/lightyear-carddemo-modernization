"""CI-only refusal and workflow-source tests; no proof/signature is fabricated."""
import copy
import os
from pathlib import Path
import pickle
import unittest
from unittest.mock import patch

from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.tower_drill_context import (
    HumanDrillExecutionContext, _workflow_source, admit_human_drill_context)


class HumanDrillContextTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.location='howardweale/lightyear-carddemo-modernization/.github/workflows/drills.yml'
        self.review=dict(drill_binding=dict(ci=dict(workflow_ref=self.location+'@'+'a'*40)))
        self.environment=dict(GITHUB_WORKFLOW_REF=self.location+'@refs/pull/455/merge',
                              GITHUB_WORKFLOW_SHA='b'*40)

    def test_supplied_receipt_dictionary_cannot_construct_or_consume_context(self):
        with self.assertRaisesRegex(ExecutionContractError,'no-receipt-constructor'):
            HumanDrillExecutionContext(dict(status='passed'))
        with patch('lightyear_execution.tower_drill_context.reserve_human_drill_plan') as consume:
            with self.assertRaisesRegex(ExecutionContractError,'native-public-context-required'):
                admit_human_drill_context(dict(status='passed'),None,None,None,
                    source_root=Path('.'),input_paths={},read_manifest={},evidence_path=Path('unused'))
            consume.assert_not_called()

    def test_unregistered_copied_or_serialized_object_cannot_be_used(self):
        context=object.__new__(HumanDrillExecutionContext)
        context.admission_receipt=dict(status='passed')
        for invoke in (lambda:context.bind('a'*64,'2026-10-27T00:00:00Z'),
                       lambda:context.authorize('planner','factory:plan','2026-10-27T00:00:00Z'),
                       context.summary):
            with self.subTest(invoke=invoke),self.assertRaises(ExecutionContractError):invoke()
        for invoke in (lambda:copy.copy(context),lambda:copy.deepcopy(context),lambda:pickle.dumps(context)):
            with self.subTest(invoke=invoke),self.assertRaises(ExecutionContractError):invoke()
        with self.assertRaisesRegex(ExecutionContractError,'secrets-forbidden'):
            context.lease_secret('planner','anything','now')

    def test_workflow_source_binds_two_git_blobs_without_granting_execution(self):
        with patch('lightyear_execution.tower_drill_context.subprocess.check_output',
                   return_value=b'public synthetic workflow\n') as git:
            result=_workflow_source(Path('.'),self.review,self.environment)
        self.assertEqual(git.call_count,2)
        refs=[call.args[0][-1] for call in git.call_args_list]
        self.assertEqual(refs,['a'*40+':.github/workflows/drills.yml','b'*40+':.github/workflows/drills.yml'])
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['signed_executable'],'a'*40)
        self.assertEqual(result['workflow_sha'],'b'*40)

    def test_wrong_workflow_environment_refuses_before_git(self):
        cases=[{},dict(self.environment,GITHUB_WORKFLOW_SHA='refs/heads/main'),
               dict(self.environment,GITHUB_WORKFLOW_REF='another/repository/.github/workflows/drills.yml@main')]
        with patch('lightyear_execution.tower_drill_context.subprocess.check_output') as git:
            for environment in cases:
                with self.subTest(environment=environment),self.assertRaises(ExecutionContractError):
                    _workflow_source(Path('.'),self.review,environment)
            git.assert_not_called()

    def test_changed_empty_or_oversized_workflow_source_fails_closed(self):
        for first,second in ((b'a',b'b'),(b'',b''),(b'x'*262145,b'x'*262145)):
            with self.subTest(size=len(first)),patch(
                    'lightyear_execution.tower_drill_context.subprocess.check_output',side_effect=[first,second]):
                with self.assertRaisesRegex(ExecutionContractError,'workflow-source-changed'):
                    _workflow_source(Path('.'),self.review,self.environment)


if __name__=='__main__':unittest.main()
