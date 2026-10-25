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


if __name__=='__main__':
    unittest.main()
