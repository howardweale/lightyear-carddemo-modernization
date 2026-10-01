import ast
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import CalibrationError, canonical, read_json, seal
from lightyear_calibration.journey_order import save
from lightyear_control_tower.decisions import verify_envelope
from tests.test_ms94_a3_entry_v2 import test_signer
from tools import ms94_b04_controller as controller
from tools import ms94_b04_evidence as evidence
from tools.ms94_b04_measure import decision, summary

ROOT = Path(__file__).resolve().parents[1]


class UnchangedBuilderTests(unittest.TestCase):
    def test_prompt_assembly_and_candidate_creation_are_unchanged(self):
        def functions(path):
            return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body
                    if isinstance(n,ast.FunctionDef)}
        old=functions(ROOT/'tools/ms94_controller_v5.py');new=functions(ROOT/'tools/ms94_b04_controller.py')
        for name in ('public_prompt','assemble','candidate','tool_runtime'):
            self.assertEqual(old[name],new[name],name)
        from tools.ms94_controller_v5 import public_prompt
        self.assertEqual(canonical(public_prompt(ROOT)),canonical(controller.public_prompt(ROOT)))

    def test_transport_diff_is_only_controller_binding(self):
        old=(ROOT/'tools/ms94_transport_v5.py').read_text()
        new=(ROOT/'tools/ms94_b04_transport.py').read_text()
        self.assertEqual(old.replace('tools.ms94_controller_v5','tools.ms94_b04_controller'),new)

    def test_candidate_execution_block_is_exact_qualified_dated_block(self):
        def block(path):
            s=path.read_text();a=s.index('        runner=runner_type(root,run,plan,emit)')
            b=s.index('    except Exception as exc:',a)
            return s[a:b]
        self.assertEqual(block(ROOT/'tools/ms94_dated_native.py'),block(ROOT/'tools/ms94_b04_native.py'))


class ControllerFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.campaign=self.root/'campaign';self.signer=test_signer()
        self.plan=seal({'initial_prompt':{'public_trace_contract':{},'api_reference':{}},
                        'builder_client':{},'max_elapsed_seconds':7200,'max_client_invocations':5})
        save(self.campaign/'authorization.json',self.signer.sign({'plan_sha256':self.plan['content_sha256']}))
        save(self.root/'factory/idempiere/analyst-repair/api-provenance.json',{})
        self.roles=[];self.statuses=['execution-failure','passed'];self.suspect=False;self.cleanup=True
        self.diagnostics=[{'id':'runtime-1','category':'candidate-runtime-exception','exception_class':'AssertionError'}]
        def invoke(root,campaign,executable,role,prompt,schema,remaining):
            self.roles.append(role);folder=campaign/'calls'/f'{len(self.roles):03d}-{role}';folder.mkdir(parents=True)
            save(folder/'invocation.json',{'role':role});save(folder/'prompt.json',prompt)
            save(folder/'receipt.json',{'role':role,'usage':None,'elapsed_seconds':1})
            save(folder/'tool-transcript.json',[])
            return folder,{'edits':[{'replace':'candidate'}]}
        def candidate(root,campaign,folder,proposal):
            build=folder/'build';build.mkdir();return build,{}
        def native(root,campaign,build,builder,remaining):
            index=sum(x=='builder' for x in self.roles)-1;run=root/f'native-{index}'
            gate=seal({'status':self.statuses[index]});save(run/'gate.json',gate)
            receipt=self.signer.sign({'cleanup_complete':self.cleanup,'elapsed_seconds':2,'equipment_suspect':self.suspect})
            save(run/'receipt.json',receipt);return run,receipt
        patches=[(controller,'frozen',lambda *a,**k:self.plan),(controller,'JourneySigner',lambda root:self.signer),
                 (controller,'check_client',lambda *a:None),(controller,'candidate',candidate),
                 (controller,'audit',lambda *a:{'verified':True}),
                 (controller,'select_feedback',lambda observed,*a:observed),
                 (controller,'analyst_prompt',lambda observed,*a:{'diagnostics':observed}),
                 (controller,'analyst_schema',lambda observed:{})]
        for obj,name,value in patches:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        for name,value in [('tools.ms94_b04_transport.invoke',invoke),('tools.ms94_b04_native.execute_native',native),
                           ('tools.qualification_feedback_v4.export',lambda *a,**k:self.diagnostics),
                           ('tools.qualification_feedback_v4.equipment_suspect',lambda *a,**k:self.suspect)]:
            p=patch(name,value);p.start();self.addCleanup(p.stop)

    def run_trial(self):return controller.run(self.root,self.campaign,Path('unused'))

    def test_runtime_repair_and_no_restart(self):
        r=self.run_trial();self.assertEqual(r['status'],'passed');self.assertTrue(r['repaired_pass'])
        self.assertEqual(self.roles,['builder','analyst','builder'])
        self.assertTrue(r['metrics']['repair_conversion_eligible'])
        self.assertEqual(r['metrics']['execution_failures_with_diagnostic_sent'],1)
        self.assertTrue(verify_envelope(r,self.signer.public))
        with self.assertRaises(FileExistsError):self.run_trial()
        self.assertEqual(len(self.roles),3)

    def test_support_suspect_is_empty_and_never_sent(self):
        self.suspect=True;self.diagnostics=[]
        r=self.run_trial();self.assertEqual(r['status'],'halted-equipment-suspect')
        self.assertEqual(self.roles,['builder']);self.assertFalse(r['metrics']['repair_conversion_eligible'])

    def test_unqualified_support_feedback_fails_closed(self):
        self.suspect=True
        r=self.run_trial();self.assertEqual(r['status'],'halted-controller-failure');self.assertEqual(self.roles,['builder'])

    def test_business_failure_has_no_repair(self):
        self.statuses=['business-failure'];self.diagnostics=[]
        r=self.run_trial();self.assertEqual(r['status'],'halted-no-supported-repair');self.assertEqual(self.roles,['builder'])

    def test_equipment_failure_voids_before_analyst(self):
        self.statuses=['judge-error'];r=self.run_trial();self.assertEqual(r['status'],'void-equipment-failure')
        self.assertEqual(self.roles,['builder'])

    def test_insufficient_evidence_voids_before_analyst(self):
        self.statuses=['insufficient-evidence'];r=self.run_trial();self.assertEqual(r['status'],'void-equipment-failure')
        self.assertEqual(self.roles,['builder'])

    def test_cleanup_failure_stops_before_analyst(self):
        self.cleanup=False;r=self.run_trial();self.assertEqual(r['status'],'halted-controller-failure')
        self.assertEqual(self.roles,['builder'])

    def test_three_attempts_never_exceed_five_calls(self):
        self.statuses=['execution-failure']*3
        r=self.run_trial();self.assertEqual(r['status'],'halted-frozen-budget-exhausted')
        self.assertEqual(self.roles,['builder','analyst','builder','analyst','builder'])
        self.assertEqual(r['metrics']['execution_failures'],3)
        self.assertEqual(r['metrics']['execution_failures_with_diagnostic_sent'],2)

    def test_bad_authorization_cannot_call_model(self):
        auth=read_json(self.campaign/'authorization.json');auth['plan_sha256']='wrong';save(self.campaign/'authorization.json',auth)
        with self.assertRaises(CalibrationError):self.run_trial()
        self.assertEqual(self.roles,[])


class ReplayBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.run=self.root/'native';self.signer=test_signer()
        plan=seal({'harness_sha256':'candidate'});save(self.run/'plan.json',plan)
        self.body={'diagnostics':[],'equipment_suspect':True,'disposition':'halted-equipment-suspect',
                   'diagnostic_bytes_sha256':'empty','gate_sha256':'gate','candidate_sha256':'candidate'}
        projected=self.signer.sign(self.body);save(self.run/'diagnostic-projection.json',projected)
        save(self.run/'receipt.json',self.signer.sign({'plan_sha256':plan['content_sha256'],'cleanup_complete':True,
                                                    'diagnostic_projection_sha256':projected['content_sha256']}))
        save(self.run/'cleanup.json',self.signer.sign({'complete':True}))
        self.entry={'passed':True,'native_entry_checks':{'both':'checked'}}
        save(self.run/'a3-entry-admission.json',self.signer.sign(self.entry))
        for name,value in [('check',lambda run:seal(self.entry)),('projection',lambda root,run:self.body)]:
            p=patch.object(evidence,name,value);p.start();self.addCleanup(p.stop)

    def verify(self):return evidence.verify_attempt(self.root,self.run,self.signer.public)

    def test_all_entry_and_diagnostic_flags_required(self):
        result=self.verify();self.assertTrue(result['full_entry_replayed']);self.assertTrue(result['diagnostic_replayed'])

    def test_absent_entry_fails(self):
        (self.run/'a3-entry-admission.json').unlink()
        with self.assertRaises(CalibrationError):self.verify()

    def test_sealed_before_signing_entry_fails(self):
        save(self.run/'a3-entry-admission.json',self.signer.sign(seal(self.entry)))
        with self.assertRaises(CalibrationError):self.verify()

    def test_actual_diagnostics_suspicion_and_disposition_bound(self):
        for field,value in [('diagnostics',[{'unexpected':'private'}]),('equipment_suspect',False),('disposition','other')]:
            original=copy.deepcopy(self.body);self.body[field]=value
            with self.subTest(field=field),self.assertRaises(CalibrationError):self.verify()
            self.body=original

    def test_cleanup_failure_fails_even_with_signed_receipt(self):
        save(self.run/'cleanup.json',self.signer.sign({'complete':False}))
        with self.assertRaises(CalibrationError):self.verify()


class StatisticsTests(unittest.TestCase):
    def test_decision_thresholds_and_undefined_denominator(self):
        self.assertIn('works',decision(1,2,20));self.assertIn('partial',decision(1,5,20))
        self.assertIn('not-enough',decision(1,6,20));self.assertIn('undefined',decision(0,0,20))
        self.assertIn('void',decision(10,10,20,True));self.assertIn('incomplete',decision(10,10,19))

    def test_pilots_are_never_effectiveness_successes(self):
        m={'repair_conversion_eligible':True,'execution_failures':1,'execution_failures_with_diagnostic_sent':1,
           'execution_failures_with_diagnostic_exported':1,'post_repair_business_failures':0}
        r={'phase':'cohort','index':1,'first_try_pass':False,'repaired_pass':True,'metrics':m,
           'status':'passed','cost':{'usage_complete':True}}
        results=[copy.deepcopy(r) for _ in range(20)]
        results += [{**r,'phase':'pilot','first_try_pass':True} for _ in range(3)]
        result=summary(results);self.assertEqual(result['first_try_passes'],0)
        self.assertEqual(result['repair_passes'],20);self.assertEqual(result['repair_eligible'],20)
        self.assertEqual(result['repair_conversion'],1);self.assertEqual(result['diagnostic_coverage'],1)
        self.assertIsNone(summary(results,True)['repair_conversion'])


