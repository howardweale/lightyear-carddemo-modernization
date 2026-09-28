"""Adversarial checks for typed rules and irreversible campaign declaration."""
import copy
from datetime import date
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import time

from lightyear_calibration.contracts import read_json, seal
from lightyear_calibration.declared_rules import exact_decimal, decimal_value, validate_register, NUMERIC, STAMP
from lightyear_calibration.measured_judge import VERSION
from lightyear_calibration.measured_judge import admit_finding, compare_traces
from lightyear_calibration.measured_campaign import frozen, authorize, audit
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_calibration.journey_order import save, file_hash

ROOT = Path(__file__).resolve().parents[1]
REG = Path('factory/idempiere/repeatability/comparison-register.json')
INV = Path('docs/calibration/idempiere-boundaries/mappings.json')


def reseal(value):
    return seal({k:v for k,v in value.items() if k!='content_sha256'})


class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.register = read_json(ROOT/REG); cls.inventory = read_json(ROOT/INV)

    def test_all_numeric_columns_come_from_inventory(self):
        rules = validate_register(self.register,self.inventory,date(2026,9,27))
        self.assertEqual(9393,len(rules[NUMERIC]['columns']))
        self.assertIn(['c_orderline','discount'],rules[NUMERIC]['columns'])
        self.assertNotIn(['c_bpartner','name'],rules[NUMERIC]['columns'])

    def test_exact_no_tolerance(self):
        self.assertTrue(exact_decimal('10.000',{'decimal':'10'}))
        self.assertTrue(exact_decimal('-0.00',0))
        self.assertFalse(exact_decimal('1.00000000000000001','1'))

    def test_exponents_and_nonfinite_even_if_equal(self):
        for value in ('1e2','1E+2','0E-6','NaN','Infinity',' 1','1 ',True,1.0,{'decimal':'1e2'}):
            with self.subTest(value=value):
                self.assertFalse(exact_decimal(value,value))
                with self.assertRaises(ValueError):decimal_value(value)

    def test_empty_scope_is_not_zero(self):
        changed = copy.deepcopy(self.register);changed['entries'][0]['columns']=[]
        with self.assertRaises(ValueError):validate_register(reseal(changed),self.inventory,date(2026,9,27))

    def test_scope_cannot_omit_a_numeric_column(self):
        changed = copy.deepcopy(self.register);changed['entries'][0]['columns'].pop()
        with self.assertRaises(ValueError):validate_register(reseal(changed),self.inventory,date(2026,9,27))

    def test_unmeasured_radius_fails(self):
        changed = copy.deepcopy(self.register);changed['entries'][0]['blast_radius']['state']='not-assessed'
        with self.assertRaises(ValueError):validate_register(reseal(changed),self.inventory,date(2026,9,27))

    def test_expired_or_unowned_rule_fails(self):
        with self.assertRaises(ValueError):validate_register(self.register,self.inventory,date(2026,12,25))
        changed = copy.deepcopy(self.register);changed['entries'][0]['owner']=' '
        with self.assertRaises(ValueError):validate_register(reseal(changed),self.inventory,date(2026,9,27))

    def test_timestamp_cannot_expand(self):
        changed = copy.deepcopy(self.register)
        rule = next(r for r in changed['entries'] if r['id']==STAMP)
        rule['columns'].append(['c_order','dateordered'])
        with self.assertRaises(ValueError):validate_register(reseal(changed),self.inventory,date(2026,9,27))

    def test_metadata_needs_owned_register_entry(self):
        changed = copy.deepcopy(self.register);changed['metadata_entries'][0]['blast_radius']['fields'].append('anything')
        with self.assertRaises(ValueError):validate_register(reseal(changed),self.inventory,date(2026,9,27))

    def test_numeric_looking_text_has_no_decimal_fallback(self):
        class Cells:
            numeric={('unknown_business_name','anything')}
            def finding(self,value):pass
        finding={'table':'unknown_business_name','column':'anything','key':'[1]','oracle':'10','postgresql':'10.00'}
        self.assertEqual(NUMERIC,admit_finding(finding,Cells(),{}))
        finding['table']='c_bpartner';finding['column']='name'
        self.assertIsNone(admit_finding(finding,Cells(),{},'exact-native-decimal-value'))

    def test_legacy_predicate_cannot_escape_registered_scope(self):
        class Cells:
            numeric=set()
            def finding(self,value):pass
        finding={'table':'c_bpartner','column':'name','key':'[1]','oracle':'A','postgresql':'B'}
        rules={'legacy':{'columns':[['c_bpartner','description']]}}
        self.assertIsNone(admit_finding(finding,Cells(),rules,'legacy'))

    def test_unbound_trace_does_not_gain_numeric_privileges(self):
        class Cells: pass
        lanes={'oracle':{'trace':{'unbound':'10'}},'postgresql':{'trace':{'unbound':'10.00'}}}
        admitted,blocked=compare_traces(lanes,Cells(),{},[])
        self.assertEqual([],admitted);self.assertEqual(1,len(blocked))

    def test_bound_equal_exponent_trace_is_rejected(self):
        class Cells:
            numeric={('c_order','grandtotal')}
            def bind(self,*args): return 100
        trace={'order.id':'1','order.total':'1e2'}
        lanes={lane:{'trace':trace} for lane in ('oracle','postgresql')}
        with self.assertRaises(ValueError):compare_traces(lanes,Cells(),{},[])

    def test_changed_trace_cannot_borrow_native_column_type(self):
        class Cells:
            numeric={('c_order','grandtotal')}
            def bind(self,*args): return 20
        trace={'order.id':'1','order.total':'19.99'}
        lanes={lane:{'trace':trace} for lane in ('oracle','postgresql')}
        with self.assertRaises(ValueError):compare_traces(lanes,Cells(),{},[])


