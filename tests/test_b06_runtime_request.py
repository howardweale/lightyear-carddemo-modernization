"""Real Tower inbox/envelope checks; no Docker or model calls."""
import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from lightyear_calibration.contracts import seal
from lightyear_control_tower.requests import RequestInbox
from lightyear_control_tower.kinds import default_registry
from lightyear_control_tower.verification import verify_decision
from tools.b06_image_artifacts import runtime_launch as launch
from test_b06_image_artifacts import test_signer,proof

class RuntimeRequestTests(unittest.TestCase):
 def plan(self):
  return seal(dict(id='b06-runtime-closure-r4',maximum_runtime_seconds=2700,snapshot_sha256='a'*64,
    window=dict(not_before_utc='2026-10-08T16:15:00+00:00',latest_start_utc='2026-10-08T16:20:00+00:00',deadline_utc='2026-10-08T17:15:00+00:00')))
 def test_live_inbox_and_reader_bind_same_request_envelope(self):
  with tempfile.TemporaryDirectory() as tmp:
   plan=self.plan();identifier,bound=launch.write_request(tmp,plan,'b'*40)
   item=RequestInbox(Path(tmp),'ms94-b06',default_registry()).item(identifier)
   self.assertEqual(item['bound'],bound);self.assertEqual(launch.bound(plan,'b'*40),bound)
   signer=test_signer();now=datetime.now(timezone.utc);decision=proof(signer,bound,now)
   verify_decision(decision,signer.public,'campaign-authorization',bound,scope='ms94-b06',outcomes={'authorized'},expected_head=decision['journal']['journal_head_sha256'],now=now)
   changed=dict(bound,request='c'*64)
   with self.assertRaises(Exception):verify_decision(decision,signer.public,'campaign-authorization',changed,scope='ms94-b06',outcomes={'authorized'},expected_head=decision['journal']['journal_head_sha256'],now=now)
 def test_commit_window_and_request_are_deterministic_and_bound(self):
  p=self.plan();a=launch.bound(p,'b'*40);self.assertEqual(a,launch.bound(p,'b'*40));self.assertNotEqual(a,launch.bound(p,'c'*40))
  raw={k:v for k,v in p.items() if k!='content_sha256'};raw['window']={**raw['window'],'latest_start_utc':'2026-10-08T16:19:00+00:00'}
  self.assertNotEqual(a,launch.bound(seal(raw),'b'*40))
