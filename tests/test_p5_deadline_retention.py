"""Retained deadline evidence must not accept corruption or unrelated outcomes."""
import copy
from pathlib import Path
import tempfile
import unittest
from tools.ci.p5_terminal_deadline import observe
from tools.ci.p5_additional_controller_drills import deadline_valid


class DeadlineRetentionTests(unittest.TestCase):
    def test_clean_original_documents_bind_report_and_source(self):
        with tempfile.TemporaryDirectory() as temp:
            value=observe(Path(temp)/'clean',False)
        self.assertTrue(deadline_valid(value))
        self.assertTrue(value['artifacts'])
        self.assertEqual(value['source_before_sha256'],value['source_after_sha256'])
        for key,changed in [('work_order_sha256','0'*64),('source_after_sha256','0'*64),('receipt_sha256','0'*64),('ledger_sha256','0'*64),('artifacts',[]),('production_controller_receipt',True)]:
            bad=copy.deepcopy(value);bad[key]=changed
            with self.subTest(field=key):self.assertFalse(deadline_valid(bad))

    def test_modified_report_or_artifact_cannot_replace_original(self):
        with tempfile.TemporaryDirectory() as temp:
            value=observe(Path(temp)/'clean',False)
        bad=copy.deepcopy(value);bad['gate_reports'][0]['gates'][0]['command']=['unrelated']
        self.assertFalse(deadline_valid(bad))
        bad=copy.deepcopy(value);bad['artifacts'][0]['utf8']+=' '
        self.assertFalse(deadline_valid(bad))

    def test_success_cannot_be_relabelled_as_expired_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            value=observe(Path(temp)/'clean',False)
        value.update(expired=True,clock_delta=value['wall_seconds']+1,error='Factory exceeded max_elapsed_seconds')
        self.assertFalse(deadline_valid(value))
