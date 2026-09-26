"""Verify the fractional, taxed and Unicode boundary journey on native readbacks.

Application traces are checked against independently read database rows. The
result remains bounded to this scenario and requires a separately admitted
whole-state comparison before a journey-equivalence claim can become true.
"""
from decimal import Decimal
import hashlib
from pathlib import Path

from .contracts import digest, require, seal, verify
from .native_reconciliation import rows, state, valid_uuid
from .application_journey import read_trace, number
from .boundary_contract import INPUT, check_values, expected

STAGES = {'customer': 'c_bpartner', 'product': 'm_product', 'order': 'c_order',
          'shipment': 'm_inout', 'invoice': 'c_invoice', 'payment': 'c_payment'}
AUXILIARY = {'customerLocation': 'c_bpartner_location', 'productPrice': 'm_productprice',
             'openingInventory': 'm_inventory'}
SOURCE_COMMIT = '731515dcdd5278b843db33b9d3109d155b881951'


def verify_lane(folder, trace_path, execution, harness_bytes):
    verify(execution)
    lane = execution['lane']
    require(lane in ('oracle', 'postgresql'), 'Unknown application lane')
    require(execution['exit_code'] == 0, 'Application process did not succeed')
    require(execution['application_source_commit'] == SOURCE_COMMIT, 'Application source changed')
    require(execution['harness_sha256'] == hashlib.sha256(harness_bytes).hexdigest(), 'Journey harness changed')
    trace, trace_hash = read_trace(trace_path)
    require(trace.get('status') == 'completed-and-committed' and trace.get('database') == lane,
            'Missing committed native journey completion')
    require(trace.get('newIssueCount') == '0', 'Application reported a new issue')
    snapshot = state(Path(folder), lane)
    require(snapshot['evidence_class'] == 'native-database-observation', 'Non-native application readback')
    observed_tables = {}
    def table(name):
        if name not in observed_tables:
            require(name in snapshot['tables'], 'Missing application table')
            observed_tables[name] = rows(Path(folder), snapshot['tables'][name])
        return observed_tables[name]
    def only(name, **conditions):
        selected = [row for row in table(name) if all(row.get(k) == v for k, v in conditions.items())]
        require(len(selected) == 1, 'Missing or ambiguous committed application record: '+name)
        return selected[0]
    observed = {}
    for stage, name in {**STAGES, **AUXILIARY}.items():
        require(trace.get(stage+'.saved') == 'true', 'Missing saved stage')
        identity = int(trace[stage+'.id']); require(identity > 0, 'Invalid stage identity')
        row = only(name, **{name+'_id': identity})
        require(valid_uuid(trace[stage+'.uuid']) and row[name+'_uu'] == trace[stage+'.uuid'], 'Stage UUID differs from committed row')
        if stage in ('order', 'shipment', 'invoice', 'payment', 'openingInventory'):
            require(trace.get(stage+'.status') == row['docstatus'] == 'CO', 'Document is not completed')
        observed[stage] = row
    customer, product, order, shipment, invoice, payment = (observed[x] for x in STAGES)
    location, price, inventory = (observed[x] for x in AUXILIARY)
    require(location['c_bpartner_id'] == customer['c_bpartner_id'], 'Customer location belongs to another customer')
    require(price['m_product_id'] == product['m_product_id'] and number(price['pricestd']) == Decimal('17.9955'), 'Product pricing setup differs')
    inventory_line = only('m_inventoryline', m_inventory_id=inventory['m_inventory_id'])
    require(inventory_line['m_product_id'] == product['m_product_id'] and number(inventory_line['qtycount']) == 10, 'Opening inventory setup differs')
    require(customer['iscustomer'] == 'Y' and product['issold'] == product['isstocked'] == 'Y', 'Wrong customer/product role')
    for row in (order, shipment, invoice, payment):
        require(row['c_bpartner_id'] == customer['c_bpartner_id'], 'Journey customer links differ')
    for row in (order, shipment, invoice):
        require(row['c_bpartner_location_id'] == location['c_bpartner_location_id'], 'Document customer location differs')
    require(shipment['c_order_id'] == order['c_order_id'] and payment['c_invoice_id'] == invoice['c_invoice_id'], 'Journey document links differ')
    order_line = only('c_orderline', c_order_id=order['c_order_id'])
    shipment_line = only('m_inoutline', m_inout_id=shipment['m_inout_id'])
    invoice_line = only('c_invoiceline', c_invoice_id=invoice['c_invoice_id'])
    for row in (order_line, shipment_line, invoice_line):
        require(row['m_product_id'] == product['m_product_id'], 'Journey product links differ')
    require(shipment_line['c_orderline_id'] == order_line['c_orderline_id'], 'Shipment does not fulfill the order line')
    require(invoice_line['m_inoutline_id'] == shipment_line['m_inoutline_id'], 'Invoice does not bill the shipment line')
    require(number(order_line['qtyordered']) == number(order_line['qtydelivered']) ==
            number(shipment_line['movementqty']) == number(invoice_line['qtyinvoiced']) == 3, 'Quantity outcome differs')
    require(number(order['totallines']) == expected()['net'], 'Order net amount differs')
    require(number(order['grandtotal']) == number(invoice['grandtotal']) == number(payment['payamt']) == expected()['gross'], 'Monetary outcomes differ')
    for key, value in [('order.total', order['grandtotal']), ('order.net', order['totallines']),
                       ('invoice.total', invoice['grandtotal']), ('payment.amount', payment['payamt']),
                       ('shipment.delivered', order_line['qtydelivered'])]:
        require(number(trace[key]) == number(value), 'Trace differs from committed business value: '+key)
    require(invoice['ispaid'] == 'Y' and trace['invoice.paid'] == 'true', 'Invoice remains unpaid')
    allocations = [r for r in table('c_allocationline') if r['c_invoice_id'] == invoice['c_invoice_id'] and r['c_payment_id'] == payment['c_payment_id']]
    require(allocations and sum(number(r['amount']) for r in allocations) == number(payment['payamt']), 'Payment allocation amount differs')
    for allocation in allocations:
        header = only('c_allocationhdr', c_allocationhdr_id=allocation['c_allocationhdr_id'])
        require(header['docstatus'] == 'CO', 'Allocation is not completed')
    accounting_keys = {(318, invoice['c_invoice_id']), (335, payment['c_payment_id'])}
    accounting_keys.update((735, r['c_allocationhdr_id']) for r in allocations)
    accounting = [r for r in table('fact_acct') if (r['ad_table_id'], r['record_id']) in accounting_keys]
    require({(r['ad_table_id'], r['record_id']) for r in accounting} == accounting_keys, 'Missing accounting entries')
    balances = {}
    for row in accounting:
        key = (row['ad_table_id'], row['record_id'], row['c_acctschema_id'], row['c_currency_id'])
        debit_credit = (number(row['amtacctdr'])-number(row['amtacctcr']),
                        number(row['amtsourcedr'])-number(row['amtsourcecr']))
        previous = balances.get(key, (Decimal(0), Decimal(0)))
        balances[key] = tuple(a+b for a, b in zip(previous, debit_credit))
    require(all(value == (0, 0) for value in balances.values()), 'Unbalanced accounting entries')
    stock = [r for r in table('m_storageonhand') if r['m_product_id'] == product['m_product_id']]
    require(stock and sum(number(r['qtyonhand']) for r in stock) == 7, 'Closing inventory differs')
    require(number(trace['inventory.onHand']) == 7 and number(trace['openingInventory.quantity']) == 10, 'Inventory trace differs')
    moves = [r for r in table('m_transaction') if r['m_product_id'] == product['m_product_id']]
    require(len(moves) == int(trace['inventory.movements']) and len(moves) >= 2, 'Missing inventory movement readback')
    order_tax = only('c_ordertax', c_order_id=order['c_order_id'])
    invoice_tax = only('c_invoicetax', c_invoice_id=invoice['c_invoice_id'])
    require(order_tax['c_tax_id'] == invoice_tax['c_tax_id'] == order_line['c_tax_id'] == 107, 'Wrong declared fixture tax')
    require(number(only('c_tax', c_tax_id=107)['rate']) == Decimal(INPUT['tax_percent']), 'Tax fixture rate changed')
    boundary = check_values(customer, order_line, order, invoice, order_tax, invoice_tax, shipment)
    require(trace['customer.name.input'] == INPUT['customer_name'] and trace['customer.description.input'] == 'empty-string', 'Wrong text inputs')
    require(trace['shipment.shipDate.input'].replace(' ', 'T') == INPUT['shipment_timestamp'], 'Wrong fractional-time input')
    return seal({'artifact_type': 'lightyear-native-boundary-journey-lane', 'lane': lane,
                 'evidence_class': 'native-application-and-database-observation', 'independently_attested': False,
                 'trace': trace, 'trace_sha256': trace_hash, 'execution_sha256': execution['content_sha256'],
                 'state_sha256': snapshot['content_sha256'], 'harness_sha256': execution['harness_sha256'],
                 'stages': list(STAGES), 'status': 'business-readback-verified-boundaries-measured',
                 'boundary_contract': boundary, 'input': INPUT,
                 'accounting_entries_verified': len(accounting), 'balanced_accounting_groups': len(balances),
                 'observed_table_row_hashes': {name: snapshot['tables'][name]['row_multiset'] for name in observed_tables}})


