"""Disposable CI mutation during the actual assembled-workspace read window."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.workspace import IsolatedWorkspace
from tools.ci.p5_budget_evidence import retain as retain_budget
from tools.ci.p5_controller_budgets import BudgetStub
from tools.ci.p5_fixture import Fixture
from tools.ci.p5_workspace_evidence import validate

CASES = ('clean', 'read-mutation')


def observe_case(parent, repository, case):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or case not in CASES:
        raise ValueError('p5-workspace-ci-only')
    parent = Path(parent); parent.mkdir()
    fixture = Fixture(parent, repository, controller_probe=True)
    try:
        digest = lambda raw: hashlib.sha256(raw).hexdigest()
        roles = []
        class RecordingStub(BudgetStub):
            def complete(self, role, instruction, payload, schema):
                roles.append(role)
                return super().complete(role, instruction, payload, schema)
        stub = RecordingStub('control', fixture.order)
        agents = ModelAgentSet(stub)
        _, admission = fixture.verify_order()
        context = HardenedExecutionContext(fixture.policy,
            OCIContainerBackend(fixture.policy, 'docker', execute=False), admission, fixture.key)
        runs = parent/'runs'; run_id = 'p5-workspace-'+case
        target = (runs/run_id/'workspace/worker.py').resolve()
        source = fixture.root/'worker.py'; original = source.read_bytes()
        controller = FactoryOrchestrator(fixture.root, runs, agents,
            execution_context=context, model_admission=fixture.admission,
            factory_input_paths=fixture.input_paths,
            workspace_read_manifest=fixture.runtime()['workspace_read_manifest'],
            private_expected_values_path=fixture.private_values_path)
        real_open, real_scan = Path.open, IsolatedWorkspace.scan_contents
        active = None; boundary = []; reads = []; injections = []; intercepted = False

        class ReadWindow:
            def __init__(self, handle): self.handle = handle
            def __enter__(self):
                self.handle.__enter__()
                return self
            def __exit__(self, *args): return self.handle.__exit__(*args)
            def fileno(self): return self.handle.fileno()
            def read(self, *args):
                raw = self.handle.read(*args)  # Real read, before the production post-read fstat.
                reads.append(digest(raw))
                if case == 'read-mutation':
                    if injections or roles != ['planner'] or raw != original:
                        raise ValueError('p5-workspace-injection-sequence')
                    replacement = raw+b'# synthetic mutation during open read\n'
                    target.write_bytes(replacement)
                    injections.append(dict(before_sha256=digest(raw), after_sha256=digest(replacement),
                                           before_bytes=len(raw), after_bytes=len(replacement)))
                return raw

        def open_window(path, *args, **kwargs):
            nonlocal intercepted
            mode = args[0] if args else kwargs.get('mode', 'r')
            handle = real_open(path, *args, **kwargs)
            if active == 'builder-workspace' and path.resolve() == target and mode == 'rb' and not intercepted:
                intercepted = True
                return ReadWindow(handle)
            return handle

        def recording_boundary(workspace, scanner, surface):
            nonlocal active
            previous = active; active = surface
            try:
                result = real_scan(workspace, scanner, surface)
            except ContractError as error:
                boundary.append(dict(surface=surface, outcome=str(error)))
                raise
            else:
                boundary.append(dict(surface=surface, outcome='passed'))
                return result
            finally:
                active = previous

        refused = False
        with patch.object(Path, 'open', open_window), patch.object(IsolatedWorkspace, 'scan_contents', recording_boundary):
            try:
                controller.run(fixture.order, run_id)
            except ContractError as error:
                if str(error) != 'factory-isolation-run-refused':
                    raise ValueError('p5-workspace-wrong-controller-refusal') from None
                refused = True
        budget = agents.bounded_provider
        if type(budget) is not AccountedModelProvider or stub.calls != len(budget.calls):
            raise ValueError('p5-workspace-accounted-provider-required')
        value = dict(schema='p5-retained-workspace-evidence/1',
            origin='disposable CI controller; mutation after real file read before post-read fstat',
            case=case, run_id=run_id, work_order_sha256=fixture.order.content_sha256,
            controller_refused=refused, transport_roles=roles, transport_calls=stub.calls,
            source_before_sha256=digest(original), source_after_sha256=digest(source.read_bytes()),
            workspace_after_sha256=digest(target.read_bytes()), reads=reads,
            injections=injections, boundaries=boundary)
        directory = runs/run_id
        if case == 'clean':
            value['clean_control'] = retain_budget(directory, budget.calls, case='control',
                run_id=run_id, work_order_sha256=fixture.order.content_sha256)
        else:
            for kind, filename in (('receipt', 'receipt.json'), ('identity', 'attempt-identity.json'), ('ledger', 'events.jsonl')):
                raw = (directory/filename).read_bytes()
                value[kind+'_utf8'], value[kind+'_sha256'] = raw.decode('utf-8'), digest(raw)
            raw = json.dumps(budget.calls, sort_keys=True, separators=(',', ':'), allow_nan=False)
            value['calls_utf8'], value['calls_sha256'] = raw, digest(raw.encode())
        validate(value, case=case, work_order_sha256=fixture.order.content_sha256)
        return value
    finally:
        fixture.close()


def observe(fixture, repository):
    root = fixture.parent/'workspace-controller-probes'; root.mkdir()
    return [observe_case(root/case, repository, case) for case in CASES]
