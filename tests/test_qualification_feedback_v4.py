import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import seal
from tools import qualification_feedback_v4 as feedback


class RuntimeFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.run = self.root/'run'
        (self.run/'inputs').mkdir(parents=True)
        self.source = ('public class LightyearOperationsTest {\n'
                       ' public void journey() {\n'
                       '  throw new IllegalStateException("private amount");\n'
                       ' }\n}\nfinal class JourneySupport {\n void postOnce() {}\n}\n')
        (self.run/'inputs/operations.java').write_text(self.source)
        self.contract = {'trace_fields':['invoice.id','failure','creditReversal.id'],'optional_trace_fields':['failure']}
        self.write('execution-failure', 1)

    def write(self, status, code, message='private amount', origin='candidate'):
        (self.run/'gate.json').write_text(json.dumps(seal({'status':status})))
        for lane in ('oracle','postgresql'):
            p = self.run/'cases/operations/1/execution'/lane; p.mkdir(parents=True,exist_ok=True)
            (p/'execution.json').write_text(json.dumps(seal({'exit_code':code})))
            frame = ('\tat org.idempiere.test.JourneySupport.postOnce(LightyearOperationsTest.java:7)\n' if origin=='support' else '')
            (p/'maven.log').write_text('java.lang.IllegalStateException: '+message+'\n'+frame+
                '\tat org.idempiere.test.LightyearOperationsTest.journey(LightyearOperationsTest.java:3)\n'+
                '\tat org.idempiere.test.JourneySupport.transaction(LightyearOperationsTest.java:7)\n')
            (p/'journey.xml').write_text('<properties><entry key="invoice.id">123</entry></properties>')

    def test_private_messages_and_trace_values_do_not_change_bytes(self):
        with patch.object(feedback,'legacy_export',return_value=[]):
            a=feedback.export(self.run,self.contract,root=self.root,api={})
            self.write('execution-failure',1,'different secret identifier 987654')
            for p in self.run.glob('cases/*/*/execution/*/journey.xml'):
                p.write_text('<properties><entry key="invoice.id">987654</entry></properties>')
            b=feedback.export(self.run,self.contract,root=self.root,api={})
        self.assertEqual(a,b);self.assertEqual(a[0]['lanes'],'both')
        self.assertEqual(a[0]['public_stage'],'invoice');self.assertNotIn('api_call',a[0])
        self.assertNotIn('secret',json.dumps(a));self.assertNotIn('123',json.dumps(a))

    def test_support_suppresses_even_legacy_feedback(self):
        self.write('execution-failure',1,origin='support')
        with patch.object(feedback,'legacy_export',return_value=[{'id':'structural-1'}]):
            self.assertEqual(feedback.export(self.run,self.contract,root=self.root,api={}),[])
        self.assertTrue(feedback.equipment_suspect(self.run,self.contract,root=self.root,api={}))

    def test_transaction_wrapper_below_candidate_is_not_support_origin(self):
        out,suspect=feedback.runtime(self.run,self.contract,root=self.root,api={})
        self.assertFalse(suspect);self.assertEqual(out[0]['thrown_by'],'candidate')

    def test_unlisted_exception_is_other(self):
        for p in self.run.glob('cases/*/*/execution/*/maven.log'):
            p.write_text(p.read_text().replace('java.lang.IllegalStateException','private.example.SecretException'))
        out,_=feedback.runtime(self.run,self.contract,root=self.root,api={})
        self.assertEqual(out[0]['exception_class'],'other')

    def test_outside_candidate_has_no_diagnostic(self):
        for p in self.run.glob('cases/*/*/execution/*/maven.log'):
            p.write_text('java.lang.IllegalStateException: secret\n\tat private.observer.Run.go(Observer.java:10)\n')
        out,suspect=feedback.runtime(self.run,self.contract,root=self.root,api={})
        self.assertEqual(out,[]);self.assertTrue(suspect)

    def test_entry_order_and_values_are_not_chronology(self):
        p=self.root/'trace.xml'
        p.write_text('<properties><entry key="creditReversal.id">9</entry><entry key="invoice.id">7</entry></properties>')
        self.assertEqual(feedback.stage(p,self.contract),'reversal allocation')
        p.write_text('<properties><entry key="invoice.id">7</entry><entry key="invoice.id">8</entry></properties>')
        self.assertIsNone(feedback.stage(p,self.contract))

    def test_business_failure_exports_legacy_unchanged(self):
        self.write('business-failure',0)
        expected=[{'id':'structural-1','category':'compile-error'}]
        with patch.object(feedback,'legacy_export',return_value=expected) as legacy:
            self.assertEqual(feedback.export(self.run,self.contract,root=self.root,api={}),expected)
            legacy.assert_called_once()

    def test_application_throw_with_candidate_caller(self):
        for p in self.run.glob('cases/*/*/execution/*/maven.log'):
            p.write_text('org.adempiere.exceptions.AdempiereException: secret\n'
                         '\tat org.compiere.model.PO.saveEx(PO.java:100)\n'
                         '\tat org.idempiere.test.LightyearOperationsTest.journey(LightyearOperationsTest.java:3)\n')
        out,suspect=feedback.runtime(self.run,self.contract,root=self.root,api={})
        self.assertFalse(suspect);self.assertEqual(out[0]['thrown_by'],'application')

    def test_no_trace_omits_stage(self):
        for p in self.run.glob('cases/*/*/execution/*/journey.xml'):p.unlink()
        out,_=feedback.runtime(self.run,self.contract,root=self.root,api={})
        self.assertNotIn('public_stage',out[0])


if __name__=='__main__':unittest.main()
