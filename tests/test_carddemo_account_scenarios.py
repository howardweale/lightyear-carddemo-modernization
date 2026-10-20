"""Synthetic CI-only scenario denominator fixtures; no application replay."""
from copy import deepcopy
import unittest
from tools.carddemo_account_scenarios import MODES, PROGRAMS, verify_scenarios

HEAD = 'a'*40


def fixture():
    cases = [dict(id=f'case-{i}', status='passed', interactions=6 if i < 65 else 5) for i in range(119)]
    cases.append(dict(id='update-conflict', status='passed', interactions=14))
    rows = [dict(case=c['id']) for c in cases[:-1] for _ in range(c['interactions'])]
    rows += [dict(case=name) for name, count in [('update-conflict-reader', 7), ('update-conflict-writer', 7), ('account-update-inventory', 4)] for _ in range(count)]
    summary = dict(schema='carddemo-six-screen-proof/1', head=HEAD, passed=True,
        full_slice_screen_equivalence=True, remaining=[], programs_compared=sorted(PROGRAMS),
        required_programs=sorted(PROGRAMS), case_denominator_status='complete generated suite',
        completed_case_count=120, planned_case_count=120, interactions_compared=678,
        bms_interactions_compared=666, validated_fields=['ACSSTTE', 'ACSZIPC'], cases=cases)
    gate = dict(passed=True, planned_cases=120, completed_cases=120, interactions=678,
        programs_compared=6, programs_required=6, cases=deepcopy(cases), bms_interactions=666,
        case_denominator_status='complete generated suite', validated_fields=['ACSSTTE', 'ACSZIPC'])
    references = {mode: dict(summary=deepcopy(summary), rows=deepcopy(rows)) for mode in MODES}
    gates = {mode: deepcopy(gate) for mode in MODES}
    gates['browser'] = dict(passed=True, interactions=678, required=678)
    browser = dict(schema='carddemo-browser-proof/1', head=HEAD, passed=True,
        full_slice_screen_equivalence=True, programs_compared=sorted(PROGRAMS),
        interactions_compared=678, interactions_required=678)
    return gates, references, browser


class AccountScenarioTests(unittest.TestCase):
    def test_full_counts_and_inputs_preserved(self):
        args = fixture(); original = deepcopy(args)
        self.assertEqual(verify_scenarios(*args, HEAD), dict(journeys=120, interactions=678,
            named_case_interactions=674, setup_interactions=4, conflict_reader_interactions=7, conflict_writer_interactions=7))
        self.assertEqual(args, original)

    def test_missing_extra_rows_and_consistently_reduced_denominator_refused(self):
        for mode in MODES:
            for change in ('missing', 'extra', 'reduced'):
                args = fixture(); item = args[1][mode]
                if change == 'extra': item['rows'].append(deepcopy(item['rows'][0]))
                else: item['rows'].pop()
                if change == 'reduced':
                    item['summary']['interactions_compared'] = 677; args[0][mode]['interactions'] = 677
                with self.subTest(mode=mode, change=change), self.assertRaises(ValueError):
                    verify_scenarios(*args, HEAD)

    def test_duplicate_missing_or_failed_named_cases_refused(self):
        for change in ('duplicate', 'missing', 'failed', 'zero'):
            args = fixture(); cases = args[1]['api-reference']['summary']['cases']
            if change == 'duplicate': cases[1]['id'] = cases[0]['id']
            elif change == 'missing': cases.pop()
            elif change == 'failed': cases[0]['status'] = 'failed'
            else: cases[0]['interactions'] = 0
            with self.subTest(change=change), self.assertRaises(ValueError): verify_scenarios(*args, HEAD)

    def test_conflict_split_setup_and_unexplained_rows_refused(self):
        for old, new in [('update-conflict-reader', 'update-conflict-writer'),
                         ('account-update-inventory', 'case-0'), ('case-0', 'unexplained')]:
            args = fixture(); row = next(r for r in args[1]['mutation-reference']['rows'] if r['case'] == old)
            row['case'] = new
            with self.subTest(old=old, new=new), self.assertRaisesRegex(ValueError, 'row-groups'):
                verify_scenarios(*args, HEAD)

    def test_type_substitution_and_wrong_head_refused(self):
        for field, value in [('planned_case_count', 120.0), ('completed_case_count', True),
                             ('interactions_compared', 678.0), ('head', 'b'*40), ('passed', 1)]:
            args = fixture(); args[1]['browser-reference']['summary'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): verify_scenarios(*args, HEAD)

    def test_missing_modes_programs_and_incomplete_summary_refused(self):
        for change in ('mode', 'program', 'remaining', 'equivalence'):
            args = fixture(); summary = args[1]['api-reference']['summary']
            if change == 'mode': del args[1]['mutation-reference']
            elif change == 'program': summary['programs_compared'].pop()
            elif change == 'remaining': summary['remaining'] = ['missing proof']
            else: summary['full_slice_screen_equivalence'] = False
            with self.subTest(change=change), self.assertRaises(ValueError): verify_scenarios(*args, HEAD)

    def test_receipt_gate_and_browser_claims_refused(self):
        for target, field, value in [('gate', 'interactions', 678.0), ('gate', 'programs_required', 5),
                                     ('gate', 'passed', False), ('browser', 'head', 'b'*40),
                                     ('browser', 'interactions_required', 677), ('browser', 'passed', 1)]:
            args = fixture(); value_target = args[0]['api-reference'] if target == 'gate' else args[2]
            value_target[field] = value
            with self.subTest(target=target, field=field), self.assertRaises(ValueError): verify_scenarios(*args, HEAD)

    def test_internally_consistent_different_mode_cases_refused(self):
        args = fixture(); mode = 'mutation-reference'; item = args[1][mode]
        item['summary']['cases'][0]['id'] = 'replacement'; args[0][mode]['cases'][0]['id'] = 'replacement'
        for row in item['rows']:
            if row['case'] == 'case-0': row['case'] = 'replacement'
        with self.assertRaisesRegex(ValueError, 'mode-inventory'): verify_scenarios(*args, HEAD)


if __name__ == '__main__':
    unittest.main()
