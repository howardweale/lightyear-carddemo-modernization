"""Frozen inputs and independently calculated expectations for the risky journey."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from .application_journey import number
from .contracts import digest

INPUT = {
    'scenario': 'fractional-tax-unicode-empty-timestamp-v1',
    'list_price': '19.995', 'discount_percent': '10', 'quantity': '3',
    'tax_percent': '7.5', 'currency_scale': 2, 'rounding': 'HALF_UP',
    'customer_name': 'Café 東京 Łódź', 'optional_description': '',
    'shipment_timestamp': '2026-09-26T12:34:56.123456',
    'opening_stock': '10',
}


def expected():
    price = Decimal(INPUT['list_price'])*(1-Decimal(INPUT['discount_percent'])/100)
    net = (price*Decimal(INPUT['quantity'])).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    tax = (net*Decimal(INPUT['tax_percent'])/100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return {'actual_price': price, 'net': net, 'tax': tax, 'gross': net+tax,
            'ending_stock': Decimal(INPUT['opening_stock'])-Decimal(INPUT['quantity'])}


def check_business_values(customer, order_line, order, invoice, order_tax, invoice_tax):
    e = expected()
    checks = []
    def check(name, actual, expected, passed):
        checks.append({'check': name, 'observed': actual, 'expected': expected, 'passed': bool(passed)})
    for field, target in [('pricelist', Decimal(INPUT['list_price'])), ('priceactual', e['actual_price']),
                          ('discount', Decimal(INPUT['discount_percent'])), ('linenetamt', e['net'])]:
        value = order_line[field]
        check('order-line-'+field, value, str(target), number(value) == target)
    for label, row in [('order', order), ('invoice', invoice)]:
        for field, target in [('totallines', e['net']), ('grandtotal', e['gross'])]:
            check(label+'-'+field, row[field], str(target), number(row[field]) == target)
    for label, row in [('order-tax', order_tax), ('invoice-tax', invoice_tax)]:
        for field, target in [('taxbaseamt', e['net']), ('taxamt', e['tax'])]:
            check(label+'-'+field, row[field], str(target), number(row[field]) == target)
    name = customer['name']
    check('unicode-customer-name', name, INPUT['customer_name'], name == INPUT['customer_name'])
    # This is the ordinary PO empty-string contract; raw SQL empty text differs.
    check('empty-optional-description', customer['description'], None, customer['description'] is None)
    return checks


def check_values(customer, order_line, order, invoice, order_tax, invoice_tax, shipment):
    checks = check_business_values(customer, order_line, order, invoice, order_tax, invoice_tax)
    value = shipment['shipdate']
    try:
        equal = datetime.fromisoformat(value) == datetime.fromisoformat(INPUT['shipment_timestamp'])
    except (TypeError, ValueError):
        equal = False
    checks.append({'check': 'fractional-shipment-timestamp-preserved', 'observed': value,
                   'expected': INPUT['shipment_timestamp'], 'passed': equal})
    return {'input_sha256': digest(INPUT), 'checks': checks,
            'all_inputs_and_business_outcomes_preserved': all(x['passed'] for x in checks)}
