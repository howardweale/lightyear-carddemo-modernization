import copy
import json
import unittest
from tools.check_oct12_operator_review import ROOT, DECISION, validate, seal, validate_domain_approval


class OperatorReviewTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads((ROOT / DECISION).read_text())

    def altered(self):
        self.d['content_sha256'] = seal({k: v for k, v in self.d.items() if k != 'content_sha256'})
        return self.d

    def test_bound_review_and_deduplication(self):
        self.assertEqual(validate()['pending_evidence_items'], [20, 23, 42])
        self.assertEqual(validate()['new_decisions'], 44)

    def test_new_zos_scope_refused(self):
        self.d['new_acceptances'][0]['new_zos_facing_acceptance'] = True
        with self.assertRaisesRegex(ValueError, 'scope'):
            validate(decision=self.altered())

    def test_pending_cannot_activate_without_verified_receipt(self):
        next(r for r in self.d['new_acceptances'] if r['item'] == 20)['effective_for_individual_review'] = True
        with self.assertRaisesRegex(ValueError, 'conditional-acceptance'):
            validate(decision=self.altered())

    def test_cross_head_evidence_refused(self):
        next(r for r in self.d['new_acceptances'] if r['item'] == 42)['required_evidence']['head'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'rerun-binding'):
            validate(decision=self.altered())

    def test_register_fix_invalidates_each_dependency(self):
        original = json.loads((ROOT / 'docs/factory/keep-or-fix-register.json').read_text())
        for key in ['REWRITE-109', 'CBACT04C-FINAL-ACCOUNT-EOF-ELSE']:
            register = copy.deepcopy(original)
            next(r for r in register['defects'] if r['id'] == key)['fix_authorized'] = True
            with self.assertRaisesRegex(ValueError, 'register-changed'):
                validate(register=register)

    def test_constant_source_change_invalidates(self):
        self.d['constant_field_acceptances'][0]['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source-binding'):
            validate(decision=self.altered())

    def test_duplicate_acceptance_refused(self):
        self.d['new_acceptances'].append(self.d['existing_acceptance_references'][0])
        with self.assertRaisesRegex(ValueError, 'deduplication'):
            validate(decision=self.altered())


    def test_domain_approval_cannot_waive_fresh_evidence_or_expand_scope(self):
        folder = ROOT / 'docs/factory'
        proposal_text = (folder / 'intcalc-duplicate-category-proposal-2026-10-12.json').read_text()
        proposal = json.loads(proposal_text)
        original = json.loads((folder / 'intcalc-duplicate-category-approval-2026-10-12.json').read_text())
        validate_domain_approval(original, proposal, proposal_text)
        for field, value, reason in [('effective', True, 'fresh-evidence-required'), ('new_zos_facing_acceptances', 1, 'approval-limits'), ('proposal_content_sha256', '0' * 64, 'approved-proposal-binding')]:
            changed = copy.deepcopy(original)
            changed[field] = value
            changed['content_sha256'] = seal({k: v for k, v in changed.items() if k != 'content_sha256'})
            with self.assertRaisesRegex(ValueError, reason):
                validate_domain_approval(changed, proposal, proposal_text)


if __name__ == '__main__':
    unittest.main()
