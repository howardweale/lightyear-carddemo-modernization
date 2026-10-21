"""CI-only scope projection fixtures using committed account scope inputs."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from tools.carddemo_account_scope import project_scope, scope_paragraph

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    'account_input_java': 'idiomatic-account-input-scope.json',
    'account_text_money_java': 'idiomatic-account-text-money-scope.json',
    'account_ssn_fico_java': 'idiomatic-account-ssn-fico-scope.json',
    'account_location_java': 'idiomatic-account-location-scope.json',
}


def fixture():
    scopes = {key: json.loads((ROOT/'spec/modernization/carddemo-screens'/name).read_bytes())
              for key, name in PATHS.items()}
    source = deepcopy(scopes['account_input_java']['source'])
    group = dict(program='COACTUPC', whole_screen_idiomatic=False, publication_date='2026-10-19')
    return group, scopes, source


class AccountScopeProjectionTests(unittest.TestCase):
    def test_separate_dates_and_unchanged_scope_inputs(self):
        group, scopes, source = fixture(); before = deepcopy(scopes)
        value = project_scope(group, scopes, source, '2026-10-18')
        self.assertEqual(value['measurement_date'], '2026-10-18')
        self.assertEqual(value['publication_date'], '2026-10-19')
        self.assertFalse(value['whole_screen_idiomatic'])
        self.assertEqual(value['validation_paragraph_count'], 12)
        self.assertEqual(scopes, before)

    def test_text_changes_with_bound_date_and_scope(self):
        group, scopes, source = fixture()
        original = scope_paragraph(project_scope(group, scopes, source, '2026-10-18'))
        group['publication_date'] = '2026-10-20'
        changed = scope_paragraph(project_scope(group, scopes, source, '2026-10-18'))
        self.assertNotEqual(original, changed); self.assertIn('2026-10-20', changed)
        scopes['account_input_java']['validation_paragraphs'].append('1290-FIXTURE-ONLY')
        expanded = scope_paragraph(project_scope(group, scopes, source, '2026-10-18'))
        self.assertNotEqual(changed, expanded); self.assertIn('13 validation paragraphs', expanded)

    def test_whole_screen_and_program_relabel_refused(self):
        for field, value in (('whole_screen_idiomatic', True), ('whole_screen_idiomatic', 0), ('program', 'COSGN00C')):
            group, scopes, source = fixture(); group[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): project_scope(group, scopes, source, '2026-10-18')

    def test_every_scope_keeps_engine_source_and_program(self):
        for key in PATHS:
            for field, value in (('program', 'COSGN00C'), ('source', {}), ('remaining_statement_engine_programs', ['COACTVWC'])):
                group, scopes, source = fixture(); scopes[key][field] = value
                with self.subTest(key=key, field=field), self.assertRaises(ValueError): project_scope(group, scopes, source, '2026-10-18')

    def test_missing_group_and_empty_duplicate_overlapping_paragraphs_refused(self):
        for kind in ('missing', 'empty', 'duplicate', 'overlap', 'bad-name'):
            group, scopes, source = fixture(); target = scopes['account_ssn_fico_java']
            if kind == 'missing': del scopes['account_ssn_fico_java']
            elif kind == 'empty': target['validation_paragraphs'] = []
            elif kind == 'duplicate': target['validation_paragraphs'] *= 2
            elif kind == 'overlap': target['validation_paragraphs'] = scopes['account_input_java']['validation_paragraphs'][:]
            else: target['validation_paragraphs'] = ['not-a-paragraph']
            with self.subTest(kind=kind), self.assertRaises(ValueError): project_scope(group, scopes, source, '2026-10-18')

    def test_invalid_or_backdated_publication_refused(self):
        for value in ('2026-10-17', '2026-02-30', '20261019', None):
            group, scopes, source = fixture(); group['publication_date'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): project_scope(group, scopes, source, '2026-10-18')

    def test_missing_or_duplicate_method_and_java_lists_refused(self):
        for field in ('rule_methods', 'java_files'):
            for value in (None, [], ['x', 'x'], ['']):
                group, scopes, source = fixture(); scopes['account_input_java'][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError): project_scope(group, scopes, source, '2026-10-18')

    def test_additional_location_scope_is_not_silently_projected(self):
        group, scopes, source = fixture()
        scopes['account_future_java'] = deepcopy(scopes['account_input_java'])
        with self.assertRaisesRegex(ValueError, 'account-publication-scope'):
            project_scope(group, scopes, source, '2026-10-18')
