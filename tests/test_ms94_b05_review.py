import copy,tempfile,unittest
from contextlib import ExitStack
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import Mock,patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from lightyear_workflow.campaign_engine import Signer
from lightyear_calibration.contracts import CalibrationError,seal,read_json
from lightyear_calibration.journey_order import save
from tools.ms94_b05_review import review_reasons,validate_decision,write_decision,wait_for_review,require_review_clear,summarize_trial,verify_trial_review,REVIEW
from tools.ms94_b05_stops import IMMEDIATE,record_failure
from tools.ms94_b05_admission import CAMPAIGN,CONFIG,APPROVED

class ReviewTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.signer=object.__new__(Signer);self.signer.key=Ed25519PrivateKey.generate()
  self.signer.public=self.signer.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
  key=self.root/'work/ms87/operator/authority.public.pem';key.parent.mkdir(parents=True);key.write_bytes(self.signer.public)
  self.trial=self.root/CAMPAIGN/'trials/cohort-01';self.trial.mkdir(parents=True)
  save(self.root/'execution-snapshot.json',seal({'fixture':True}))
  save(self.root/CONFIG/'campaign.json',seal({'slots':[{'path':self.trial.relative_to(self.root).as_posix(),'plan_sha256':'p'}]}))
  save(self.root/APPROVED/'amendment-r2/amendment.json',seal({'fixture':True}))
  self.receipt=self.signer.sign({'status':'halted-equipment-suspect','plan_sha256':'p','attempts':[]})
  save(self.trial/'receipt.json',self.receipt);save(self.trial/'supervision-receipt.json',self.signer.sign({'complete':True}))
  self.stack=ExitStack();self.addCleanup(self.stack.close)
  for module in ('review','stops'):self.stack.enter_context(patch('tools.ms94_b05_'+module+'.JourneySigner',return_value=self.signer))
 def test_same_trial_attempts_never_match(self):
  self.assertEqual(review_reasons('a','business-failure',['x','x'],[{'trial_directory':'a','fingerprints':['x']}]),([],[]))
 def test_cross_trial_repeat_pauses(self):
  self.assertEqual(review_reasons('b','business-failure',['x','x'],[{'trial_directory':'a','fingerprints':['x','x']}]),(['repeated-cause-across-trials'],['x']))
 def test_equipment_suspect_pauses_but_is_not_hard_stop(self):
  self.assertNotIn('halted-equipment-suspect',IMMEDIATE)
  self.assertEqual(review_reasons('b','halted-equipment-suspect',[],[]),(['equipment-suspect'],[]))
 def test_trial_summary_unions_attempts_and_preserves_verdict(self):
  for n in ('one','two'):
   run=self.root/'work/native'/n;gate=seal({'status':'business-failure','error':{'type':'BusinessViolation','message':'same candidate mistake'}})
   save(run/'gate.json',gate);save(run/'diagnostic-projection.json',{'diagnostics':[]});record_failure(self.root,self.trial,run,gate,[])
  self.receipt=self.signer.sign({'status':'halted-no-supported-repair','plan_sha256':'p','attempts':[]});save(self.trial/'receipt.json',self.receipt)
  summary=summarize_trial(self.root,self.trial,self.receipt)
  self.assertEqual(len(summary['fingerprints']),1);self.assertFalse(summary['review_required'])
  self.assertEqual(verify_trial_review(self.root,self.trial,self.signer.public),summary)
  self.assertEqual(read_json(self.trial/'receipt.json'),self.receipt)
 def decide_after_wait(self,action):
  summarize_trial(self.root,self.trial,self.receipt)
  called=[]
  def on_sleep(seconds):
   called.append(seconds)
   with self.assertRaises((CalibrationError,FileNotFoundError)):require_review_clear(self.root)
   write_decision(self.root,self.root/CAMPAIGN/'reviews/cohort-01/pause.json',action,'Reviewed fixture evidence','Explicit fixture approval')
  with patch('tools.ms94_b05_review.time.sleep',side_effect=on_sleep),patch('tools.ms94_b05_admission.bindings'):
   resolution=wait_for_review(self.root,self.trial,0,10**20)
  self.assertEqual(called,[5]);self.assertEqual(read_json(self.trial/'receipt.json'),self.receipt)
  self.assertFalse((self.root/CAMPAIGN/'stopping.json').exists())
  return resolution
 def test_signed_continue_releases_next_slot_only_after_decision(self):
  self.assertEqual(self.decide_after_wait('continue')['action'],'continue');require_review_clear(self.root)
 def test_signed_void_does_not_release_next_slot(self):
  self.assertEqual(self.decide_after_wait('void')['action'],'void')
  with self.assertRaises(CalibrationError):require_review_clear(self.root)
 def test_signed_stop_does_not_release_next_slot(self):
  self.assertEqual(self.decide_after_wait('stop')['action'],'stop')
  with self.assertRaises(CalibrationError):require_review_clear(self.root)
 def test_forged_or_misbound_decisions_fail(self):
  self.decide_after_wait('continue');folder=self.root/CAMPAIGN/'reviews/cohort-01'
  original=read_json(folder/'decision.json');pause=read_json(folder/'pause.json')
  for field,value in [('action','retry'),('reason',''),('pause_sha256','wrong'),('snapshot_sha256','wrong'),('trial_receipt_sha256','wrong'),('amendment_sha256','wrong'),('verdict_changed',True),('review','independent')]:
   body={k:v for k,v in original.items() if k not in ('signature','content_sha256')};body[field]=value
   with self.subTest(field=field),self.assertRaises(CalibrationError):validate_decision(self.signer.sign(body),pause,self.signer.public)
  forged=copy.deepcopy(original);forged['reason']='altered'
  with self.assertRaises(CalibrationError):validate_decision(forged,pause,self.signer.public)
 def test_hard_stop_cannot_be_overridden(self):
  summarize_trial(self.root,self.trial,self.receipt);save(self.root/CAMPAIGN/'stopping.json',{'hard':True})
  with self.assertRaises(CalibrationError):wait_for_review(self.root,self.trial,0,10**20)
 def test_campaign_deadline_bounds_operator_wait(self):
  summarize_trial(self.root,self.trial,self.receipt)
  with self.assertRaises(CalibrationError):wait_for_review(self.root,self.trial,0,0)
 def test_changed_verdict_prevents_continue(self):
  self.decide_after_wait('continue');save(self.trial/'receipt.json',self.signer.sign({'changed':True}))
  with self.assertRaises(CalibrationError):require_review_clear(self.root)
 def test_decision_cannot_be_replaced(self):
  self.decide_after_wait('continue')
  with self.assertRaises(CalibrationError):write_decision(self.root,self.root/CAMPAIGN/'reviews/cohort-01/pause.json','continue','reason','approval')

