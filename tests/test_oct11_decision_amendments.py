import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_control_tower.decisions import digest
from lightyear_factory.posttran_preflight import verify_approval
from lightyear_factory.posttran_broker import dispatch
from lightyear_mainframe.posttran_review import body,SHEET,render
from lightyear_mainframe.zos_bindings import ROOT
from tools.amend_posttran_oct11 import amended_plan,BASE
from tools.build_factory_current_status import generate,INPUTS
from tools.b07_prefreeze_power import pvalue,paired_lower,effect_interval,simulate

class DecisionAmendmentTests(unittest.TestCase):
    def test_amendment_preserves_budget_inputs_and_requires_exact_go(self):
        old=json.loads((ROOT/'docs/factory/posttran-second-opinion/revised-plan.json').read_bytes());new=amended_plan()
        self.assertEqual(BASE,new['supersedes_plan_sha256'])
        for key in ('phases','inputs','prompts','model','reasoning_effort','service_tier'):self.assertEqual(old[key],new[key])
        a=dict(plan_sha256=new['content_sha256'],approved_phase=1,approved_limits=new['phases']['1'],human_answer='Approve Phase 1 budget')
        with self.assertRaises(ValueError):verify_approval(new,a)
        a['human_answer']='go POSTTRAN '+new['content_sha256'];self.assertFalse(verify_approval(new,a)['phase2_authorized'])
        a['human_answer']='go POSTTRAN '+BASE
        with self.assertRaises(ValueError):verify_approval(new,a)

    def execute(self,transport,root):
        plan=amended_plan();exe=root/'fake-client';exe.write_bytes(b'test-only')
        plan['client']['sha256']=hashlib.sha256(exe.read_bytes()).hexdigest();plan.pop('content_sha256');plan['content_sha256']=digest(plan)
        a=dict(plan_sha256=plan['content_sha256'],approved_phase=1,approved_limits=plan['phases']['1'],human_answer='go POSTTRAN '+plan['content_sha256'])
        packet={k:(ROOT/k).read_bytes() for k in plan['inputs']};packet['phase1-work-order.md']=(ROOT/'docs/factory/posttran-second-opinion/phase1-work-order.md').read_bytes()
        with patch('lightyear_factory.posttran_broker.STATE_ROOT',root):
            dispatch(plan,a,exe,packet,transport,attempt=1)
        return plan

    def test_count_is_durable_before_generation_and_failures_consume_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);seen=[]
            def transport(endpoint,payload):
                seen.append((endpoint,payload))
                state=json.loads((root/'work/posttran-second-opinion/revised-phase1-ledger.json').read_text())
                events=state['reservations'][0]['preflight']
                self.assertTrue(all(e['generation'] is False for e in events))
                if endpoint.endswith('input_tokens'):
                    self.assertEqual('requested',events[-1]['status']);return dict(object='response.input_tokens',input_tokens=123)
                self.assertEqual('completed',events[-1]['status']);self.assertEqual(123,events[-1]['input_tokens'])
                self.assertEqual(seen[0][1]['input'],payload['input'])
                return dict(status='completed',usage=dict(input_tokens=123,output_tokens=30))
            self.execute(transport,root);self.assertEqual(2,len(seen))
        for response in (dict(object='response.input_tokens',input_tokens=250001),dict(input_tokens=1)):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);calls=[]
                def invalid(endpoint,payload):calls.append(endpoint);return response
                with self.assertRaises(ValueError):self.execute(invalid,root)
                state=json.loads((root/'work/posttran-second-opinion/revised-phase1-ledger.json').read_text())
                self.assertEqual('failed',state['reservations'][0]['preflight'][-1]['status'])
                self.assertEqual(1,len(calls));self.assertEqual(11.05,state['reservations'][0]['reserved_usd'])

    def test_unsigned_decisions_bound_but_never_authenticated(self):
        d=json.loads((ROOT/'docs/factory/posttran-decisions-unsigned-2026-10-11.json').read_bytes())
        s=json.loads(SHEET.read_bytes());checked=body(s,d,'Howard Weale')
        self.assertTrue(all(r['decision']=='accept' for r in checked['decisions']));self.assertNotIn('signature',d)
        bad=copy.deepcopy(d);bad['sheet_sha256']='changed'
        with self.assertRaises(ValueError):body(s,bad,'Howard Weale')
        s['records'][0]['account_state_before']={'credit_limit':'<446.00>','WS-TEMP-BAL':'715.44'}
        page=render(s);self.assertIn('&lt;446.00&gt;',page)

    def test_source_bound_decisions_and_stale_status_refusal(self):
        d=json.loads((ROOT/INPUTS[0]).read_bytes())
        self.assertEqual(d['content_sha256'],digest({k:v for k,v in d.items() if k!='content_sha256'}))
        self.assertEqual(20,len(d['equivalence_review']['accepted_mutants']))
        self.assertFalse(d['equivalence_review']['independent_human_attestation'])
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for path in INPUTS:
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/path).read_bytes())
            before,text=generate(root)
            self.assertEqual((ROOT/'docs/factory/current-status.md').read_text(encoding='utf-8'),text)
            path=root/INPUTS[1];register=json.loads(path.read_bytes());register['defects'][0]['disposition']='fix'
            path.write_text(json.dumps(register),encoding='utf-8')
            after,_=generate(root)
            self.assertNotEqual(before['content_sha256'],after['content_sha256'])
            path=root/INPUTS[0];changed=json.loads(path.read_bytes());changed['decided_by']='unbound reviewer'
            path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'status-input-seal'):generate(root)

    def test_power_math_and_simulation_are_deterministic(self):
        self.assertEqual(1,pvalue(0,0));self.assertEqual(.0625,pvalue(5,0));self.assertEqual(pvalue(3,7),pvalue(7,3))
        self.assertLess(paired_lower(0,0,72),0)
        lo,hi=effect_interval(0,0,72);self.assertAlmostEqual(lo,-hi)
        a=simulate(100,seed=42);self.assertEqual(a,simulate(100,seed=42))
        self.assertFalse(a['freeze_ready']);self.assertEqual(0,a['model_calls'])

if __name__=='__main__':unittest.main()
