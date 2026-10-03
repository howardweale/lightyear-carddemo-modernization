"""Prospective J2 invoice/date predicates supplementing the native v3 judge.

The inherited judge still owns quantities, amounts, allocation sign, ownership,
write footprint and full native reconciliation. These checks are not a qualified
gate until the combined native adapter and its mutant campaign pass.
"""
from lightyear_calibration.ms94_v3_errors import business_require


def verify_rows(before, after, trace, business_date):
    def one(tables, table, **where):
        found = [r for r in tables[table] if all(r.get(k) == v for k,v in where.items())]
        business_require(len(found) == 1, 'procurement-missing-or-ambiguous-row')
        return found[0]
    docs = {}
    for stage, table, base in (('purchaseOrder','c_order','POO'),('receipt','m_inout','MMR'),
                               ('vendorInvoice','c_invoice','API'),('vendorPayment','c_payment','APP')):
        row = one(after, table, **{table+'_id': int(trace[stage+'.id'])})
        dtype = one(before, 'c_doctype', c_doctype_id=row['c_doctype_id'])
        business_require(dtype['docbasetype'] == base and dtype['issotrx'] == 'N',
                         'procurement-document-type')
        if 'c_doctypetarget_id' in row:
            business_require(row['c_doctypetarget_id'] == row['c_doctype_id'], 'procurement-target-document-type')
        business_require(str(row['dateacct'])[:10] == business_date, 'procurement-accounting-date')
        docs[stage] = row
    for stage, field in (('purchaseOrder','dateordered'),('purchaseOrder','datepromised'),
                         ('receipt','movementdate'),('vendorInvoice','dateinvoiced'),('vendorPayment','datetrx')):
        business_require(str(docs[stage][field])[:10] == business_date, 'procurement-document-date')
    relevant = {(318,docs['vendorInvoice']['c_invoice_id']), (335,docs['vendorPayment']['c_payment_id'])}
    allocations = [r for r in after['c_allocationline'] if
                   r['c_invoice_id'] == docs['vendorInvoice']['c_invoice_id'] and
                   r['c_payment_id'] == docs['vendorPayment']['c_payment_id']]
    for row in allocations:
        header = one(after, 'c_allocationhdr', c_allocationhdr_id=row['c_allocationhdr_id'])
        business_require(str(header['dateacct'])[:10] == business_date, 'procurement-allocation-date')
        relevant.add((735,header['c_allocationhdr_id']))
    facts = [r for r in after['fact_acct'] if (r['ad_table_id'],r['record_id']) in relevant]
    business_require(facts and {(r['ad_table_id'],r['record_id']) for r in facts} == relevant,
                     'procurement-accounting-missing')
    for row in facts:
        period = one(before,'c_period',c_period_id=row['c_period_id'])
        business_require(str(row['dateacct'])[:10] == business_date and
                         str(period['startdate'])[:10] <= business_date <= str(period['enddate'])[:10],
                         'procurement-posting-period')
    return {'passed':True,'invoice_type_checked':True,'all_document_dates_checked':True,
            'posting_period_checked':True,'facts_checked':len(facts)}
