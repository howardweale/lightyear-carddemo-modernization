"""CI-only untrusted input relationships; no proof, copied worker or context."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
from lightyear_factory.contracts import WorkOrder, ContractError, canonical_hash
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_receipt_answer_inputs import (
    DOCUMENTS, PUBLIC_ISOLATION, WORKER, WORKER_SHA256,
    validate_answer_input_bindings, validate_answer_workspace_scope)
from lightyear_execution.configured_receipt_answer_runtime import verify_answer_receipt_runtime
from lightyear_execution.configured_receipt_answer_isolation import (
    validate_answer_isolation_document, review_answer_receipt_isolation)
from lightyear_execution.configured_receipt_isolation import validate_configured_isolation_document


class AnswerInputTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        root = Path(__file__).resolve().parents[1]
        self.document = json.loads((root / 'docs/factory/p5-human-clean-control/configured-build-control/work-order.json').read_bytes())
        self.document['id'] = 'answer-fragment'
        self.order = WorkOrder.from_dict(self.document)
        self.manifest = {WORKER: WORKER_SHA256}
        self.plan = {'bound_inputs': {k: {'path': DOCUMENTS + n, 'sha256': 'a' * 64}
            for k, n in (('scope', 'scope.json'), ('freeze', 'freeze.json'),
                         ('workspace', 'workspace.json'), ('execution_policy', 'receipt-execution-policy.json'))}}
        self.isolation = dict(schema='factory-public-drill-isolation/1', case_id='answer-fragment',
            work_order_sha256=self.order.content_sha256,
            values=['public synthetic answer isolation fixture ' + str(n) * 40 for n in range(3)])
        self.isolation['content_sha256'] = canonical_hash(self.isolation)

    def test_fixed_relationships_do_not_change_inputs_or_return_authority(self):
        plan = deepcopy(self.plan)
        manifest = deepcopy(self.manifest)
        self.assertIsNone(validate_answer_input_bindings(self.plan))
        self.assertIsNone(validate_answer_workspace_scope(self.order, self.manifest))
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.manifest, manifest)
        self.assertEqual(self.order.to_dict(), self.document)
        self.assertEqual(PUBLIC_ISOLATION, DOCUMENTS + 'public-isolation.json')

    def test_control_alias_extra_missing_and_unbound_input_paths_refuse(self):
        for replacement in (
                DOCUMENTS.replace('answer-fragment', 'configured-build-control') + 'scope.json',
                DOCUMENTS + '../answer-fragment/scope.json', DOCUMENTS + 'other.json'):
            plan = deepcopy(self.plan)
            plan['bound_inputs']['scope']['path'] = replacement
            with self.assertRaisesRegex(ExecutionContractError, 'exact-input-bindings'):
                validate_answer_input_bindings(plan)
        for mutate in (lambda v: v['bound_inputs'].pop('workspace'),
                       lambda v: v['bound_inputs'].update(extra={}),
                       lambda v: v['bound_inputs']['scope'].update(extra=True),
                       lambda v: v['bound_inputs']['scope'].update(sha256=True),
                       lambda v: v['bound_inputs']['scope'].update(sha256='a' * 63)):
            plan = deepcopy(self.plan)
            mutate(plan)
            with self.assertRaisesRegex(ExecutionContractError, 'exact-input-bindings'):
                validate_answer_input_bindings(plan)

    def test_other_case_mode_schema_graph_or_budget_refuses(self):
        for order in (
                replace(self.order, order_id='configured-build-control'),
                replace(self.order, metadata={'context_schema': '1.1', 'graph': 'packed'}),
                replace(self.order, metadata={'context_schema': '1.0', 'graph': 'plain-search'}),
                replace(self.order, metadata=dict(self.order.metadata, extra=True)),
                replace(self.order, graph_node_ids=('public-node',)),
                replace(self.order, max_file_bytes=1000),
                replace(self.order, max_context_bytes=1000),
                replace(self.order, allow_network=True)):
            with self.assertRaisesRegex(ExecutionContractError, 'original-workspace-scope'):
                validate_answer_workspace_scope(order, self.manifest)

    def test_changed_worker_manifest_or_allowed_paths_refuse(self):
        for manifest in ({}, {WORKER: 'b' * 64}, dict(self.manifest, extra='a' * 64),
                         {WORKER.replace('worker.py', 'different.py'): WORKER_SHA256}):
            with self.assertRaisesRegex(ExecutionContractError, 'original-workspace-scope'):
                validate_answer_workspace_scope(self.order, manifest)
        with self.assertRaisesRegex(ExecutionContractError, 'original-workspace-scope'):
            validate_answer_workspace_scope(replace(self.order, allowed_paths=(WORKER, 'other.py')), self.manifest)

    def test_exact_public_values_return_only_tuple_and_preserve_document(self):
        before = deepcopy(self.isolation)
        values = validate_answer_isolation_document(self.isolation, self.order.content_sha256)
        self.assertEqual(values, tuple(before['values']))
        self.assertIs(type(values), tuple)
        self.assertEqual(self.isolation, before)
        with self.assertRaises(ContractError):
            validate_configured_isolation_document(self.isolation, self.order.content_sha256)

    def test_rehashed_wrong_case_or_order_and_wrong_digest_refuse(self):
        for key, value in (('case_id', 'configured-build-control'), ('work_order_sha256', 'b' * 64)):
            changed = deepcopy(self.isolation)
            changed[key] = value
            changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
            with self.assertRaises(ContractError):
                validate_answer_isolation_document(changed, self.order.content_sha256)
        changed = dict(self.isolation, content_sha256='0' * 64)
        with self.assertRaises(ContractError):
            validate_answer_isolation_document(changed, self.order.content_sha256)

    def test_missing_duplicate_short_or_authority_values_refuse(self):
        for values in (self.isolation['values'][:2], [self.isolation['values'][0]] * 3,
                       ['short', 'also short', 'still short'], ['x' * 50, 'y' * 50, True]):
            changed = dict(self.isolation, values=values)
            changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
            with self.assertRaises(ContractError):
                validate_answer_isolation_document(changed, self.order.content_sha256)
        changed = dict(self.isolation, execution_authorized=True)
        changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
        with self.assertRaises(ContractError):
            validate_answer_isolation_document(changed, self.order.content_sha256)

    def test_passed_mapping_refuses_before_unusable_caller_paths(self):
        with self.assertRaisesRegex(ExecutionContractError, 'real-verifier'):
            verify_answer_receipt_runtime({'status': 'passed'}, self.order, object(),
                source_root=object(), input_paths=object(), read_manifest=object())
        with self.assertRaisesRegex(ExecutionContractError, 'real-verifier'):
            review_answer_receipt_isolation({'status': 'passed'}, self.order, object(), object(), object())
