"""Partial invoice evidence floors and unexplained differences fail closed."""
import copy
import unittest
from lightyear_calibration.contracts import seal
from lightyear_calibration.partial_invoicing import compare_lanes

class PartialInvoiceTests(unittest.TestCase):
    def fixture(self):
        lanes={lane:seal({'lane':lane,'evidence_class':'native-application-and-database-observation',
                 'state_sha256':lane,'harness_sha256':'a'*64,'invoices':[{'quantity':'1','gross':'19.35'},{'quantity':'2','gross':'38.69'}],
                 'trace':{'database':lane,'invoice.total':'38.690' if lane=='oracle' else '38.69'}}) for lane in ('oracle','postgresql')}
        effects=seal({'state_sha256':{l:l for l in lanes},'admitted_for_selected_journeys':True,'unresolved_differences':[]})
        return lanes,effects

    def test_exact_decimal_trace_rendering_is_equivalent(self):
        lanes,effects=self.fixture();result=compare_lanes(lanes,effects)
        self.assertTrue(result['bounded_partial_invoicing_equivalence'])
        for key in ('application_equivalence','schema_equivalence','platform_qualification','independently_attested'):self.assertFalse(result[key])

    def test_unknown_trace_difference_is_not_admitted(self):
        lanes,effects=self.fixture()
        for lane,value in lanes.items():
            data={k:v for k,v in value.items() if k!='content_sha256'};data['trace']['unreviewed']=lane;lanes[lane]=seal(data)
        result=compare_lanes(lanes,effects)
        self.assertFalse(result['bounded_partial_invoicing_equivalence'])
        self.assertTrue(any(x['rule'] is None for x in result['raw_trace_differences']))

    def test_one_simulated_lane_cannot_inherit_native_claim(self):
        lanes,effects=self.fixture();data={k:v for k,v in lanes['oracle'].items() if k!='content_sha256'}
        data['evidence_class']='simulated';lanes['oracle']=seal(data)
        with self.assertRaises(ValueError):compare_lanes(lanes,effects)

    def test_unexplained_rows_or_unadmitted_effects_prevent_equivalence(self):
        for change in ({'unresolved_differences':[{'reason':'unknown'}]},{'admitted_for_selected_journeys':False}):
            lanes,effects=self.fixture();effects=seal({**{k:v for k,v in effects.items() if k!='content_sha256'},**change})
            self.assertFalse(compare_lanes(lanes,effects)['bounded_partial_invoicing_equivalence'])

    def test_mismatched_harness_or_readback_cannot_compare(self):
        for field,value in [('harness_sha256','b'*64),('state_sha256','other')]:
            lanes,effects=self.fixture();data={k:v for k,v in lanes['oracle'].items() if k!='content_sha256'}
            data[field]=value;lanes['oracle']=seal(data)
            with self.assertRaises(ValueError):compare_lanes(lanes,effects)

if __name__=='__main__':unittest.main()