class CampaignReviewTests(unittest.TestCase):
 def campaign(self,actions,status='halted-no-supported-repair'):
  from tools.ms94_b05_measure import run
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);output=root/CAMPAIGN
   slots=[{'phase':'pilot' if i<3 else 'cohort','index':i+1,'path':(CAMPAIGN/'trials'/str(i)).as_posix(),'plan_sha256':'p'} for i in range(23)]
   plan=seal({'slots':slots,'max_elapsed_seconds':93600,'max_client_invocations':115,'max_compilations':69,'first_attempt_comparison':{}})
   save(output/'plan.json',plan);save(root/CONFIG/'campaign.json',plan)
   for slot in slots:save(root/slot['path']/'supervision-receipt.json',{'content_sha256':'s','total_elapsed_seconds':1})
   metrics={k:0 for k in ('repair_conversion_eligible','execution_failures','execution_failures_with_diagnostic_sent','execution_failures_with_diagnostic_exported','post_repair_business_failures')}
   result=seal({'status':status,'first_try_pass':False,'repaired_pass':False,'attempts':[],'cost':{'client_invocations':0,'compilations':0,'usage_complete':True},'metrics':metrics})
   signer=Mock();signer.sign.side_effect=seal
   decisions=[dict(action=a,waiting_seconds=1,verdict_changed=False,review=REVIEW) for a in actions]
   with patch('tools.ms94_b05_admission.model_authorization'),patch('tools.ms94_b05_measure.JourneySigner',return_value=signer),patch('tools.ms94_b05_stops.JourneySigner',return_value=signer),patch('tools.ms94_b05_measure.controller.frozen',return_value={'content_sha256':'p'}),patch('tools.ms94_b05_supervisor.run_unit',return_value={'result':result}) as unit,patch('tools.ms94_b05_review.wait_for_review',side_effect=decisions) as wait:
    report=run(root,output,root/'unused-executable');calls=[c.args[1].relative_to(root).as_posix() for c in unit.call_args_list]
   return report,calls,wait.call_count
 def test_continue_advances_exact_next_fresh_slot_then_void(self):
  report,calls,waits=self.campaign(['continue','void'])
  self.assertEqual(calls,[(CAMPAIGN/'trials/0').as_posix(),(CAMPAIGN/'trials/1').as_posix()]);self.assertEqual(waits,2)
  self.assertTrue(report['cohort_void']);self.assertIsNone(report['rate']);self.assertEqual(report['unstarted_slots'],21)
  self.assertEqual([r['status'] for r in report['results']],['halted-no-supported-repair']*2)
 def test_equipment_suspect_pauses_and_operator_stop_preserves_nonvoid_incomplete(self):
  report,calls,waits=self.campaign(['stop'],'halted-equipment-suspect')
  self.assertEqual(len(calls),1);self.assertEqual(waits,1);self.assertFalse(report['cohort_void']);self.assertIsNone(report['rate'])
 def test_deadline_is_immediate_void_without_operator_wait(self):
  report,calls,waits=self.campaign([],'halted-trial-deadline')
  self.assertEqual(len(calls),1);self.assertEqual(waits,0);self.assertTrue(report['cohort_void'])

if __name__=='__main__':unittest.main()
