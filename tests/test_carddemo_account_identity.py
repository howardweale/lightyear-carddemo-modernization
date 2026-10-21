"""CI-only receipt identity refusal fixtures; these do not replay proof."""
import copy
import unittest
from tools.carddemo_account_identity import GATES, JOBS, PROGRAMS, REQUEST, verify_receipt_identity


class ReceiptIdentityTests(unittest.TestCase):
    def setUp(self):
        self.source = 'a' * 40
        self.tested = 'b' * 40
        self.run = {'id': 123, 'head_sha': self.source, 'event': 'pull_request',
                    'run_started_at': '2026-10-19T17:18:50Z', 'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
                    'path': '.github/workflows/carddemo-web.yml',
                    'repository': {'full_name': 'howardweale/lightyear-carddemo-modernization'}}
        self.receipt = {'source_head': self.source, 'tested_commit': self.tested, 'run_id': '123',
                        'schema': 'carddemo-slice-receipt/1', 'status': 'proved-in-ci',
                        'unsigned': True, 'acceptance_complete': True, 'date': '2026-10-18',
                        'factory_request': copy.deepcopy(REQUEST), 'remaining_evidence_gaps': [],
                        'scope': {'programs': list(PROGRAMS)},
                        'gates': {key: {'passed': True} for key in GATES}}
        self.receipt['gates']['ci-jobs']['results'] = {key: {'outputs': {}, 'result': 'success'} for key in JOBS}

    def verify(self, receipt=None, run=None):
        return verify_receipt_identity(self.receipt if receipt is None else receipt,
                                       self.run if run is None else run, self.source, self.tested)

    def test_preserves_original_date_and_unsigned_authority(self):
        result = self.verify()
        self.assertEqual(result['original_receipt_date'], '2026-10-18')
        self.assertIs(result['activation_authorized'], False)
        self.assertIs(result['phase2_authorized'], False)

    def test_rejects_head_or_tested_commit_mix(self):
        for key in ('source_head', 'tested_commit'):
            receipt = copy.deepcopy(self.receipt); receipt[key] = 'c' * 40
            with self.subTest(key=key), self.assertRaises(ValueError): self.verify(receipt=receipt)
        run = copy.deepcopy(self.run); run['head_sha'] = 'c' * 40
        with self.assertRaises(ValueError): self.verify(run=run)

    def test_rejects_authority_expansion_and_boolean_alias(self):
        for key, value in (('activation_authorized', True), ('phase2_authorized', True),
                           ('signature', 'signed'), ('activation_authorized', 0)):
            receipt = copy.deepcopy(self.receipt); receipt['factory_request'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): self.verify(receipt=receipt)
        receipt = copy.deepcopy(self.receipt); receipt['unsigned'] = 1
        with self.assertRaises(ValueError): self.verify(receipt=receipt)

    def test_rejects_incomplete_or_foreign_workflow(self):
        for key, value in (('event', 'push'), ('status', 'in_progress'), ('conclusion', 'failure'),
                           ('path', 'other.yml'), ('run_attempt', True), ('id', True), ('id', 123.0)):
            run = copy.deepcopy(self.run); run[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): self.verify(run=run)
        run = copy.deepcopy(self.run); run['repository']['full_name'] = 'other/repo'
        with self.assertRaises(ValueError): self.verify(run=run)

    def test_rejects_missing_extra_failed_and_aliased_gates(self):
        for operation in ('missing', 'extra', 'failed', 'alias'):
            receipt = copy.deepcopy(self.receipt)
            if operation == 'missing': del receipt['gates']['browser']
            elif operation == 'extra': receipt['gates']['unknown'] = {'passed': True}
            else: receipt['gates']['browser']['passed'] = False if operation == 'failed' else 1
            with self.subTest(operation=operation), self.assertRaises(ValueError): self.verify(receipt=receipt)
        receipt = copy.deepcopy(self.receipt); receipt['gates']['ci-jobs']['results']['compose-smoke']['result'] = 'skipped'
        with self.assertRaises(ValueError): self.verify(receipt=receipt)

    def test_rejects_program_gaps_bad_date_and_incomplete_evidence(self):
        for key, value in (('date', '2026-02-30'), ('date', '20261018'), ('remaining_evidence_gaps', ['missing']),
                           ('acceptance_complete', 1), ('run_id', 123)):
            receipt = copy.deepcopy(self.receipt); receipt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.verify(receipt=receipt)
        receipt = copy.deepcopy(self.receipt); receipt['scope']['programs'].pop()
        with self.assertRaises(ValueError): self.verify(receipt=receipt)
