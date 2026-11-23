"""Unsigned CI controller/gate path using scripted answers and the real OCI runner.

The harness supplies the backend at GateRunner construction. This is not evidence
of deployed admission, Tower authority, signed receipt or production qualification.
"""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from lightyear_execution.backend import OCIContainerBackend
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.contracts import WorkOrder, canonical_hash
from lightyear_factory.gates import GateRunner
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.providers import ScriptedModelProvider


def retain_file(path):
    raw = path.read_bytes()
    if not 0 < len(raw) < 200000:
        raise ValueError('p5-controller-network-evidence-size')
    return dict(utf8=raw.decode('utf-8'), sha256=hashlib.sha256(raw).hexdigest())


def validate(value):
    def require(ok):
        if not ok: raise ValueError('p5-controller-network-evidence-invalid')
    def text(row):
        raw = row['utf8'].encode()
        require(0 < len(raw) < 200000 and hashlib.sha256(raw).hexdigest() == row['sha256'])
        return row['utf8']
    def document(row):
        result = json.loads(text(row))
        require(result['content_sha256'] == canonical_hash(result, {'content_sha256'}))
        return result
    try:
        require(value['schema'] == 'p5-keyless-controller-network/1')
        require(value['scope'] == 'real controller and OCI gate; backend supplied by test harness; admission unmeasured')
        require(value['production_controller_receipt'] is False)
        require(value['real_model_calls'] == 0 and value['signing'] is False)
        receipt = document(value['receipt'])
        require(receipt['status'] == 'blocked' and receipt['attempts'] == 1)
        require(receipt['run_id'] == 'p5-keyless-worker-network')
        require(receipt['work_order_sha256'] == value['work_order_sha256'])
        require(receipt['execution_security']['production_ready'] is False)
        require(receipt['intelligence']['provider'] == 'scripted-test' and receipt['intelligence']['calls'] == 3)
        require(value['scripted_roles'] == ['planner', 'failure_analyst', 'builder'])
        require(value['source_before_sha256'] == value['source_after_sha256'])
        artifacts = value['artifacts']; refs = receipt['artifacts']
        require(len(artifacts) == len(refs))
        verifications = []; call_contents = []
        for reference, retained in zip(refs, artifacts):
            require(reference['path'] == retained['path'])
            envelope = document(retained)
            require(envelope['run_id'] == receipt['run_id'])
            require(envelope['content_sha256'] == reference['content_sha256'])
            require(envelope['artifact_type'] == reference['artifact_type'])
            if envelope['artifact_type'] == 'verification-report': verifications.append(envelope['content'])
            if envelope['artifact_type'] == 'model-call-evidence':
                content = envelope['content']
                require(content['content_sha256'] == canonical_hash(content, {'content_sha256'}))
                call_contents.append(content['content_sha256'])
        require(call_contents == receipt['intelligence']['call_evidence_sha256'])
        require(len(verifications) == 1 and verifications[0]['status'] == 'failed')
        gates = verifications[0]['gates']; require(len(gates) == 1)
        gate = gates[0]
        require(gate['id'] == 'worker-network' and gate['status'] == 'failed')
        require(type(gate['exit_code']) is int and gate['exit_code'] == 42 and gate['timed_out'] is False)
        require(gate['command'] == value['command'])
        execution = gate['execution']
        require(execution['content_sha256'] == canonical_hash(execution, {'content_sha256'}))
        require(execution['enforced'] is True and execution['network_mode'] == 'none')
        require(execution['candidate_build_root'] == '/tmp/factory-build')
        require(execution['workspace_read_only'] is True and execution['host_workspace_writable'] is False)
        require(receipt['verification']['status'] == 'failed')
        require(receipt['verification']['gates'] == [dict(id=gate['id'], status='failed', output_sha256=gate['output_sha256'])])
        events = [json.loads(line) for line in text(value['ledger']).splitlines()]
        previous = None
        for sequence, event in enumerate(events, 1):
            require(event['sequence'] == sequence and event['previous_sha256'] == previous)
            require(event['event_sha256'] == canonical_hash(event, {'event_sha256'}))
            previous = event['event_sha256']
        require(previous == receipt['ledger_head_sha256'] and len(events) == receipt['event_count'])
        require(sum(e['kind'] == 'baseline_verified' for e in events) == 1)
        require(any(e['kind'] == 'builder_blocked' for e in events))
        return True
    except (KeyError, TypeError, ValueError, IndexError):
        raise ValueError('p5-controller-network-evidence-invalid') from None


