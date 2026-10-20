"""CI-only fixtures for account class evidence reconciliation."""
from copy import deepcopy
import unittest
import xml.etree.ElementTree as ET
from tools.carddemo_account_proof import verify_account_classes

GROUPS = {
    'account_input_java': ('AccountInputRules',),
    'account_text_money_java': ('AccountTextRules', 'AccountMoneyRule', 'CobolNumber'),
    'account_ssn_fico_java': ('AccountSsnRule', 'AccountFicoRule'),
    'account_location_java': ('AccountLocationRules',),
}


def fixture(killed=9, total=10, other='SURVIVED'):
    root = ET.Element('mutations'); gate = {}
    for key, names in GROUPS.items():
        gate[key] = {}
        for name in names:
            non_killed = []
            for index in range(total):
                status = 'KILLED' if index < killed else other
                node = ET.SubElement(root, 'mutation', status=status)
                ET.SubElement(node, 'mutatedClass').text = 'fixture.'+name
                if status != 'KILLED':
                    non_killed.append(dict(status=status, method=None, line=None, mutator=None, description=None))
            counts = {'KILLED': killed}
            if total > killed: counts[other] = total-killed
            gate[key][name] = dict(total=total, killed=killed, percent=100*killed/total,
                status_counts=counts, passed=bool(10*killed >= 9*total), non_killed=non_killed)
    return root, gate


class AccountClassProofTests(unittest.TestCase):
    def test_exact_ninety_for_all_six_classes(self):
        root, gate = fixture()
        actual = verify_account_classes(ET.tostring(root), gate)
        self.assertEqual(set(actual), {name for names in GROUPS.values() for name in names})
        self.assertTrue(all(row['killed'] == 9 and row['total'] == 10 for row in actual.values()))

    def test_missing_raw_class_cannot_borrow_other_green(self):
        for names in GROUPS.values():
            for name in names:
                root, gate = fixture()
                for node in list(root):
                    if node.findtext('mutatedClass') == 'fixture.'+name: root.remove(node)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    verify_account_classes(ET.tostring(root), gate)

    def test_missing_gate_class_and_extra_class_refused(self):
        for key, names in GROUPS.items():
            for kind in ('gate', 'class', 'extra'):
                root, gate = fixture()
                if kind == 'gate': del gate[key]
                elif kind == 'class': del gate[key][names[0]]
                else: gate[key]['Unexpected'] = deepcopy(gate[key][names[0]])
                with self.subTest(key=key, kind=kind), self.assertRaises(ValueError):
                    verify_account_classes(ET.tostring(root), gate)

    def test_receipt_summary_and_type_tampering_refused(self):
        for field, value in (('total', 9), ('killed', 10), ('percent', 100), ('passed', 1),
                             ('total', 10.0), ('non_killed', []), ('status_counts', {'KILLED': 10})):
            root, gate = fixture(); gate['account_input_java']['AccountInputRules'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                verify_account_classes(ET.tostring(root), gate)

    def test_each_non_killed_status_stays_in_denominator(self):
        for status in ('SURVIVED', 'TIMED_OUT', 'NO_COVERAGE', 'RUN_ERROR', 'MEMORY_ERROR'):
            root, gate = fixture(other=status)
            actual = verify_account_classes(ET.tostring(root), gate)
            self.assertEqual(actual['AccountFicoRule']['status_counts'], {'KILLED': 9, status: 1})
            gate['account_ssn_fico_java']['AccountFicoRule']['killed'] = 10
            with self.subTest(status=status), self.assertRaises(ValueError):
                verify_account_classes(ET.tostring(root), gate)

    def test_truthful_eighty_nine_percent_is_not_accepted(self):
        root, gate = fixture(killed=89, total=100)
        with self.assertRaises(ValueError): verify_account_classes(ET.tostring(root), gate)

    def test_missing_status_and_wrong_xml_root_refused(self):
        root, gate = fixture(); del root[0].attrib['status']
        with self.assertRaises(ValueError): verify_account_classes(ET.tostring(root), gate)
        with self.assertRaises(ValueError): verify_account_classes(b'<wrong/>', gate)

    def test_other_receipt_gates_are_not_silently_reclassified(self):
        root, gate = fixture(); gate['idiomatic_java'] = {'preserved': 'separate verification'}
        before = deepcopy(gate)
        verify_account_classes(ET.tostring(root), gate)
        self.assertEqual(gate, before)

    def test_location_receipt_or_raw_class_cannot_enter_three_group_profile(self):
        for kind in ('extra-gate', 'raw-location', 'raw-selector'):
            root, gate = fixture()
            if kind == 'extra-gate': gate['account_location_java'] = {}
            else:
                node = ET.SubElement(root, 'mutation', status='KILLED')
                name = 'AccountLocationRules' if kind == 'raw-location' else 'AccountValidationModel'
                ET.SubElement(node, 'mutatedClass').text = 'fixture.' + name
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_account_classes(ET.tostring(root), gate)
