import unittest
from tools.legacy_twin.index_order import KEYS
from lightyear_mainframe.posttran_invariants import runtime_register
class IndexedOrderTests(unittest.TestCase):
    def test_mixed_keys_need_storage_adapter(self):
        self.assertNotEqual(sorted(KEYS,key=lambda x:x.encode('ascii')),sorted(KEYS,key=lambda x:x.encode('cp037')))
        self.assertEqual([' ','a','z','A','Z','0','9'],sorted(KEYS,key=lambda x:x.encode('cp037')))
    def test_109_never_disappears_or_becomes_input_rejection(self):
        absent=runtime_register([])[0];self.assertTrue(absent['promotion_blocker']);self.assertEqual('unresolved',absent['status'])
        observed=runtime_register([{'DALYTRAN-ID':'public-test','WS-VALIDATION-FAIL-REASON':'109'}])[0]
        self.assertEqual(['public-test'],observed['observed_rejection_ids'])
        self.assertEqual('unresolved',observed['status'])
