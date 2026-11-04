"""Keyless CI clock probe after a real successful gate; original receipt retained."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.contracts import ContractError, WorkOrder
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
        policy=dict(allow_network=False, max_elapsed_seconds=30, max_model_calls=1, max_model_cost_usd=0), metadata={}))
    scripted = ScriptedModelProvider([dict(summary='Public plan', risks=[], tasks=[dict(
        id='clock', objective='Observe terminal deadline', paths=['worker.py'], graph_node_ids=[], evidence_capsule_ids=[])])])
    agents = ModelAgentSet(scripted); clock = [1000.0]; reports = []
    real_run = GateRunner.run
    def run(runner, gates):
        report = real_run(runner, gates)
        reports.append(report)
        if expired: clock[0] += order.max_elapsed_seconds + 1
        return report
    controller = FactoryOrchestrator(source, parent/'runs', agents)
    error = None
    with patch('lightyear_factory.orchestrator.time', SimpleNamespace(monotonic=lambda: clock[0])), patch.object(GateRunner, 'run', run):
        try:
            controller.run(order, 'p5-terminal-deadline')
        except ContractError as exc:
            error = str(exc)
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
    return dict(schema='p5-terminal-deadline-observation/1', expired=expired,
        scope='unsigned scripted controller; only controller clock advanced after real gate return',
        gate_reports=reports, error=error, clock_delta=clock[0]-1000.0, wall_seconds=order.max_elapsed_seconds,
        work_order_sha256=order.content_sha256, artifacts=artifacts,
        source_before_sha256=hashlib.sha256(b'print("public clock fixture")\n').hexdigest(),
        source_after_sha256=hashlib.sha256((source/'worker.py').read_bytes()).hexdigest(),
        scripted_roles=[r['role'] for r in scripted.requests], production_controller_receipt=False,
        receipt_utf8=raw.decode(), receipt_sha256=hashlib.sha256(raw).hexdigest(),
        ledger_utf8=ledger.decode(), ledger_sha256=hashlib.sha256(ledger).hexdigest())
