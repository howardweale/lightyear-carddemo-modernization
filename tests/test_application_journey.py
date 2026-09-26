"""Synthetic unit fixtures; never published as native application observations."""
from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch
import uuid

from lightyear_calibration.application_journey import AUXILIARY, SOURCE_COMMIT, STAGES, compare_lanes, verify_lane
from lightyear_calibration.contracts import CalibrationError, digest, seal


def fixture(lane='oracle'):
    trace = {'status': 'completed-and-committed', 'newIssueCount': '0', 'database': lane, 'order.total': '20', 'order.net': '20',
             'invoice.total': '20', 'payment.amount': '20', 'shipment.delivered': '2', 'invoice.paid': 'true',
             'inventory.onHand': '8', 'openingInventory.quantity': '10', 'inventory.movements': '2'}
    data = {}
    for i, (stage, table) in enumerate({**STAGES, **AUXILIARY}.items(), 100):
        unique = str(uuid.UUID(int=i))
        trace.update({stage+'.id': str(i), stage+'.uuid': unique, stage+'.saved': 'true', stage+'.status': 'CO'})
        data[table] = [{table+'_id': i, table+'_uu': unique, 'docstatus': 'CO'}]
    data['c_bpartner'][0].update(iscustomer='Y')
    data['m_product'][0].update(issold='Y', isstocked='Y')
    data['c_bpartner_location'][0].update(c_bpartner_id=100)
    data['m_productprice'][0].update(m_product_id=101, pricestd=10)
    data['m_inventoryline'] = [{'m_inventory_id': 108, 'm_product_id': 101, 'qtycount': 10}]
    for table in ('c_order','m_inout','c_invoice','c_payment'):
        data[table][0].update(c_bpartner_id=100, c_bpartner_location_id=106)
    data['c_order'][0].update(totallines=20, grandtotal=20)
    data['m_inout'][0].update(c_order_id=102)
    data['c_invoice'][0].update(grandtotal=20, ispaid='Y')
    data['c_payment'][0].update(payamt=20, c_invoice_id=104)
    data['c_orderline'] = [{'c_order_id':102, 'c_orderline_id':201, 'm_product_id':101, 'qtyordered':2, 'qtydelivered':2}]
    data['m_inoutline'] = [{'m_inout_id':103, 'm_inoutline_id':202, 'c_orderline_id':201, 'm_product_id':101, 'movementqty':2}]
    data['c_invoiceline'] = [{'c_invoice_id':104, 'm_inoutline_id':202, 'm_product_id':101, 'qtyinvoiced':2}]
    data['c_allocationline'] = [{'c_invoice_id':104, 'c_payment_id':105, 'c_allocationhdr_id':301, 'amount':20}]
    data['c_allocationhdr'] = [{'c_allocationhdr_id':301, 'docstatus':'CO'}]
    data['m_storageonhand'] = [{'m_product_id':101, 'qtyonhand':8}]
    data['m_transaction'] = [{'m_product_id':101}, {'m_product_id':101}]
    data['fact_acct'] = []
    for table, record in ((318,104),(335,105),(735,301)):
        for debit, credit in ((20,0),(0,20)):
            data['fact_acct'].append({'ad_table_id':table,'record_id':record,'c_acctschema_id':1,'c_currency_id':100,
                                      'amtacctdr':debit,'amtacctcr':credit,'amtsourcedr':debit,'amtsourcecr':credit})
    return trace, data


def observed(trace, data, lane='oracle'):
    snapshot = seal({'lane':lane, 'evidence_class':'native-database-observation',
                     'tables':{name:{'name':name,'row_multiset':{digest(row):1 for row in records}} for name, records in data.items()}})
    execution = seal({'lane':lane,'exit_code':0,'application_source_commit':SOURCE_COMMIT,
                      'harness_sha256':hashlib.sha256(b'unit-test-only').hexdigest()})
    with patch('lightyear_calibration.application_journey.state', return_value=snapshot), \
         patch('lightyear_calibration.application_journey.rows', side_effect=lambda folder, item:data[item['name']]), \
         patch('lightyear_calibration.application_journey.read_trace', return_value=(trace,'test-trace-hash')):
        return verify_lane('fixture', 'fixture.xml', execution, b'unit-test-only')


class ApplicationJourneyTests(unittest.TestCase):
    def test_business_readback_and_balanced_accounting(self):
        self.assertEqual('passed-committed-journey-readback', observed(*fixture())['status'])

    def test_status_totals_links_stock_and_accounting_are_not_inferred_from_trace(self):
        for mode in ('status','total','link','stock','allocation','accounting','uuid','missing'):
            trace, data = fixture()
            if mode=='status':data['c_invoice'][0]['docstatus']='DR'
            if mode=='total':data['c_invoice'][0]['grandtotal']=21
            if mode=='link':data['c_payment'][0]['c_invoice_id']=999
            if mode=='stock':data['m_storageonhand'][0]['qtyonhand']=7
            if mode=='allocation':data['c_allocationline'][0]['amount']=19
            if mode=='accounting':data['fact_acct'][0]['amtacctdr']=21
            if mode=='uuid':data['c_order'][0]['c_order_uu']=str(uuid.UUID(int=999))
            if mode=='missing':data['c_order']=[]
            with self.subTest(mode=mode), self.assertRaises(CalibrationError): observed(trace, data)

    def test_whole_state_admission_is_required_even_when_business_outcomes_match(self):
        lanes = {lane:observed(*fixture(lane), lane=lane) for lane in ('oracle','postgresql')}
        checkpoint = {'artifact_type':'lightyear-bounded-application-effects',
                      'state_sha256':{lane:item['state_sha256'] for lane,item in lanes.items()},
                      'admitted_for_selected_journeys':True,'unresolved_differences':[]}
        result=compare_lanes(lanes,seal(checkpoint))
        self.assertTrue(result['bounded_journey_equivalence'])
        self.assertFalse(result['application_equivalence']); self.assertFalse(result['platform_qualification'])
        checkpoint['unresolved_differences']=[{'reason':'new-application-issue'}]
        self.assertFalse(compare_lanes(lanes,seal(checkpoint))['bounded_journey_equivalence'])

    def test_mislabeled_or_stale_evidence_does_not_acquire_claim(self):
        lanes = {lane:observed(*fixture(lane), lane=lane) for lane in ('oracle','postgresql')}
        checkpoint=seal({'artifact_type':'lightyear-bounded-application-effects','state_sha256':{lane:item['state_sha256'] for lane,item in lanes.items()},
                         'admitted_for_selected_journeys':True,'unresolved_differences':[]})
        for mode in ('simulated','missing-stage','stale-state','changed-harness'):
            altered=deepcopy(lanes);item=altered['oracle'];item.pop('content_sha256')
            if mode=='simulated':item['evidence_class']='simulated'
            if mode=='missing-stage':item['stages'].pop()
            if mode=='stale-state':item['state_sha256']='0'*64
            if mode=='changed-harness':item['harness_sha256']='0'*64
            altered['oracle']=seal(item)
            with self.subTest(mode=mode), self.assertRaises(CalibrationError):compare_lanes(altered,checkpoint)


if __name__ == '__main__': unittest.main()
