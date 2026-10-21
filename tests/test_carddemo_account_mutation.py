"""CI-only complete mutation-gate reconciliation fixtures."""
import copy
from hashlib import sha256
import unittest
from tools.carddemo_account_mutation import verify_mutation_gate


class MutationGateTests(unittest.TestCase):
    def setUp(self):
        self.groups = {'account_input_java': ['AccountInputRules'],
                       'account_text_money_java': ['AccountTextRules', 'AccountMoneyRule', 'CobolNumber'],
                       'account_ssn_fico_java': ['AccountSsnRule', 'AccountFicoRule'],
                       'account_location_java': ['AccountLocationRules']}
        self.names = ['SignonService', 'SignonRules', 'MenuService', 'AccountViewService',
                      'AccountUpdateService', 'AuthorizationListService', 'AuthorizationDetailService']
        self.names += [name for names in self.groups.values() for name in names]
        def xml(names):
            return ('<mutations>' + ''.join('<mutation status="KILLED"><mutatedClass>p.' + name +
                    '</mutatedClass><mutatedMethod>x</mutatedMethod><lineNumber>1</lineNumber>'
                    '<mutator>M</mutator><description>D</description></mutation>' for name in names for _ in range(10)) + '</mutations>').encode()
        self.raw = xml(self.names); self.old = xml(['SignonService'])
        summary = {'total': 10, 'killed': 10, 'percent': 100.0, 'status_counts': {'KILLED': 10}, 'passed': True, 'non_killed': []}
        self.gate = {'passed': True, 'killed': 140, 'total': 140, 'percent': 100.0, 'threshold': 90,
                     'missing_screen_handlers': [], 'status_counts': {'KILLED': 140},
                     'denominator': 'every PIT mutation in configured screen-handler/helper scope; timeout, no-coverage and errors are not counted killed',
                     'report': {'path': 'work/carddemo-proof-artifacts/carddemo-proof-mutation/pit-reports/mutations.xml', 'sha256': sha256(self.raw).hexdigest()},
                     'idiomatic_java': {'schema': 'carddemo-idiomatic-mutation/1', 'program': 'COSGN00C',
                        'passed': True, 'threshold': 90, 'denominator': 'all generated mutants per required class; KILLED only',
                        'previous': {'report': 'docs/modernization/carddemo-slice-1-evidence-2026-10-18/mutations.xml',
                                     'sha256': sha256(self.old).hexdigest(), 'classes': {'SignonService': copy.deepcopy(summary)}},
                        'current': {name: copy.deepcopy(summary) for name in ('SignonService', 'SignonRules')},
                        'remaining_statement_engine_programs': ['COACTVWC', 'COACTUPC', 'COPAUS0C', 'COPAUS1C']}}
        for group, names in self.groups.items(): self.gate[group] = {name: copy.deepcopy(summary) for name in names}

    def test_accepts_complete_synthetic_gate(self):
        self.assertEqual(verify_mutation_gate(self.raw, self.old, self.gate)['total'], 140)

    def test_refuses_timeout_credit_with_matching_current_hash(self):
        raw = self.raw.replace(b'status="KILLED"', b'status="TIMED_OUT"', 1)
        gate = copy.deepcopy(self.gate); gate['report']['sha256'] = sha256(raw).hexdigest()
        with self.assertRaises(ValueError): verify_mutation_gate(raw, self.old, gate)

    def test_refuses_historical_baseline_substitution(self):
        old = self.old.replace(b'status="KILLED"', b'status="SURVIVED"', 1)
        with self.assertRaises(ValueError): verify_mutation_gate(self.raw, old, self.gate)
        gate = copy.deepcopy(self.gate); gate['idiomatic_java']['previous']['sha256'] = sha256(old).hexdigest()
        with self.assertRaises(ValueError): verify_mutation_gate(self.raw, old, gate)

    def test_refuses_missing_handler_or_future_class(self):
        for old, new in ((b'MenuService', b'UnrelatedService'), (b'MenuService', b'AccountValidationModel')):
            raw = self.raw.replace(old, new)
            gate = copy.deepcopy(self.gate); gate['report']['sha256'] = sha256(raw).hexdigest()
            with self.subTest(new=new), self.assertRaises(ValueError): verify_mutation_gate(raw, self.old, gate)

    def test_refuses_changed_scope_hash_and_numeric_types(self):
        for key, value in (('threshold', 89), ('total', 140.0), ('passed', 1), ('denominator', 'covered only'), ('extra', True)):
            gate = copy.deepcopy(self.gate); gate[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): verify_mutation_gate(self.raw, self.old, gate)
        gate = copy.deepcopy(self.gate); gate['report']['sha256'] = '0' * 64
        with self.assertRaises(ValueError): verify_mutation_gate(self.raw, self.old, gate)

    def test_refuses_malformed_empty_or_incomplete_xml(self):
        for raw in (b'<wrong/>', b'<mutations/>', b'<mutations><extra/></mutations>', b'<mutations><mutation status="KILLED"/></mutations>'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): verify_mutation_gate(raw, self.old, self.gate)