class CohortFailureTests(unittest.TestCase):
    def setUp(self):
        from tools import ms94_b04_measure as measure
        self.measure=measure;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'campaign';self.signer=test_signer()
        slots=[{'phase':phase,'index':i,'path':f'campaign/trials/{phase}-{i}','plan_sha256':'trial'}
               for phase,count in [('pilot',3),('cohort',20)] for i in range(1,count+1)]
        plan=seal({'slots':slots,'max_elapsed_seconds':93600,'max_client_invocations':115,'max_compilations':69,
                   'first_attempt_comparison':{'pooled_n40_allowed':False}})
        save(self.out/'plan.json',plan)
        for n in ('declaration.json','authorization.json'):
            save(self.out/n,self.signer.sign({'plan_sha256':plan['content_sha256'],'b04_publication_sha256':'pub'}))
        self.runs=0;self.replay_ok=True;self.status='passed';self.saw_stopping=False
        m={'repair_conversion_eligible':False,'execution_failures':0,'execution_failures_with_diagnostic_sent':0,
           'execution_failures_with_diagnostic_exported':0,'post_repair_business_failures':0}
        def run(*args):
            self.runs+=1
            return {'content_sha256':'receipt','status':self.status,'first_try_pass':True,'repaired_pass':False,
                    'attempts':[{'result_class':'passed','run_directory':'native'}],
                    'metrics':m,'cost':{'usage_complete':True,'client_invocations':1,'compilations':1}}
        def publish(*args):self.saw_stopping=(self.out/'stopping.json').exists()
        def replay(*args):
            return {'verified':True,'full_entry_replayed':self.replay_ok,'complete_gate_replayed':True,'diagnostic_replayed':True}
        for target,value in [('tools.ms94_b04_measure.JourneySigner',lambda root:self.signer),
                             ('tools.ms94_b04_admission.public_freeze',lambda *a:{'content_sha256':'pub'}),
                             ('tools.ms94_b04_controller.frozen',lambda *a:{'content_sha256':'trial'}),
                             ('tools.ms94_b04_controller.run',run),
                             ('tools.ms94_b04_publication.publish',publish),('tools.ms94_b04_publication.replay',replay)]:
            p=patch(target,value);p.start();self.addCleanup(p.stop)

    def test_exact_schedule_and_no_restart(self):
        r=self.measure.run(self.root,self.out,Path('unused'))
        self.assertEqual(self.runs,23);self.assertEqual(r['cohort_passed'],20)
        self.assertEqual(r['measurement']['first_try_passes'],20);self.assertFalse(r['cohort_void'])
        with self.assertRaises(FileExistsError):self.measure.run(self.root,self.out,Path('unused'))
        self.assertEqual(self.runs,23)

    def test_equipment_failure_notifies_before_archive_and_stops(self):
        self.status='invalid-provenance';r=self.measure.run(self.root,self.out,Path('unused'))
        self.assertTrue(self.saw_stopping);self.assertTrue(r['cohort_void']);self.assertEqual(self.runs,1)

    def test_incomplete_entry_replay_voids_and_stops(self):
        self.replay_ok=False;r=self.measure.run(self.root,self.out,Path('unused'))
        self.assertTrue(r['cohort_void']);self.assertEqual(self.runs,1)
        self.assertTrue((self.out/'stopping.json').exists())

    def test_support_suspicion_does_not_automatically_void(self):
        self.status='halted-equipment-suspect';r=self.measure.run(self.root,self.out,Path('unused'))
        self.assertFalse(r['cohort_void']);self.assertEqual(self.runs,23)
        self.assertEqual(len(r['measurement']['equipment_suspect_review_required']),23)


class ProspectivePublicationTests(unittest.TestCase):
    def test_missing_publication_blocks_authorization(self):
        from tools.ms94_b04_admission import public_freeze
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(CalibrationError):public_freeze(Path(t),Path(t)/'campaign',{},test_signer().public)

    def test_signed_but_incomplete_publication_is_rejected(self):
        from tools.ms94_b04_admission import public_freeze
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);out=root/'campaign';signer=test_signer()
            plan={'content_sha256':'plan','slots':[]}
            value={'plan_sha256':'plan','remote_verified':True,'all_remote_bytes_verified':True,
                   'public_before_generation':True,'commit':'a'*40,'files':{}}
            save(out/'published-plan.json',signer.sign(value))
            with self.assertRaises(CalibrationError):public_freeze(root,out,plan,signer.public)


if __name__=='__main__':unittest.main()