class FrozenPlanTests(unittest.TestCase):
    def setUp(self):
        clock=patch('lightyear_calibration.measured_campaign.date');mock_date=clock.start();mock_date.today.return_value=date(2026,9,27);self.addCleanup(clock.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.campaign=self.root/'campaign';self.campaign.mkdir()
        for relative in (REG,INV):
            (self.root/relative).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,self.root/relative)
        (self.root/'controller.py').write_text('original')
        self.signer=JourneySigner(self.root)
        self.plan=seal({'judge_version':VERSION,'implementation_sha256':{'controller.py':file_hash(self.root/'controller.py')},
                        'max_client_invocations':3,'judge_sha256':{'judge.py':'pinned'}})
        save(self.campaign/'plan.json',self.plan)
        save(self.campaign/'declaration.json',self.signer.sign({'plan_sha256':self.plan['content_sha256']}))

    def test_original_declaration_passes(self):
        self.assertEqual(self.plan,frozen(self.root,self.campaign))

    def test_budget_reseal_does_not_amend_declaration(self):
        save(self.campaign/'plan.json',reseal({**self.plan,'max_client_invocations':4}))
        with self.assertRaises(ValueError):frozen(self.root,self.campaign)

    def test_controller_edit_invalidates_campaign(self):
        (self.root/'controller.py').write_text('repair')
        with self.assertRaises(ValueError):frozen(self.root,self.campaign)

    def test_authorization_is_exact_and_single_use(self):
        with self.assertRaises(ValueError):authorize(self.root,self.campaign,'wrong','approved')
        authorize(self.root,self.campaign,self.plan['content_sha256'],'explicit test approval')
        with self.assertRaises(ValueError):authorize(self.root,self.campaign,self.plan['content_sha256'],'again')

    def test_missing_native_attempt_cannot_report_zero_repairs(self):
        folder=self.campaign/'calls/001-builder/build';folder.mkdir(parents=True)
        save(folder/'receipt.json',{})
        with self.assertRaises(ValueError):audit(self.root,self.campaign,[])

    def test_lossless_failed_campaign_publication_and_tamper(self):
        import hashlib
        from tools.publish_measured_campaign import publish, verify_publication
        self.plan=reseal({**self.plan,'implementation_sha256':{
            p.as_posix():file_hash(self.root/p) for p in (REG,INV,Path('controller.py'))}})
        save(self.campaign/'plan.json',self.plan)
        save(self.campaign/'declaration.json',self.signer.sign({'plan_sha256':self.plan['content_sha256']}))
        provenance=audit(self.root,self.campaign,[])
        save(self.campaign/'receipt.json',self.signer.sign({'plan_sha256':self.plan['content_sha256'],
            'attempts':[],'provenance':provenance,'judge_version':VERSION,'dark_factory_run':False}))
        output=self.root/'publication';publish(self.root,self.campaign,output)
        identity=hashlib.sha256(self.signer.public).hexdigest()
        result=verify_publication(self.root,output,identity)
        self.assertEqual('verified-complete-frozen-campaign',result['status'])
        self.assertFalse(result['dark_factory_run']);self.assertEqual(0,result['new_native_executions'])
        with self.assertRaises(ValueError):verify_publication(self.root,output,'untrusted')
        with (output/'evidence.zip').open('ab') as stream:stream.write(b'tamper')
        with self.assertRaises(ValueError):verify_publication(self.root,output,identity)


