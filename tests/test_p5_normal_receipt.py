"""CI-only comparison of the real PASSED finalizer against its exact prior source."""
import hashlib
import os
from pathlib import Path
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from lightyear_factory import orchestrator
from lightyear_factory.agents import LocalAgentSet
from lightyear_factory.benchmark import benchmark_work_order
from lightyear_factory.ledger import RunLedger


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        value=cls(2026,10,24,12,0,0,tzinfo=timezone.utc)
        return value if tz else value.replace(tzinfo=None)


class NormalReceiptTests(unittest.TestCase):
    def test_passed_receipt_bytes_unchanged_with_fixed_clock(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        repository=Path(__file__).resolve().parents[1]
        raw=(repository/'tests/fixtures/p5/normal_finish_before.txt').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'd87b0de3f05d8d7f65fe500bc151e8f50b1d9f4415c140943657929312545bf8')
        baseline=types.ModuleType('lightyear_factory._p5_before_finalizer')
        baseline.__dict__.update(orchestrator.__dict__)
        # Immutable exact _finish from bc91d308, complete source SHA beee2917….
        # No admission, model or Tower function is replaced by this comparison.
        exec(compile(raw,'p5-reviewed-before-finalizer','exec'),baseline.__dict__)
        class BaselineController(orchestrator.FactoryOrchestrator):
            _finish=baseline.__dict__['_finish']
        baseline.FactoryOrchestrator=BaselineController
        order=benchmark_work_order('rounding-mode')
        with tempfile.TemporaryDirectory(prefix='p5-normal-ci-') as temp:
            root=Path(temp); run=root/'runs'/'normal-completion'; run.mkdir(parents=True)
            source=root/'source';source.mkdir()
            with patch('lightyear_factory.ledger.datetime',FixedDatetime):
                ledger=RunLedger(run/'events.jsonl')
                ledger.append('PASSED','acceptance_gates_passed',dict(status='passed'))
            outputs=[]
            for module in (baseline,orchestrator):
                controller=module.FactoryOrchestrator(source,root/'runs',LocalAgentSet())
                with patch.object(module,'datetime',FixedDatetime):
                    receipt=controller._finish(run,'normal-completion',order,'PASSED',1,
                        '2026-10-24T11:59:00+00:00',ledger,[],{}, {},
                        dict(status='passed',gates=[dict(id='synthetic',status='passed',output_sha256='1'*64)]),
                        'Synthetic finalizer comparison only',{})
                self.assertEqual(receipt['status'],'passed')
                outputs.append(((run/'receipt.json').read_bytes(),(run/'summary.json').read_bytes()))
            self.assertEqual(outputs[0],outputs[1])


    def test_full_normal_reference_completion_receipt_bytes_unchanged(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        import shutil
        from dataclasses import replace
        from lightyear_factory import benchmark
        from lightyear_execution.backend import LocalProcessBackend
        repository=Path(__file__).resolve().parents[1]
        before=types.ModuleType('lightyear_factory._p5_before_run')
        before.__dict__.update(orchestrator.__dict__)
        for filename,expected in (
            ('normal_finish_before.txt','d87b0de3f05d8d7f65fe500bc151e8f50b1d9f4415c140943657929312545bf8'),
            ('normal_run_before.txt','ac167e17bed879494496b5083cf5bbed7229498989d5b00748a3a4d090eaec48')):
            raw=(repository/'tests/fixtures/p5'/filename).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),expected)
            exec(compile(raw,'p5-reviewed-before-'+filename,'exec'),before.__dict__)
        BeforeController=type('BeforeController',(orchestrator.FactoryOrchestrator,),
            {name:before.__dict__[name] for name in ('run','_run','_finish')})
        execute=LocalProcessBackend.execute
        def timed(self,*args,**kwargs):
            # Real synthetic subprocess gates still run; only duration is fixed.
            return replace(execute(self,*args,**kwargs),duration_ms=0)
        with tempfile.TemporaryDirectory(prefix='p5-normal-run-ci-') as temp:
            output=Path(temp)/'normal';receipts=[]
            for controller in (BeforeController,orchestrator.FactoryOrchestrator):
                with patch.object(benchmark,'FactoryOrchestrator',controller), \
                     patch.object(orchestrator,'datetime',FixedDatetime), \
                     patch.object(before,'datetime',FixedDatetime), \
                     patch('lightyear_factory.ledger.datetime',FixedDatetime), \
                     patch.object(LocalProcessBackend,'execute',timed):
                    result=benchmark.run_mutation_benchmark(repository,output,['rounding-mode'])
                self.assertEqual(result['status'],'passed')
                self.assertEqual(result['autonomously_repaired'],1)
                run=output/'runs'/'benchmark-rounding-mode'
                receipts.append(((run/'receipt.json').read_bytes(),(run/'summary.json').read_bytes()))
                self.assertEqual(output.resolve().parent,Path(temp).resolve())
                shutil.rmtree(output)
            self.assertEqual(receipts[0],receipts[1])


    def test_blocked_model_run_preserves_provenance_and_finalizer_bytes(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        import json
        from dataclasses import replace
        from lightyear_factory.agents import ModelAgentSet
        from lightyear_factory.providers import ScriptedModelProvider, ProviderResult
        from lightyear_factory.contracts import canonical_hash, write_json
        from lightyear_factory.build_receipt import compute_build_receipt
        from lightyear_factory.qualification import _run_provenance
        from lightyear_execution.backend import OCIContainerBackend, LocalProcessBackend
        from lightyear_execution.integration import HardenedExecutionContext
        from tools.ci.p5_fixture import Fixture
        from contextlib import ExitStack
        from lightyear_factory.gates import CandidateBuildBackend

        repository = Path(__file__).resolve().parents[1]
        raw = (repository/'tests/fixtures/p5/normal_finish_before.txt').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'd87b0de3f05d8d7f65fe500bc151e8f50b1d9f4415c140943657929312545bf8')
        baseline = types.ModuleType('lightyear_factory._p5_blocked_before')
        baseline.__dict__.update(orchestrator.__dict__)
        exec(compile(raw, 'p5-reviewed-before-finalizer', 'exec'), baseline.__dict__)
        check = self
        compared = []

        class ComparedController(orchestrator.FactoryOrchestrator):
            def _finish(self, *args, **kwargs):
                check.assertEqual(args[3], 'BLOCKED')
                check.assertEqual(args[-1]['approved_roots'], [])
                check.assertEqual(args[-1]['nodes'], [])
                check.assertEqual(args[-1]['edges'], [])
                check.assertIsNone(args[-1]['semantic_memory'])
                run = args[0]
                tick = orchestrator.time.monotonic()
                with patch.object(baseline, 'datetime', FixedDatetime), \
                     patch('time.monotonic', return_value=tick):
                    old = baseline.__dict__['_finish'](self, *args, **kwargs)
                old_bytes = (run/'receipt.json').read_bytes()
                old_summary = (run/'summary.json').read_bytes()
                with patch.object(orchestrator, 'datetime', FixedDatetime), \
                     patch('time.monotonic', return_value=tick):
                    current = super()._finish(*args, **kwargs)
                    check.assertEqual(current['intelligence'], self.agents.intelligence_summary())
                check.assertEqual(old['intelligence'], current['intelligence'])
                check.assertEqual(set(current)-set(old), {'failure_accounting'})
                check.assertEqual(current['failure_accounting']['schema'],
                                  'factory-sanitized-accounting/1')
                normalized = dict(current)
                normalized.pop('failure_accounting')
                normalized['content_sha256'] = canonical_hash(normalized, {'content_sha256'})
                write_json(normalized, run/'normalized-receipt.json')
                if old_bytes != (run/'normalized-receipt.json').read_bytes():
                    # Only fixed receipt-field names/counts/hashes, never field contents.
                    import re
                    changed = sorted(key for key in set(old) | set(normalized)
                                     if old.get(key) != normalized.get(key))
                    safe_keys = [key if re.fullmatch('[a-z_]{1,64}', key) else 'redacted'
                                 for key in changed[:32]]
                    print('p5-receipt-difference:' + json.dumps(dict(
                        fields=safe_keys, old_event_count=old.get('event_count'),
                        current_event_count=normalized.get('event_count'),
                        old_bytes_sha256=hashlib.sha256(old_bytes).hexdigest(),
                        current_bytes_sha256=hashlib.sha256((run/'normalized-receipt.json').read_bytes()).hexdigest()), sort_keys=True), flush=True)
                check.assertEqual(old_bytes, (run/'normalized-receipt.json').read_bytes())
                summary = json.loads((run/'summary.json').read_bytes())
                summary['receipt_sha256'] = old['content_sha256']
                write_json(summary, run/'normalized-summary.json')
                check.assertEqual(old_summary, (run/'normalized-summary.json').read_bytes())
                compared.append(True)
                return current

        class SyntheticProvider(ScriptedModelProvider):
            # Explicit synthetic identity: structural validation, never real-model qualification.
            provider_id = 'p5-synthetic-provenance'
            model = 'p5-synthetic-only-2026-10-24'

            def complete(self, *args, **kwargs):
                result = super().complete(*args, **kwargs)
                evidence = dict(result.evidence, cost_estimate_available=True)
                evidence['content_sha256'] = canonical_hash(evidence, {'content_sha256'})
                return ProviderResult(result.content, evidence)

        path = 'factory/benchmarks/intcalc_candidate.py'
        plan = dict(summary='Synthetic divergent plan', risks=[], tasks=[dict(
            id='synthetic', objective='Preserve deliberately divergent rounding',
            paths=[path], graph_node_ids=[], evidence_capsule_ids=[])])
        diagnosis = dict(summary='Synthetic gate divergence', failure_codes=['GATE_FAILED:private-intcalc-policy'],
                         builder_guidance='Synthetic refusal case', risk='medium')
        proposal = dict(summary='Synthetic divergent edit', edits=[dict(path=path,
            find='ROUNDING = "half-up"', replace='ROUNDING = "half-up"  # still divergent',
            rationale='Exercise exhausted attempts without changing the wrong behaviour')], blocked_reason=None)
        provider = SyntheticProvider([plan, diagnosis, proposal, diagnosis])
        agents = ModelAgentSet(provider)
        # Receipt regression uses packed file context, not the unrelated full public graph.
        order = replace(benchmark_work_order('rounding-mode'), max_attempts=1, graph_node_ids=())

        def prepare(workspace, _):
            target = workspace.resolve(path)
            source = target.read_text(encoding='utf-8')
            self.assertIn('ROUNDING = "down"', source)
            target.write_text(source.replace('ROUNDING = "down"', 'ROUNDING = "half-up"', 1), encoding='utf-8')

        with ExitStack() as cleanup:
            temp = cleanup.enter_context(tempfile.TemporaryDirectory(prefix='p5-blocked-model-ci-'))
            root = Path(temp)
            fixture = Fixture(root, repository, controller_probe=True,
                blocked_receipt_order=order,
                blocked_receipt_identity=(provider.provider_id, provider.model))
            cleanup.callback(fixture.close)
            self.assertEqual(fixture.order.content_sha256, order.content_sha256)
            _, admission = fixture.verify_order()
            backend = OCIContainerBackend(fixture.policy, 'docker', execute=True)
            context = HardenedExecutionContext(fixture.policy, backend, admission, fixture.key)
            controller = ComparedController(fixture.root, root/'runs', agents,
                prepare_workspace=prepare, execution_context=context,
                model_admission=fixture.admission, factory_input_paths=fixture.input_paths,
                workspace_read_manifest=fixture.runtime()['workspace_read_manifest'],
                private_expected_values_path=fixture.private_values_path)
            gate_results = []
            def synthetic_container(container, command, workspace, environment, timeout):
                # CI fixture only: real benchmark subprocess and real admission;
                # OCI execution evidence is simulated, never acceptance evidence.
                _, plan = container.build_invocation(command, workspace, environment)
                result = LocalProcessBackend().execute(command, workspace, environment, timeout)
                self.assertEqual(result.exit_code, 1)
                self.assertIn(b'INTCALC private policy gate failed', result.stderr)
                gate_results.append(result.exit_code)
                return replace(result, evidence=dict(plan, assurance='enforced', enforced=True,
                    synthetic_execution=True))
            with patch.object(CandidateBuildBackend, 'execute', new=synthetic_container):
                try:
                    receipt = controller.run(order, 'blocked-model')
                except Exception as error:
                    # CI synthetic fixture: disclose only types, safe codes and source locations.
                    import re
                    chain = []
                    seen = set()
                    while error is not None and id(error) not in seen and len(chain) < 6:
                        seen.add(id(error))
                        code = str(error) if type(error).__name__ == 'ContractError' else ''
                        if not re.fullmatch('[a-z][a-z0-9-]{0,79}', code):
                            code = 'redacted'
                        frames = []
                        tb = error.__traceback__
                        while tb is not None:
                            frames.append(dict(file=Path(tb.tb_frame.f_code.co_filename).name,
                                               line=tb.tb_lineno, function=tb.tb_frame.f_code.co_name))
                            tb = tb.tb_next
                        chain.append(dict(type=type(error).__name__, code=code, frames=frames[-6:]))
                        error = error.__context__
                    raise AssertionError('p5-blocked-fixture-refused:' + json.dumps(chain, sort_keys=True)) from None
            self.assertEqual(gate_results, [1, 1])
            run = root/'runs'/'blocked-model'
            ledger = RunLedger(run/'events.jsonl')
            self.assertEqual(compared, [True])
            self.assertEqual(receipt['status'], 'blocked')
            self.assertEqual(receipt['attempts'], order.max_attempts)
            self.assertTrue(any(e['kind']=='attempt_budget_exhausted' for e in ledger.events))
            intelligence = receipt['intelligence']
            self.assertEqual(receipt['failure_accounting']['calls'], intelligence['calls'])
            self.assertEqual(intelligence['calls'], 4)
            fields = dict(model_calls='calls', provider_attempts='provider_attempts',
                provider_retries='provider_retries', input_tokens='input_tokens', output_tokens='output_tokens',
                estimated_cost_usd='estimated_cost_usd', elapsed_ms='elapsed_ms',
                cost_estimate_available='cost_estimate_available')
            result = dict(receipt_sha256=receipt['content_sha256'], status='blocked', attempts=1,
                          **{out:intelligence[source] for out,source in fields.items()})
            totals = {key:result[key] for key in fields if key!='elapsed_ms'}
            provenance = _run_provenance(root, dict(results=[result], totals=totals))
            self.assertEqual(provenance['providers'], [provider.provider_id])
            self.assertEqual(provenance['call_evidence_sha256'], sorted(intelligence['call_evidence_sha256']))
            runtime = dict(schema='factory-model-admission/1', work_order_sha256=order.content_sha256,
                           provider_verified=False)
            build = compute_build_receipt(order, ledger, receipt, agents.bounded_provider.calls, runtime, run)
            self.assertEqual(build['status'], 'blocked')
            self.assertFalse(build['qualifies_for_factory_receipt'])
            self.assertIn('acceptance-gates', build['reasons'])
            self.assertEqual(build['accounting_sha256'], canonical_hash(intelligence))
            accounting_reasons = {'model-call-budget','accounting-digests','cost-accounting',
                'accounted-input_tokens','accounted-output_tokens','accounted-cost','token-budget',
                'budget-input_bytes','budget-output_bytes','budget-estimated_cost_usd','budget-elapsed_ms'}
            self.assertFalse(accounting_reasons.intersection(build['reasons']))
            # The public synthetic run has no signed transport/package; it must not become qualified.
            self.assertIn('signed-history', build['reasons'])


if __name__=='__main__':
    unittest.main()
