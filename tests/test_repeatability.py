"""Fixed-sample denominators, controlled ablations and purchasing gate checks."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lightyear_calibration.contracts import read_json,seal
from lightyear_calibration.repeatability import schedule,rates,wilson,outcome,report
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_calibration.journey_order import save
from lightyear_calibration import procurement_journey as procurement

ROOT=Path(__file__).resolve().parents[1]


class RateTests(unittest.TestCase):
    def test_ten_each_without_outcome_stopping(self):
        values=schedule(('baseline','procure-to-pay','without-decimal','without-boolean'),10,17)
        self.assertEqual(40,len(values));self.assertEqual(values,schedule(('baseline','procure-to-pay','without-decimal','without-boolean'),10,17))
        for name in ('baseline','procure-to-pay','without-decimal','without-boolean'):
            self.assertEqual(list(range(1,11)),[x['replicate'] for x in values if x['variant']==name])
        for i in range(0,40,4):self.assertEqual(4,len({r['variant'] for r in values[i:i+4]}))
    def test_halts_and_invalids_remain_in_denominator(self):
        r=rates([{'outcome':x} for x in ['first-try-pass']*4+['pass-after-repair']*2+['halt']*2+['invalid','not-started']],10)
        self.assertEqual(9,r['started']);self.assertEqual(1,r['not_started'])
        self.assertEqual(4/9,r['first_try_rate']);self.assertEqual(6/9,r['eventual_pass_rate']);self.assertFalse(r['complete_fixed_sample'])
    def test_zero_observations_not_zero_percent(self):
        r=rates([{'outcome':'not-started'}]*10,10)
        self.assertIsNone(r['first_try_rate']);self.assertIsNone(r['first_try_wilson_95'])
    def test_ten_passes_do_not_claim_certainty(self):
        lo,hi=wilson(10,10);self.assertGreater(lo,.72);self.assertLess(lo,.73);self.assertAlmostEqual(1,hi)
        lo,hi=wilson(0,10);self.assertAlmostEqual(0,lo);self.assertGreater(hi,.27)
    def test_invalid_rate_counts_rejected(self):
        for a,b in ((11,10),(-1,10),(True,10),(0,-1)):
            with self.assertRaises(ValueError):wilson(a,b)
    def test_failed_transport_not_first_try_success(self):
        r={'attempts':[{}],'combined_gate_passed':False,'status':'halted-campaign-error','cost':{'attempted_client_invocations':1},'provenance':{},'content_sha256':'x'}
        self.assertEqual('halt',outcome(r)['outcome'])
        r['combined_gate_passed']=True;self.assertEqual('first-try-pass',outcome(r)['outcome'])
        r['attempts']=[{},{}];r['cost']['attempted_client_invocations']=3;self.assertEqual('pass-after-repair',outcome(r)['outcome'])
    def test_signed_report_lists_all_slots_and_refuses_forged_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cohort=root/'cohort';cohort.mkdir();signer=JourneySigner(root)
            p=seal({'variant_plans':{'baseline':'abc'},'schedule':schedule(('baseline',),10,1),'runs_per_variant':10})
            save(cohort/'plan.json',p)
            r=report(root,cohort,'explicit-stop');self.assertEqual(10,len(r['outcomes']));self.assertEqual(10,r['rates']['baseline']['not_started'])
            trial=cohort/'trials/001-baseline';trial.mkdir(parents=True)
            save(trial/'receipt.json',{'plan_sha256':'abc','signature':{},'content_sha256':'forged'})
            self.assertEqual(1,report(root,cohort)['rates']['baseline']['invalid'])


class InputTests(unittest.TestCase):
    def test_baseline_keeps_every_ms91_input(self):
        old=read_json(ROOT/'factory/idempiere/declared-factory/builder-input.json')
        new=read_json(ROOT/'factory/idempiere/repeatability/baseline/builder-input.json')
        self.assertEqual(old,new)
    def test_each_ablation_removes_only_one_explicit_hint(self):
        area=ROOT/'factory/idempiere/repeatability';base=read_json(area/'baseline/builder-input.json')
        no_bool=read_json(area/'without-boolean/builder-input.json');no_bool['api_reference']['typed_boolean_signature']=base['api_reference']['typed_boolean_signature']
        self.assertEqual(base,no_bool)
        no_dec=read_json(area/'without-decimal/builder-input.json');original=no_dec['trace_contract']['instructions']
        no_dec['trace_contract']['instructions']=base['trace_contract']['instructions'];self.assertEqual(base,no_dec)
        self.assertNotIn('stripTrailingZeros',original)
        self.assertNotIn('toPlainString',original)
    def test_procurement_has_no_new_api_example(self):
        area=ROOT/'factory/idempiere/repeatability';base=read_json(area/'baseline/builder-input.json');p=read_json(area/'procure-to-pay/builder-input.json')
        self.assertEqual(base['api_reference'],p['api_reference']);self.assertEqual(base['instruction'],p['instruction'])
        self.assertEqual(base['patch_limits'],p['patch_limits']);self.assertIsNone(p['gate_output'])


class ProcurementTests(unittest.TestCase):
    def fixture(self):
        import hashlib
        tables={};trace={'status':'completed-and-committed','database':'oracle','newIssueCount':'0','vendorInvoice.paid':'true'}
        for n,(stage,table) in enumerate(procurement.STAGES.items(),1):
            uid=f'00000000-0000-4000-8000-{n:012d}';row={table+'_id':n,table+'_uu':uid}
            if stage in ('purchaseOrder','receipt','vendorInvoice','vendorPayment'):row.update(docstatus='CO',c_bpartner_id=1,c_bpartner_location_id=2,issotrx='N',posted='Y');trace[stage+'.status']='CO'
            tables[table]=[row];trace.update({stage+'.saved':'true',stage+'.id':str(n),stage+'.uuid':uid})
        tables['c_bpartner'][0].update(isvendor='Y',name=procurement.INPUT['customer_name'],description=None)
        tables['c_bpartner_location'][0]['c_bpartner_id']=1
        tables['m_product'][0].update(ispurchased='Y',isstocked='Y')
        tables['m_productprice'][0]['m_product_id']=3
        tables['c_order'][0].update(totallines='53.99',grandtotal='58.04')
        tables['m_inout'][0]['c_order_id']=5
        tables['c_invoice'][0].update(totallines='53.99',grandtotal='58.04',ispaid='Y')
        tables['c_payment'][0].update(isreceipt='N',c_invoice_id=7,payamt='58.04')
        tables['c_orderline']=[dict(c_orderline_id=11,c_order_id=5,m_product_id=3,qtyordered='3',qtydelivered='3',qtyinvoiced='3',priceactual='17.9955',pricelist='19.995',discount='10',linenetamt='53.99',c_tax_id=107)]
        tables['m_inoutline']=[dict(m_inoutline_id=12,m_inout_id=6,c_orderline_id=11,m_product_id=3,movementqty='3')]
        tables['c_invoiceline']=[dict(c_invoiceline_id=13,c_invoice_id=7,m_inoutline_id=12,m_product_id=3,qtyinvoiced='3',priceactual='17.9955',linenetamt='53.99')]
        tables['c_ordertax']=[dict(c_order_id=5,c_tax_id=107,taxamt='4.05',taxbaseamt='53.99')]
        tables['c_invoicetax']=[dict(c_invoice_id=7,c_tax_id=107,taxamt='4.05',taxbaseamt='53.99')]
        tables['m_storageonhand']=[dict(m_product_id=3,qtyonhand='3')]
        tables['m_transaction']=[dict(m_product_id=3,movementtype='V+',movementqty='3',m_inoutline_id=12)]
        tables['c_allocationline']=[dict(c_invoice_id=7,c_payment_id=8,c_allocationhdr_id=14,amount='-58.04')]
        tables['c_allocationhdr']=[dict(c_allocationhdr_id=14,docstatus='CO')]
        tables['fact_acct']=[]
        for table,record in [(318,7),(335,8),(735,14)]:
            for dr,cr in [('58.04','0'),('0','58.04')]:tables['fact_acct'].append(dict(ad_table_id=table,record_id=record,c_acctschema_id=1,c_currency_id=100,amtacctdr=dr,amtacctcr=cr,amtsourcedr=dr,amtsourcecr=cr))
        execution=seal({'lane':'oracle','exit_code':0,'application_source_commit':procurement.SOURCE_COMMIT,'harness_sha256':hashlib.sha256(b'fixture').hexdigest()})
        return tables,trace,execution
    def run_gate(self,tables,trace,execution):
        snap={'evidence_class':'native-database-observation','content_sha256':'fixture','tables':{t:t for t in tables}}
        with patch.object(procurement,'state',return_value=snap),patch.object(procurement,'rows',side_effect=lambda folder,t:tables[t]),patch.object(procurement,'read_trace',return_value=(trace,'fixture')):
            return procurement.verify_lane(Path('.'),Path('trace.xml'),execution,b'fixture')
    def test_purchasing_readback(self):
        self.assertEqual('passed-bounded-procure-to-pay',self.run_gate(*self.fixture())['status'])
    def test_wrong_direction_or_wrong_money_or_unpaid_rejected(self):
        for table,key,value in [('c_payment','isreceipt','Y'),('c_order','issotrx','Y'),('c_bpartner','isvendor','N'),('c_invoice','grandtotal','58.05'),('c_invoice','ispaid','N'),('c_allocationline','amount','58.04'),('m_transaction','movementtype','C-'),('c_orderline','discount','0'),('c_invoiceline','priceactual','18'),('c_ordertax','taxbaseamt','54')]:
            with self.subTest(table=table,key=key):
                tables,trace,ex=self.fixture();tables[table][0][key]=value
                with self.assertRaises(ValueError):self.run_gate(tables,trace,ex)


class CohortLifecycleTests(unittest.TestCase):
    def exercise(self, mode):
        from contextlib import ExitStack
        from lightyear_calibration import repeatability as module
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cohort=root/'cohort';cohort.mkdir();signer=JourneySigner(root)
            p=seal({'variant_plans':{'baseline':'abc'},'schedule':schedule(('baseline',),3,1),
                    'runs_per_variant':3,'maximum_active_seconds':10800})
            save(cohort/'plan.json',p)
            save(cohort/'authorization.json',signer.sign({'plan_sha256':p['content_sha256']}))
            template=cohort/'templates/baseline';template.mkdir(parents=True)
            save(template/'plan.json',{});save(template/'declaration.json',{})
            invoked=[]
            def execute(root,folder,executable,remaining_seconds=None):
                invoked.append(folder.name)
                native=root/('native-'+folder.name);native.mkdir()
                save(native/'cleanup.json',{'complete':mode!='cleanup-failure'})
                save(native/'receipt.json',{'observer_capture_integrity':mode!='capture-failure'})
                r=signer.sign({'plan_sha256':'abc','combined_gate_passed':False,'status':'halted-no-supported-repair',
                    'attempts':[{'run_directory':native.relative_to(root).as_posix()}],
                    'cost':{'attempted_client_invocations':1,'accounting_complete':True},
                    'provenance':{'verified':mode!='provenance-failure'}})
                save(folder/'receipt.json',r)
                if mode=='cancel':module.cancel(root,cohort,'Operator stop')
                return r
            with ExitStack() as stack:
                stack.enter_context(patch.object(module,'frozen',return_value=p))
                stack.enter_context(patch.object(module.trial,'authorize'))
                stack.enter_context(patch.object(module.trial,'run',side_effect=execute))
                stack.enter_context(patch('tools.publish_measured_campaign.publish'))
                result=module.run(root,cohort,Path('unused'))
            return invoked,result
    def test_business_halts_do_not_end_fixed_sample(self):
        calls,r=self.exercise('business-halt')
        self.assertEqual(3,len(calls));self.assertEqual(3,r['rates']['baseline']['halts'])
        self.assertIsNone(r['stop_reason']);self.assertTrue(r['rates']['baseline']['complete_fixed_sample'])
    def test_integrity_cleanup_and_operator_stops_preserve_unstarted_slots(self):
        for mode in ('cleanup-failure','capture-failure','provenance-failure','cancel'):
            with self.subTest(mode=mode):
                calls,r=self.exercise(mode);self.assertEqual(1,len(calls))
                self.assertEqual(2,r['rates']['baseline']['not_started']);self.assertIsNotNone(r['stop_reason'])


if __name__=='__main__':unittest.main()