class NativeLifecycleTests(unittest.TestCase):
    def test_generated_candidate_is_used_and_cleanup_failure_prevents_pass(self):
        from lightyear_calibration import measured_native as native
        for cleanup_complete in (True,False):
            with self.subTest(cleanup=cleanup_complete),tempfile.TemporaryDirectory() as temporary,ExitStack() as stack:
                root=Path(temporary);campaign=root/'campaign';campaign.mkdir()
                for relative in (REG,INV):
                    target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
                build=root/'build';(build/'workspace').mkdir(parents=True)
                generated=b'generated candidate';(build/'workspace'/native.HARNESS).write_bytes(generated)
                (root/'old.java').write_bytes(b'old deterministic reference')
                save(campaign/'authorization.json',{'content_sha256':'test-campaign-authorization'})
                plan=seal({'scenario':'procure-to-pay','declaration':{'policy':{'max_elapsed_seconds':300},'application':{
                    'harnesses':[{'id':'operations','file':'old.java'}],'source_commit':'test-source'}},
                    'implementation_sha256':{},'inputs_sha256':{},'campaign_plan_sha256':'frozen',
                    'judge_sha256':{},'builder_client':{},'comparison_register_sha256':'register',
                    'extension_declaration_sha256':'extension','model_calls':1,'campaign_directory':'campaign',
                    'harness_sha256':__import__('hashlib').sha256(generated).hexdigest()})
                builder={'content_sha256':'test-builder'}
                executed=[]
                class Runner:
                    def __init__(self,root,run,plan,emit):
                        self.root=root;self.run=run;self.plan=plan;self.deadline=time.monotonic()+300
                    def prepare(self,case,attempt):
                        folder=self.run/'cases'/case/str(attempt);folder.mkdir(parents=True);return folder
                    def checkpoint(self,stage):pass
                    def owned(self,kind):return []
                    def inside(self,path):return '/output/'+path.relative_to(self.run).as_posix()
                    def worker(self,command,payload,timeout):
                        if command=='execute':
                            self_test.assertEqual(generated,(self.run/'inputs/operations.java').read_bytes())
                            self_test.assertEqual('LightyearOperationsTest',payload['test']);executed.append(payload['lane'])
                        return {'exit_code':0,'content_sha256':'fixture-native'}
                    def cleanup(self,retain=False):
                        return {'complete':cleanup_complete,'remaining_containers':[],'remaining_networks':[],
                                'credentials_destroyed':True}
                self_test=self
                for name,value in [('native_plan',lambda *args:plan),('archived',lambda *args:{}),
                                   ('LocalRunner',Runner),('bounded_gate',lambda runner:seal({'passed':True,'plan_sha256':runner.plan['content_sha256']}))]:
                    stack.enter_context(patch.object(native,name,value))
                stack.enter_context(patch.object(native.subprocess,'Popen'))
                stack.enter_context(patch.object(native.RunIndex,'record'))
                run,receipt=native.execute_native(root,campaign,build,builder,300)
                self.assertEqual(['oracle','postgresql'],executed)
                self.assertEqual(cleanup_complete,receipt['bounded_observed_journey_equivalence'])
                self.assertEqual(cleanup_complete,read_json(run/'cleanup.json')['complete'])


if __name__=='__main__':unittest.main()
