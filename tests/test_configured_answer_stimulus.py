"""Disposable native component tests; never an authenticated clean control."""
from copy import deepcopy
from hashlib import sha256
import json,os,tempfile,unittest
from pathlib import Path
from lightyear_factory.contracts import ContractError,WorkOrder,canonical_hash
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.isolation_scan import scan
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_execution.configured_receipt_answer_stimulus import (
    WORKER,WORKER_SHA256,_fragment,_stimulus_bytes,_clean_boundary,
    _replace_copied_bytes,_match_intended_fragment,prepare_original_answer_fragment)
import test_configured_receipt_scan_observation as fixtures

class AnswerStimulusComponents(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.source=Path(__file__).resolve().parents[1]
        doc=json.loads((self.source/'docs/factory/p5-human-clean-control/configured-build-control/work-order.json').read_bytes())
        self.order=WorkOrder.from_dict(dict(doc,id='answer-fragment'))
        self.original=(self.source/WORKER).read_bytes()
        self.assertEqual(sha256(self.original).hexdigest(),WORKER_SHA256)
        self.values=tuple(fixtures.PUBLIC+str(i) for i in range(3))
        self.temp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.worker=self.root/WORKER
        self.worker.parent.mkdir(parents=True);self.worker.write_bytes(self.original)
        self.addCleanup(lambda:self.assertEqual((self.source/WORKER).read_bytes(),self.original))

    def assemble(self):return GraphContextAssembler(None,None).assemble(self.order,self.root)
    def encode(self,value):return json.dumps(value,sort_keys=True,ensure_ascii=False).encode()

    def test_fixed_writer_original_assembler_and_native_breach_compose(self):
        self.assertEqual(scan([('initial-workspace-file',self.original)],fixtures.CANARIES,self.values)['status'],'passed')
        proposed=_stimulus_bytes(self.original,self.values)
        _replace_copied_bytes(self.worker,self.original,proposed)
        value=self.assemble()
        try:scan([('controller-context',self.encode(value))],fixtures.CANARIES,self.values)
        except ContractError as error:
            self.assertEqual(error.args,('isolation-breach',));trace=error.__traceback__
            try:
                while trace.tb_next is not None:trace=trace.tb_next
                self.assertIs(trace.tb_frame.f_code,scan.__code__)
                result=_match_intended_fragment(value,proposed,self.values,trace.tb_frame.f_locals['normalized'])
                self.assertEqual(result,(sha256(proposed).hexdigest(),len(proposed),sha256(_fragment(self.values).encode()).hexdigest()))
                self.assertNotIn(_fragment(self.values),str(result))
            finally:del trace
        else:self.fail('native scan failed to refuse fixed normalized fragment')

    def test_clean_original_assembler_component_passes_without_authority(self):
        value=self.assemble()
        self.assertEqual(scan([('controller-context',self.encode(value))],fixtures.CANARIES,self.values)['status'],'passed')
        self.assertNotIn('admission_receipt',value)
        self.assertNotIn('qualification',value)

    def test_changed_original_worker_refuses_before_payload(self):
        with self.assertRaisesRegex(ContractError,'original-worker'):_stimulus_bytes(self.original+b'changed',self.values)

    def test_wrong_public_value_shape_and_nonascii_window_refuse(self):
        for value in (list(self.values),(),('short',)*3,('é'*40,)*3,(True,)*3):
            with self.subTest(value=value),self.assertRaises(ContractError):_stimulus_bytes(self.original,value)

    def test_original_unadmitted_controller_cannot_invoke_mutation(self):
        controller=FactoryOrchestrator(self.source,self.root/'runs',None)
        with self.assertRaisesRegex(ContractError,'original-answer-owner'):
            prepare_original_answer_fragment(controller,self.order,self.root)
        self.assertEqual(self.worker.read_bytes(),self.original)

    def test_unregistered_exact_context_cannot_bypass_original_call_boundary(self):
        from lightyear_execution.configured_receipt_context import ConfiguredReceiptExecutionContext
        context=object.__new__(ConfiguredReceiptExecutionContext)
        controller=FactoryOrchestrator(self.source,self.root/'runs',None,execution_context=context)
        with self.assertRaisesRegex(ContractError,'original-boundary'):
            prepare_original_answer_fragment(controller,self.order,self.root)
        self.assertEqual(self.worker.read_bytes(),self.original)

    def events(self):
        manifest={WORKER:WORKER_SHA256}
        return [dict(kind='workspace_read_manifest',payload=dict(files=manifest,sha256=canonical_hash(manifest))),
            dict(kind='model_isolation_scan_passed',payload={'scanned':[dict(artifact='initial-workspace-file',sha256=WORKER_SHA256)]}),
            dict(kind='model_isolation_scan_passed',payload={'scanned':[dict(artifact='approved-work-order',sha256=sha256(self.encode(self.order.to_dict())).hexdigest())]}),
            dict(kind='work_order_accepted',payload={'work_order_sha256':self.order.content_sha256}),
            dict(kind='candidate_controller_bound',payload={'order_sha256':self.order.content_sha256}),
            dict(kind='workspace_isolated',payload=dict(allowed_paths=[WORKER],initial_snapshot_sha256=canonical_hash(manifest)))]

    def test_pure_boundary_relationships_return_no_authority(self):
        rows=self.events();before=deepcopy(rows)
        self.assertIsNone(_clean_boundary(rows,self.order,self.original));self.assertEqual(rows,before)

    def test_missing_or_duplicate_initial_scan_refuses(self):
        rows=self.events()
        for changed in (rows[:1]+rows[2:],rows[:2]+[deepcopy(rows[1])]+rows[2:]):
            with self.assertRaisesRegex(ContractError,'initial-scans'):_clean_boundary(changed,self.order,self.original)

    def test_early_or_late_mutation_boundary_refuses(self):
        rows=self.events();changed=deepcopy(rows);changed[1],changed[4]=changed[4],changed[1]
        for value in (changed,rows+[dict(kind='later',payload={})],rows[:-1]):
            with self.assertRaises(ContractError):_clean_boundary(value,self.order,self.original)

    def test_changed_scan_manifest_order_or_snapshot_refuses(self):
        for index,key in ((0,'sha256'),(3,'work_order_sha256'),(4,'order_sha256'),(5,'initial_snapshot_sha256')):
            rows=self.events();rows[index]['payload'][key]='0'*64
            with self.subTest(index=index),self.assertRaisesRegex(ContractError,'clean-binding'):
                _clean_boundary(rows,self.order,self.original)

    def test_wrong_stopping_view_cannot_claim_intended_match(self):
        proposed=_stimulus_bytes(self.original,self.values);_replace_copied_bytes(self.worker,self.original,proposed)
        with self.assertRaisesRegex(ContractError,'intended-fragment'):
            _match_intended_fragment(self.assemble(),proposed,self.values,'unrelated native stopping view')

    def test_changed_truncated_or_missing_assembled_file_refuses(self):
        proposed=_stimulus_bytes(self.original,self.values);_replace_copied_bytes(self.worker,self.original,proposed)
        value=self.assemble()
        for mutate in (lambda v:v.update(allowed_files=[]),lambda v:v.update(semantic_memory={}),
                lambda v:v['allowed_files'][0].update(truncated=True),lambda v:v['allowed_files'][0].update(sha256='0'*64),
                lambda v:v['allowed_files'][0].update(bytes=True),lambda v:v['allowed_files'][0].update(content='other')):
            changed=deepcopy(value);mutate(changed)
            with self.assertRaises(ContractError):_match_intended_fragment(changed,proposed,self.values,_fragment(self.values))

    def test_changed_copy_and_repeat_write_refuse_without_overwrite(self):
        proposed=_stimulus_bytes(self.original,self.values);self.worker.write_bytes(b'changed')
        with self.assertRaisesRegex(ContractError,'changed-before-write'):_replace_copied_bytes(self.worker,self.original,proposed)
        self.assertEqual(self.worker.read_bytes(),b'changed')
        self.worker.write_bytes(self.original);_replace_copied_bytes(self.worker,self.original,proposed)
        with self.assertRaisesRegex(ContractError,'changed-before-write'):_replace_copied_bytes(self.worker,self.original,proposed)
        self.assertEqual(self.worker.read_bytes(),proposed)

    def test_oversize_write_refuses_before_changing_copy(self):
        with self.assertRaisesRegex(ContractError,'write-shape'):_replace_copied_bytes(self.worker,self.original,self.original+b'x'*20000)
        self.assertEqual(self.worker.read_bytes(),self.original)
