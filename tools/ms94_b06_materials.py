"""Materials business predicates over independently admitted native table rows.

This module is not an entry checker or a qualified gate. The native adapter must
authenticate complete before/after captures and bind the private contract before
calling it. It never accepts accounting expectations from candidate traces.
"""
from collections import Counter
from decimal import Decimal
from lightyear_calibration.contracts import require
from lightyear_calibration.ms94_v3_errors import business_require


def number(value):
    result = Decimal(str(value))
    require(result.is_finite(), 'Non-finite native decimal')
    return result


def verify_rows(before, after, trace, contract):
    """Closed reasons; identifiers and amounts are never part of an error."""
    def one(tables, table, **where):
        rows = [r for r in tables[table] if all(r.get(k) == v for k, v in where.items())]
        business_require(len(rows) == 1, 'materials-missing-or-ambiguous-row')
        return rows[0]

    product_id = int(trace['product.id'])
    product = one(after, 'm_product', m_product_id=product_id)
    business_require(not any(r['m_product_id'] == product_id for r in before['m_product']),
                     'materials-product-not-new')
    business_require(product['isstocked'] == 'Y' and product['producttype'] == 'I' and
                     product['m_product_category_id'] == contract['product_category_id'],
                     'materials-product-contract')
    source = contract['source_locator_id']
    destination = (int(trace['destinationLocator.id']) if contract.get('destination_locator_new')
                   else contract['destination_locator_id'])
    business_require(source != destination, 'materials-locators-not-distinct')
    for locator in (source, destination):
        if locator == destination and contract.get('destination_locator_new'):
            business_require(not any(r['m_locator_id'] == locator for r in before['m_locator']),
                             'materials-destination-locator-not-new')
            row = one(after, 'm_locator', m_locator_id=locator)
            business_require(row['ad_org_id'] == product['ad_org_id'], 'materials-locator-organization')
        else:
            row = one(before, 'm_locator', m_locator_id=locator)
            business_require(one(after, 'm_locator', m_locator_id=locator) == row, 'materials-locator-modified')
        business_require(row['m_warehouse_id'] == contract['warehouse_id'], 'materials-warehouse-link')
    business_date = contract['business_date']
    stages = ('openingInventory', 'movement', 'internalUse', 'physicalCount')
    tables = ('m_inventory', 'm_movement', 'm_inventory', 'm_inventory')
    docs, lines = {}, {}
    for stage, table in zip(stages, tables):
        doc_id = int(trace[stage + '.id'])
        doc = one(after, table, **{table + '_id': doc_id})
        business_require(not any(r[table + '_id'] == doc_id for r in before[table]), 'materials-document-not-new')
        business_require(doc['docstatus'] == 'CO' and doc['processed'] == 'Y' and doc['posted'] == 'Y',
                         'materials-document-incomplete-or-unposted')
        business_require(str(doc['movementdate'])[:10] == business_date, 'materials-document-date')
        dtype = one(before, 'c_doctype', c_doctype_id=doc['c_doctype_id'])
        expected_type = contract['document_types'][stage]
        business_require(dtype['docbasetype'] == expected_type['base'] and
                         (dtype.get('docsubtypeinv') or '') == expected_type['subtype'], 'materials-document-type')
        if table == 'm_inventory':
            business_require(doc['m_warehouse_id'] == contract['warehouse_id'], 'materials-warehouse-link')
        line = one(after, table + 'line', **{table + '_id': doc_id})
        business_require(line['m_product_id'] == product_id and
                         line.get('m_attributesetinstance_id', 0) in (None, 0), 'materials-product-link')
        docs[stage], lines[stage] = doc, line
    business_require(len({docs[x]['m_inventory_id'] for x in stages if x != 'movement'}) == 3,
                     'materials-inventory-documents-not-distinct')
    opening, moved, used, counted = (number(contract[x]) for x in ('opening_quantity', 'movement_quantity',
                                                                  'internal_use_quantity', 'count_quantity'))
    unit_cost = number(contract['unit_cost'])
    require(opening > moved > used > 0 and 0 <= counted < moved-used and unit_cost > 0,
            'Unsupported materials qualification contract')
    count_diff = counted - (moved-used)
    for stage, locator, book, count, internal in (
            ('openingInventory', source, Decimal(0), opening, Decimal(0)),
            ('internalUse', destination, None, None, used),
            ('physicalCount', destination, moved-used, counted, Decimal(0))):
        line = lines[stage]
        business_require(line['m_locator_id'] == locator and number(line['qtyinternaluse']) == internal,
                         'materials-quantity-sign-or-locator')
        if book is not None:
            business_require(number(line['qtybook']) == book and number(line['qtycount']) == count,
                             'materials-count-book-or-quantity')
        business_require((line.get('c_charge_id') or 0) ==
                         (contract['internal_use_charge_id'] if stage == 'internalUse' else 0),
                         'materials-charge-selection')
    move = lines['movement']
    business_require(move['m_locator_id'] == source and move['m_locatorto_id'] == destination and
                     number(move['movementqty']) == moved, 'materials-movement-quantity-sign-or-link')
    stock = [r for r in after['m_storageonhand'] if r['m_product_id'] == product_id]
    business_require(all(r['m_locator_id'] in (source, destination) for r in stock), 'materials-unexpected-stock-location')
    for locator, quantity in ((source, opening-moved), (destination, counted)):
        business_require(sum((number(r['qtyonhand']) for r in stock if r['m_locator_id'] == locator), Decimal(0)) == quantity,
                         'materials-final-stock')
    expected_moves = Counter()
    for stage, locator, qty, movement_type in (
            ('openingInventory', source, opening, 'I+'), ('movement', source, -moved, 'M-'),
            ('movement', destination, moved, 'M+'), ('internalUse', destination, -used, 'I-'),
            ('physicalCount', destination, count_diff, 'I-')):
        key = 'm_movementline_id' if stage == 'movement' else 'm_inventoryline_id'
        expected_moves[(locator, qty, movement_type, key, lines[stage][key])] += 1
    observed_moves = Counter()
    for row in after['m_transaction']:
        if row['m_product_id'] != product_id: continue
        key = 'm_movementline_id' if row.get('m_movementline_id') else 'm_inventoryline_id'
        observed_moves[(row['m_locator_id'], number(row['movementqty']), row['movementtype'], key, row[key])] += 1
    business_require(observed_moves == expected_moves, 'materials-transaction-sign-quantity-or-link')

    def account(combination):
        return one(before, 'c_validcombination', c_validcombination_id=combination)['account_id']

    fact_count = 0
    for schema in contract['accounting_schemas']:
        sid = schema['id']
        category = one(before, 'm_product_category_acct', m_product_category_id=contract['product_category_id'], c_acctschema_id=sid)
        asset = account(category['p_asset_acct'])
        warehouse = one(before, 'm_warehouse_acct', m_warehouse_id=contract['warehouse_id'], c_acctschema_id=sid)
        difference = account(warehouse['w_differences_acct'])
        charge = one(before, 'c_charge_acct', c_charge_id=contract['internal_use_charge_id'], c_acctschema_id=sid)
        expense = account(charge['ch_expense_acct'])
        product_acct = one(after, 'm_product_acct', m_product_id=product_id, c_acctschema_id=sid)
        business_require(product_acct['p_asset_acct'] == category['p_asset_acct'], 'materials-product-asset-account')
        cost = one(after, 'm_cost', m_product_id=product_id, c_acctschema_id=sid,
                   m_costelement_id=schema['material_cost_element_id'], ad_org_id=schema['cost_org_id'],
                   m_attributesetinstance_id=0, m_costtype_id=schema['cost_type_id'])
        final_qty = opening-used+count_diff
        business_require(number(cost['currentcostprice']) == unit_cost and
                         number(cost['currentcostpricell']) == 0 and number(cost['currentqty']) == final_qty,
                         'materials-cost-or-valuation')
        for stage in stages:
            table = 'm_movement' if stage == 'movement' else 'm_inventory'
            table_id = contract['table_ids'][table]
            doc_id = docs[stage][table + '_id']
            facts = [r for r in after['fact_acct'] if r['ad_table_id'] == table_id and r['record_id'] == doc_id and r['c_acctschema_id'] == sid]
            if stage == 'movement':
                expected_facts = Counter({(asset, source, -moved*unit_cost): 1, (asset, destination, moved*unit_cost): 1})
            else:
                qty = {'openingInventory': opening, 'internalUse': -used, 'physicalCount': count_diff}[stage]
                locator = source if stage == 'openingInventory' else destination
                offset = expense if stage == 'internalUse' else difference
                expected_facts = Counter([(asset, locator, qty*unit_cost), (offset, locator, -qty*unit_cost)])
            observed = Counter()
            for row in facts:
                amounts = {key: number(row[key]) for key in
                           ('amtacctdr','amtacctcr','amtsourcedr','amtsourcecr')}
                business_require(all(value >= 0 for value in amounts.values()) and
                                 not (amounts['amtacctdr'] and amounts['amtacctcr']) and
                                 not (amounts['amtsourcedr'] and amounts['amtsourcecr']),
                                 'materials-accounting-debit-credit-sign')
                business_require(row['postingtype'] == 'A' and row['c_currency_id'] == schema['currency_id'] and
                                 str(row['dateacct'])[:10] == business_date and row['c_period_id'] == schema['period_id'] and
                                 row['m_product_id'] == product_id, 'materials-accounting-period-or-dimensions')
                balance = number(row['amtacctdr']) - number(row['amtacctcr'])
                business_require(amounts['amtacctdr'] == amounts['amtsourcedr'] and
                                 amounts['amtacctcr'] == amounts['amtsourcecr'], 'materials-accounting-currency')
                observed[(row['account_id'], row['m_locator_id'], balance)] += 1
            business_require(observed == expected_facts, 'materials-accounting-account-cost-or-sign')
            fact_count += len(facts)
            if stage != 'movement':
                details = [r for r in after['m_costdetail'] if r['m_inventoryline_id'] == lines[stage]['m_inventoryline_id'] and r['c_acctschema_id'] == sid]
                qty = {'openingInventory': opening, 'internalUse': -used, 'physicalCount': count_diff}[stage]
                business_require(details and all(r['processed'] == 'Y' and r['m_product_id'] == product_id for r in details) and
                                 sum((number(r['qty']) for r in details), Decimal(0)) == qty and
                                 sum((number(r['amt']) for r in details), Decimal(0)) == qty*unit_cost,
                                 'materials-cost-detail')
    permitted = {(contract['table_ids']['m_movement' if x == 'movement' else 'm_inventory'],
                  docs[x]['m_movement_id' if x == 'movement' else 'm_inventory_id']) for x in stages}
    related = [r for r in after['fact_acct'] if r.get('m_product_id') == product_id]
    business_require(len(related) == fact_count and all((r['ad_table_id'], r['record_id']) in permitted for r in related),
                     'materials-unexpected-accounting')
    return {'passed': True, 'accounting_entries_verified': fact_count,
            'quantity_checked': True, 'cost_valuation_checked': True, 'account_selection_checked': True}
