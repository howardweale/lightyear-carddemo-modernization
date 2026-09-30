"""Prospective public relationship check; never applied to a prior declaration."""
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, seal, verify
from lightyear_calibration.native_reconciliation import state, rows
from lightyear_calibration.application_journey import read_trace

PUBLIC = Path('factory/idempiere/qualification-ms94-v5/public')


def check_rows(order, invoice, document_types):
    """Compare configured relationships, never a fixture-specific identifier."""
    matches = [r for r in document_types if r['c_doctype_id'] == order['c_doctype_id']]
    require(len(matches) == 1, 'Missing or ambiguous order document type')
    expected = matches[0]['c_doctypeinvoice_id']
    require(type(expected) is int and expected > 0, 'Missing order-derived invoice type')
    require(sum(r['c_doctype_id'] == expected for r in document_types) == 1,
            'Missing or ambiguous configured invoice type')
    return [field for field in ('c_doctypetarget_id', 'c_doctype_id') if invoice[field] != expected]


def evaluate(run):
    run = Path(run)
    contract = read_json(run/'inputs/invoice-type-contract.json'); verify(contract)
    require(contract['version'] == 'ms94-public-shapes-v5-order-derived-invoice', 'Wrong invoice type contract')
    lanes = {}
    for lane in ('oracle', 'postgresql'):
        folder = run/'cases/operations/1/after'/lane
        snapshot = state(folder, lane)
        trace, _ = read_trace(run/'cases/operations/1/execution'/lane/'journey.xml')
        def table(name):
            require(name in snapshot['tables'], 'Missing invoice type evidence table')
            return rows(folder, snapshot['tables'][name])
        def only(name, identity):
            matches = [r for r in table(name) if r[name+'_id'] == identity]
            require(len(matches) == 1, 'Missing or ambiguous invoice type evidence row')
            return matches[0]
        fields = check_rows(only('c_order', int(trace['order.id'])),
                            only('c_invoice', int(trace['invoice.id'])), table('c_doctype'))
        lanes[lane] = {'passed': not fields, 'stage': 'invoice', 'divergent_fields': fields}
    return seal({'contract_sha256': contract['content_sha256'], 'lanes': lanes,
                 'passed': all(x['passed'] for x in lanes.values()), 'builder_visible': False})
