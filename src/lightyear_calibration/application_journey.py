"""Compare committed native outcomes of the pinned six-stage iDempiere journey.

Application traces are checked against independently read database rows. The
result remains bounded to this scenario and requires a separately admitted
whole-state comparison before a journey-equivalence claim can become true.
"""
from decimal import Decimal
import argparse
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from .contracts import canonical, digest, read_json, require, seal, verify
from .native_reconciliation import rows, state, valid_uuid

STAGES = {'customer': 'c_bpartner', 'product': 'm_product', 'order': 'c_order',
          'shipment': 'm_inout', 'invoice': 'c_invoice', 'payment': 'c_payment'}
AUXILIARY = {'customerLocation': 'c_bpartner_location', 'productPrice': 'm_productprice',
             'openingInventory': 'm_inventory'}
SOURCE_COMMIT = '731515dcdd5278b843db33b9d3109d155b881951'


def read_trace(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 65536, 'Application trace exceeds bound')
    root = ET.fromstring(raw)
    require(root.tag == 'properties', 'Wrong application trace format')
    result = {}
    for element in root:
        if element.tag == 'comment': continue
        require(element.tag == 'entry' and not list(element), 'Unexpected trace element')
        key = element.get('key')
        require(key and key not in result and element.text is not None, 'Duplicate or missing trace field')
        result[key] = element.text
    return result, hashlib.sha256(raw).hexdigest()


def number(value):
    require(not isinstance(value, bool), 'Boolean is not a monetary or quantity value')
    if isinstance(value, dict):
        require(set(value) == {'decimal'}, 'Unknown numeric observation')
        value = value['decimal']
    result = Decimal(str(value))
    require(result.is_finite(), 'Nonfinite application value')
    return result


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
    require(price['m_product_id'] == product['m_product_id'] and number(price['pricestd']) == 10, 'Product pricing setup differs')
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
            number(shipment_line['movementqty']) == number(invoice_line['qtyinvoiced']) == 2, 'Quantity outcome differs')
    require(number(order['totallines']) == 20, 'Order net amount differs')
    require(number(order['grandtotal']) == number(invoice['grandtotal']) == number(payment['payamt']) > 0, 'Monetary outcomes differ')
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
    require(stock and sum(number(r['qtyonhand']) for r in stock) == 8, 'Closing inventory differs')
    require(number(trace['inventory.onHand']) == 8 and number(trace['openingInventory.quantity']) == 10, 'Inventory trace differs')
    moves = [r for r in table('m_transaction') if r['m_product_id'] == product['m_product_id']]
    require(len(moves) == int(trace['inventory.movements']) and len(moves) >= 2, 'Missing inventory movement readback')
    return seal({'artifact_type': 'lightyear-native-application-journey-lane', 'lane': lane,
                 'evidence_class': 'native-application-and-database-observation', 'independently_attested': False,
                 'trace': trace, 'trace_sha256': trace_hash, 'execution_sha256': execution['content_sha256'],
                 'state_sha256': snapshot['content_sha256'], 'harness_sha256': execution['harness_sha256'],
                 'stages': list(STAGES), 'status': 'passed-committed-journey-readback',
                 'accounting_entries_verified': len(accounting), 'balanced_accounting_groups': len(balances),
                 'observed_table_row_hashes': {name: snapshot['tables'][name]['row_multiset'] for name in observed_tables}})


def compare_lanes(lanes, effect_checkpoint):
    require(set(lanes) == {'oracle', 'postgresql'}, 'Both application lanes required')
    verify(effect_checkpoint)
    require(effect_checkpoint.get('artifact_type') == 'lightyear-bounded-application-effects', 'Wrong effects checkpoint')
    require(effect_checkpoint['state_sha256'] == {lane: x['state_sha256'] for lane, x in lanes.items()}, 'Application effects refer to different states')
    for lane, item in lanes.items():
        verify(item)
        require(item['lane'] == lane and item['status'] == 'passed-committed-journey-readback', 'Invalid application lane')
        require(item['evidence_class'] == 'native-application-and-database-observation', 'Non-native application evidence')
        require(item['stages'] == list(STAGES), 'Incomplete application journey')
    require(lanes['oracle']['harness_sha256'] == lanes['postgresql']['harness_sha256'], 'Different journey harnesses')
    traces = {lane: x['trace'] for lane, x in lanes.items()}
    require(set(traces['oracle']) == set(traces['postgresql']), 'Different trace fields')
    differences = []
    for field, left in traces['oracle'].items():
        right = traces['postgresql'][field]
        if left == right: continue
        rule = None
        if field == 'database' and left == 'oracle' and right == 'postgresql': rule = 'expected-engine-identity'
        elif field.endswith('.uuid') and valid_uuid(left) and valid_uuid(right): rule = 'validated-generated-uuid'
        elif field in {'openingInventory.quantity', 'shipment.delivered', 'payment.amount', 'order.reserved',
                        'invoice.total', 'order.total', 'order.net', 'inventory.onHand'} and number(left) == number(right):
            rule = 'exact-decimal-value'
        differences.append({'field': field, 'oracle': left, 'postgresql': right, 'rule': rule})
    passed = (effect_checkpoint.get('admitted_for_selected_journeys') is True and
              effect_checkpoint.get('unresolved_differences') == [] and all(x['rule'] for x in differences))
    return seal({'artifact_type': 'lightyear-native-application-journey-comparison',
                 'status': 'passed-bounded-journey-equivalence' if passed else 'application-review-required',
                 'bounded_journey_equivalence': passed, 'stages': list(STAGES), 'raw_trace_differences': differences,
                 'lane_receipt_sha256': {lane: x['content_sha256'] for lane, x in lanes.items()},
                 'effect_checkpoint_sha256': effect_checkpoint['content_sha256'],
                 'schema_equivalence': False, 'application_equivalence': False, 'platform_qualification': False,
                 'scope': 'One priced, stocked customer-to-payment journey through six stages on the pinned application; no broader application certification'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for lane in ('oracle', 'postgresql'):
        for item in ('snapshot', 'trace', 'execution'):
            parser.add_argument('--'+lane+'-'+item, required=True, type=Path)
    parser.add_argument('--harness', required=True, type=Path)
    parser.add_argument('--effect-checkpoint', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    lanes = {lane: verify_lane(getattr(args, lane+'_snapshot'), getattr(args, lane+'_trace'),
                               read_json(getattr(args, lane+'_execution')), args.harness.read_bytes())
             for lane in ('oracle', 'postgresql')}
    result = compare_lanes(lanes, read_json(args.effect_checkpoint))
    args.output.mkdir(parents=True, exist_ok=False)
    for lane, receipt in lanes.items(): (args.output/(lane+'.json')).write_bytes(canonical(receipt))
    (args.output/'comparison.json').write_bytes(canonical(result))
    print(result['status'])
    return 0 if result['bounded_journey_equivalence'] else 3


if __name__ == '__main__': raise SystemExit(main())
