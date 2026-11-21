"""CI-only controller construction and fail-closed receipt regressions.

Disposable authority, real admission, no transport or production authority.
These probes do not claim abrupt-process recovery or full P5 qualification.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.providers import BoundedModelProvider
from lightyear_factory.routing import TaskRouter, RoutedBudget
from lightyear_factory.workspace import IsolatedWorkspace
from tools.ci.p5_fixture import Fixture
from tools.ci.p5_drills import Stub


class P5ControllerBindingTests(unittest.TestCase):
    def test_real_admission_constructs_accounted_direct_and_configured_routes(self):
        repository = Path(__file__).resolve().parents[1]
        for routed in (False, True):
            with self.subTest(routed=routed), tempfile.TemporaryDirectory() as temporary:
                fixture = Fixture(Path(temporary), repository)
                try:
                    stub = Stub()
                    provider = TaskRouter({'synthetic': stub}, 'synthetic') if routed else stub
                    agents = ModelAgentSet(provider)
                    _, admission = fixture.verify_order()
                    execution = HardenedExecutionContext(fixture.policy,
                        OCIContainerBackend(fixture.policy, 'docker', execute=False),
                        admission, fixture.key)
                    controller = FactoryOrchestrator(fixture.root, fixture.parent/'runs', agents,
                        execution_context=execution, model_admission=fixture.admission,
                        factory_input_paths=fixture.input_paths,
                        workspace_read_manifest=fixture.runtime()['workspace_read_manifest'])
                    constructed = []
                    original = BoundedModelProvider.__init__

                    def observe(instance, *args, **kwargs):
                        constructed.append(type(instance))
                        return original(instance, *args, **kwargs)

                    # Inject only an assembly fault after the actual controller binds
                    # its provider. Admission and both constructors are unmodified.
                    with patch.object(BoundedModelProvider, '__init__', observe), patch.object(
                            IsolatedWorkspace, 'create', side_effect=OSError('synthetic assembly fault')):
                        with self.assertRaisesRegex(ContractError, '^factory-isolation-run-refused$'):
                            controller.run(fixture.order, 'p5-controller-binding')
                    self.assertEqual([AccountedModelProvider], constructed)
                    bound = agents.bounded_provider
                    if routed:
                        self.assertIs(type(bound), RoutedBudget)
                        self.assertIs(bound.router, provider)
                        bound = bound.budget
                    self.assertIs(type(bound), AccountedModelProvider)
                    self.assertIs(bound.provider, stub)
                    self.assertIs(bound.order, fixture.order)
                    self.assertIs(bound.model_admission, fixture.admission)
                    self.assertTrue(callable(bound.runtime_admission))
                    self.assertIs(agents._provider_for(fixture.order), agents.bounded_provider)
                    self.assertEqual(0, stub.calls)
                    directory = fixture.parent/'runs'/'p5-controller-binding'
                    raw = (directory/'receipt.json').read_bytes()
                    receipt = json.loads(raw)
                    self.assertEqual('blocked', receipt['status'])
                    self.assertFalse(receipt['qualifies_for_factory_receipt'])
                    self.assertEqual(fixture.order.content_sha256, receipt['work_order_sha256'])
                    self.assertEqual(receipt['content_sha256'], canonical_hash(receipt, {'content_sha256'}))
                    events = (directory/'events.jsonl').read_bytes()
                    self.assertNotIn(b'synthetic assembly fault', raw + events)
                    summary = json.loads((directory/'summary.json').read_bytes())
                    self.assertEqual(receipt['content_sha256'], summary['receipt_sha256'])
                    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in directory.iterdir() if p.is_file()}
                    # Refusing the same attempt must preserve the first receipt.
                    with self.assertRaisesRegex(ContractError, '^factory-isolation-run-refused$'):
                        controller.run(fixture.order, 'p5-controller-binding')
                    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in directory.iterdir() if p.is_file()}
                    self.assertEqual(before, after)
                finally:
                    fixture.close()

    def test_bare_wrapper_is_rejected_before_any_f2_transport(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary), repository)
            try:
                for routed in (False, True):
                    with self.subTest(routed=routed):
                        stub = Stub()
                        provider = TaskRouter({'synthetic': stub}, 'synthetic') if routed else stub
                        agents = ModelAgentSet(provider)
                        agents.order_sha256 = fixture.order.content_sha256
                        base = BoundedModelProvider(stub, fixture.order)
                        if routed:
                            agents.bounded_provider = provider.bind_order(fixture.order,
                                model_admission=fixture.admission, runtime_admission=fixture.runtime)
                            agents.bounded_provider.budget = base
                        else:
                            agents.bounded_provider = base
                        with self.assertRaisesRegex(ContractError, '^factory-model-controller-binding-required$'):
                            agents._provider_for(fixture.order)
                        self.assertEqual(0, stub.calls)
            finally:
                fixture.close()
