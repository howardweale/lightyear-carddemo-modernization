import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_factory.posttran_broker import request,dispatch
from lightyear_control_tower.decisions import digest
from lightyear_mainframe.legacy_twin import ROOT

class RevisedBrokerTests(unittest.TestCase):
 def test_exact_revision_required_and_server_cap_includes_reasoning(self):
  reservation=patch('lightyear_factory.posttran_broker.reserve');reservation.start();self.addCleanup(reservation.stop)
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
   for bad in (-1,float('nan'),float('inf'),True):
    with self.assertRaisesRegex(ValueError,'invalid-prior-spend'):request(plan,approval,executable,packet,attempt=1,spent_usd=bad)
   self.assertEqual('default',payload['service_tier'])
   def fake_response(usage,status='completed'):
    return lambda e,b: dict(object='response.input_tokens',input_tokens=100) if e.endswith('input_tokens') else dict(status=status,usage=usage)
   for field,value in [('pricing_status','unverified'),('transport_contract_verified_offline',False)]:
    blocked=copy.deepcopy(plan);blocked[field]=value;blocked.pop('content_sha256');blocked['content_sha256']=digest(blocked)
    bound={**approval,'plan_sha256':blocked['content_sha256']};forbidden=[]
    with self.assertRaisesRegex(ValueError,'live-dispatch-blocked'):
     dispatch(blocked,bound,executable,packet,lambda e,b:forbidden.append(b),attempt=1)
    self.assertEqual([],forbidden)
   for count in (-1,True,float('nan'),None):
    calls=[]
    def bad_count(e,b):
     calls.append(e);return dict(object='response.input_tokens',input_tokens=count)
    with self.assertRaisesRegex(ValueError,'invalid-input-token-count'):dispatch(plan,approval,executable,packet,bad_count,attempt=1)
    self.assertEqual(['/v1/responses/input_tokens'],calls)
   with self.assertRaisesRegex(ValueError,'input-token-preflight-cap'):
    dispatch(plan,approval,executable,packet,lambda e,b:dict(object='response.input_tokens',input_tokens=250001),attempt=1)
   for usage in ({'output_tokens':64001,'input_tokens':100},{'output_tokens':10,'input_tokens':250001}):
    with self.assertRaisesRegex(ValueError,'token-cap-breach'):dispatch(plan,approval,executable,packet,fake_response(usage),attempt=1)
   for usage in ({},{'output_tokens':-1,'input_tokens':100},{'output_tokens':False,'input_tokens':100},{'output_tokens':float('inf'),'input_tokens':100}):
    with self.assertRaisesRegex(ValueError,'missing-billed-usage'):dispatch(plan,approval,executable,packet,fake_response(usage),attempt=1)
   with self.assertRaisesRegex(ValueError,'input-count-usage-mismatch'):
    dispatch(plan,approval,executable,packet,fake_response(dict(output_tokens=10,input_tokens=101)),attempt=1)
   corrupted={**packet,'phase1-work-order.md':b'changed'}
   with self.assertRaisesRegex(ValueError,'packet-bytes'):request(plan,approval,executable,corrupted,attempt=1)
   calls=[]
   def fake(endpoint,body):
    calls.append((endpoint,body))
    if endpoint.endswith('input_tokens'):return dict(object='response.input_tokens',input_tokens=100)
    return dict(status='incomplete',usage=dict(output_tokens=64000,input_tokens=100))
   with self.assertRaisesRegex(ValueError,'incomplete'):dispatch(plan,approval,executable,packet,fake,attempt=1)
   self.assertEqual(2,len(calls));self.assertEqual('/v1/responses',calls[1][0]);self.assertEqual(calls[0][1]['input'],calls[1][1]['input'])
 def test_durable_reservations_survive_failures_and_refuse_reset_attempts(self):
  from lightyear_factory.posttran_broker import reserve
  from datetime import datetime,timedelta,timezone
  plan=json.loads((ROOT/'docs/factory/posttran-second-opinion/revised-plan.json').read_text())
  with tempfile.TemporaryDirectory() as d,patch('lightyear_factory.posttran_broker.STATE_ROOT',Path(d)):
   reserve(plan,1)
   with self.assertRaisesRegex(ValueError,'durable-attempt'):reserve(plan,1)
   reserve(plan,2);reserve(plan,3)
   with self.assertRaisesRegex(ValueError,'durable-attempt'):reserve(plan,4)
   p=Path(d)/plan['dispatch']['reservation_ledger'];state=json.loads(p.read_text())
   self.assertEqual(3,len(state['reservations']));self.assertAlmostEqual(33.15,sum(x['reserved_usd'] for x in state['reservations']))
   changed={**plan,'content_sha256':'changed'}
   with self.assertRaisesRegex(ValueError,'ledger-plan'):reserve(changed,4)
   state['started_at']=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat();p.write_text(json.dumps(state))
   with self.assertRaisesRegex(ValueError,'phase-time'):reserve(plan,4)
   p.with_suffix('.lock').write_text('interrupted')
   with self.assertRaisesRegex(ValueError,'reservation-busy'):reserve(plan,4)
 def test_cp037_projection_is_opt_in_and_preserves_business_source(self):
  from lightyear_mainframe.cp037_twin import derive,helper,adapter
  from lightyear_mainframe.legacy_twin import indexed_adapter
  for p in ('CBACT04C','CBTRN02C'):
   text=(ROOT/f'spec/mainframe/public-source/{p}.cbl').read_text();changed=derive(text,p)
   self.assertIn('LY-ACCOUNT-FILE-KEY',changed);self.assertIn('CALL "LYKEY"',changed)
   self.assertIn('RECORD KEY IS LY-',changed)
  self.assertIn('when 66 move x"c1"',helper())
  self.assertIn('write physical-record',adapter(indexed_adapter('INTCALC','XREFFILE'),16,True))
