import os
from pathlib import Path
import tempfile
import unittest
from tools.b06_host_probe.transient_peak import run

class TransientPeakTests(unittest.TestCase):
    def test_output_reuse_refused_before_compilation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'transient-output-exists'):
                run(Path('missing-jdk'),Path(tmp))

    @unittest.skipUnless(os.environ.get('B06_HOST_JDK'),'explicit host JDK not configured')
    def test_production_serializer_at_85_percent_192_mib_heap(self):
        override=os.environ.get('B06_HOST_OBSERVER_SOURCE')
        with tempfile.TemporaryDirectory() as tmp:
            result=run(Path(os.environ['B06_HOST_JDK']),Path(tmp)/'peak',Path(override) if override else None)
            self.assertEqual(result['heap_max_bytes'],192*1024*1024)
            self.assertGreaterEqual(result['heap_before_bytes'],.85*result['heap_max_bytes'])
            self.assertEqual(result['definition_bytes'],1024*1024)
            self.assertEqual(result['graph_nodes'],4096)
            self.assertTrue(result['independent_reference_equal'])
            self.assertGreater(result['serialization_allocated_bytes'],0)
            self.assertLess(result['sampled_peak_bytes'],result['heap_max_bytes'])
            self.assertFalse(result['oom'])

if __name__=='__main__':unittest.main()
