"""CI-only native scanner/pure descriptor refusals; no admitted origin fabricated."""
import hashlib
import unittest
from lightyear_factory.contracts import ContractError
from lightyear_factory.isolation_scan import scan,MAX_BYTES
from lightyear_execution.configured_receipt_scan_observation import (
    _describe_failed_bytes,record_original_context_scan_failure,emit_original_context_scan_failure)

PUBLIC='synthetic-account-7e091c2d-amount-178352.91-balance-782146.32'
CANARIES={k:hashlib.sha256(('public-'+k).encode()).hexdigest()
    for k in ('expected-state','reference-output','session-answer')}


class OriginalContextScanObservationTests(unittest.TestCase):
    def test_native_normalized_breach_descriptor_contains_only_digest_size(self):
        raw=(' '.join(PUBLIC.upper())).encode()
        try:scan([('controller-context',raw)],CANARIES,[PUBLIC])
        except ContractError as error:
            self.assertEqual(error.args,('isolation-breach',))
            descriptor=_describe_failed_bytes('controller-context',raw,error)
        else:self.fail('native scanner did not refuse public normalized fragment')
        self.assertEqual(descriptor,(hashlib.sha256(raw).hexdigest(),len(raw)))
        self.assertNotIn(PUBLIC,str(descriptor))

    def test_native_clean_scan_remains_passed(self):
        row=scan([('controller-context',b'ordinary public context')],CANARIES,[PUBLIC])
        self.assertEqual(row['status'],'passed')

    def test_wrong_native_reason_is_not_breach(self):
        with self.assertRaisesRegex(ContractError,'observation-shape'):
            _describe_failed_bytes('controller-context',b'x',ContractError('isolation-scan-limit'))

    def test_exception_subclass_cannot_supply_breach_descriptor(self):
        class Derived(ContractError):pass
        with self.assertRaisesRegex(ContractError,'observation-shape'):
            _describe_failed_bytes('controller-context',b'x',Derived('isolation-breach'))

    def test_wrong_or_early_surface_refused(self):
        for name in ('initial-workspace-file','planner-prompt','',True):
            with self.subTest(name=name),self.assertRaisesRegex(ContractError,'observation-shape'):
                _describe_failed_bytes(name,b'x',ContractError('isolation-breach'))

    def test_bytes_type_and_bounds_refused(self):
        for raw in ('x',bytearray(b'x'),b'',b'x'*(MAX_BYTES+1)):
            with self.assertRaisesRegex(ContractError,'observation-shape'):
                _describe_failed_bytes('controller-context',raw,ContractError('isolation-breach'))

    def test_no_unadmitted_registration_from_pure_descriptor(self):
        raw=b'public';error=ContractError('isolation-breach')
        self.assertEqual(_describe_failed_bytes('controller-context',raw,error)[1],6)
        with self.assertRaisesRegex(ContractError,'original-controller-required'):
            record_original_context_scan_failure(object(),'controller-context',error)

    def test_no_unadmitted_emission(self):
        with self.assertRaisesRegex(ContractError,'original-controller-required'):
            emit_original_context_scan_failure(object())
