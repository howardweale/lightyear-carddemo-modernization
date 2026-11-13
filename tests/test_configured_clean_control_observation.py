"""Disposable clean-context components; never authenticated control evidence."""
from copy import deepcopy
from hashlib import sha256
import json,os,tempfile,unittest
from pathlib import Path
from lightyear_factory.contracts import ContractError,WorkOrder,canonical_hash
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.isolation_scan import scan
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_execution.configured_receipt_clean_control import (
    _describe_clean_context,record_original_clean_context,require_original_clean_context,WORKER,WORKER_SHA256)
import test_configured_receipt_scan_observation as fixtures

class CleanControlObservationComponents(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.source=Path(__file__).resolve().parents[1]
        self.order=WorkOrder.from_dict(json.loads((self.source/'docs/factory/p5-human-clean-control/configured-build-control/work-order.json').read_bytes()))
        self.original=(self.source/WORKER).read_bytes()
        self.temp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);worker=self.root/WORKER;worker.parent.mkdir(parents=True);worker.write_bytes(self.original)
        self.value=GraphContextAssembler(None,None).assemble(self.order,self.root)
        self.values=tuple(fixtures.PUBLIC+str(i) for i in range(3))
        self.result=scan([('controller-context',self.encode(self.value))],fixtures.CANARIES,self.values)

    def encode(self,value):return json.dumps(value,sort_keys=True,ensure_ascii=False).encode()
    def events(self):
        manifest={WORKER:WORKER_SHA256}
        return [dict(kind='workspace_read_manifest',payload=dict(files=manifest,sha256=canonical_hash(manifest))),
            dict(kind='model_isolation_scan_passed',payload={'scanned':[dict(artifact='initial-workspace-file',sha256=WORKER_SHA256)]}),
            dict(kind='model_isolation_scan_passed',payload={'scanned':[dict(artifact='approved-work-order',sha256=sha256(self.encode(self.order.to_dict())).hexdigest())]}),
            dict(kind='work_order_accepted',payload={'work_order_sha256':self.order.content_sha256}),
            dict(kind='candidate_controller_bound',payload={'order_sha256':self.order.content_sha256}),
            dict(kind='workspace_isolated',payload=dict(allowed_paths=[WORKER],initial_snapshot_sha256=canonical_hash(manifest))),
            dict(kind='model_isolation_scan_passed',payload=self.result)]

    def test_original_assembler_scanner_relationships_return_only_tuple(self):
        before=deepcopy(self.value);rows=self.events()
        value=_describe_clean_context(self.value,self.original,self.order,rows)
        self.assertEqual(value,(sha256(self.encode(self.value)).hexdigest(),len(self.encode(self.value)),WORKER_SHA256,self.order.content_sha256))
        self.assertEqual(self.value,before)

    def test_original_unadmitted_controller_cannot_record_observation(self):
        controller=FactoryOrchestrator(self.source,self.root/'runs',None)
        with self.assertRaisesRegex(ContractError,'same-process-origin-required'):
            record_original_clean_context(controller,self.order,self.root,self.value)

    def test_original_unadmitted_controller_cannot_claim_control(self):
        controller=FactoryOrchestrator(self.source,self.root/'runs',None)
        with self.assertRaisesRegex(ContractError,'same-process-origin-required'):
            require_original_clean_context(controller,self.events())

    def test_answer_case_cannot_substitute_for_control(self):
        order=WorkOrder.from_dict(dict(self.order.to_dict(),id='answer-fragment'))
        with self.assertRaisesRegex(ContractError,'control-order'):
            _describe_clean_context(self.value,self.original,order,self.events())

    def test_graph_memory_truncation_and_missing_worker_refuse(self):
        for key,value in (('graph_content_sha256','a'*64),('evidence_pack_sha256','b'*64),('semantic_memory',{}),('truncated',True),('allowed_files',[])):
            changed=deepcopy(self.value);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ContractError):_describe_clean_context(changed,self.original,self.order,self.events())

    def test_worker_content_path_size_digest_and_truncation_refuse(self):
        for key,value in (('content','different'),('path','other.py'),('bytes',True),('sha256','f'*64),('truncated',True)):
            changed=deepcopy(self.value);changed['allowed_files'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ContractError,'context-worker'):_describe_clean_context(changed,self.original,self.order,self.events())

    def test_missing_duplicate_or_late_context_scan_refuses(self):
        rows=self.events()
        for changed in (rows[:-1],rows+[deepcopy(rows[-1])],rows+[dict(kind='model_call_reserved',payload={})]):
            with self.assertRaises(ContractError):_describe_clean_context(self.value,self.original,self.order,changed)

    def test_failed_wrong_digest_surface_or_normalization_refuses(self):
        for key,value in (('status','failed'),('scanned',[dict(artifact='controller-context',sha256='a'*64)]),('scanned',[dict(artifact='other',sha256=sha256(self.encode(self.value)).hexdigest())]),('normalization','other'),('expected_window_count',False)):
            rows=deepcopy(self.events());rows[-1]['payload'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ContractError,'original-scan-row'):_describe_clean_context(self.value,self.original,self.order,rows)

    def test_modified_public_worker_refuses_even_rehashed_context(self):
        original=self.original+b'\n#changed\n'
        with self.assertRaisesRegex(ContractError,'original-worker'):_describe_clean_context(self.value,original,self.order,self.events())

    def test_native_scanner_refuses_contamination_before_clean_descriptor(self):
        changed=deepcopy(self.value);changed['allowed_files'][0]['content']+=self.values[0]
        with self.assertRaisesRegex(ContractError,'isolation-breach'):
            scan([('controller-context',self.encode(changed))],fixtures.CANARIES,self.values)
