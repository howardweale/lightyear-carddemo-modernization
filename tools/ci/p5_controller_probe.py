"""CI-only abrupt controller termination probe; never an acceptance authority."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from lightyear_execution.admission import AdmissionNonceStore
from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.ledger import RunLedger
from lightyear_factory.providers import ProviderResult
from tools.ci.p5_fixture import Fixture

READY = b'P5-CONTROLLER-BUILDER-READY'
RUN_ID = 'p5-abrupt-controller'


class ControllerStub:
    provider_id = 'p5-stub'
    model = 'p5-stub-2026-10-23'
    manage_failure_budget = True

    def __init__(self, pause):
        self.pause = pause
        self.calls = 0

    def complete(self, role, instruction, payload, schema):
        self.calls += 1
        if role == 'planner':
            value = dict(summary='Synthetic controller plan', risks=[], tasks=[dict(
                id='synthetic', objective='Observe the controller', paths=['worker.py'],
                graph_node_ids=[], evidence_capsule_ids=[])])
        elif role == 'builder':
            print(READY.decode(), flush=True)
            if self.pause:
                time.sleep(120)
            value = dict(summary='Synthetic no-edit control', edits=[], blocked_reason='Synthetic stop')
        else:
            raise ValueError('p5-unexpected-role')
        return ProviderResult(value, dict(input_tokens=1, output_tokens=1,
            estimated_cost_usd=0.0, cost_estimate_available=True, provider=self.provider_id,
            model=self.model, role=role))


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def child(repository, parent, runs, mode):
    parent.mkdir()
    fixture = Fixture(parent, repository, controller_probe=True)
    try:
        stub = ControllerStub(mode == 'wait')
        store = AdmissionNonceStore(runs/'admission-nonces.sha256')
        if mode == 'reenter':
            before_nonce = store.path.read_bytes()
            try:
                fixture.verify_order(store=store)
            except Exception as error:
                if 'already been consumed' not in str(error):
                    raise ValueError('p5-duplicate-nonce-wrong-refusal') from None
            else:
                raise ValueError('p5-duplicate-nonce-admitted')
            if store.path.read_bytes() != before_nonce:
                raise ValueError('p5-duplicate-nonce-mutated')
            # Existing stronger run-directory control is retained as well.
            _, admission = fixture.verify_order()
        else:
            _, admission = fixture.verify_order(store=store)
        context = HardenedExecutionContext(fixture.policy,
            OCIContainerBackend(fixture.policy, 'docker', execute=False), admission, fixture.key)
        controller = FactoryOrchestrator(fixture.root, runs, ModelAgentSet(stub),
            execution_context=context, model_admission=fixture.admission,
            factory_input_paths=fixture.input_paths,
            workspace_read_manifest=fixture.runtime()['workspace_read_manifest'],
            private_expected_values_path=fixture.private_values_path)
        if mode == 'reenter':
            before = snapshot(runs/RUN_ID)
            try:
                controller.run(fixture.order, RUN_ID)
            except ContractError as error:
                if str(error) != 'factory-isolation-run-refused':
                    raise ValueError('p5-reentry-wrong-refusal') from None
            else:
                raise ValueError('p5-reentry-admitted')
            if snapshot(runs/RUN_ID) != before or stub.calls:
                raise ValueError('p5-reentry-mutated-attempt')
        else:
            receipt = controller.run(fixture.order, RUN_ID)
            if receipt['status'] != 'blocked' or stub.calls != 2:
                raise ValueError('p5-positive-controller-result')
        print('P5-CONTROLLER-PROBE-COMPLETE', flush=True)
    finally:
        fixture.close()


def inspect_receipt(path):
    raw = path.read_bytes()
    value = json.loads(raw)
    if (value.get('status') != 'blocked'
            or value.get('qualifies_for_factory_receipt') is True
            or value.get('factory_build_receipt', {}).get('qualifies_for_factory_receipt') is True
            or value.get('content_sha256') != canonical_hash(value, {'content_sha256'})):
        raise ValueError('p5-controller-receipt-invalid')
    return dict(sha256=hashlib.sha256(raw).hexdigest(), content_sha256=value['content_sha256'],
                status=value['status'], qualification_field=value.get('qualifies_for_factory_receipt'),
                factory_build_receipt_present='factory_build_receipt' in value)


def observe(fixture, repository):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('p5-ci-only')
    base = fixture.parent/'controller-probe'
    base.mkdir()
    command = [sys.executable, '-B', '-m', 'tools.ci.p5_controller_probe',
               '--repository', str(repository)]
    env = dict(os.environ, PYTHONUNBUFFERED='1')
    positive = subprocess.run(command+['--parent', str(base/'positive'),
        '--runs', str(base/'positive-runs'), '--mode', 'complete'], cwd=repository,
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
    if positive.returncode != 0 or READY not in positive.stdout:
        raise ValueError('p5-positive-controller-unreached')
    positive_receipt = inspect_receipt(base/'positive-runs'/RUN_ID/'receipt.json')
    runs = base/'killed-runs'
    process = subprocess.Popen(command+['--parent', str(base/'killed'),
        '--runs', str(runs), '--mode', 'wait'], cwd=repository, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        try:
            process.communicate(timeout=30)
            raise ValueError('p5-controller-ended-before-kill')
        except subprocess.TimeoutExpired as error:
            reached = READY in (error.output or b'')
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
        if not reached or process.returncode == 0:
            # Counts, marker-presence booleans and hashes only; never raw output.
            diagnostic = dict(timeout_marker_seen=reached, final_marker_seen=READY in stdout,
                killed_exit=process.returncode, stdout_bytes=len(stdout), stderr_bytes=len(stderr),
                stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                stderr_sha256=hashlib.sha256(stderr).hexdigest())
            raise ValueError('p5-controller-builder-not-killed:' + json.dumps(diagnostic, sort_keys=True))
        run_dir = runs/RUN_ID
        before = snapshot(run_dir)
        identity = json.loads((run_dir/'attempt-identity.json').read_bytes())
        if identity['attempt_id'] != RUN_ID:
            raise ValueError('p5-attempt-identity-mismatch')
        nonce_before = (runs/'admission-nonces.sha256').read_bytes()
        ledger_before = (run_dir/'events.jsonl').read_bytes()
        from lightyear_factory.cli import main as abort_cli
        arguments = ['reconcile-interrupted', '--runs-root', str(runs), '--run-id', RUN_ID]
        for key in ('work_order_sha256','consumed_nonce_sha256','sealed_workspace_sha256'):
            arguments.extend(['--'+key.replace('_','-'), identity[key]])
        import contextlib
        import io
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = abort_cli(arguments)
        if code != 0:
            raise ValueError('p5-abort-cli-refused')
        event = json.loads(output.getvalue())
        payload = event['payload']
        ledger = RunLedger(run_dir/'events.jsonl')
        if (ledger.events[-1] != event or event['state'] != 'INTERRUPTED'
                or payload['status'] != 'interrupted; awaiting human attestation'
                or payload['unsigned'] is not True or payload['human_attestation'] is not None
                or any(payload[key] != identity[key] for key in
                       ('attempt_id','work_order_sha256','consumed_nonce_sha256','sealed_workspace_sha256'))
                or not (run_dir/'events.jsonl').read_bytes().startswith(ledger_before)):
            raise ValueError('p5-abort-record-binding')
        accounting = payload['accounting']
        if (accounting['calls'] != 1 or accounting['input_tokens'] != 1
                or accounting['output_tokens'] != 1 or accounting['estimated_cost_usd'] != 0
                or accounting['in_flight_final_usage'] != 'unknown'
                or not any(row['role']=='builder' and row['response_sha256'] is None
                           for row in accounting['scanned_transports'])):
            raise ValueError('p5-abort-accounting-mismatch')
        after = snapshot(run_dir)
        if set(after) != set(before) or any(after[k] != v for k,v in before.items() if k != 'events.jsonl'):
            raise ValueError('p5-abort-changed-other-evidence')
        with contextlib.redirect_stdout(io.StringIO()):
            if abort_cli(arguments) != 1:
                raise ValueError('p5-terminal-abort-not-refused')
        if snapshot(run_dir) != after or (runs/'admission-nonces.sha256').read_bytes() != nonce_before:
            raise ValueError('p5-abort-duplicate-mutated')
        before = after
        # Fresh disposable admission is a deliberately stronger re-entry probe:
        # even another otherwise valid invocation must not overwrite this attempt.
        again = subprocess.run(command+['--parent', str(base/'reenter'),
            '--runs', str(runs), '--mode', 'reenter'], cwd=repository, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
        preserved = before == snapshot(run_dir)
        receipt_exists = (run_dir/'receipt.json').exists()
        result = dict(controller_builder_reached=True, killed_exit=process.returncode,
            positive_controller_receipt=positive_receipt,
            post_kill_receipt_exists=receipt_exists, reentry_refused=again.returncode == 0,
            attempt_files_preserved=preserved, retained_file_count=len(before),
            retained_inventory_sha256=canonical_hash(before),
            stdout_sha256=hashlib.sha256(stdout).hexdigest(), stderr_sha256=hashlib.sha256(stderr).hexdigest(),
            real_model_calls=0, actual_spend=0,
            recovery_scope='Abort-only unsigned ledger record; consumed nonce and sealed workspace bound; no resume/retry/readmission.',
            interrupted_record=event, interrupted_record_sha256=canonical_hash(event),
            consumed_nonce_unchanged=(runs/'admission-nonces.sha256').read_bytes()==nonce_before,
            terminal_abort_refused=True, human_attestation_verified=False)
        if receipt_exists:
            result['post_kill_receipt'] = inspect_receipt(run_dir/'receipt.json')
        gaps = ['Existing human Tower path has not attested the interrupted record; no gap acceptance is inferred.',
                'Kill during in-flight transport leaves final billable usage unknown; observed accounting is not final billing.']
        return result, again.returncode == 0 and preserved, gaps
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def main():
    try:
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            raise ValueError('p5-ci-only')
        parser = argparse.ArgumentParser()
        parser.add_argument('--repository', type=Path, required=True)
        parser.add_argument('--parent', type=Path, required=True)
        parser.add_argument('--runs', type=Path, required=True)
        parser.add_argument('--mode', choices=('complete', 'wait', 'reenter'), required=True)
        args = parser.parse_args()
        child(args.repository.resolve(), args.parent.resolve(), args.runs.resolve(), args.mode)
        return 0
    except Exception:
        print('P5 controller probe refused; inspect counts only', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
