"""CI-only native scanner probes; pure classification never registers origin."""
import base64,unittest
import test_configured_receipt_scan_observation as fixtures
from lightyear_factory.contracts import ContractError
from lightyear_factory.isolation_scan import scan
from lightyear_execution.configured_receipt_scan_match import classify_stopping_view
from lightyear_execution.configured_receipt_scan_observation import record_original_context_scan_failure


class NativeStoppingViewTests(unittest.TestCase):
    def native_match(self,raw,expected):
        try:scan([('controller-context',raw)],fixtures.CANARIES,expected)
        except ContractError as error:
            self.assertEqual(error.args,('isolation-breach',))
            trace=error.__traceback__
            try:
                while trace.tb_next is not None:trace=trace.tb_next
                self.assertIs(trace.tb_frame.f_code,scan.__code__)
                values=trace.tb_frame.f_locals
                return classify_stopping_view(values['tokens'],values['windows'],values['normalized'])
            finally:del trace
        self.fail('expected original native breach')
    def test_original_expected_window_match(self):
        self.assertEqual(self.native_match(fixtures.PUBLIC.encode(),[fixtures.PUBLIC]),'expected-window')
    def test_native_normalized_expected_window_match(self):
        raw=' '.join(fixtures.PUBLIC.upper()).encode()
        self.assertEqual(self.native_match(raw,[fixtures.PUBLIC]),'expected-window')
    def test_native_canary_is_not_labelled_expected_window(self):
        raw=next(iter(fixtures.CANARIES.values())).encode()
        self.assertEqual(self.native_match(raw,[fixtures.PUBLIC]),'canary')
    def test_both_match_same_native_stopping_view(self):
        raw=(fixtures.PUBLIC+' '+next(iter(fixtures.CANARIES.values()))).encode()
        self.assertEqual(self.native_match(raw,[fixtures.PUBLIC]),'canary-and-expected-window')
    def test_native_decoded_expected_window_match(self):
        self.assertEqual(self.native_match(base64.b64encode(fixtures.PUBLIC.encode()),[fixtures.PUBLIC]),'expected-window')
    def test_no_matching_view_refuses(self):
        with self.assertRaisesRegex(ContractError,'no-native-match'):
            classify_stopping_view(set(fixtures.CANARIES.values()),{'public answer fragment'},'ordinary context')
    def test_invalid_native_local_shapes_refuse(self):
        tokens=set(fixtures.CANARIES.values())
        for args in ((list(tokens),set(),'x'),(tokens,{''},'x'),(tokens,[], 'x'),
                     (tokens,set(),b'x'),({'short'},set(),'x'),(tokens,{True},'x')):
            with self.subTest(args=args),self.assertRaisesRegex(ContractError,'match-shape'):
                classify_stopping_view(*args)
    def test_classification_does_not_grant_original_registration(self):
        self.assertEqual(classify_stopping_view(set(fixtures.CANARIES.values()),{'public'},'public'),'expected-window')
        with self.assertRaisesRegex(ContractError,'original-controller-required'):
            record_original_context_scan_failure(object(),'controller-context',ContractError('isolation-breach'))
