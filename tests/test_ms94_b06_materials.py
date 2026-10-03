"""Synthetic predicate regressions, not native qualification or J3 references."""
import copy
import unittest
from tools.ms94_b06_materials import verify_rows


def fixture():
    contract = {'product_category_id': 7, 'source_locator_id': 1, 'destination_locator_id': 2,
                'warehouse_id': 3, 'business_date': '2026-10-03', 'opening_quantity': '20',
                'movement_quantity': '8', 'internal_use_quantity': '2', 'count_quantity': '5',
                'unit_cost': '3', 'internal_use_charge_id': 4,
                'document_types': {x: {'base': 'MMM' if x == 'movement' else 'MMI',
                                      'subtype': '' if x == 'movement' else ('I' if x == 'internalUse' else 'P')}
                                   for x in ('openingInventory', 'movement', 'internalUse', 'physicalCount')},
                'accounting_schemas': [{'id': 9, 'material_cost_element_id': 10, 'cost_org_id': 0,
                                        'cost_type_id': 11, 'currency_id': 12, 'period_id': 13}],
                'table_ids': {'m_inventory': 321, 'm_movement': 323}}
    before = {'m_product': [], 'm_inventory': [], 'm_movement': [],
              'm_locator': [{'m_locator_id': i, 'm_warehouse_id': 3} for i in (1, 2)],
              'c_doctype': [{'c_doctype_id': i, 'docbasetype': b, 'docsubtypeinv': s}
                           for i, b, s in ((1, 'MMI', 'P'), (2, 'MMI', 'I'), (3, 'MMM', ''))],
              'c_validcombination': [{'c_validcombination_id': i, 'account_id': i + 100} for i in (1, 2, 3)],
              'm_product_category_acct': [{'m_product_category_id': 7, 'c_acctschema_id': 9, 'p_asset_acct': 1}],
              'm_warehouse_acct': [{'m_warehouse_id': 3, 'c_acctschema_id': 9, 'w_differences_acct': 2}],
              'c_charge_acct': [{'c_charge_id': 4, 'c_acctschema_id': 9, 'ch_expense_acct': 3}]}
    after = copy.deepcopy(before)
    after['m_product'] = [{'m_product_id': 50, 'isstocked': 'Y', 'producttype': 'I', 'm_product_category_id': 7}]
    after['m_product_acct'] = [{'m_product_id': 50, 'c_acctschema_id': 9, 'p_asset_acct': 1}]
    trace = {'product.id': '50', 'openingInventory.id': '60', 'movement.id': '70',
             'internalUse.id': '61', 'physicalCount.id': '62'}
    for table, ids in (('m_inventory', (60, 61, 62)), ('m_movement', (70,))):
        after[table] = [{table+'_id': i, 'docstatus': 'CO', 'processed': 'Y', 'posted': 'Y',
                         'movementdate': '2026-10-03T00:00:00', 'm_warehouse_id': 3,
                         'c_doctype_id': 3 if i == 70 else (2 if i == 61 else 1)} for i in ids]
    after['m_inventoryline'] = [
        {'m_inventory_id': 60, 'm_inventoryline_id': 600, 'm_product_id': 50, 'm_locator_id': 1,
         'qtybook': '0', 'qtycount': '20', 'qtyinternaluse': '0', 'c_charge_id': 0},
        {'m_inventory_id': 61, 'm_inventoryline_id': 610, 'm_product_id': 50, 'm_locator_id': 2,
         'qtybook': '8', 'qtycount': '8', 'qtyinternaluse': '2', 'c_charge_id': 4},
        {'m_inventory_id': 62, 'm_inventoryline_id': 620, 'm_product_id': 50, 'm_locator_id': 2,
         'qtybook': '6', 'qtycount': '5', 'qtyinternaluse': '0', 'c_charge_id': 0}]
    after['m_movementline'] = [{'m_movement_id': 70, 'm_movementline_id': 700, 'm_product_id': 50,
                               'm_locator_id': 1, 'm_locatorto_id': 2, 'movementqty': '8'}]
    after['m_storageonhand'] = [{'m_product_id': 50, 'm_locator_id': 1, 'qtyonhand': '12'},
                                {'m_product_id': 50, 'm_locator_id': 2, 'qtyonhand': '5'}]
    after['m_transaction'] = [
        {'m_product_id': 50, 'm_locator_id': loc, 'movementqty': str(qty), 'movementtype': kind,
         'm_movementline_id' if kind.startswith('M') else 'm_inventoryline_id': line}
        for loc, qty, kind, line in ((1, 20, 'I+', 600), (1, -8, 'M-', 700),
                                      (2, 8, 'M+', 700), (2, -2, 'I-', 610), (2, -1, 'I-', 620))]
    after['m_cost'] = [{'m_product_id': 50, 'c_acctschema_id': 9, 'm_costelement_id': 10,
                        'ad_org_id': 0, 'm_attributesetinstance_id': 0, 'm_costtype_id': 11,
                        'currentcostprice': '3', 'currentcostpricell': '0', 'currentqty': '17'}]
    after['m_costdetail'] = [{'m_product_id': 50, 'm_inventoryline_id': line, 'c_acctschema_id': 9,
                             'processed': 'Y', 'qty': str(qty), 'amt': str(amt)}
                            for line, qty, amt in ((600, 20, 60), (610, -2, -6), (620, -1, -3))]
    # Independently stated posting ledger: no call into the predicate to generate expected rows.
    ledger = ((321, 60, 101, 1, 60), (321, 60, 102, 1, -60),
              (323, 70, 101, 1, -24), (323, 70, 101, 2, 24),
              (321, 61, 101, 2, -6), (321, 61, 103, 2, 6),
              (321, 62, 101, 2, -3), (321, 62, 102, 2, 3))
    after['fact_acct'] = [{'ad_table_id': tab, 'record_id': doc, 'account_id': account,
                           'm_locator_id': loc, 'c_acctschema_id': 9, 'c_currency_id': 12,
                           'm_product_id': 50, 'postingtype': 'A', 'dateacct': '2026-10-03', 'c_period_id': 13,
                           'amtacctdr': str(max(amt, 0)), 'amtacctcr': str(max(-amt, 0)),
                           'amtsourcedr': str(max(amt, 0)), 'amtsourcecr': str(max(-amt, 0))}
                          for tab, doc, account, loc, amt in ledger]
    return before, after, trace, contract


