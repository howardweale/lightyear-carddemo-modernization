import copy
import unittest
from pathlib import Path
from tools.ms94_diagnostic_controls_v6 import BASE,FAULTS,construct,assess
from tools.ms94_diagnostic_qualification_v6 import schedule


class DiagnosticQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=Path(BASE).read_text(encoding='utf-8')

    def test_only_test_support_control_changes_support(self):
        before=self.source.split('final class JourneySupport {',1)[1]
        for fault in FAULTS:
            candidate,expected=construct(self.source,fault)
            self.assertEqual(candidate.split('final class JourneySupport {',1)[1]==before,fault!='support-throw')
            if 'candidate_frame' in expected:
                line=candidate.splitlines()[expected['candidate_frame']['line']-1]
                self.assertTrue(any(x in line for x in ('throw new AssertionError','unloadedInvoice.getGrandTotal','new MInOut(wrongShipmentOrder')))

    def test_runtime_must_match_provenance_stage_class_and_both_lanes(self):
        _,expected=construct(self.source,'reversal-allocation-assertion')
        diagnostic={k:copy.deepcopy(v) for k,v in expected.items() if k not in ('status','equipment_suspect')}
        diagnostic.update(category='candidate-runtime-exception',lanes='both')
        manifest={'expected':expected};gate={'status':'execution-failure'}
        self.assertTrue(assess(gate,[diagnostic],False,manifest))
        for key,value in [('thrown_by','application'),('public_stage','invoice'),('exception_class','NullPointerException'),('lanes','one'),('candidate_frame',{'method':'require','line':1})]:
            changed={**diagnostic,key:value}
            self.assertFalse(assess(gate,[changed],False,manifest))
        self.assertFalse(assess(gate,[diagnostic,diagnostic],False,manifest))
        self.assertFalse(assess(gate,[],False,manifest))

    def test_support_case_requires_suppression_and_suspect(self):
        _,expected=construct(self.source,'support-throw');manifest={'expected':expected}
        self.assertTrue(assess({'status':'execution-failure'},[],True,manifest))
        self.assertFalse(assess({'status':'execution-failure'},[],False,manifest))
        self.assertFalse(assess({'status':'execution-failure'},[{'category':'trace-contract'}],True,manifest))

    def test_contract_fault_cannot_pass_as_judge_error_or_other_contract_failure(self):
        for fault in ('nonnumeric-order-id','missing-rollback-wait'):
            _,expected=construct(self.source,fault);manifest={'expected':expected}
            diagnostic={'category':'trace-contract','code':expected['code']}
            if 'field' in expected:diagnostic['field']=expected['field']
            self.assertTrue(assess({'status':'contract-violation'},[diagnostic],False,manifest))
            for status in ('passed','judge-error','insufficient-evidence','execution-failure'):
                self.assertFalse(assess({'status':status},[diagnostic],False,manifest))
            self.assertFalse(assess({'status':'contract-violation'},[{'category':'trace-contract','code':'undeclared-field'}],False,manifest))

    def test_schedule_has_six_faults_three_times_no_replacements(self):
        items=schedule(Path('.'))
        self.assertEqual(len(items),18)
        self.assertEqual(items,[{'fault':f,'repeat':i} for f in FAULTS for i in (1,2,3)])


if __name__=='__main__':unittest.main()
