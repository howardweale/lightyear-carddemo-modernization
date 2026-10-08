import copy,hashlib,tempfile,unittest
from pathlib import Path
from tools.b06_image_artifacts.frozen_runtime import application_review
from tools.b06_image_artifacts.runtime_launch import HISTORY_AMENDMENT,historical_policy,request
from lightyear_calibration.contracts import seal
from test_b06_application_identity import jar

class HistoryAmendmentTests(unittest.TestCase):
 def policy(self):
  return dict(schema='b06-runtime-closure-plan/3',historical_content_required=False,historical_content_amendment=copy.deepcopy(HISTORY_AMENDMENT))
 def captures(self,root):
  (root/'runtime-application').mkdir()
  obs=dict(schema='b06-runtime-launch-observation/4',install_area='file:/application/test',bundles=[])
  for i in range(44):
   n='app.bundle'+str(i);raw=jar(symbolic=n);p=root/'runtime-application'/f'{i+1}.jar';p.write_bytes(raw)
   obs['bundles'].append(dict(id=i+1,symbolic_name=n,version='1.2.3.one',location=f'file:/application/{n}.jar',application_copy=dict(path=f'/results/runtime-application/{i+1}.jar',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),kind='jar')))
  return obs
 def test_no_history_needed_but_missing_or_tampered_current_copy_refused(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);obs=self.captures(root)
   result=application_review(root,self.policy(),root/'no-historical-directory',obs)
   self.assertTrue(result['passed']);self.assertEqual(len(result['captures']),44);self.assertEqual(result['comparisons'],[])
   p=root/'runtime-application/1.jar';raw=p.read_bytes();p.write_bytes(raw+b'changed')
   with self.assertRaisesRegex(ValueError,'application-copy-bytes'):application_review(root,self.policy(),root,obs)
   p.unlink()
   with self.assertRaisesRegex(ValueError,'application-copy-missing'):application_review(root,self.policy(),root,obs)
 def test_old_schema_cannot_bypass_history_with_new_flag(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);obs=self.captures(root);plan={**self.policy(),'schema':'b06-runtime-closure-plan/2'}
   self.assertTrue(historical_policy(plan))
   with self.assertRaises(FileNotFoundError):application_review(root,plan,root,obs)
 def test_amendment_is_required_exact_and_not_generic_bypass(self):
  for change in ({'historical_content_required':True},{'historical_content_amendment':{}},{'historical_content_sha256':'a'*64}):
   with self.subTest(change=change),self.assertRaises(ValueError):historical_policy({**self.policy(),**change})
 def test_tower_request_binds_new_policy_and_current_check(self):
  plan=seal({**self.policy(),'id':'b06-runtime-fidelity-r11','source_commit':'1'*40,'snapshot_sha256':'2'*64,'maximum_runtime_seconds':2700,'cleanup_reserve_seconds':600,'window':None})
  checks=dict(passed=True,application_content_basis='current-capture-validation',checks={k:True for k in ('census','source_only','application_content','tycho','warning_baseline','frozen_bytes','cleanup')},source_commit=plan['source_commit'],snapshot_sha256=plan['snapshot_sha256'],plan_sha256=plan['content_sha256'])
  window=dict(not_before_utc='2026-10-09T10:00:00Z',latest_start_utc='2026-10-09T10:05:00Z',deadline_utc='2026-10-09T11:00:00Z')
  _,_,artifacts=request(plan,'3'*40,window=window,practice=checks)
  self.assertEqual(artifacts['plan']['historical_content_amendment'],HISTORY_AMENDMENT)
  checks.pop('application_content_basis')
  with self.assertRaisesRegex(ValueError,'current-capture-check-required'):request(plan,'3'*40,window=window,practice=checks)
