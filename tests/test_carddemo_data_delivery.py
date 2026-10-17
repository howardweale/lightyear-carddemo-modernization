"""Verify that the published bounded review still describes its measured code."""
from hashlib import sha256
import json
from pathlib import Path
import unittest

from lightyear_control_tower.factory_policy import validate_contract
from lightyear_data.carddemo.plan import build

ROOT=Path(__file__).resolve().parents[1]


class DeliveryTests(unittest.TestCase):
    def test_review_request_binds_summary_and_measured_implementation(self):
        request=json.loads((ROOT/'docs/factory/carddemo-data-review-request-2026-10-15.json').read_bytes())
        validate_contract(request)
        source=request['sources'][0];raw=(ROOT/source['path']).read_bytes()
        self.assertEqual(source['sha256'],sha256(raw).hexdigest())
        self.assertEqual(request['details']['packet_sha256'],source['sha256'])
        evidence=json.loads(raw);binding=evidence['summary']
        raw=(ROOT/binding['path']).read_bytes()
        self.assertEqual(binding['sha256'],sha256(raw).hexdigest())
        summary=json.loads(raw);digest=summary.pop('content_sha256')
        self.assertEqual(digest,sha256(json.dumps(summary,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertFalse(summary['release_authorized'])
        self.assertEqual('indeterminate',summary['measured']['verdict'])
        for path,digest in summary['measured']['implementation_files'].items():
            self.assertEqual(digest,sha256((ROOT/path).read_bytes()).hexdigest(),path)
        binding=summary['evidence_index']
        self.assertEqual(binding['sha256'],sha256((ROOT/binding['path']).read_bytes()).hexdigest())

    def test_committed_generated_mapping_matches_pinned_source(self):
        plan,_=build(ROOT/'spec/modernization/carddemo-data')
        retained=json.loads((ROOT/'docs/modernization/carddemo-data-2026-10-15/plan.json').read_bytes())
        self.assertEqual(plan,retained)


if __name__=='__main__':unittest.main()
