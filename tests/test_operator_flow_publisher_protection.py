"""CI-only untrusted repository-configuration relationships; no API or approval."""
import copy,unittest
from tools.ci.operator_flow_publisher_preflight import (_protection_digest,
    _check_repository_protection,_expected_protection,_protection_snapshot)
class PublisherProtection(unittest.TestCase):
    def setUp(self):
        self.protection={'enforce_admins':{'enabled':True},'required_status_checks':{'strict':True,'contexts':['required-ci']}}
        self.rules=[{'type':'required_signatures'},{'type':'pull_request','parameters':{'required_approving_review_count':1}}]
        self.expected=(_protection_digest(self.protection),_protection_digest(self.rules))
    def check(self):return _check_repository_protection(self.protection,self.rules,*self.expected)
    def test_matching_complete_records_return_only_digests(self):
        before=copy.deepcopy((self.protection,self.rules));self.assertEqual(self.check(),self.expected)
        self.assertEqual(before,(self.protection,self.rules));self.assertEqual(len(self.check()),2)
    def test_changed_required_check_refuses(self):
        self.protection['required_status_checks']['contexts']=[]
        with self.assertRaisesRegex(ValueError,'protection-or-rules-changed'):self.check()
    def test_boolean_integer_substitution_refuses(self):
        self.protection['enforce_admins']['enabled']=1
        with self.assertRaisesRegex(ValueError,'protection-or-rules-changed'):self.check()
    def test_changed_rules_refuse(self):
        self.rules[1]['parameters']['required_approving_review_count']=0
        with self.assertRaisesRegex(ValueError,'protection-or-rules-changed'):self.check()
    def test_rule_order_change_refuses(self):
        self.rules.reverse()
        with self.assertRaisesRegex(ValueError,'protection-or-rules-changed'):self.check()
    def test_wrong_native_record_shapes_refuse(self):
        for protection,rules in (([],self.rules),(self.protection,{}),(None,self.rules)):
            with self.subTest(protection=protection),self.assertRaisesRegex(ValueError,'native-protection-shapes'):
                _check_repository_protection(protection,rules,*self.expected)
    def test_missing_or_malformed_independent_expectations_refuse(self):
        for value in (None,True,'','A'*64,'0'*63):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'independent-protection-digests'):
                _expected_protection(value,self.expected[1])
    def test_public_native_reader_refuses_missing_expectations_before_api(self):
        with self.assertRaisesRegex(ValueError,'independent-protection-digests'):_protection_snapshot(None,None)
