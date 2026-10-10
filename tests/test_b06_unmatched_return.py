import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.ms94_b06_unmatched_return import POLICY, SPEC, SCOPE, enabled, validate_event
from tools.ms94_b06_group_decision import request
from tools.ms94_b06_posting_replay import replay_stream
from tools.ms94_b06_posting_broker import PostingBroker
from lightyear_calibration.contracts import seal

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/b06-generation-prefix/diagnostic-r1.json'

class DiagnosticTests(unittest.TestCase):
    def test_opt_in_is_exact_and_normal_replay_refuses(self):
        self.assertFalse(enabled({}))
        spec=dict(observer_binding_v2={'policy':'observer-binding-v2'},unmatched_return=copy.deepcopy(SPEC))
        self.assertTrue(enabled(spec))
        spec['unmatched_return']['qualification_credit']=True
        with self.assertRaises(ValueError):enabled(spec)
        with self.assertRaisesRegex(ValueError,'diagnostic-not-admissible'):
            replay_stream(Path('does-not-exist'),{'diagnostic_only':True},{},'oracle')

    def test_scope_and_one_window_review_exception_are_bound(self):
        body=dict(purpose='observer-native-practice',journey='J1',slot_count=1,qualification_credit=False,
            measurement_authorized=False,model_calls=0,snapshot_sha256='a'*64,diagnostic_scope=copy.deepcopy(SCOPE),
            docker_run_window=dict(not_before_utc='2026-10-10T17:30:00Z',deadline_utc='2026-10-10T20:30:00Z'))
        r,_,_=request(seal(body),'b'*40);self.assertIn('every other anomaly stops',r['summary'])
        for key,value in [('qualification_credit',True),('stop_at_first_other_anomaly',False),('automatic_retry',True)]:
            bad=copy.deepcopy(body);bad['diagnostic_scope'][key]=value
            with self.assertRaises(ValueError):request(seal(bad),'b'*40)
        body['docker_run_window']['deadline_utc']='2026-10-10T21:30:00Z'
        with self.assertRaises(ValueError):request(seal(body),'b'*40)

    def test_signed_diagnostic_fields_never_assert_complete_observation(self):
        broker=object.__new__(PostingBroker);broker.diagnostic_unmatched=True;broker.failure=None;broker.unmatched_returns=[231090]
        r=broker.diagnostic_result()
        self.assertFalse(r['observation_complete']);self.assertEqual(r['diagnostic_outcome'],'indeterminate')
        self.assertFalse(r['qualification_credit']);self.assertFalse(r['measurement_credit'])

    def test_anomaly_matches_pre_dispatch_context_and_cannot_swallow_other_failures(self):
        f=json.loads(FIXTURE.read_bytes());d=copy.deepcopy(f['thread_events'][-1]['detail']);d['thread_id']=f['thread']
        prior=dict(kind='observer-audit',action='jdi-event',detail=d);loc=d['location']
        event=dict(kind='diagnostic-unmatched-return',policy=POLICY,checkpoint=False,observation_complete=False,
            provenance_created=False,context=dict(thread_id=f['thread'],depth=d['depth'],code_index=loc['code_index'],
                method=loc['class']+'.'+loc['method']+loc['signature']))
        validate_event(event,prior)
        for key,value in [('pending',[{'generation_id':1}]),('arm',{}),('selected_generation',False),('top_location',{}),('return_breakpoint',False)]:
            bad=copy.deepcopy(prior);bad['detail'][key]=value
            with self.assertRaises(ValueError):validate_event(event,bad)
        event['context']['depth']+=1
        with self.assertRaises(ValueError):validate_event(event,prior)

