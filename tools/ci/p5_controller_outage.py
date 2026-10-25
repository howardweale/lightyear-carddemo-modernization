"""Synthetic CI observations of controller outage and terminal attempt identity."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import threading
from urllib.request import ProxyHandler, build_opener

from lightyear_execution.admission import AdmissionNonceStore
from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError
from lightyear_factory.orchestrator import FactoryOrchestrator
from tools.ci.p5_controller_budgets import BudgetStub
from tools.ci.p5_controller_evidence import validate as validate_evidence
from tools.ci.p5_controller_probe import inspect_receipt, snapshot
from tools.ci.p5_fixture import Fixture


def observe(parent, repository):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('p5-controller-outage-ci-only')
    parent = Path(parent)
    parent.mkdir()
    fixture = Fixture(parent, repository, controller_probe=True)
    server = thread = None
    try:
        class Relay(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(fixture.head.encode('ascii'))

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Relay)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = 'http://127.0.0.1:' + str(server.server_address[1])
        opener = build_opener(ProxyHandler({}))
        stopped = False

        def stop():
            nonlocal stopped
            if not stopped:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                stopped = True
                if thread.is_alive():
                    raise ValueError('p5-controller-outage-relay-still-running')

        def trusted_head():
            with opener.open(address, timeout=2) as response:
                return response.read(65).decode('ascii')

        fixture.admission.trusted_head = trusted_head
        runtime = fixture.runtime()  # Real verifier with a reachable positive control.
        runs = parent/'runs'
        store = AdmissionNonceStore(runs/'admission-nonces.sha256')
        _, admission = fixture.verify_order(store=store)
        consumed = store.path.read_bytes()
        context = HardenedExecutionContext(fixture.policy,
            OCIContainerBackend(fixture.policy, 'docker', execute=False), admission, fixture.key)

        class OutageStub(BudgetStub):
            def complete(self, role, instruction, payload, schema):
                result = super().complete(role, instruction, payload, schema)
                if role == 'planner':
                    stop()  # Actual socket outage, before the next admitted model call.
                return result

        stub = OutageStub('control', fixture.order)
        agents = ModelAgentSet(stub)

        def controller(agent_set):
            return FactoryOrchestrator(fixture.root, runs, agent_set,
                execution_context=context, model_admission=fixture.admission,
                factory_input_paths=fixture.input_paths,
                workspace_read_manifest=runtime['workspace_read_manifest'],
                private_expected_values_path=fixture.private_values_path)

        run_id = 'p5-operator-outage'
        try:
            controller(agents).run(fixture.order, run_id)
        except ContractError as error:
            if str(error) != 'factory-isolation-run-refused':
                raise ValueError('p5-controller-outage-wrong-refusal') from None
        else:
            raise ValueError('p5-controller-outage-admitted')
        bounded = agents.bounded_provider
        if type(bounded) is not AccountedModelProvider or stub.calls != 1:
            raise ValueError('p5-controller-outage-call-boundary')
        receipt_path = runs/run_id/'receipt.json'
        receipt = inspect_receipt(receipt_path)
        raw = json.loads(receipt_path.read_bytes())
        accounting = raw.get('failure_accounting', {})
        if (raw.get('work_order_sha256') != fixture.order.content_sha256
                or accounting.get('schema') != 'factory-sanitized-accounting/1'
                or accounting.get('calls') != len(bounded.calls)
                or accounting.get('input_tokens') != bounded.input_tokens
                or accounting.get('output_tokens') != bounded.output_tokens
                or accounting.get('estimated_cost_usd') != bounded.estimated_cost_usd
                or len(accounting.get('call_hashes', [])) != len(bounded.calls)
                or type(accounting.get('duration_ms')) is not int):
            raise ValueError('p5-controller-outage-receipt-accounting')
        if store.path.read_bytes() != consumed:
            raise ValueError('p5-controller-outage-nonce-changed')

        # Restore only the synthetic trust accessor; do not admit a new attempt.
        fixture.admission.trusted_head = lambda: fixture.head
        before = snapshot(runs/run_id)
        duplicate_stub = BudgetStub('control', fixture.order)
        try:
            controller(ModelAgentSet(duplicate_stub)).run(fixture.order, run_id)
        except ContractError as error:
            if str(error) != 'factory-isolation-run-refused':
                raise ValueError('p5-controller-identity-wrong-refusal') from None
        else:
            raise ValueError('p5-controller-identity-admitted')
        if (duplicate_stub.calls != 0 or snapshot(runs/run_id) != before
                or store.path.read_bytes() != consumed):
            raise ValueError('p5-controller-identity-mutated')
        identity_path = runs/run_id/'attempt-identity.json'
        retained = dict(schema='p5-retained-controller-evidence/1',
            origin='disposable CI controller with stub transport',
            run_id=run_id, work_order_sha256=fixture.order.content_sha256,
            receipt_utf8=receipt_path.read_bytes().decode('utf-8'),
            receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            identity_utf8=identity_path.read_bytes().decode('utf-8'),
            identity_sha256=hashlib.sha256(identity_path.read_bytes()).hexdigest(),
            attempt_files_before=before, attempt_files_after=snapshot(runs/run_id),
            consumed_nonce_store_utf8=consumed.decode('ascii'),
            nonce_before_sha256=hashlib.sha256(consumed).hexdigest(),
            nonce_after_sha256=hashlib.sha256(store.path.read_bytes()).hexdigest(),
            transport_calls_before_reentry=stub.calls,
            duplicate_transport_calls=duplicate_stub.calls)
        validate_evidence(retained, run_id=run_id, work_order_sha256=fixture.order.content_sha256)
        return dict(operator_outage_refused=True, controller_receipt=receipt,
            retained_controller_evidence=retained,
            receipt_bytes_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            accounted_calls=len(bounded.calls), stub_calls=stub.calls,
            duplicate_attempt_refused=True, duplicate_stub_calls=duplicate_stub.calls,
            attempt_files_unchanged=True, nonce_unchanged=True,
            real_model_calls=0, actual_spend=0,
            limitation='Disposable trust-head relay; deployed Tower append and fallback remain unmeasured.')
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        fixture.close()
