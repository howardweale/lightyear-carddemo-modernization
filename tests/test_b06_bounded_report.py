import unittest
from tools.b06_host_probe.bounded_report import fitted_growth

class BoundedFitTests(unittest.TestCase):
    def rows(self,slope):
        return [dict(events=i*1000,heap_used_after_gc=int(10_000_000+slope*i*1000+((-1)**i)*40000)) for i in range(1,201)]
    def test_flat_curve_is_not_positive_and_known_growth_is_detected(self):
        flat=fitted_growth(self.rows(0))
        self.assertFalse(flat['significantly_positive'])
        self.assertLess(flat['slope_95_percent'][0],0)
        growth=fitted_growth(self.rows(100))
        self.assertTrue(growth['significantly_positive'])
        self.assertAlmostEqual(growth['bytes_per_emitted_event'],100,delta=1)
    def test_no_claim_from_insufficient_warmup_or_samples(self):
        with self.assertRaises(ValueError):fitted_growth(self.rows(0)[:60])