class MaterialsTests(unittest.TestCase):
    def test_new_destination_locator_must_be_new_and_in_same_organization(self):
        before, after, trace, contract = fixture()
        contract.pop('destination_locator_id')
        contract['destination_locator_new'] = True
        trace['destinationLocator.id'] = '2'
        before['m_locator'] = before['m_locator'][:1]
        after['m_locator'][1]['ad_org_id'] = 11
        after['m_product'][0]['ad_org_id'] = 11
        self.assertTrue(verify_rows(before, after, trace, contract)['passed'])
        after['m_locator'][1]['ad_org_id'] = 12
        with self.assertRaisesRegex(Exception, 'materials-locator-organization'):
            verify_rows(before, after, trace, contract)
        after['m_locator'][1]['ad_org_id'] = 11
        before['m_locator'].append(dict(after['m_locator'][1]))
        with self.assertRaisesRegex(Exception, 'materials-destination-locator-not-new'):
            verify_rows(before, after, trace, contract)

    def test_expected_ledger_and_inventory(self):
        self.assertEqual(8, verify_rows(*fixture())['accounting_entries_verified'])

    def test_wrong_cost_account_and_sign_rejected_even_when_balanced(self):
        mutations = [
            ('m_cost', 0, 'currentcostprice', '4'),
            ('fact_acct', 5, 'account_id', 102),
            ('m_transaction', 3, 'movementqty', '2'),
            ('m_inventoryline', 1, 'qtyinternaluse', '-2'),
            ('fact_acct', 7, 'c_period_id', 99),
            ('m_costdetail', 1, 'amt', '-7'),
            ('m_cost', 0, 'currentqty', '18'),
            ('m_movementline', 0, 'm_locatorto_id', 1),
        ]
        for table, index, key, value in mutations:
            with self.subTest(table=table, key=key):
                before, after, trace, contract = fixture()
                after[table][index][key] = value
                with self.assertRaises(Exception): verify_rows(before, after, trace, contract)

    def test_missing_duplicate_and_other_schema_facts_fail(self):
        for mutation in ('missing', 'duplicate', 'schema'):
            with self.subTest(mutation=mutation):
                before, after, trace, contract = fixture()
                if mutation == 'missing': after['fact_acct'].pop()
                elif mutation == 'duplicate': after['fact_acct'].append(dict(after['fact_acct'][0]))
                else: after['fact_acct'][0]['c_acctschema_id'] = 99
                with self.assertRaises(Exception): verify_rows(before, after, trace, contract)

    def test_balanced_negative_debits_are_not_valid_postings(self):
        before, after, trace, contract = fixture()
        # Same net balance as the expected credit, expressed as an invalid debit.
        row = after['fact_acct'][1]
        row.update(amtacctdr='-60', amtacctcr='0', amtsourcedr='-60', amtsourcecr='0')
        with self.assertRaisesRegex(Exception, 'materials-accounting-debit-credit-sign'):
            verify_rows(before, after, trace, contract)


if __name__ == '__main__': unittest.main()
