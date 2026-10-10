import json
from pathlib import Path
import tempfile
import unittest
from tools.b06_host_probe.alternatives_analysis import summarize,compare


class AlternativesTests(unittest.TestCase):
    def test_jdk_method_is_not_image_only_proof(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'events.jsonl'
            path.write_text(json.dumps(dict(sequence=1,kind='generation-entry',record=dict(entry_method='java.lang.invoke.InnerClassLambdaMetafactory.spinInnerClass')))+'\n')
            result=summarize(path)
            self.assertEqual(result['classifications'],{'unresolved':1})
            self.assertFalse(result['complete']);self.assertEqual(result['percentages']['unresolved'],100)
    def test_partial_run_cannot_claim_calls_removed(self):
        with self.assertRaisesRegex(ValueError,'incomplete'):
            compare(dict(complete=False),dict(complete=True),{}, {})
    def test_different_workload_cannot_claim_reduction(self):
        with self.assertRaisesRegex(ValueError,'workload'):
            compare(dict(complete=True),dict(complete=True),dict(iterations=1),dict(iterations=2))
    def test_matched_complete_comparison_is_not_native_extrapolation(self):
        workload=dict(fixture_sha256='a'*64,input_sha256='b'*64,iterations=100)
        result=compare(dict(complete=True,watched_calls=20),dict(complete=True,watched_calls=15),workload,workload)
        self.assertEqual(result['percentage_removed'],25);self.assertFalse(result['extrapolation_to_native_allowed'])
