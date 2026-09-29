import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lightyear_calibration.contracts import CalibrationError,seal
from lightyear_calibration.journey_order import RUNS,save
from lightyear_calibration.ms94_v3_errors import BusinessViolation
from lightyear_calibration import ms94_v3_judge
from tools.ms94_v3_scope import validate,accounting_cache,PURCHASING
from tools.ms94_v3_source_policy import check
from tests import test_procurement_scope

ROOT=Path(__file__).resolve().parents[1]
SUPPORT=ROOT/'factory/idempiere/qualification-ms94-v3/public/JourneySupport.java'


class OwnedEffects(unittest.TestCase):
    def setUp(self):
        fixture=test_procurement_scope.Scope();fixture.setUp();self.records=fixture.records;self.trace=fixture.trace
        self.records['m_matchinv'][0].update(m_product_id=10,ad_client_id=11,ad_org_id=11)
        self.records['m_matchpo']=[];self.records['m_product_po']=[]
        for i,row in enumerate(self.records['t_fact_acct_history']):row['account_id']=500+i
        self.before={t:[] for t in PURCHASING}
        self.bounds={'status':'measured-reference-bound','source_run_sha256':'reference',
            'maximum_rows_per_document_schema_currency_account':1,'maximum_history_rows':2,'content_sha256':'bound'}

    def run_check(self):return validate(self.records,self.before,self.trace,self.bounds)

    def test_reference_shape(self):self.assertEqual(self.run_check()['owned_delta_counts']['m_costdetail'],1)

    def test_other_product_cost_detail_cannot_hide_in_filter(self):
        row=copy.deepcopy(self.records['m_costdetail'][0]);row['m_product_id']=999
        self.records['m_costdetail'].append(row)
        with self.assertRaises(BusinessViolation):self.run_check()

    def test_foreign_matchpo_rejected(self):
        self.records['m_matchpo']=[{'ad_client_id':11,'ad_org_id':11,'m_product_id':999}]
        with self.assertRaises(BusinessViolation):self.run_check()

    def test_wrong_match_links_rejected(self):
        self.records['m_matchpo']=[{'ad_client_id':11,'ad_org_id':11,'m_product_id':10,
            'c_orderline_id':31,'m_inoutline_id':999}]
        with self.assertRaises(BusinessViolation):self.run_check()

    def test_unchanged_foreign_seed_rows_allowed_but_edits_not(self):
        row={'ad_client_id':11,'ad_org_id':0,'m_product_id':999,'c_bpartner_id':888,'pricelastpo':1}
        self.before['m_product_po']=[copy.deepcopy(row)];self.records['m_product_po']=[row]
        self.run_check();row['pricelastpo']=2
        with self.assertRaises(BusinessViolation):self.run_check()

    def test_owned_vendor_price_update_is_explicitly_bounded(self):
        row={'ad_client_id':11,'ad_org_id':0,'m_product_id':10,'c_bpartner_id':20,'pricelastpo':1,'pricepo':1}
        self.before['m_product_po']=[copy.deepcopy(row)];self.records['m_product_po']=[row]
        row['pricelastpo']=2;self.run_check();row['pricepo']=3
        with self.assertRaises(BusinessViolation):self.run_check()

    def test_own_match_reposting_history_rejected_despite_balanced_totals(self):
        additions=copy.deepcopy(self.records['t_fact_acct_history'])
        for row in additions:row['fact_acct_id']+=100
        self.records['t_fact_acct_history']+=additions
        with self.assertRaisesRegex(BusinessViolation,'generation bound'):self.run_check()

    def test_scope_failure_remains_business_when_message_changes(self):
        self.records['m_costqueue'][0]['m_product_id']=999
        with self.assertRaises(BusinessViolation):self.run_check()

    def test_configuration_changes_are_not_blanket_allowed(self):
        old={'c_acctschema_id':101,'ad_client_id':11,'c_period_id':1,'updatedby':100,'name':'standard'}
        current={**old,'c_period_id':2,'updatedby':101}
        records={'c_acctschema':[current],'fact_acct':[{'ad_table_id':318,'record_id':50,
            'c_acctschema_id':101,'c_period_id':2,'ad_client_id':11,'createdby':101}]}
        before={'c_acctschema':[old]}
        accounting_cache(records,before,self.trace)
        current['name']='changed'
        with self.assertRaises(BusinessViolation):accounting_cache(records,before,self.trace)


