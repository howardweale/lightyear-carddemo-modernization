"""Offline failure preservation and handler activation tests; no native credit."""
import copy, hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import canonical, seal
from tools.ms94_b06_generation_catch import validate_unwind
from tools.ms94_b06_qualification_replay import incomplete_equipment
from tests.test_ms94_a3_entry_v2 import test_signer

class CatchProofTests(unittest.TestCase):
    def test_observed_handler_depth_and_history(self):
        event={'record':{'thread_id':7,'entry_depth':8},'catch_depth':3,'exception_class':'X',
               'catch_resolution':{'kind':'handler-breakpoint','thread_id':7,'frame_count':3,
                'location':{'class':'Fixture','method':'recurse','signature':'()V','code_index':21}}}
        validate_unwind(event,True)
        for field,value in [('thread_id',8),('frame_count',4),('kind','first-method-match')]:
            bad=copy.deepcopy(event);bad['catch_resolution'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_unwind(bad,True)
        old={k:v for k,v in event.items() if k!='catch_resolution'}
        validate_unwind(old)
        with self.assertRaisesRegex(ValueError,'proof-missing'):validate_unwind(old,True)
        uncaught={**old,'catch_depth':-1,'catch_resolution':{'kind':'uncaught','thread_id':7,'frame_count':0}}
        validate_unwind(uncaught,True)
        bad=copy.deepcopy(event);bad['catch_resolution']['location']['code_index']=-1
        with self.assertRaises(ValueError):validate_unwind(bad,True)

class PartialAuditTests(unittest.TestCase):
    def fixture(self,tmp):
        from tools.ms94_b06_forwarding_stub import receipt_records
        signer=test_signer();run=Path(tmp);folder=run/'posting-observer/oracle';folder.mkdir(parents=True)
        plan=seal({'posting_observer':{}})
        receipt={'status':'equipment-failure','equipment_suspect':True,'error':{'kind':'equipment-failure'},
                 'runtime_delivery_sha256':None,'gate_sha256':None}
        event=seal({'previous_sha256':None,'event':{'sequence':1,'kind':'ready','checkpoint':False},'readback_sha256':None})
        raw=canonical(event)+b'\n';(folder/'events.jsonl').write_bytes(raw)
        census={'plan_sha256':plan['content_sha256'],'lane':'oracle','model_calls':0,'native_qualification':False,
                'event_file_sha256':hashlib.sha256(raw).hexdigest(),'event_count':1,'last_event_sha256':event['content_sha256'],
                'frame_records':receipt_records([event]),'complete':False}
        failure={k:census[k] for k in ('plan_sha256','lane','event_count','last_event_sha256','complete')}
        (folder/'frame-census.json').write_bytes(canonical(signer.sign(census)))
        (folder/'failure.json').write_bytes(canonical(signer.sign(failure)))
        return run,plan,receipt,signer,folder

    def test_missing_clocks_audited_without_claiming_complete_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            run,plan,receipt,signer,folder=self.fixture(tmp)
            result=incomplete_equipment(run,plan,receipt,signer.public)
            self.assertTrue(result['equipment_failure_audited']);self.assertTrue(result['partial_evidence'])
            self.assertIn('b06-clock-evidence.json',result['missing_artifacts'])
            self.assertEqual(1,result['collector_prefixes'][0]['event_count'])
            self.assertNotIn('observer_replayed',result)
            self.assertFalse((run/'b06-clock-evidence.json').exists())
            (folder/'events.jsonl').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'event-bytes'):incomplete_equipment(run,plan,receipt,signer.public)

    def test_wrong_plan_missing_failure_and_feedback_refused(self):
        for mode in ('wrong-plan','missing-failure','feedback','candidate-result'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                run,plan,receipt,signer,folder=self.fixture(tmp)
                if mode=='wrong-plan':plan=seal({'different':True})
                if mode=='missing-failure':(folder/'failure.json').unlink()
                if mode=='feedback':(run/'zero-model-builder-inbox.json').write_text('{}')
                if mode=='candidate-result':receipt['status']='execution-failure'
                with self.assertRaises(ValueError):incomplete_equipment(run,plan,receipt,signer.public)
