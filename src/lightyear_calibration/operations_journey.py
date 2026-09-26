"""Verify native partial shipments, credit reversal, rollback/retry and controlled row locking.

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
from .boundary_contract import INPUT, check_business_values, expected

STAGES = {'customer': 'c_bpartner', 'product': 'm_product', 'order': 'c_order',
          'shipment': 'm_inout', 'invoice': 'c_invoice', 'payment': 'c_payment'}
AUXILIARY = {'customerLocation': 'c_bpartner_location', 'productPrice': 'm_productprice',
             'openingInventory': 'm_inventory', 'firstShipment': 'm_inout'}
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
        if stage in ('order', 'shipment', 'invoice', 'payment', 'openingInventory', 'firstShipment'):
            require(trace.get(stage+'.status') == row['docstatus'] == 'CO', 'Document is not completed')
        observed[stage] = row
    customer, product, order, shipment, invoice, payment = (observed[x] for x in STAGES)
    location, price, inventory = (observed[x] for x in ('customerLocation', 'productPrice', 'openingInventory'))
    first = observed['firstShipment']
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
    require(invoice_line['c_orderline_id'] == order_line['c_orderline_id'], 'Aggregate invoice does not bill the order line')
    first_line = only('m_inoutline', m_inout_id=first['m_inout_id'])
    require(first['c_order_id'] == order['c_order_id'] and first_line['c_orderline_id'] == order_line['c_orderline_id'], 'Partial shipment links differ')
    require(number(first_line['movementqty']) == 1 and number(shipment_line['movementqty']) == 2, 'Partial shipment quantities differ')
    require(number(order_line['qtyordered']) == number(order_line['qtydelivered']) ==
            number(invoice_line['qtyinvoiced']) == 3, 'Quantity outcome differs')
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
    require(len(moves) == int(trace['inventory.movements']) and len(moves) == 3, 'Missing inventory movement readback')
    order_tax = only('c_ordertax', c_order_id=order['c_order_id'])
    invoice_tax = only('c_invoicetax', c_invoice_id=invoice['c_invoice_id'])
    require(order_tax['c_tax_id'] == invoice_tax['c_tax_id'] == order_line['c_tax_id'] == 107, 'Wrong declared fixture tax')
    require(number(only('c_tax', c_tax_id=107)['rate']) == Decimal(INPUT['tax_percent']), 'Tax fixture rate changed')
    checks = check_business_values(customer, order_line, order, invoice, order_tax, invoice_tax)
    require(all(c['passed'] for c in checks), 'Operations business boundary failed')
    require(trace['customer.name.input'] == INPUT['customer_name'] and trace['customer.description.input'] == 'empty-string', 'Wrong text inputs')
    require(number(trace['partial.delivered']) == 1 and number(trace['partial.reserved']) == 2 and
            number(trace['partial.stock']) == 9, 'Partial shipment checkpoint differs')
    require(number(order_line['qtyreserved']) == 0 and number(order_line['qtyinvoiced']) == 3,
            'Final order fulfillment differs')
    for document, quantity in [(first_line, -1), (shipment_line, -2)]:
        movement = [r for r in moves if r['m_inoutline_id'] == document['m_inoutline_id']]
        require(len(movement) == 1 and number(movement[0]['movementqty']) == quantity,
                'Partial shipment lacks the expected committed stock movement')
    credit = only('c_invoice', c_invoice_id=int(trace['credit.id']))
    reversal = only('c_invoice', c_invoice_id=int(trace['creditReversal.id']))
    require(credit['ref_invoice_id'] == invoice['c_invoice_id'] and credit['c_doctype_id'] == 118,
            'Credit memo is not linked to the original invoice')
    require(credit['docstatus'] == reversal['docstatus'] == 'RE' and
            credit['reversal_id'] == reversal['c_invoice_id'] and reversal['reversal_id'] == credit['c_invoice_id'],
            'Missing reciprocal credit reversal')
    require(credit['c_invoice_uu'] == trace['credit.uuid'] and reversal['c_invoice_uu'] == trace['creditReversal.uuid'],
            'Credit UUID readback differs')
    credit_line = only('c_invoiceline', c_invoice_id=credit['c_invoice_id'])
    reverse_line = only('c_invoiceline', c_invoice_id=reversal['c_invoice_id'])
    require(number(credit_line['qtyinvoiced']) == 1 and number(reverse_line['qtyinvoiced']) == -1,
            'Credit reversal quantity differs')
    require(credit_line['m_product_id'] == reverse_line['m_product_id'] == product['m_product_id'],
            'Credit reversal product differs')
    for row, sign in [(credit, 1), (reversal, -1)]:
        require(number(row['totallines']) == Decimal('18.00')*sign and
                number(row['grandtotal']) == Decimal('19.35')*sign, 'Credit/reversal amount differs')
        tax_row = only('c_invoicetax', c_invoice_id=row['c_invoice_id'])
        require(number(tax_row['taxamt']) == Decimal('1.35')*sign, 'Credit/reversal tax differs')
    credit_facts = [r for r in table('fact_acct') if r['ad_table_id'] == 318 and
                    r['record_id'] in (credit['c_invoice_id'], reversal['c_invoice_id'])]
    require({r['record_id'] for r in credit_facts} == {credit['c_invoice_id'], reversal['c_invoice_id']},
            'Missing credit or reversal accounting')
    by_account = {}; credit_groups = {}
    for row in credit_facts:
        key = (row['c_acctschema_id'], row['c_currency_id'], row['account_id'])
        delta = (number(row['amtacctdr'])-number(row['amtacctcr']),
                 number(row['amtsourcedr'])-number(row['amtsourcecr']))
        by_account[key] = tuple(a+b for a,b in zip(by_account.get(key, (0,0)), delta))
        group = (row['record_id'], row['c_acctschema_id'], row['c_currency_id'])
        credit_groups[group] = tuple(a+b for a,b in zip(credit_groups.get(group, (0,0)), delta))
    require(all(v == (0,0) for v in by_account.values()), 'Reversal does not cancel each accounting account')
    require(all(v == (0,0) for v in credit_groups.values()), 'Unbalanced credit/reversal document')
    retry = only('c_bpartner', c_bpartner_id=int(trace['recoveryCustomer.id']))
    require(retry['value'] == 'LY-BOUNDARY-RETRY' and retry['c_bpartner_uu'] == trace['recoveryCustomer.uuid'],
            'Missing retried application record')
    require(sum(r['value'] == 'LY-BOUNDARY-RETRY' for r in table('c_bpartner')) == 1,
            'Retry produced a duplicate business key')
    require(all(r['c_bpartner_id'] != int(trace['recovery.rolledBackId']) for r in table('c_bpartner')),
            'Rolled-back record survived')
    require(trace['recovery.rowsAfterRollback'] == '0' and trace['recovery.rowsAfterRepeatedRequest'] == '1'
            and trace['recovery.repeatedRequest'] == 'existing-record-returned', 'Failure/retry checkpoint differs')
    require(number(customer['so_creditlimit']) == Decimal('100.02') and
            number(trace['concurrency.finalCreditLimit']) == Decimal('100.02'), 'Concurrent update was lost')
    require(number(trace['concurrency.firstValue']) == Decimal('100.01') and
            number(trace['concurrency.secondValue']) == Decimal('100.02') and
            trace['concurrency.secondWaitedForLock'] == 'true', 'Controlled lock interleaving failed')
    require(trace['concurrency.lockingApi'] == 'Query.setForUpdate(true).list-single-primary-key',
            'The failed firstOnly locking API cannot inherit the collection-query result')
    return seal({'artifact_type': 'lightyear-native-operations-journey-lane', 'lane': lane,
                 'evidence_class': 'native-application-and-database-observation', 'independently_attested': False,
                 'trace': trace, 'trace_sha256': trace_hash, 'execution_sha256': execution['content_sha256'],
                 'state_sha256': snapshot['content_sha256'], 'harness_sha256': execution['harness_sha256'],
                 'stages': list(STAGES), 'status': 'passed-bounded-operations-readback',
                 'business_checks': checks,
                 'accounting_entries_verified': len(accounting), 'balanced_accounting_groups': len(balances),
                 'credit_reversal_accounting_entries': len(credit_facts),
                 'balanced_credit_reversal_groups': len(credit_groups),
                 'observed_table_row_hashes': {name: snapshot['tables'][name]['row_multiset'] for name in observed_tables}})


def compare_lanes(lanes, effects):
    require(set(lanes) == {'oracle', 'postgresql'}, 'Both operations lanes required')
    verify(effects)
    require(effects['artifact_type'] == 'lightyear-bounded-application-effects', 'Wrong effects checkpoint')
    require(effects['state_sha256'] == {lane: value['state_sha256'] for lane, value in lanes.items()},
            'Operations readbacks and effects refer to different states')
    for lane, value in lanes.items():
        verify(value)
        require(value['lane'] == lane and value['artifact_type'] == 'lightyear-native-operations-journey-lane', 'Wrong operations lane')
        require(value['evidence_class'] == 'native-application-and-database-observation', 'Non-native operations evidence')
        require(value['status'] == 'passed-bounded-operations-readback', 'Incomplete operations checks')
        require(len(value['business_checks']) == 14 and all(c['passed'] for c in value['business_checks']), 'Business checks did not pass')
    require(lanes['oracle']['harness_sha256'] == lanes['postgresql']['harness_sha256'], 'Different operations harnesses')
    traces = {lane: value['trace'] for lane, value in lanes.items()}
    require(set(traces['oracle']) == set(traces['postgresql']), 'Different operations trace fields')
    numeric_fields = {'openingInventory.quantity', 'shipment.delivered', 'payment.amount', 'order.reserved',
                      'invoice.total', 'order.total', 'order.net', 'inventory.onHand', 'partial.delivered',
                      'partial.reserved', 'partial.stock', 'credit.net', 'credit.total', 'creditReversal.total',
                      'order.priceList', 'order.priceActual', 'order.discount', 'order.taxRate',
                      'concurrency.firstValue', 'concurrency.secondValue', 'concurrency.finalCreditLimit'}
    differences = []
    for field, a in traces['oracle'].items():
        b = traces['postgresql'][field]
        if a == b: continue
        rule = None
        if field == 'database' and a == 'oracle' and b == 'postgresql': rule = 'expected-engine-identity'
        elif field.endswith('.uuid') and valid_uuid(a) and valid_uuid(b): rule = 'validated-generated-uuid'
        elif field in numeric_fields and number(a) == number(b): rule = 'exact-decimal-value'
        differences.append({'field': field, 'oracle': a, 'postgresql': b, 'rule': rule})
    passed = effects['admitted_for_selected_journeys'] and not effects['unresolved_differences'] and all(x['rule'] for x in differences)
    return seal({'artifact_type': 'lightyear-native-operations-journey-comparison',
                 'status': 'passed-bounded-operations-equivalence' if passed else 'operations-review-required',
                 'bounded_operations_equivalence': bool(passed),
                 'lane_receipt_sha256': {lane: value['content_sha256'] for lane, value in lanes.items()},
                 'effect_checkpoint_sha256': effects['content_sha256'], 'raw_trace_differences': differences,
                 'unresolved_row_difference_count': len(effects['unresolved_differences']),
                 'schema_equivalence': False, 'application_equivalence': False, 'platform_qualification': False,
                 'scope': 'Two partial shipments and aggregate invoice; one credit and its reversal; pre-commit injected rollback and caller-keyed retry; two overlapping explicit-row-lock updates'})