@unittest.skipUnless(os.environ.get('B06_HOST_JDK'),'host JDK explicitly enabled')
class DiagnosticHostTests(unittest.TestCase):
    def test_captured_operands_continue_without_creating_activation(self):
        f=json.loads(FIXTURE.read_bytes());d=f['thread_events'][-1]['detail'];loc=d['location'];jdk=Path(os.environ['B06_HOST_JDK'])
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([str(jdk/'bin/javac.exe'),'--add-modules','jdk.jdi','-d',tmp,
                str(ROOT/'factory/idempiere/b06-observer/PostingObserver.java'),str(ROOT/'tools/b06_host_probe/CapturedReturnProbe.java')],check=True,capture_output=True,timeout=60)
            result=subprocess.run([str(jdk/'bin/java.exe'),'--add-modules','jdk.jdi','-cp',tmp,'CapturedReturnProbe',loc['class'],loc['method'],loc['signature'],str(f['thread']),str(d['depth']),str(loc['code_index']),'diagnostic'],check=True,capture_output=True,text=True,timeout=30)
        event=json.loads(result.stdout);self.assertEqual(event['kind'],'diagnostic-unmatched-return')
        self.assertFalse(event['provenance_created']);self.assertFalse(event['observation_complete'])

    def test_real_host_jdi_collection_continues_after_missing_outer_entry(self):
        from test_b06_observer_audit import host_capture
        from tools.ms94_b06_observer_audit import Audit
        jdk=Path(os.environ['B06_HOST_JDK']);source=(ROOT/'factory/idempiere/b06-observer/PostingObserver.java').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            observed,events,_=host_capture(jdk/'bin/java.exe',jdk/'bin/javac.exe',source,Path(tmp)/'probe',diagnostic=True)
        self.assertEqual(observed.returncode,0,observed.stderr)
        self.assertEqual(events[-1]['kind'],'vm-death')
        anomalies=[(i,e) for i,e in enumerate(events) if e['kind']=='diagnostic-unmatched-return']
        self.assertGreaterEqual(len(anomalies),40)
        for i,e in anomalies:validate_event(e,events[i-1])
        audit=Audit()
        for e in events:
            if e['kind']=='observer-audit':audit.event(e)
        audit.complete()
        # Seal a test-only two-lane archive from the actual host stream. Verify
        # diagnostic authentication and tamper rejection without native claims.
        from tests.test_ms94_a3_entry_v2 import test_signer
        from tools.ms94_b06_forwarding_stub import receipt_records
        from tools.ms94_b06_observer_v2 import commitments
        from tools.ms94_b06_qualification_replay import incomplete_equipment
        from lightyear_calibration.contracts import canonical
        from unittest.mock import patch
        signer=test_signer();plan=seal(dict(posting_observer=dict(observer_binding_v2={'policy':'observer-binding-v2'},unmatched_return=SPEC)))
        native=dict(status='diagnostic-only',equipment_suspect=True,diagnostic_only=True,qualification_credit=False,
            measurement_credit=False,error=dict(kind='diagnostic-only',exception_type='DiagnosticOnly',closed_reason='observer-diagnostic-not-admissible'),
            runtime_delivery_sha256=None,gate_sha256=None,execution_sha256={})
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);records=[];previous=None
            for e in events:
                item=seal(dict(event=e,previous_sha256=previous,readback_sha256=None));records.append(item);previous=item['content_sha256']
            raw=b''.join(canonical(r)+b'\n' for r in records)
            for lane in ('oracle','postgresql'):
                folder=run/'posting-observer'/lane;folder.mkdir(parents=True)
                (folder/'events.jsonl').write_bytes(raw)
                execution=seal({'test_only_lane':lane});native['execution_sha256'][lane]=execution['content_sha256']
                ex=run/'cases/operations/1/execution'/lane;ex.mkdir(parents=True);(ex/'execution.json').write_bytes(canonical(execution))
                broker=object.__new__(PostingBroker);broker.diagnostic_unmatched=True;broker.failure=None;broker.unmatched_returns=[e['sequence'] for _,e in anomalies]
                census=dict(plan_sha256=plan['content_sha256'],lane=lane,model_calls=0,native_qualification=False,
                    complete=True,event_count=len(records),last_event_sha256=previous,event_file_sha256=hashlib.sha256(raw).hexdigest(),
                    frame_records=receipt_records(records),v2_records=commitments(records),**broker.diagnostic_result())
                (folder/'frame-census.json').write_bytes(canonical(signer.sign(census)))
                (folder/'receipt.json').write_bytes(canonical(signer.sign({**census,'execution_sha256':execution['content_sha256']})))
            with patch('tools.ms94_b06_qualification_replay.replay_clocks') as clocks:
                result=incomplete_equipment(run,plan,native,signer.public);clocks.assert_called_once()
                self.assertTrue(result['diagnostic_capture_audited']);self.assertEqual(result['diagnostic_outcome'],'indeterminate')
                self.assertFalse(result['equipment_failure_audited']);self.assertFalse(result['qualification_credit'])
                self.assertNotIn('observer_replayed',result)
                census['observation_complete']=True
                (folder/'frame-census.json').write_bytes(canonical(signer.sign(census)))
                with self.assertRaisesRegex(ValueError,'disposition-binding'):incomplete_equipment(run,plan,native,signer.public)

if __name__=='__main__':unittest.main()
