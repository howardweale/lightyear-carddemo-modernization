"""CI-only failure observations. A component pass is not a factory go decision."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import http.server
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from unittest.mock import patch

from lightyear_control_tower.decisions import canonical, verify_envelope
from lightyear_execution.admission import AdmissionNonceStore
from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.contracts import ExecutionContractError
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError
from lightyear_factory.isolation_scan import scan
from lightyear_factory.providers import ProviderResult
from tools.ci.p5_fixture import Fixture

DRILLS = ('kill-mid-build', 'worker-network', 'budget-exhausted', 'tower-unreachable',
          'workspace-changed', 'answer-fragment', 'wall-and-window', 'duplicate-attempt')
EXPECTED = dict(zip(DRILLS, (
    'Real controller killed at builder transport; existing attempt preserved on refused re-entry.',
    'Reachable positive control; actual isolated worker connection denied.',
    'Two admitted calls accounted; third call refused before stub transport.',
    'Unavailable trust and append both refused; journal count unchanged after outage.',
    'Changed sealed bytes refused before any stub call.',
    'Clean control passes; normalized answer fragment refused before any stub call.',
    'At and beyond wall cap refused; before window end admitted and at end refused.',
    'Sequential replay refused; exactly one of eight concurrent admissions succeeds.')))
SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'],
          'additionalProperties': False}


class Stub:
    provider_id = 'p5-stub'
    model = 'p5-stub-2026-10-23'
    manage_failure_budget = True

    def __init__(self):
        self.calls = 0

    def complete(self, role, instruction, payload, schema):
        self.calls += 1
        return ProviderResult({'ok': True}, dict(input_tokens=1, output_tokens=1,
            estimated_cost_usd=0.0, cost_estimate_available=True, provider=self.provider_id,
            model=self.model, role=role))


def wrapped(fixture):
    stub = Stub()
    return stub, AccountedModelProvider(stub, fixture.order, model_admission=fixture.admission,
                                        runtime_admission=fixture.runtime)


def call(provider):
    return provider.complete('builder', 'Synthetic drill', {}, SCHEMA)


def refused(action, expected=ContractError):
    try:
        action()
    except expected:
        return True
    return False


def kill_mid_build(f):
    from tools.ci.p5_controller_probe import observe
    return observe(f, Path(__file__).resolve().parents[2])


def worker_network(f):
    f.runtime()
    f.verify_order()

    class Probe(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.sendall(b'P5-REACHABLE')

    server = socketserver.ThreadingTCPServer(('0.0.0.0', 0), Probe)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        network = json.loads(subprocess.check_output(['docker', 'network', 'inspect', 'bridge']))
        gateway = network[0]['IPAM']['Config'][0]['Gateway']
        port = server.server_address[1]
        code = ("import socket,sys\ntry:\n s=socket.create_connection((sys.argv[1],int(sys.argv[2])),2)\n"
                " data=s.recv(32);s.close();sys.exit(0 if data==b'P5-REACHABLE' else 43)\n"
                "except OSError:sys.exit(42)\n")
        # Positive control is explicitly outside the networkless worker, on CI's bridge.
        positive = subprocess.run(['docker', 'run', '--rm', '--network', 'bridge', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--user', f.policy.run_as_user,
            f.policy.image_reference, 'python3', '-c', code, gateway, str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        backend = OCIContainerBackend(f.policy, 'docker', execute=True)
        result = backend.execute(('python3', '-c', code, gateway, str(port)), f.root, {}, 15)
        observed = dict(positive_exit=positive.returncode, worker_exit=result.exit_code,
            timed_out=result.timed_out, enforced=result.evidence['enforced'],
            backend_evidence_sha256=hashlib.sha256(canonical(result.evidence)).hexdigest(),
            policy_sha256=f.policy.content_sha256)
        # Recheck reachability after denial so a dead positive-control server cannot pass.
        restored = subprocess.run(positive.args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=30, check=False)
        from tools.ci.p5_network_evidence import retain as retain_network
        observed['retained_network_evidence'] = retain_network(
            positive, result, restored, f.policy, code, gateway, port)
        return observed, positive.returncode == 0 and result.exit_code == 42 and not result.timed_out and result.evidence['enforced'] and restored.returncode == 0, [
            'OCI denial is measured directly; the factory controller post-denial receipt path is not exercised.']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def budget_exhausted(f):
    from tools.ci.p5_controller_budgets import observe
    stub, provider = wrapped(f)
    call(provider)
    call(provider)
    stopped = refused(lambda: call(provider))
    controller_cases = observe(f, Path(__file__).resolve().parents[2])
    from tools.ci.p5_fallback_probe import observe as observe_fallback
    fallback_cases = [observe_fallback(f.parent/('fallback-'+str(changed)),
        Path(__file__).resolve().parents[2], changed_fallback_model=changed)
        for changed in (False, True)]
    observed = dict(calls=stub.calls, accounted_calls=len(provider.calls), call_cap=f.order.max_model_calls,
                    third_call_refused=stopped, real_model_calls=0, actual_spend=0,
                    controller_cases=controller_cases, fallback_cases=fallback_cases)
    return observed, stopped and stub.calls == len(provider.calls) == 2, [
        'Controller dollar/token preflight and returned-usage refusals retain blocked receipts; simulated accounting is observed separately.',
        'Signed synthetic routing exercises shared-cap fallback and rejects a fallback model outside F2 approval; it grants no real routing authority.',
        'Isolation failure receipts do not yet durably retain all model charge details; observer accounting is not a replacement controller receipt.',
        'Full signed factory build receipts and abrupt-stop recovery remain unqualified.']


def tower_unreachable(f):
    from tools.ci.p5_controller_outage import observe as observe_controller
    controller = observe_controller(f.parent/'outage-controller', Path(__file__).resolve().parents[2])
    head = f.head

    class Relay(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(head.encode('ascii'))

        def do_POST(self):
            with f.service.transaction() as db:
                event = f.service.append(db, 'p5-ci-probe', {'synthetic': True}, f.service.system_actor())
            self.send_response(200)
            self.end_headers()
            self.wfile.write(canonical(event))

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Relay)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = 'http://127.0.0.1:' + str(server.server_address[1])
    opener = build_opener(ProxyHandler({}))

    def trust():
        with opener.open(address, timeout=2) as response:
            return response.read(65).decode('ascii')

    original = f.admission.trusted_head
    try:
        f.admission.trusted_head = trust
        f.runtime()
        with opener.open(address, data=b'probe', timeout=2) as response:
            event = json.loads(response.read(65536))
        if not verify_envelope(event, f.service.public_key):
            raise ValueError('p5-journal-positive-control')
        with f.service.transaction() as db:
            before = len(f.service.events(db))
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        admission_stopped = refused(f.runtime, (URLError, OSError, ContractError))
        append_stopped = refused(lambda: opener.open(address, data=b'probe', timeout=2), (URLError, OSError))
        with f.service.transaction() as db:
            after = len(f.service.events(db))
        return dict(admission_refused=admission_stopped, append_refused=append_stopped,
                    journal_events_before=before, journal_events_after=after,
                    controller_outage=controller), admission_stopped and append_stopped and before == after and controller['operator_outage_refused'], [
            'Real verifier and signed journal sit behind a disposable HTTP relay, not the deployed Tower API.',
            'Production controller handling of an unavailable append and its fallback receipt remains unmeasured.']
    finally:
        f.admission.trusted_head = original
        server.shutdown()
        server.server_close()


def workspace_changed(f):
    from tools.ci.p5_controller_workspace import observe as observe_workspace
    controller = observe_workspace(f, Path(__file__).resolve().parents[2])
    from tools.ci.p5_workspace_replacement import observe as observe_replacement
    replacement = observe_replacement()
    f.runtime()
    path = f.root / 'worker.py'
    old = path.read_bytes()
    stub, provider = wrapped(f)
    try:
        path.write_bytes(old + b'# tampered after sealing\n')
        stopped = refused(lambda: call(provider))
        return dict(admission_refused=stopped, stub_calls=stub.calls,
                    original_sha256=hashlib.sha256(old).hexdigest(),
                    changed_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    controller_workspace=controller, workspace_path_replacement=replacement), stopped and stub.calls == 0 and (
                        tuple(row['case'] for row in controller) == ('clean', 'read-mutation')) and all(
                        row['controller_refused'] is (row['case'] != 'clean') and
                        row['transport_calls'] == (2 if row['case'] == 'clean' else 1) for row in controller), [
            'Tracked-source tampering is measured; race-time replacement inside the assembled worker needs an end-to-end drill.']
    finally:
        path.write_bytes(old)


def answer_fragment(f):
    from tools.ci.p5_controller_context import observe as observe_context
    controller = observe_context(f, Path(__file__).resolve().parents[2])
    values = ['synthetic-account-7e091c2d-amount-178352.91-balance-782146.32']
    canaries = {name: hashlib.sha256(('p5-' + name).encode()).hexdigest()
                for name in ('expected-state', 'reference-output', 'session-answer')}
    clean = scan([('context', 'ordinary synthetic context')], canaries, values)
    planted = ' '.join(values[0].upper())
    stub, provider = wrapped(f)

    def contaminated():
        scan([('context', planted)], canaries, values)
        call(provider)

    stopped = refused(contaminated)
    return dict(clean_scan=clean['status'], expected_windows=clean['expected_window_count'],
                normalized_fragment_refused=stopped, stub_calls=stub.calls,
                controller_context=controller), stopped and stub.calls == 0 and (
                    tuple(row['case'] for row in controller) == ('clean', 'normalized', 'base64', 'hex')) and all(
                    row['controller_refused'] is (row['case'] != 'clean') and
                    row['transport_calls'] == (2 if row['case'] == 'clean' else 0) for row in controller), [
        'The unchanged scanner is exercised before the stub; full controller context construction and failure receipt remain unmeasured.']


def wall_and_window(f):
    from tools.ci.p5_controller_wall import observe as observe_wall
    controller = observe_wall(f, Path(__file__).resolve().parents[2])
    stub, provider = wrapped(f)
    with patch('lightyear_factory.providers.time.monotonic', return_value=provider.started + f.order.max_elapsed_seconds):
        at_wall = refused(lambda: call(provider))
    with patch('lightyear_factory.providers.time.monotonic', return_value=provider.started + f.order.max_elapsed_seconds + 0.001):
        past_wall = refused(lambda: call(provider))
    before_window = not refused(lambda: f.runtime(now=f.end - timedelta(microseconds=1)))
    at_window = refused(lambda: f.runtime(now=f.end))
    observed = dict(at_wall_refused=at_wall, past_wall_refused=past_wall,
        before_window_admitted=before_window, at_window_refused=at_window, stub_calls=stub.calls,
        controller_wall=controller,
        clock_injection='monotonic boundary only; real signed-window verifier receives explicit timestamps')
    gaps = ['Complete controller timeout and signed failure receipt remain unmeasured.']
    if not at_wall:
        gaps.append('The provider elapsed boundary uses >, so a call exactly at the wall cap was admitted.')
    return observed, at_wall and past_wall and before_window and at_window and (
        tuple(row['case'] for row in controller) == ('clean', 'past-wall')) and all(
        row['controller_refused'] is (row['case'] == 'past-wall') and
        row['transport_calls'] == (2 if row['case'] == 'clean' else 1)
        for row in controller), gaps


def duplicate_attempt(f):
    from tools.ci.p5_controller_outage import observe as observe_controller
    controller = observe_controller(f.parent/'duplicate-controller', Path(__file__).resolve().parents[2])
    ledger = f.parent / 'nonce-ledger'
    store = AdmissionNonceStore(ledger)
    f.verify_order(store)
    sequential = refused(lambda: f.verify_order(store), ExecutionContractError)
    race = f.parent / 'race-ledger'
    race.write_text('', encoding='ascii')
    store = AdmissionNonceStore(race)
    entered, release = threading.Event(), threading.Event()
    read = Path.read_text

    def interleave(path, *args, **kwargs):
        contents = read(path, *args, **kwargs)
        if path == race and not entered.is_set():
            entered.set()
            if not release.wait(timeout=20):
                raise ValueError('p5-replay-schedule-timeout')
        return contents

    def contender():
        return not refused(lambda: f.verify_order(AdmissionNonceStore(race)), ExecutionContractError)

    # Hold the first real read before append; every overlapping contender must
    # refuse at the real OS lock. No signature, ledger value or write is mocked.
    with patch.object(Path, 'read_text', interleave), ThreadPoolExecutor(max_workers=8) as pool:
        first = pool.submit(contender)
        try:
            if not entered.wait(timeout=20):
                raise ValueError('p5-replay-reader-timeout')
            remaining = [pool.submit(contender) for _ in range(7)]
            admitted = sum(future.result(timeout=20) for future in remaining)
        finally:
            release.set()
        admitted += first.result(timeout=20)
    return dict(sequential_replay_refused=sequential, concurrent_admissions=admitted, contenders=8,
                forced_schedule='first real read held before append while seven contenders attempt admission',
                nonce_rows=len(race.read_text(encoding='ascii').splitlines()),
                controller_attempt=controller), sequential and admitted == 1 and controller['duplicate_attempt_refused'], [
        'Real controller terminal re-entry and unchanged attempt/nonce bytes are retained; this disposable observation is not a signed production factory receipt.']


FUNCTIONS = dict(zip(DRILLS, (kill_mid_build, worker_network, budget_exhausted, tower_unreachable,
                            workspace_changed, answer_fragment, wall_and_window, duplicate_attempt)))


def inventory_ok(rows):
    return len(rows) == len(DRILLS) and {r.get('id') for r in rows} == set(DRILLS)


def collect(repository, output):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or output.exists():
        raise ValueError('p5-ci-or-exclusive-output')
    output.mkdir(parents=True)
    rows = []
    sources = {p: hashlib.sha256((repository / p).read_bytes()).hexdigest() for p in (
        'tools/ci/p5_fixture.py', 'tools/ci/p5_drills.py', 'tools/ci/p5_controller_probe.py',
        'tools/ci/p5_controller_budgets.py', 'tests/test_p5_controller_budgets.py',
        'tools/ci/p5_budget_evidence.py', 'tests/test_p5_budget_evidence.py',
        'tools/ci/p5_controller_outage.py', 'tools/ci/p5_controller_evidence.py',
        'tests/test_p5_controller_evidence.py',
        'tools/ci/p5_controller_workspace.py', 'tools/ci/p5_workspace_evidence.py',
        'tests/test_p5_controller_workspace.py',
        'tools/ci/p5_controller_wall.py', 'tests/test_p5_controller_wall.py',
        'tests/test_p5_wall_collection.py',
        'tools/ci/p5_workspace_replacement.py',
        'tests/test_p5_workspace_replacement.py',
        'tools/ci/p5_network_evidence.py',
        'tests/test_p5_network_evidence.py',
        'tools/ci/p5_controller_context.py', 'tools/ci/p5_context_evidence.py',
        'tests/test_p5_controller_context.py', 'src/lightyear_factory/context.py',
        'src/lightyear_factory/ledger.py', 'src/lightyear_factory/workspace.py',
        'tools/ci/p5_fallback_probe.py', 'tests/test_p5_controller_fallback.py',
        'src/lightyear_factory/orchestrator.py', 'src/lightyear_factory/agents.py',
        'src/lightyear_factory/routing.py', 'src/lightyear_factory/model_admission.py',
        'src/lightyear_factory/providers.py', 'src/lightyear_factory/budgeted_providers.py',
        'src/lightyear_factory/isolation_scan.py', 'src/lightyear_execution/admission.py',
        'src/lightyear_execution/backend.py', 'src/lightyear_control_tower/decisions.py',
        'src/lightyear_control_tower/verification.py', 'src/lightyear_control_tower/factory_policy.py')}
    for name, function in FUNCTIONS.items():
        with tempfile.TemporaryDirectory(prefix='p5-ci-') as temp:
            fixture = None
            try:
                fixture = object.__new__(Fixture)
                fixture.__init__(Path(temp), repository)
                # A corrupt HMAC must be refused by the real admission verifier.
                bad = copy.deepcopy(fixture.envelope)
                bad['signature']['value'] = '0' * 64
                if not refused(lambda: fixture.verify_order(envelope=bad), ExecutionContractError):
                    raise ValueError('p5-admission-negative-control')
                observed, matched, gaps = function(fixture)
                body = dict(schema='p5-disposable-observation/1', id=name, expected=EXPECTED[name], observed=observed,
                    expectation_met=matched, gaps=gaps, production_controller_receipt=False,
                    receipt_origin='disposable CI observer, not production controller',
                    source_sha256=sources, commit=os.environ.get('GITHUB_SHA'),
                    run_id=os.environ.get('GITHUB_RUN_ID'), run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'))
                receipt = fixture.signed_observation(body)
                row = dict(id=name, expectation_met=matched, gaps=gaps, harness_error=False,
                    receipt_file=name + '.json', public_key_file=name + '.public.pem',
                    receipt_sha256=hashlib.sha256(canonical(receipt)).hexdigest())
                (output / row['receipt_file']).write_bytes(canonical(receipt))
                (output / row['public_key_file']).write_bytes(fixture.service.public_key)
            except Exception as error:
                # Type only: never traceback, credential, authority bytes or synthetic answer values.
                row = dict(id=name, expectation_met=False, harness_error=True,
                           error_type=type(error).__name__, gaps=['Harness incomplete; no accepted drill result.'])
            finally:
                if fixture is not None and hasattr(fixture, 'service'):
                    fixture.close()
            rows.append(row)
            (output / 'summary.json').write_bytes(canonical(dict(schema='p5-drills/1', drills=rows,
                complete=inventory_ok(rows), go=False, real_models=False, production_authority=False)))
    return all(not row['harness_error'] for row in rows)


def qualify(output):
    report = json.loads((output / 'summary.json').read_bytes())
    if report.get('schema') != 'p5-drills/1' or not report.get('complete') or not inventory_ok(report['drills']):
        return False
    qualified = True
    for row in report['drills']:
        if row.get('harness_error'):
            qualified = False
            continue
        # Exact inventory-derived names prevent an artifact from choosing filesystem paths.
        name = row['id']
        raw = (output / (name + '.json')).read_bytes()
        receipt = json.loads(raw)
        if hashlib.sha256(raw).hexdigest() != row['receipt_sha256']:
            return False
        if not verify_envelope(receipt, (output / (name + '.public.pem')).read_bytes()):
            return False
        if receipt.get('id') != name or receipt.get('expected') != EXPECTED[name] or receipt.get('expectation_met') != row.get('expectation_met') or receipt.get('gaps') != row.get('gaps'):
            return False
        if not receipt.get('expectation_met') or receipt.get('gaps') or receipt.get('production_controller_receipt') is not True:
            qualified = False
    return qualified


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qualify', action='store_true')
    args = parser.parse_args()
    try:
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            raise ValueError('p5-ci-only')
        result = qualify(args.output) if args.qualify else collect(Path.cwd(), args.output)
        print('P5 qualification passed' if args.qualify and result else
              'P5 observations retained; qualification is separate' if result else
              'P5 blocked: inspect public gaps and harness-error counts')
        return 0 if result else 1
    except Exception:
        print('P5 harness refused; no drill or qualification pass', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