class SourceAndEnvelope(unittest.TestCase):
    def test_execution_source_copy_is_independent_and_inventory_is_closed(self):
        from tools.ms94_execution_snapshot import copy_snapshot,guard
        with tempfile.TemporaryDirectory() as directory:
            original=Path(directory);source=original/'src/code.py';source.parent.mkdir();source.write_text('version=1')
            snapshot=original/'work/ms94/execution-snapshots/test'
            copy_snapshot(original,snapshot,['src/code.py'])
            source.write_text('version=2');guard(snapshot)
            self.assertEqual((snapshot/'src/code.py').read_text(),'version=1')
            (snapshot/'src/extra.py').write_text('version=3')
            with self.assertRaises(CalibrationError):guard(snapshot)
        with tempfile.TemporaryDirectory() as directory:
            original=Path(directory)
            with self.assertRaises(CalibrationError):copy_snapshot(original,original/'outside',[])

    def test_real_reference_own_match_mutant_is_refused(self):
        from tools.ms94_v3_mutations import own_match_repost,duplicate_trace
        source=(SUPPORT.parent.parent/'references/procure-to-pay/LightyearOperationsTest.java').read_text(encoding='utf-8')
        source=source[:source.index('/** Deterministic plumbing;')]
        check(source)
        with self.assertRaises(BusinessViolation):check(own_match_repost(source))
        self.assertEqual(duplicate_trace(source).count('fact("newIssueCount", issuesAfter - issuesBefore);'),2)

    def test_posting_bypasses_and_unicode_obfuscation_rejected(self):
        for source in ('DocManager.postDocument(a,b,c,false,true,t);','postImmediate(a,b,c,false,t);',
                       r'DocManager.post\u0044ocument(a,b,c,false,false,t);','x::postDocument',
                       'Class.forName(name).getMethod(name).invoke(x);'):
            with self.subTest(source=source),self.assertRaises(BusinessViolation):check(source)
        check('JourneySupport.postOnce(doc, schemas); // postDocument is forbidden\nString x="postImmediate";')

    def test_all_five_classes_persist_and_ignore_exception_message(self):
        for desired in ('passed','business-failure','execution-failure','judge-error','insufficient-evidence'):
            with self.subTest(status=desired),tempfile.TemporaryDirectory() as directory:
                run=Path(directory)/RUNS/'journey-test';save(run/'plan.json',seal({'scenario':'operations'}))
                (run/'inputs').mkdir();(run/'inputs/JourneySupport.java').write_text(SUPPORT.read_text())
                embedded=SUPPORT.read_text().replace('package org.idempiere.test;','').replace('public final class JourneySupport','final class JourneySupport').strip()
                (run/'inputs/operations.java').write_text('class Candidate {}\n'+embedded)
                for lane in ('oracle','postgresql'):
                    if desired=='insufficient-evidence' and lane=='postgresql':continue
                    save(run/'cases/operations/1/execution'/lane/'execution.json',seal({'exit_code':1 if desired=='execution-failure' else 0}))
                def verifier(_):
                    if desired=='business-failure':raise BusinessViolation('Entirely renamed message')
                    if desired=='judge-error':raise CalibrationError('Quantity outcome differs')
                    return seal({'passed':True})
                with patch.object(ms94_v3_judge,'structural_result',return_value=seal({'passed':True})):
                    result=ms94_v3_judge.evaluate(run,verifier=verifier)
                self.assertEqual(result['status'],desired)
                self.assertEqual(json.loads((run/'gate.json').read_bytes()),result)


