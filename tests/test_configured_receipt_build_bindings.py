"""CI-only untrusted relationships; no controller, key, admission or API."""
import copy,os,unittest
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_execution.configured_receipt_build_bindings import verify_configured_terminal_build
from lightyear_execution.configured_receipt_tail import verify_configured_receipt_tail
import test_configured_receipt_build_tail as tail_examples


def refresh(receipt,summary,events):
    receipt['factory_build_receipt']=tail_examples.hashed(receipt['factory_build_receipt'])
    receipt=tail_examples.hashed(receipt)
    summary.update(receipt_sha256=receipt['content_sha256'],status=receipt['status'])
    events[1]=tail_examples.scan('factory-build-receipt',receipt['factory_build_receipt'])
    events[2]['payload']=copy.deepcopy(receipt['factory_build_receipt'])
    events[3]=tail_examples.scan('run-receipt',receipt)
    events[4]=tail_examples.scan('run-summary',summary)
    return receipt,summary,events


def records(passed=True):
    receipt,summary,events=tail_examples.records(passed)
    for section in ('intelligence','execution_security','candidate_package_finalization'):
        receipt[section]=tail_examples.hashed(dict(untrusted_example=section,observed_count=1))
    build=receipt['factory_build_receipt']
    build.update(accounting_sha256=canonical_hash(receipt['intelligence']),
        execution_security_sha256=receipt['execution_security']['content_sha256'],
        candidate_package_sha256=receipt['candidate_package_finalization']['content_sha256'])
    return refresh(receipt,summary,events)


class ConfiguredReceiptBuildBindings(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
    def test_matched_passed_and_blocked_relationships_preserve_inputs(self):
        for passed in (True,False):
            value=records(passed);before=copy.deepcopy(value)
            self.assertEqual(verify_configured_terminal_build(*value),3)
            self.assertEqual(value,before)
    def test_intelligence_whole_document_reference_is_required(self):
        receipt,summary,events=records()
        receipt['factory_build_receipt']['accounting_sha256']=receipt['intelligence']['content_sha256']
        value=refresh(receipt,summary,events)
        self.assertEqual(verify_configured_receipt_tail(*value),3)
        with self.assertRaisesRegex(ContractError,'section-binding'):
            verify_configured_terminal_build(*value)
    def test_security_reference_substitution_refuses(self):
        receipt,summary,events=records()
        receipt['execution_security']=tail_examples.hashed(dict(untrusted_example='changed-security'))
        value=refresh(receipt,summary,events)
        self.assertEqual(verify_configured_receipt_tail(*value),3)
        with self.assertRaisesRegex(ContractError,'section-binding'):verify_configured_terminal_build(*value)
    def test_package_reference_substitution_refuses(self):
        receipt,summary,events=records()
        receipt['candidate_package_finalization']=tail_examples.hashed(dict(untrusted_example='changed-package'))
        value=refresh(receipt,summary,events)
        self.assertEqual(verify_configured_receipt_tail(*value),3)
        with self.assertRaisesRegex(ContractError,'section-binding'):verify_configured_terminal_build(*value)
    def test_boolean_integer_substitution_cannot_use_python_mapping_equality(self):
        receipt,summary,events=records()
        receipt['intelligence']['observed_count']=True
        receipt['intelligence']=tail_examples.hashed(receipt['intelligence'])
        value=refresh(receipt,summary,events)
        with self.assertRaisesRegex(ContractError,'section-binding'):verify_configured_terminal_build(*value)
    def test_missing_non_mapping_and_invalid_section_digests_refuse(self):
        for section in ('intelligence','execution_security','candidate_package_finalization'):
            for change in ('missing','list','digest'):
                receipt,summary,events=records()
                if change=='missing':del receipt[section]
                elif change=='list':receipt[section]=[]
                else:receipt[section]['content_sha256']='0'*64
                with self.subTest(section=section,change=change),self.assertRaisesRegex(ContractError,'section-digest'):
                    verify_configured_terminal_build(*refresh(receipt,summary,events))
    def test_missing_build_references_refuse_after_valid_tail(self):
        for reference in ('accounting_sha256','execution_security_sha256','candidate_package_sha256'):
            receipt,summary,events=records();del receipt['factory_build_receipt'][reference]
            value=refresh(receipt,summary,events)
            self.assertEqual(verify_configured_receipt_tail(*value),3)
            with self.subTest(reference=reference),self.assertRaisesRegex(ContractError,'section-binding'):
                verify_configured_terminal_build(*value)
    def test_early_refusal_and_tail_failure_stay_unchanged(self):
        receipt={'ledger_head_sha256':'a'*64};summary={};events=[{'event_sha256':'a'*64}]
        self.assertEqual(verify_configured_terminal_build(receipt,summary,events),1)
        with self.assertRaisesRegex(ContractError,'snapshot-missing'):
            verify_configured_terminal_build(receipt,summary,[])
        receipt,summary,events=records();events.pop()
        with self.assertRaisesRegex(ContractError,'exact-two-final-scans'):
            verify_configured_terminal_build(receipt,summary,events)
