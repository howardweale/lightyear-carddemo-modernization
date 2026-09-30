import copy
import unittest
from lightyear_calibration.contracts import CalibrationError
from lightyear_calibration.ms94_a3_checkpoint import OFFSET, number, verify_table


class CheckpointTransformTests(unittest.TestCase):
    def price(self):
        b={'m_productprice_id':17,'pricelist':{'decimal':'12.25'},'pricestd':7,
           'pricelimit':None,'m_product_id':42,'updated':'unchanged'}
        a={**b,'m_productprice_id':17+OFFSET,'pricelist':{'decimal':'25.50'},'pricestd':15}
        return b,a

    def test_all_declared_price_cells_and_identity_are_checked(self):
        b,a=self.price()
        self.assertEqual(verify_table('m_productprice',[b],[a]),{'identifier_cells':1,'monetary_cells':2})

    def test_undeclared_cell_changes_are_rejected(self):
        for field in ('m_product_id','updated'):
            b,a=self.price();a[field]='changed'
            with self.assertRaises(CalibrationError):verify_table('m_productprice',[b],[a])

    def test_missing_or_incorrect_perturbations_are_rejected(self):
        for field in ('m_productprice_id','pricelist','pricestd'):
            b,a=self.price();a[field]=b[field]
            with self.assertRaises(CalibrationError):verify_table('m_productprice',[b],[a])

    def test_duplicate_or_dropped_rows_are_rejected(self):
        b,a=self.price()
        for before,after in (([b,b],[a,a]),([b],[]),([],[a])):
            with self.assertRaises(CalibrationError):verify_table('m_productprice',before,after)

    def test_stock_quantity_identity_and_other_cells_are_preserved(self):
        b={'m_storageonhand_uu':'stock-1','qtyonhand':7,'m_product_id':42}
        a={**b,'qtyonhand':17}
        self.assertEqual(verify_table('m_storageonhand',[b],[a]),{'quantity_cells':1})
        a['m_product_id']=43
        with self.assertRaises(CalibrationError):verify_table('m_storageonhand',[b],[a])

    def test_only_active_table_identifier_sequences_change(self):
        b=[{'ad_sequence_id':i,'currentnext':20,'istableid':table,'isactive':active}
           for i,(table,active) in enumerate((('Y','Y'),('Y','N'),('N','Y')),1)]
        a=copy.deepcopy(b);a[0]['currentnext']+=OFFSET
        self.assertEqual(verify_table('ad_sequence',b,a),{'identifier_sequence_cells':1})
        a[1]['currentnext']+=OFFSET
        with self.assertRaises(CalibrationError):verify_table('ad_sequence',b,a)

    def test_exact_numeric_contract_rejects_lossy_or_nonfinite_values(self):
        for value in (1.25,True,'1.25',{'decimal':'NaN'},{'decimal':'Infinity'},None):
            with self.assertRaises(CalibrationError):number(value)


if __name__=='__main__':unittest.main()