def compare_lanes(lanes, effects):
    require(set(lanes) == {'oracle', 'postgresql'}, 'Both boundary lanes required')
    verify(effects)
    require(effects['artifact_type'] == 'lightyear-bounded-application-effects', 'Wrong effects checkpoint')
    require(effects['state_sha256'] == {lane: value['state_sha256'] for lane, value in lanes.items()},
            'Boundary readbacks and effects refer to different states')
    for lane, value in lanes.items():
        verify(value)
        require(value['lane'] == lane and value['artifact_type'] == 'lightyear-native-boundary-journey-lane', 'Wrong boundary lane')
        require(value['evidence_class'] == 'native-application-and-database-observation', 'Non-native boundary evidence')
        require(value['input'] == INPUT and value['boundary_contract']['input_sha256'] == digest(INPUT), 'Boundary input contract changed')
    require(lanes['oracle']['harness_sha256'] == lanes['postgresql']['harness_sha256'], 'Different boundary harnesses')
    checks = {lane: value['boundary_contract']['checks'] for lane, value in lanes.items()}
    require(all(len(items) == 15 and len({x['check'] for x in items}) == 15 for items in checks.values()),
            'Incomplete or repeated boundary checks')
    require({x['check'] for x in checks['oracle']} == {x['check'] for x in checks['postgresql']}, 'Different boundary check sets')
    findings = [{'lane': lane, **item} for lane, items in checks.items() for item in items if not item['passed']]
    passed = not findings and effects['admitted_for_selected_journeys'] and not effects['unresolved_differences']
    return seal({'artifact_type': 'lightyear-native-boundary-journey-comparison',
                 'status': 'passed-bounded-boundary-journey' if passed else 'boundary-review-required',
                 'bounded_boundary_equivalence': bool(passed), 'input_sha256': digest(INPUT),
                 'lane_receipt_sha256': {lane: item['content_sha256'] for lane, item in lanes.items()},
                 'effect_checkpoint_sha256': effects['content_sha256'],
                 'checks_per_lane': 15, 'passed_check_count': {lane: sum(x['passed'] for x in items) for lane, items in checks.items()},
                 'failed_input_preservation_or_business_checks': findings,
                 'unresolved_row_difference_count': len(effects['unresolved_differences']),
                 'schema_equivalence': False, 'application_equivalence': False, 'platform_qualification': False})
