import copy,json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import CalibrationError,read_json,seal
from tools.ms94_b05_admission import validate_model_authorization,PLAN,DECLARATION
from tools.ms94_b05_controller import prepare_feedback,builder_prompt
from tools.ms94_b05_plan import period_guard
from tools.ms94_calendar import guard
from tests.test_qualification_feedback_v4 import RuntimeFeedbackTests

class B05AdmissionTests(unittest.TestCase):
    def auth(self):
        return dict(scope='b05-model-measurement-launch',model_calls_authorized=True,snapshot_sha256='s',
            preflight_report_sha256='p',publication_receipt_sha256='u',approved_plan_sha256=PLAN,
            approved_declaration_sha256=DECLARATION,operator_approval='Specific future approval',
            limits={'calls':115,'compilations':69,'seconds':93600})
    def test_preflight_cannot_authorize_models(self):
        for scope in ('b05-zero-model-preflight','preregistration',''):
            a=self.auth();a['scope']=scope
            with self.assertRaises(CalibrationError):validate_model_authorization(a,'s','p','u')
    def test_all_model_bindings_and_budgets_checked(self):
        validate_model_authorization(self.auth(),'s','p','u')
        for field in ('snapshot_sha256','preflight_report_sha256','publication_receipt_sha256','approved_plan_sha256','approved_declaration_sha256','model_calls_authorized','limits'):
            a=self.auth();a[field]=None
            with self.subTest(field=field),self.assertRaises(CalibrationError):validate_model_authorization(a,'s','p','u')
    def test_quoted_template_not_approval(self):
        a=self.auth();a['operator_approval']='I authorize snapshot <hash>'
        with self.assertRaises(CalibrationError):validate_model_authorization(a,'s','p','u')
    def test_transport_refuses_before_process_or_call_folder(self):
        from tools.ms94_b05_transport import invoke
        with tempfile.TemporaryDirectory() as d,patch('tools.ms94_b05_admission.model_authorization',side_effect=CalibrationError('No launch approval')),patch('subprocess.Popen') as proc:
            root=Path(d)
            with self.assertRaises(CalibrationError):invoke(root,root/'trial',root/'codex','builder',{}, {},10)
            proc.assert_not_called();self.assertEqual(list(root.iterdir()),[])
    def test_26h_guard_is_same_qualified_function(self):
        root=Path(__file__).resolve().parents[1]
        calendar=read_json(root/'factory/idempiere/ms94-b05-executable/preflight.json')['calendar']
        self.assertEqual(calendar['maximum_seconds'],93600)
        for stamp in ('2026-10-30T22:00:00+00:00','2026-10-31T00:00:00+00:00'):
            with self.assertRaises(CalibrationError):guard(calendar,datetime.fromisoformat(stamp))
        now=datetime.fromisoformat('2026-10-29T19:59:59+00:00');guard(calendar,now);period_guard(now,launching=True)
        with self.assertRaises(CalibrationError):period_guard(datetime.fromisoformat('2026-10-29T20:00:00+00:00'),launching=True)
    def test_fixed_trial_limits_and_prompt(self):
        root=Path(__file__).resolve().parents[1];area=root/'factory/idempiere/ms94-b05-executable'
        plans=[read_json(p) for p in area.glob('cohort-*.json')]+[read_json(p) for p in area.glob('pilot-*.json')]
        self.assertEqual(len(plans),23)
        for p in plans:
            self.assertEqual((p['max_client_invocations'],p['max_compilations'],p['max_elapsed_seconds']),(5,3,7200))
            self.assertEqual(p['initial_prompt'],read_json(root/'docs/calibration/idempiere-ms94/stage-b-05/builder-prompt.json'))
            self.assertFalse(p['preflight_only'])

class B05RoutingTests(RuntimeFeedbackTests):
    def test_candidate_direct_to_next_builder_prompt(self):
        from tools.qualification_feedback_v4 import export,equipment_suspect
        with patch('tools.qualification_feedback_v4.legacy_export',return_value=[]):
            observed=export(self.run,self.contract,root=self.root,api={})
        suspect=equipment_suspect(self.run,self.contract,root=self.root,api={})
        feedback=prepare_feedback(observed,suspect)
        self.assertEqual(feedback['diagnostics'],observed);self.assertIsNone(feedback['analyst_proposal'])
        actual=builder_prompt({'instruction':'unchanged'},'previous',feedback['diagnostics'])
        self.assertEqual(json.loads(json.dumps(actual))['analyst_feedback'],observed)
    def test_support_crash_nothing_delivered_and_halts(self):
        from tools.qualification_feedback_v4 import runtime
        self.write('execution-failure',1,origin='support')
        observed,suspect=runtime(self.run,self.contract,root=self.root,api={})
        self.assertEqual(prepare_feedback(observed,suspect),{'disposition':'halted-equipment-suspect','diagnostics':[]})
    def test_outside_crash_nothing_delivered_and_halts(self):
        from tools.qualification_feedback_v4 import runtime
        for p in self.run.glob('cases/*/*/execution/*/maven.log'):
            p.write_text('java.lang.IllegalStateException: secret\n\tat private.observer.Run.go(Observer.java:10)\n')
        observed,suspect=runtime(self.run,self.contract,root=self.root,api={})
        self.assertEqual(prepare_feedback(observed,suspect),{'disposition':'halted-equipment-suspect','diagnostics':[]})
    def test_application_origin_still_requires_analyst(self):
        from tools.qualification_feedback_v4 import export
        with patch('tools.qualification_feedback_v4.legacy_export',return_value=[]):
            observed=export(self.run,self.contract,root=self.root,api={})
        observed[0]['thrown_by']='application'
        with self.assertRaises(CalibrationError):prepare_feedback(observed,False)

if __name__=='__main__':unittest.main()
