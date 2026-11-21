"""Inactive answer-fragment fixed public input scope; no IO or authority."""
import re
from lightyear_factory.contracts import WorkOrder
from .contracts import ExecutionContractError

DOCUMENTS = 'docs/factory/p5-human-clean-control/answer-fragment/'
PUBLIC_ISOLATION = DOCUMENTS + 'public-isolation.json'
WORKER = 'tests/fixtures/p5_public/human-public-build-control/worker.py'
WORKER_SHA256 = 'db4d559f1badcf6a6473d6ade51fd463f91b814f67d1a7b3bc20f31076d3d47a'


def validate_answer_input_bindings(plan):
    expected = {'scope': 'scope.json', 'freeze': 'freeze.json',
                'workspace': 'workspace.json', 'execution_policy': 'receipt-execution-policy.json'}
    bound = plan.get('bound_inputs') if type(plan) is dict else None
    if type(bound) is not dict or set(bound) != set(expected):
        raise ExecutionContractError('configured-answer-exact-input-bindings')
    for name, suffix in expected.items():
        row = bound[name]
        if (type(row) is not dict or set(row) != {'path', 'sha256'}
                or row['path'] != DOCUMENTS + suffix
                or type(row['sha256']) is not str
                or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
            raise ExecutionContractError('configured-answer-exact-input-bindings')


def validate_answer_workspace_scope(order, manifest):
    # These are pre-stimulus source constraints. They neither create a copied
    # workspace nor establish a native assembler invocation or no-send result.
    if (type(order) is not WorkOrder or order.order_id != 'answer-fragment'
            or order.allowed_paths != (WORKER,) or order.graph_node_ids != ()
            or order.metadata != {'context_schema': '1.0', 'graph': 'packed'}
            or type(order.max_file_bytes) is not int or order.max_file_bytes != 20000
            or type(order.max_context_bytes) is not int or order.max_context_bytes != 20000
            or order.allow_network is not False
            or type(manifest) is not dict or manifest != {WORKER: WORKER_SHA256}):
        raise ExecutionContractError('configured-answer-original-workspace-scope')
