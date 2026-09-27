"""The stopped campaign must remain verifiable without an agent or database."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from tools.publish_journey_campaign import verify_archive

AUDIT = Path(__file__).resolve().parents[1] / 'docs/calibration/idempiere-analyst-repair/campaign-01'


class CampaignAuditTests(unittest.TestCase):
    def test_paired_business_readback_does_not_promote_failed_equivalence(self):
        folder=AUDIT.with_name('campaign-01-paired-review')
        result=verify_archive(folder)
        self.assertEqual(12,result['client_invocations'])
        self.assertEqual(5,result['native_attempts'])
        summary=json.loads((folder/'receipt.json').read_text())
        self.assertEqual('halted-nonrepairable',summary['status'])
        self.assertFalse(summary['attempts'][-1]['passed'])
        run='factory/idempiere/ms86-journeys/runs/'+summary['attempts'][-1]['run_id']
        with zipfile.ZipFile(folder/'campaign-audit.zip') as archive:
            gate=json.loads(archive.read(run+'/gate.json'))
            self.assertFalse(gate['passed'])
            self.assertEqual(2,gate['comparison']['unresolved_row_difference_count'])
            self.assertEqual(5,sum(d['rule'] is None for d in gate['comparison']['raw_trace_differences']))
            for lane in ('oracle','postgresql'):
                value=json.loads(archive.read(run+'/cases/partial-invoicing/1/verified/'+lane+'.json'))
                self.assertEqual('passed-bounded-partial-invoicing-readback',value['status'])
                self.assertEqual(28,value['accounting_entries_verified'])

    def test_live_recheck_forwards_supported_diagnostic_without_a_new_native_attempt(self):
        folder=AUDIT.with_name('campaign-01-recheck')
        result=verify_archive(folder)
        self.assertEqual(10,result['client_invocations'])
        self.assertEqual(4,result['native_attempts'])
        summary=json.loads((folder/'receipt.json').read_text())
        self.assertEqual('repair-feedback-ready',summary['status'])
        self.assertTrue(all(not attempt['passed'] for attempt in summary['attempts']))
        with zipfile.ZipFile(folder/'campaign-audit.zip') as archive:
            selection=json.loads(archive.read('work/ms89/campaign-01/calls/010-analyst/proposal.json'))
            self.assertEqual([{'diagnostic_id':'diagnostic-1','disposition':'forward','reason':'supported-structural-defect'}],selection['decisions'])

    def test_every_call_and_failed_attempt_is_accounted_for(self):
        result = verify_archive(AUDIT)
        self.assertEqual(9, result['client_invocations'])
        self.assertEqual(4, result['native_attempts'])
        self.assertEqual(0, result['human_authored_repair_bytes'])
        self.assertFalse(result['native_gate_replayed'])
        self.assertFalse(result['independently_attested'])

    def test_changed_cost_cannot_be_presented_as_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'audit'
            shutil.copytree(AUDIT, folder)
            path = folder / 'receipt.json'
            receipt = json.loads(path.read_text())
            receipt['cost']['failed_native_attempts'] = 0
            path.write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):
                verify_archive(folder)


if __name__ == '__main__':
    unittest.main()
