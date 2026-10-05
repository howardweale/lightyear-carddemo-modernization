"""Closed labels from native document rows; no trace or candidate provenance."""
from decimal import Decimal, InvalidOperation
from lightyear_calibration.b06_posting_probe import TABLES
from lightyear_calibration.contracts import digest
from tools.ms94_b06_admission import check


def quantity(value):
    if isinstance(value, dict):
        check(set(value)=={'decimal'}, 'posting-label-quantity-invalid')
        value=value['decimal']
    try:
        result=Decimal(str(value))
    except (InvalidOperation, ValueError):
        check(False, 'posting-label-quantity-invalid')
    check(result.is_finite(), 'posting-label-quantity-invalid')
    return result


def native_label(journey, key, before, after):
    table_id, identity = key
    check(table_id in TABLES, 'posting-label-table')
    table=TABLES[table_id]; pk=table+'_id'
    check(not any(r[pk]==identity for r in before[table]), 'posting-label-preexisting-document')
    found=[r for r in after[table] if r[pk]==identity]
    check(len(found)==1, 'posting-label-document-ambiguous')
    doc=found[0]
    types=[r for r in after['c_doctype'] if r['c_doctype_id']==doc.get('c_doctype_id')]
    check(len(types)==1, 'posting-label-type-ambiguous')
    base=types[0]['docbasetype']; subtype=types[0].get('docsubtypeinv')
    labels={('J1','c_invoice','ARI'):'invoice',('J1','c_invoice','ARC'):'credit',
            ('J1','c_order','SOO'):'order',('J1','m_inout','MMS'):'shipment',
            ('J1','c_payment','ARR'):'payment',('J2','c_order','POO'):'purchaseOrder',
            ('J2','m_inout','MMR'):'receipt',('J2','c_invoice','API'):'vendorInvoice',
            ('J2','c_payment','APP'):'vendorPayment',('J3','m_movement','MMM'):'movement'}
    label=labels.get((journey,table,base))
    if table=='m_inventory' and base=='MMI' and journey in ('J1','J3'):
        if subtype=='IU' and journey=='J3': label='internalUse'
        elif subtype=='PI':
            lines=[r for r in after['m_inventoryline'] if r['m_inventory_id']==identity]
            check(len(lines)==1, 'posting-label-inventory-lines-ambiguous')
            book=quantity(lines[0]['qtybook']);count=quantity(lines[0]['qtycount'])
            if book==0 and count>0: label='openingInventory'
            elif journey=='J3' and book>0: label='physicalCount'
    check(label is not None, 'posting-label-unavailable')
    return label


def project(causes, labels, policy):
    """Called only after real entry/clock/collector/native table replay."""
    check(set(causes)=={'oracle','postgresql'}, 'posting-delivery-lanes')
    if all(c['cause']=='no-posting-failure' and not c['equipment_suspect'] for c in causes.values()):
        return [],False
    if not all(c['cause']=='candidate-prior-processing-flag' and not c['equipment_suspect'] for c in causes.values()):
        return [],True
    check(set(labels)==set(causes), 'posting-label-lanes')
    values=[]
    for label in sorted(set(labels.values())):
        check(label in policy['attribution']['document_labels'], 'posting-label-outside-policy')
        value={'category':'candidate-posting-sequence-misuse','document':label,
               'posting_step':'JourneySupport.postOnce','lanes':'both' if list(labels.values()).count(label)==2 else 'one'}
        value={'id':digest(value),**value}
        check(set(value)==set(policy['attribution']['closed_fields']), 'posting-closed-fields-differ')
        values.append(value)
    return values,False
