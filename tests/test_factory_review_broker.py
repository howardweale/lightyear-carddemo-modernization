import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from lightyear_factory.posttran_broker import request,dispatch
from lightyear_control_tower.decisions import digest
from lightyear_mainframe.legacy_twin import ROOT

class RevisedBrokerTests(unittest.TestCase):
 def test_exact_revision_required_and_server_cap_includes_reasoning(self):
  plan=json.loads((ROOT/'docs/factory/posttran-second-opinion/revised-plan.json').read_text())
  packet={p:(ROOT/p).read_bytes() for p in plan['inputs']};packet['phase1-work-order.md']=(ROOT/'docs/factory/posttran-second-opinion/phase1-work-order.md').read_bytes()
  with tempfile.TemporaryDirectory() as d:
   executable=Path(d)/'fake-client';executable.write_bytes(b'offline-test-only')
   plan['client']['sha256']=hashlib.sha256(executable.read_bytes()).hexdigest();plan.pop('content_sha256');plan['content_sha256']=digest(plan)
   approval=dict(plan_sha256=plan['content_sha256'],approved_phase=1,approved_limits=plan['phases']['1'],human_answer='Approve Phase 1 budget')
   payload=request(plan,approval,executable,packet,attempt=1)
   self.assertEqual(64000,payload['max_output_tokens']);self.assertEqual({'effort':'high'},payload['reasoning'])
   old={**approval,'plan_sha256':plan['supersedes_plan_sha256']}
   with self.assertRaisesRegex(ValueError,'approval'):request(plan,old,executable,packet,attempt=1)
   with self.assertRaisesRegex(ValueError,'attempt'):request(plan,approval,executable,packet,attempt=4)
   with self.assertRaisesRegex(ValueError,'dollar'):request(plan,approval,executable,packet,attempt=3,spent_usd=30)
   calls=[]
   def fake(endpoint,body):
    calls.append((endpoint,body));return dict(status='incomplete',usage=dict(output_tokens=64000,input_tokens=100))
   with self.assertRaisesRegex(ValueError,'incomplete'):dispatch(plan,approval,executable,packet,fake,attempt=1)
   self.assertEqual(1,len(calls));self.assertEqual('/v1/responses',calls[0][0])
 def test_cp037_projection_is_opt_in_and_preserves_business_source(self):
  from lightyear_mainframe.cp037_twin import derive,helper,adapter
  from lightyear_mainframe.legacy_twin import indexed_adapter
  for p in ('CBACT04C','CBTRN02C'):
   text=(ROOT/f'spec/mainframe/public-source/{p}.cbl').read_text();changed=derive(text,p)
   self.assertIn('LY-ACCOUNT-FILE-KEY',changed);self.assertIn('CALL "LYKEY"',changed)
   self.assertIn('RECORD KEY IS LY-',changed)
  self.assertIn('when 66 move x"c1"',helper())
  self.assertIn('write physical-record',adapter(indexed_adapter('INTCALC','XREFFILE'),16,True))
