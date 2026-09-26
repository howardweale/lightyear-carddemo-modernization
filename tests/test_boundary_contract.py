from copy import deepcopy
from decimal import Decimal
import unittest

from lightyear_calibration.boundary_contract import INPUT, expected, check_values


class BoundaryContractTests(unittest.TestCase):
    def values(self):
        return [
            {'name': INPUT['customer_name'], 'description': None},
            {'pricelist': '19.995', 'priceactual': '17.9955', 'discount': '10', 'linenetamt': '53.99'},
            {'totallines': '53.99', 'grandtotal': '58.04'},
            {'totallines': '53.99', 'grandtotal': '58.04'},
            {'taxbaseamt': '53.99', 'taxamt': '4.05'},
            {'taxbaseamt': '53.99', 'taxamt': '4.05'},
            {'shipdate': INPUT['shipment_timestamp']},
        ]

    def test_expectations_use_decimal_arithmetic_and_explicit_rounding(self):
        self.assertEqual({'actual_price': Decimal('17.9955'), 'net': Decimal('53.99'),
                          'tax': Decimal('4.05'), 'gross': Decimal('58.04'), 'ending_stock': Decimal('7')}, expected())
        result = check_values(*self.values())
        self.assertEqual(15, len(result['checks']))
        self.assertTrue(result['all_inputs_and_business_outcomes_preserved'])

    def test_same_wrong_amount_on_both_engines_does_not_satisfy_contract(self):
        values = self.values()
        values[2]['grandtotal'] = values[3]['grandtotal'] = '58.03'
        result = check_values(*values)
        self.assertFalse(result['all_inputs_and_business_outcomes_preserved'])
        self.assertEqual(2, sum(not c['passed'] for c in result['checks']))

    def test_fractional_timestamp_cannot_be_silently_normalized(self):
        for wrong in ('2026-09-26T12:34:56', '2026-09-26T12:34:56.123000', None, 'not-a-date'):
            values = self.values(); values[-1]['shipdate'] = wrong
            result = check_values(*values)
            self.assertFalse(result['checks'][-1]['passed'])
            self.assertEqual(wrong, result['checks'][-1]['observed'])

    def test_unicode_and_empty_string_are_checked_independently(self):
        for key, value in [('name', 'Cafe ?? Lodz'), ('description', '')]:
            values = self.values(); values[0][key] = value
            self.assertFalse(check_values(*values)['all_inputs_and_business_outcomes_preserved'])

    def test_tax_and_discount_cannot_hide_inside_a_matching_total(self):
        for index, key in [(1, 'discount'), (4, 'taxamt'), (5, 'taxbaseamt')]:
            values = self.values(); values[index][key] = '0'
            self.assertFalse(check_values(*values)['all_inputs_and_business_outcomes_preserved'])


if __name__ == '__main__': unittest.main()