@unittest.skipUnless(shutil.which('javac') and shutil.which('java'),'JDK required')
class SupportTests(unittest.TestCase):
    def test_primary_exception_cleanup_numeric_serialization_and_duplicate_key(self):
        sources={
            'org/compiere/model/PO.java':'''package org.compiere.model; public class PO {
 public boolean value=true, loaded=true; public boolean load(String t){return loaded;}
 public boolean get_ValueAsBoolean(String n){return value;} public String get_TrxName(){return "unit";}
 public int get_Table_ID(){return 1;} public int get_ID(){return 1;} }''',
            'org/compiere/model/MAcctSchema.java':'package org.compiere.model; public class MAcctSchema {}',
            'org/compiere/acct/DocManager.java':'''package org.compiere.acct; public class DocManager {
 public static String error; public static String postDocument(org.compiere.model.MAcctSchema[] s,int t,int i,boolean force,boolean repost,String x){
 if(force||repost)throw new AssertionError();return error;} }''',
            'org/compiere/util/Trx.java':'''package org.compiere.util; public class Trx {
 public static boolean rollbackResult=true, closeFails=false; public static int closed,rolled;
 public static String createTrxName(String p){return p;} public static Trx get(String p,boolean c){return new Trx();}
 public boolean commit(boolean b){return true;} public boolean rollback(){rolled++;return rollbackResult;}
 public void close(){closed++;if(closeFails)throw new IllegalStateException("close");} }''',
            'Main.java':'''import org.idempiere.test.JourneySupport; import org.compiere.util.Trx;
public class Main {
 static void ok(boolean b){if(!b)throw new AssertionError();}
 interface Call {void run() throws Exception;}
 static void rejects(Call c) throws Exception {try{c.run();throw new AssertionError();}catch(IllegalArgumentException good){}}
 public static void main(String[] args) throws Exception {
  ok(JourneySupport.text(null).equals("SQL-NULL"));rejects(()->JourneySupport.text("SQL-NULL"));
  rejects(()->JourneySupport.text(1.0e10));rejects(()->JourneySupport.text(1.0f));
  ok(JourneySupport.text(new java.math.BigDecimal("1E+10")).equals("10000000000"));
  java.util.Properties p=new java.util.Properties();JourneySupport.fact(p,"quantity",1);
  rejects(()->JourneySupport.fact(p,"quantity",2));ok(p.getProperty("quantity").equals("1"));
  Exception primary=new Exception("body");Trx.rollbackResult=false;Trx.closeFails=true;
  try{JourneySupport.transaction("x",n->{throw primary;});throw new AssertionError();}
  catch(Exception caught){ok(caught==primary);ok(caught.getSuppressed().length==2);}
  ok(Trx.rolled==1&&Trx.closed==1);Trx.closeFails=false;Trx.rollbackResult=true;
  Error fatal=new AssertionError("body error");
  try{JourneySupport.transaction("x",n->{throw fatal;});throw new IllegalStateException();}
  catch(Error caught){ok(caught==fatal);}ok(Trx.rolled==2&&Trx.closed==2);
  org.compiere.model.PO model=new org.compiere.model.PO();model.loaded=false;
  try{JourneySupport.postOnce(model,new org.compiere.model.MAcctSchema[0]);throw new AssertionError();}
  catch(IllegalStateException good){ok(good.getMessage().contains("Reload"));}
  model.loaded=true;model.value=false;org.compiere.acct.DocManager.error="private application error";
  try{JourneySupport.postOnce(model,new org.compiere.model.MAcctSchema[0]);throw new AssertionError();}
  catch(IllegalStateException good){ok(good.getCause().getMessage().equals("private application error"));}
 }
}''', 'org/idempiere/test/JourneySupport.java':SUPPORT.read_text()}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,text in sources.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            compile=subprocess.run(['javac','-d',str(root),*(str(root/n) for n in sources)],capture_output=True,text=True,timeout=40)
            self.assertEqual(compile.returncode,0,compile.stderr)
            result=subprocess.run(['java','-cp',str(root),'Main'],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
