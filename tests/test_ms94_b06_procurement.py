"""Supplemental J2 predicates; synthetic rows are not qualification evidence."""
import unittest
from tools.ms94_b06_procurement import verify_rows


def fixture():
    before = {'c_doctype': [], 'c_period': [
        {'c_period_id': 10, 'startdate': '2026-10-01', 'enddate': '2026-10-31'},
        {'c_period_id': 9, 'startdate': '2026-09-01', 'enddate': '2026-09-30'}]}
    after, trace = {}, {}
    for index, (stage, table, base) in enumerate((('purchaseOrder', 'c_order', 'POO'),
            ('receipt', 'm_inout', 'MMR'), ('vendorInvoice', 'c_invoice', 'API'),
            ('vendorPayment', 'c_payment', 'APP')), 1):
        before['c_doctype'].append({'c_doctype_id': index, 'docbasetype': base, 'issotrx': 'N'})
        after[table] = [{table+'_id': index, 'c_doctype_id': index,
            'c_doctypetarget_id': index, **{key: '2026-10-01' for key in
            ('dateacct','dateordered','datepromised','movementdate','dateinvoiced','datetrx')}}]
        trace[stage+'.id'] = str(index)
    after['c_allocationline'] = [{'c_invoice_id': 3, 'c_payment_id': 4, 'c_allocationhdr_id': 5}]
    after['c_allocationhdr'] = [{'c_allocationhdr_id': 5, 'dateacct': '2026-10-01'}]
    after['fact_acct'] = [{'ad_table_id': table, 'record_id': doc, 'dateacct': '2026-10-01', 'c_period_id': 10}
                          for table, doc in ((318,3),(335,4),(735,5))]
    return before, after, trace, '2026-10-01'


class ProcurementTests(unittest.TestCase):
    def test_expected_invoice_type_and_dates(self):
        self.assertTrue(verify_rows(*fixture())['passed'])

    def test_alternate_invoice_type_rejected(self):
        args = fixture()
        args[0]['c_doctype'][2]['docbasetype'] = 'ARI'
        with self.assertRaisesRegex(Exception, 'procurement-document-type'):
            verify_rows(*args)

    def test_accounting_date_and_cached_period_must_both_match(self):
        for table, field, value, reason in (
                ('c_order', 'dateacct', '2026-10-03', 'procurement-accounting-date'),
                ('c_allocationhdr','dateacct','2026-09-30','procurement-allocation-date'),
                ('fact_acct','dateacct','2026-09-30','procurement-posting-period'),
                ('fact_acct','c_period_id',9,'procurement-posting-period')):
            with self.subTest(table=table, field=field):
                args = fixture()
                args[1][table][0][field] = value
                with self.assertRaisesRegex(Exception, reason): verify_rows(*args)

    def test_missing_posting_group_rejected(self):
        args = fixture()
        args[1]['fact_acct'].pop()
        with self.assertRaisesRegex(Exception, 'procurement-accounting-missing'):
            verify_rows(*args)


if __name__ == '__main__': unittest.main()
