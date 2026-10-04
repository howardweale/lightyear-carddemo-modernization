"""Derive private J3 expectations only from the sealed work order and entry rows.

The result belongs in a private input directory. Public manifests contain its
hash only. This module never reads a candidate trace or an after-state.
"""
from lightyear_calibration.contracts import digest
from tools.ms94_b06_admission import check


def derive_materials(tables, work_order, selection):
    inputs = work_order['scenario_inputs']
    def one(table, **where):
        found = [r for r in tables[table] if all(r.get(k) == v for k, v in where.items())]
        check(len(found) == 1, 'private-seed-selection-ambiguous')
        return found[0]
    client, org = selection['client_id'], selection['organization_id']
    category, locator = selection['product_category_id'], selection['source_locator_id']
    place = one('m_locator', m_locator_id=locator)
    check(place['ad_client_id'] == client and place['ad_org_id'] == org and
          place['m_warehouse_id'] == selection['warehouse_id'], 'private-locator-selection-invalid')
    one('m_product_category', m_product_category_id=category, ad_client_id=client, isactive='Y')
    charges = [r['c_charge_id'] for r in tables['c_charge'] if r['ad_client_id'] == client and r['isactive'] == 'Y']
    check(bool(charges), 'private-charge-selection-missing')
    charge = min(charges)
    day = inputs['business_date']
    periods = [r for r in tables['c_period'] if r['ad_client_id'] == client and r['periodtype'] == 'S'
               and str(r['startdate'])[:10] <= day <= str(r['enddate'])[:10]]
    check(len(periods) == 1, 'private-period-selection-ambiguous')
    schemas = []
    for schema in sorted((r for r in tables['c_acctschema'] if r['ad_client_id'] == client and r['isactive'] == 'Y'),
                         key=lambda r: r['c_acctschema_id']):
        sid = schema['c_acctschema_id']
        category_acct = one('m_product_category_acct', m_product_category_id=category, c_acctschema_id=sid)
        costing = category_acct.get('costingmethod') or schema['costingmethod']
        level = category_acct.get('costinglevel') or schema['costinglevel']
        check(level in ('C', 'O'), 'unsupported-private-costing-level')
        elements = [r for r in tables['m_costelement'] if r['ad_client_id'] == client and
                    r['costelementtype'] == 'M' and r.get('costingmethod') == costing]
        check(len(elements) == 1, 'private-material-cost-element-ambiguous')
        # Check every expected account independently before exposing the contract.
        warehouse = one('m_warehouse_acct', m_warehouse_id=selection['warehouse_id'], c_acctschema_id=sid)
        expense = one('c_charge_acct', c_charge_id=charge, c_acctschema_id=sid)
        for account in (category_acct['p_asset_acct'], warehouse['w_differences_acct'], expense['ch_expense_acct']):
            one('c_validcombination', c_validcombination_id=account, c_acctschema_id=sid)
        schemas.append({'id': sid, 'currency_id': schema['c_currency_id'],
                        'cost_type_id': schema['m_costtype_id'], 'cost_org_id': org if level == 'O' else 0,
                        'material_cost_element_id': elements[0]['m_costelement_id'],
                        'period_id': periods[0]['c_period_id']})
    check(bool(schemas), 'private-accounting-schemas-missing')
    table_ids = {name: one('ad_table', tablename=name)['ad_table_id'] for name in ('M_Inventory', 'M_Movement')}
    table_ids = {k.lower(): v for k, v in table_ids.items()}
    return {'journey': 'J3', **selection, 'business_date': day, 'destination_locator_new': True,
            'work_order_sha256': digest(work_order), 'selection_sha256': digest(selection),
            'opening_quantity': inputs['opening_quantity'], 'movement_quantity': inputs['movement_quantity'],
            'internal_use_quantity': inputs['internal_use_quantity'], 'count_quantity': inputs['count_quantity'],
            'unit_cost': inputs['material_unit_cost'], 'internal_use_charge_id': charge,
            'accounting_schemas': schemas, 'table_ids': table_ids, 'document_table_ids': table_ids,
            'document_types': {s: {'base': 'MMM' if s == 'movement' else 'MMI',
                                   'subtype': '' if s == 'movement' else ('IU' if s == 'internalUse' else 'PI')}
                               for s in ('openingInventory', 'movement', 'internalUse', 'physicalCount')}}


def verify_private_derivation(run, contract, before):
    from lightyear_calibration.contracts import read_json
    if contract['journey'] == 'J3':
        order = read_json(run / 'inputs/private-work-order.json')
        selection = read_json(run / 'inputs/private-selection.json')
        for lane in ('oracle', 'postgresql'):
            check(derive_materials(before[lane], order, selection) == contract,
                  'private-expectations-not-derived-from-entry')
