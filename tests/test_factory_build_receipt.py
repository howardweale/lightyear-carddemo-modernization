"""CI-only receipt joins using synthetic evidence; no signature or model proof."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from lightyear_factory.build_receipt import compute_build_receipt
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.ledger import RunLedger


class ComputedBuildReceiptTests(unittest.TestCase):
    def fixture(self, root):
        ledger=RunLedger(root/'events.jsonl');run_id='fixture-run'
        order=SimpleNamespace(content_sha256='a'*64,max_attempts=3,max_model_calls=4,
            max_model_input_bytes=10000,max_model_output_bytes=10000,max_model_tokens=1000,
            max_model_cost_usd=1,max_elapsed_seconds=60)
        runtime=dict(schema='factory-model-admission/1',work_order_sha256=order.content_sha256,
            plan_sha256='b'*64,decision_sha256='c'*64,executable_commit='d'*40,provider_verified=False)
        scans=[];calls=[];sequence=0
        def artifact(role,kind):
            nonlocal sequence
            sequence+=1;raw=(role+' '+kind).encode();cipher=b'synthetic fixture ciphertext'
            context=dict(run_id=run_id,role=role,plaintext_sha256=hashlib.sha256(raw).hexdigest())
            envelope={'context':context,'ciphertext_base64':base64.b64encode(cipher).decode()}
            encoded=json.dumps(envelope).encode();path='artifacts/'+str(sequence)+'-model-'+kind+'.encrypted.json'
            (root/'artifacts').mkdir(exist_ok=True);(root/path).write_bytes(encoded)
            scans.append({'artifact':role+'-wire-'+('request' if kind=='request' else 'response'),'sha256':context['plaintext_sha256']})
            return dict(context,path=path,artifact_sha256=hashlib.sha256(encoded).hexdigest(),ciphertext_sha256=hashlib.sha256(cipher).hexdigest())
        for role in ('planner','builder'):
            approval=dict(runtime,provider_verified=True,role=role,provider='fixture',model='fixture-2026-10-18')
            admitted=ledger.append('RUNNING','model_call_admitted',dict(run_id=run_id,attempt=1,role=role,
                provider='fixture',model='fixture-2026-10-18',approval=approval))
            start=dict(run_id=run_id,attempt=1,role=role,requested_role=role,provider='fixture',
                configured_model_version='fixture-2026-10-18',admission_event_sha256=admitted['event_sha256'],request=artifact(role,'request'))
            begun=ledger.append('RUNNING','model-transport-started',start)
            finish=dict(start,start_event_sha256=begun['event_sha256'],response=artifact(role,'response'),response_complete=True,status='response')
            ended=ledger.append('RUNNING','model-transport-finished',finish)
            call=dict(provider='fixture',model='fixture-2026-10-18',role=role,input_tokens=3,output_tokens=2,
                estimated_cost_usd=0.01,transport_record=dict(finish,end_event_sha256=ended['event_sha256']))
            call['content_sha256']=canonical_hash(call);calls.append(call)
        for name in ('controller-context','initial-workspace','builder-workspace','patched-workspace','pre-gate-workspace','post-gate-workspace','final-candidate-package'):
            scans.append({'artifact':name,'sha256':'0'*64})
        ledger.append('RUNNING','model_isolation_scan_passed',dict(status='passed',expected_window_count=10,
            canary_classes=['expected-state','reference-output','session-answer'],scanned=scans))
        audit=dict(candidate_commit='e'*40,cryptographically_verified=True,qualifies_for_factory_receipt=True,final_package_tree_sha256='f'*64)
        audit['content_sha256']=canonical_hash(audit);ledger.append('VERIFYING','candidate_authorship_audited',audit)
        package=dict(schema='factory-candidate-package-finalization/1',run_id=run_id,candidate_commit='e'*40,
            current_authorship_audit_sha256=audit['content_sha256'],tree_sha256='f'*64)
        package['content_sha256']=canonical_hash(package);ledger.append('VERIFYING','candidate_package_finalized',package)
        ledger.append('PASSED','acceptance_gates_passed',{'attempt':1})
        security=dict(production_ready=True,status='enforced',work_order_sha256=order.content_sha256,
            gate_execution_sha256=['1'*64],secrets_persisted=False)
        security['content_sha256']=canonical_hash(security)
        intelligence=dict(calls=2,call_evidence_sha256=[c['content_sha256'] for c in calls],cost_estimate_available=True,
            input_bytes=20,output_bytes=20,input_tokens=6,output_tokens=4,estimated_cost_usd=0.02,elapsed_ms=1)
        receipt=dict(run_id=run_id,work_order_sha256=order.content_sha256,status='passed',attempts=1,repair_loops=0,
            verification={'status':'passed','gates':[{'status':'passed'}]},execution_security=security,
            candidate_package_finalization=package,intelligence=intelligence)
        return order,ledger,receipt,calls,runtime

    def test_computed_join_and_missing_proof_or_budget_refuse_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);order,ledger,receipt,calls,runtime=self.fixture(root)
            result=compute_build_receipt(order,ledger,receipt,calls,runtime,root)
            self.assertTrue(result['qualifies_for_factory_receipt'])
            self.assertEqual([],result['reasons'])
            self.assertEqual(ledger.head_sha256,result['ledger_prefix_sha256'])
            self.assertEqual(4,len(result['encrypted_artifact_sha256']))
            for key,value in [('attempts',4),('repair_loops',3),('status','blocked'),('candidate_package_finalization',{})]:
                changed=copy.deepcopy(receipt);changed[key]=value
                with self.subTest(key=key):
                    self.assertFalse(compute_build_receipt(order,ledger,changed,calls,runtime,root)['qualifies_for_factory_receipt'])
            changed=copy.deepcopy(receipt);changed['intelligence']['input_tokens']=9999
            self.assertFalse(compute_build_receipt(order,ledger,changed,calls,runtime,root)['qualifies_for_factory_receipt'])
            changed=copy.deepcopy(calls);changed[0]['transport_record']['end_event_sha256']='0'*64
            self.assertFalse(compute_build_receipt(order,ledger,receipt,changed,runtime,root)['qualifies_for_factory_receipt'])

    def test_encrypted_artifact_and_persisted_ledger_tamper_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);order,ledger,receipt,calls,runtime=self.fixture(root)
            target=root/calls[0]['transport_record']['request']['path'];original=target.read_bytes()
            target.write_bytes(original+b' ')
            result=compute_build_receipt(order,ledger,receipt,calls,runtime,root)
            self.assertIn('encrypted-artifact-digest',result['reasons'])
            target.write_bytes(original)
            ledger.path.write_text(ledger.path.read_text().replace('fixture-run','changed-run',1))
            with self.assertRaisesRegex(ContractError,'^factory-build-receipt-refused$'):
                compute_build_receipt(order,ledger,receipt,calls,runtime,root)
