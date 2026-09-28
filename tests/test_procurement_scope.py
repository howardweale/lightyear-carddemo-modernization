"""Investigation must not turn three whole tables into an unrestricted footprint."""
import copy
import unittest
from tools.qualification_procurement_scope import validate,EXTRA
from lightyear_calibration.contracts import CalibrationError


class Scope(unittest.TestCase):
    def setUp(self):
        self.trace={'product.id':'10','vendor.id':'20','purchaseOrder.id':'30','receipt.id':'40','vendorInvoice.id':'50'}
        shared={'m_product_id':10,'ad_client_id':11,'ad_org_id':11}
        self.records={
            'c_orderline':[{**shared,'c_order_id':30,'c_orderline_id':31}],
            'm_inoutline':[{**shared,'m_inout_id':40,'m_inoutline_id':41,'c_orderline_id':31}],
            'c_invoiceline':[{**shared,'c_invoice_id':50,'c_invoiceline_id':51,'m_inoutline_id':41}],
            'c_acctschema':[{'ad_client_id':11,'c_acctschema_id':101}],
            'm_matchinv':[{'m_matchinv_id':60,'c_invoiceline_id':51,'m_inoutline_id':41}],
            'm_costdetail':[{**shared,'m_costdetail_id':70,'c_acctschema_id':101,'c_orderline_id':31,
                            'c_invoiceline_id':None,'m_attributesetinstance_id':0}],
            'm_costqueue':[{**shared,'ad_org_id':0,'c_acctschema_id':101,'m_attributesetinstance_id':0}],
            'm_costhistory':[{**shared,'m_costdetail_id':70,'m_attributesetinstance_id':0}],
            't_fact_acct_history':[]}
        for i in range(2):
            self.records['t_fact_acct_history'].append({**shared,'fact_acct_id':80+i,'c_acctschema_id':101,
                'ad_table_id':472,'record_id':60,'c_bpartner_id':20,'c_currency_id':100,
                'amtacctdr':2 if i==0 else 0,'amtacctcr':0 if i==0 else 2,
                'amtsourcedr':2 if i==0 else 0,'amtsourcecr':0 if i==0 else 2})
        self.before={t:[] for t in EXTRA}

    def check(self):return validate(self.records,self.before,self.trace)

    def test_linked_effects_are_investigated_but_not_admitted(self):
        self.assertFalse(self.check()['admission_granted'])

    def test_foreign_product_rejected(self):
        self.records['m_costqueue'][0]['m_product_id']=999
        with self.assertRaises(CalibrationError):self.check()

    def test_unrelated_cost_detail_rejected(self):
        self.records['m_costhistory'][0]['m_costdetail_id']=999
        with self.assertRaises(CalibrationError):self.check()

    def test_unrelated_reposting_document_rejected(self):
        self.records['t_fact_acct_history'][0]['record_id']=999
        with self.assertRaises(CalibrationError):self.check()

    def test_old_row_modification_rejected(self):
        self.before['m_costqueue']=copy.deepcopy(self.records['m_costqueue'])
        self.records['m_costqueue'][0]['new_field']='changed'
        with self.assertRaises(CalibrationError):self.check()

    def test_missing_history_leg_rejected(self):
        self.records['t_fact_acct_history'].pop()
        with self.assertRaises(CalibrationError):self.check()

    def test_duplicate_history_identity_rejected(self):
        self.records['t_fact_acct_history'][1]['fact_acct_id']=80
        with self.assertRaises(CalibrationError):self.check()


if __name__=='__main__':unittest.main()