def observe(parent, policy, command):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('p5-controller-network-ci-only')
    if len(command) != 5 or tuple(command[:2]) != ('python3', '-c'):
        raise ValueError('p5-controller-network-command')
    parent = Path(parent); parent.mkdir()
    source = parent/'source'; source.mkdir()
    original = b'print("public controller network fixture")\n'
    (source/'worker.py').write_bytes(original)
    order = WorkOrder.from_dict(dict(schema_version='1.0', id='p5:keyless-worker-network',
        title='Public scripted controller network refusal', goal='Retain the real failed OCI gate and blocked receipt',
        scope=dict(allowed_paths=['worker.py'], graph_node_ids=[]),
        acceptance=dict(baseline_first=True, max_attempts=1,
            gates=[dict(id='worker-network', command=list(command), timeout_seconds=20, expose_output_to_builder=False)]),
        policy=dict(allow_network=False, max_model_calls=4, max_elapsed_seconds=120, max_model_cost_usd=0),
        metadata={}))
    scripted = ScriptedModelProvider([
        dict(summary='Public synthetic plan', risks=[], tasks=[dict(id='network', objective='Observe the failed gate', paths=['worker.py'], graph_node_ids=[], evidence_capsule_ids=[])]),
        dict(summary='Expected OCI denial', failure_codes=['GATE_FAILED:worker-network'], builder_guidance='Do not change the worker or bypass isolation', risk='high'),
        dict(summary='No repair authorized', edits=[], blocked_reason='Network denial is the intended security boundary')])
    agents = ModelAgentSet(scripted)
    backend = OCIContainerBackend(policy, 'docker', execute=True)
    # Forward into the real GateRunner; do not fabricate its result or controller state.
    def runner(root, **kwargs):
        if kwargs.get('backend') is not None or kwargs.get('allow_network') is not False:
            raise ValueError('p5-controller-network-runner-scope')
        return GateRunner(root, allow_network=False, backend=backend, require_container=True,
                          isolation_scan=kwargs.get('isolation_scan'))
    controller = FactoryOrchestrator(source, parent/'runs', agents)
    with patch('lightyear_factory.orchestrator.GateRunner', runner):
        returned = controller.run(order, 'p5-keyless-worker-network')
    directory = parent/'runs/p5-keyless-worker-network'
    receipt = retain_file(directory/'receipt.json')
    raw_receipt = json.loads(receipt['utf8'])
    if returned != raw_receipt:
        raise ValueError('p5-controller-network-returned-receipt-mismatch')
    artifacts = []
    for reference in raw_receipt['artifacts']:
        relative = Path(reference['path'])
        target = (directory/relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or directory.resolve() not in target.parents:
            raise ValueError('p5-controller-network-artifact-path')
        artifacts.append(dict(path=reference['path'], **retain_file(target)))
    value = dict(schema='p5-keyless-controller-network/1',
        scope='real controller and OCI gate; backend supplied by test harness; admission unmeasured',
        production_controller_receipt=False, real_model_calls=0, signing=False,
        work_order_sha256=order.content_sha256, command=list(command),
        source_before_sha256=hashlib.sha256(original).hexdigest(),
        source_after_sha256=hashlib.sha256((source/'worker.py').read_bytes()).hexdigest(),
        scripted_roles=[item['role'] for item in scripted.requests], receipt=receipt,
        ledger=retain_file(directory/'events.jsonl'), artifacts=artifacts)
    # Caller validates and reports an unmet expectation with these original bytes retained.
    # A product defect must not erase the receipt or be relabelled as a successful drill.
    return value
