"""Fail-closed domain projection; no compiler or application execution."""
import copy
import unittest
from lightyear_mainframe.loader_domain import SCENARIO, PROPOSAL, sealed, assess, project


class LoaderDomainTests(unittest.TestCase):
    def setUp(self):
        self.head = 'a' * 40
        self.receipts = [sealed(dict(head=self.head, scenario=SCENARIO, proposal_sha256=PROPOSAL,
            instrumented=mode, returncode=66, program_started=False,
            input_sha256={'TCATBALF': 'b' * 64}, duplicate_keys_hex={'00': 2})) for mode in (False, True)]
        run = dict(status='executed', returncode=0, outputs={'ACCTFILE': {'sha256': 'c' * 64}},
            stdout_sha256='d' * 64, stderr_sha256='e' * 64)
        self.rows = [dict(id='one', status='evidence-gap', disposition={'argument': 'proof'},
            evidence_gaps=[{'case': SCENARIO}], valid_domain_comparisons=[dict(case='valid',
                status='survived', baseline=run, actual=copy.deepcopy(run))])]

    def overlay(self):
        return assess(self.rows, [SCENARIO, 'valid'], *self.receipts, self.head)

    def test_preserves_raw_and_all_sites_without_credit(self):
        before = copy.deepcopy(self.rows)
        overlay = self.overlay()
        self.assertEqual('resolved-by-valid-comparisons', overlay['assessments'][0]['assessment'])
        self.assertEqual('equivalent (argued, listed)', project(self.rows, overlay)[0]['status'])
        self.assertEqual(before, self.rows)
        self.assertEqual(0, overlay['sites_removed'])
        self.assertFalse(overlay['effective'])
        self.assertFalse(overlay['release_authorized'])

    def test_no_blanket_gap_clear_or_missing_case_credit(self):
        for change in ('missing', 'duplicate', 'refused', 'different', 'other-gap'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.rows)
                r = self.rows[0]
                if change == 'missing': r['valid_domain_comparisons'] = []
                if change == 'duplicate': r['valid_domain_comparisons'] *= 2
                if change == 'refused': r['valid_domain_comparisons'][0]['actual']['status'] = 'execution-refusal'
                if change == 'different': r['valid_domain_comparisons'][0]['actual']['returncode'] = 12
                if change == 'other-gap': r['evidence_gaps'].append({'case': 'another'})
                self.assertEqual('still-a-gap', self.overlay()['assessments'][0]['assessment'])
                self.rows = original

    def test_wrong_head_mode_code_or_program_start_refuses(self):
        for key, value in [('head', 'f' * 40), ('instrumented', True), ('returncode', 0), ('program_started', True), ('scenario', 'posttran-duplicate')]:
            with self.subTest(key=key):
                original = self.receipts[0]
                changed = {k: v for k, v in original.items() if k != 'content_sha256'}
                changed[key] = value; self.receipts[0] = sealed(changed)
                with self.assertRaises(ValueError): self.overlay()
                self.receipts[0] = original

    def test_tampered_record_or_population_refuses_projection(self):
        overlay = self.overlay()
        self.rows[0]['disposition']['argument'] = 'changed'
        with self.assertRaises(ValueError): project(self.rows, overlay)
        with self.assertRaises(ValueError): project([], overlay)

    def test_receipt_digest_and_input_agreement_required(self):
        self.receipts[0]['returncode'] = 0
        with self.assertRaises(ValueError): self.overlay()


if __name__ == '__main__': unittest.main()
