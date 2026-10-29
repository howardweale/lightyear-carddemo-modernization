"""Keyless CI real-clock terminal wait; no clock substitution or admission claim."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.contracts import ContractError, WorkOrder, canonical_hash
from lightyear_factory.gates import GateRunner
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.providers import ScriptedModelProvider


def observe(parent, expired):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or type(expired) is not bool:
        raise ValueError('p5-terminal-deadline-ci-only')
    parent = Path(parent); parent.mkdir()
    source = parent/'source'; source.mkdir()
    (source/'worker.py').write_bytes(b'print("public clock fixture")\n')
    order = WorkOrder.from_dict(dict(schema_version='1.0', id='p5:terminal-deadline',
        title='Terminal deadline check', goal='Do not publish success after the wall deadline',
        scope=dict(allowed_paths=['worker.py'], graph_node_ids=[]),
        acceptance=dict(baseline_first=True, max_attempts=1,
            gates=[dict(id='public-clean-control', command=[sys.executable, '-c', 'pass'], timeout_seconds=5, expose_output_to_builder=False)]),
        policy=dict(allow_network=False, max_elapsed_seconds=2 if expired else 30, max_model_calls=1, max_model_cost_usd=0), metadata={}))
    scripted = ScriptedModelProvider([dict(summary='Public plan', risks=[], tasks=[dict(
        id='clock', objective='Observe terminal deadline', paths=['worker.py'], graph_node_ids=[], evidence_capsule_ids=[])])])
    agents = ModelAgentSet(scripted); reports = []; intervals = []
    real_run = GateRunner.run
    def run(runner, gates):
        report = real_run(runner, gates)
        reports.append(report)
        gate_returned = time.monotonic()
        if expired:
            # Wait for the actual controller deadline. No clock reference changes.
            target = controller._receipt_started + order.max_elapsed_seconds + 0.05
            while time.monotonic() < target:
                time.sleep(min(0.05, max(0, target-time.monotonic())))
        intervals.append(dict(gate_returned=gate_returned, released=time.monotonic()))
        return report
    controller = FactoryOrchestrator(source, parent/'runs', agents)
    error = None
    with patch.object(GateRunner, 'run', run):
        try:
            controller.run(order, 'p5-terminal-deadline')
        except ContractError as exc:
            error = str(exc)
    finished = time.monotonic()
    directory = parent/'runs/p5-terminal-deadline'
    raw = (directory/'receipt.json').read_bytes()
    ledger = (directory/'events.jsonl').read_bytes()
    artifacts = []
    for reference in json.loads(raw)['artifacts']:
        relative = Path(reference['path']); target = (directory/relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or directory.resolve() not in target.parents:
            raise ValueError('p5-deadline-artifact-path')
        content = target.read_bytes()
        artifacts.append(dict(path=reference['path'], utf8=content.decode('utf-8'),
                              sha256=hashlib.sha256(content).hexdigest()))
    return dict(schema='p5-real-clock-deadline-observation/1', expired=expired,
        scope='unsigned scripted controller; real monotonic wait after actual gate return; no clock substitution',
        gate_reports=reports, error=error, elapsed_seconds=finished-controller._receipt_started,
        monotonic_started=controller._receipt_started, monotonic_finished=finished, intervals=intervals,
        clock_substituted=False, wall_seconds=order.max_elapsed_seconds,
        work_order_sha256=order.content_sha256, artifacts=artifacts,
        source_before_sha256=hashlib.sha256(b'print("public clock fixture")\n').hexdigest(),
        source_after_sha256=hashlib.sha256((source/'worker.py').read_bytes()).hexdigest(),
        scripted_roles=[r['role'] for r in scripted.requests], production_controller_receipt=False,
        receipt_utf8=raw.decode(), receipt_sha256=hashlib.sha256(raw).hexdigest(),
        ledger_utf8=ledger.decode(), ledger_sha256=hashlib.sha256(ledger).hexdigest())


def validate(value):
    """Original receipt and ledger must bind the clock experiment and expected outcome."""
    try:
        import math
        if (value['schema'] != 'p5-real-clock-deadline-observation/1'
                or value['clock_substituted'] is not False
                or type(value['wall_seconds']) is not int
                or value['wall_seconds'] != (2 if value['expired'] else 30)
                or len(value['intervals']) != 1):
            return False
        interval = value['intervals'][0]
        times = [value['monotonic_started'], interval['gate_returned'],
                 interval['released'], value['monotonic_finished'], value['elapsed_seconds']]
        if (any(type(t) not in (int,float) or not math.isfinite(t) for t in times)
                or not times[0] <= times[1] <= times[2] <= times[3]
                or value['elapsed_seconds'] != times[3]-times[0]
                or times[1] >= times[0]+value['wall_seconds']
                or (value['expired'] and times[2] < times[0]+value['wall_seconds'])):
            return False
        if type(value['expired']) is not bool:
            return False
        receipt_raw = value['receipt_utf8'].encode()
        ledger_raw = value['ledger_utf8'].encode()
        if hashlib.sha256(receipt_raw).hexdigest() != value['receipt_sha256']:
            return False
        if hashlib.sha256(ledger_raw).hexdigest() != value['ledger_sha256']:
            return False
        receipt = json.loads(receipt_raw)
        if receipt['content_sha256'] != canonical_hash(receipt, {'content_sha256'}):
            return False
        if receipt['run_id'] != 'p5-terminal-deadline' or value['production_controller_receipt'] is not False:
            return False
        if receipt['execution_security']['production_ready'] is not False:
            return False
        if receipt['work_order_sha256'] != value['work_order_sha256']:
            return False
        if value['source_before_sha256'] != value['source_after_sha256']:
            return False
        refs = receipt['artifacts']; retained = value['artifacts']; reports = []
        if len(refs) != len(retained):
            return False
        for ref, artifact in zip(refs, retained):
            raw = artifact['utf8'].encode('utf-8')
            if ref['path'] != artifact['path'] or hashlib.sha256(raw).hexdigest() != artifact['sha256']:
                return False
            envelope = json.loads(raw)
            if envelope['content_sha256'] != canonical_hash(envelope, {'content_sha256'}):
                return False
            if envelope['content_sha256'] != ref['content_sha256'] or envelope['artifact_type'] != ref['artifact_type']:
                return False
            if envelope['run_id'] != receipt['run_id']:
                return False
            if envelope['artifact_type'] == 'verification-report':
                reports.append(envelope['content'])
        if reports != value['gate_reports']:
            return False
        events = [json.loads(line) for line in ledger_raw.splitlines()]
        previous = None
        for sequence, event in enumerate(events, 1):
            if event['sequence'] != sequence or event['previous_sha256'] != previous:
                return False
            if event['event_sha256'] != canonical_hash(event, {'event_sha256'}):
                return False
            previous = event['event_sha256']
        if previous != receipt['ledger_head_sha256'] or len(events) != receipt['event_count']:
            return False
        if value['scripted_roles'] != ['planner'] or len(value['gate_reports']) != 1:
            return False
        if value['gate_reports'][0]['status'] != 'passed' or len(value['gate_reports'][0]['gates']) != 1:
            return False
        gate = value['gate_reports'][0]['gates'][0]
        if (gate['id'] != 'public-clean-control' or gate['status'] != 'passed'
                or type(gate['exit_code']) is not int or gate['exit_code'] != 0
                or gate['timed_out'] is not False):
            return False
        if value['expired']:
            return (value['elapsed_seconds'] > value['wall_seconds'] and receipt['status'] == 'blocked'
                    and value['error'] == 'Factory exceeded max_elapsed_seconds')
        return 0 <= value['elapsed_seconds'] < value['wall_seconds'] and receipt['status'] == 'passed' and value['error'] is None
    except (KeyError, ValueError, TypeError, IndexError):
        return False
