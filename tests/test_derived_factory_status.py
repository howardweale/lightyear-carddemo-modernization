import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.release_status_records import load, render
from tools.build_release_packet import build


class DerivedStatusTests(unittest.TestCase):
    def test_changed_measurements_change_status_and_packet_model(self):
        model = load()
        changed = copy.deepcopy(model)
        release = changed["release"]
        release["programs"]["INTCALC"]["business"]["fraction"] = "6/9"
        release["programs"]["INTCALC"]["io"]["fraction"] = "12/17"
        release["raw_kill_rate"] = "41/63"
        release["programs"]["INTCALC"]["diversity"] = {"fixture": 13}
        changed["projections"]["INTCALC"]["projected_thresholds"]["twin"]["kill_rate"] = "41/42"
        changed["activation"]["signed_only"] = False
        value, text = render(changed)
        for expected in ("6/9", "12/17", "41/63", "41/42", "| fixture | 13 |"):
            self.assertIn(expected, text)
        self.assertFalse(value["factory_activated"])
        self.assertNotEqual(render(model), (value, text))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/"docs/factory").mkdir(parents=True)
            with patch("tools.build_release_packet.load", return_value=changed):
                packet_value = build(root=root)
            self.assertEqual(value, packet_value)
            packet = next((root/"docs/factory").glob("howard-decision-packet-*.md")).read_text()
            self.assertIn("Decisions only.", packet)
            self.assertIn("Missing request inventory; nothing to sign.", packet)
            self.assertIn("All new requests are unsigned.", packet)

    def test_current_review_rates_take_precedence_over_historical_rates(self):
        model = load()
        model["release"]["scopes"]["twin"]["projected"]["kill_rate"] = "historical-only"
        model["projections"]["INTCALC"]["projected_thresholds"]["twin"]["kill_rate"] = "41/42"
        value, text = render(model)
        self.assertEqual("41/42", value["rates"]["twin"]["projected"])
        self.assertIn("41/42", text)
        self.assertNotIn("historical-only", text)
        self.assertFalse(value["effective_policy"])
        self.assertFalse(value["release_authorized"])

    def test_historical_rates_remain_available_without_a_current_review(self):
        model = load()
        model["projections"].pop("INTCALC")
        model["release"]["scopes"]["twin"]["projected"]["kill_rate"] = "41/42"
        value, text = render(model)
        self.assertEqual("41/42", value["rates"]["twin"]["projected"])
        self.assertIn("41/42", text)

    def test_ci_snapshot_cannot_borrow_success_from_another_commit_or_pending_run(self):
        model = load()
        self.assertFalse(render(model)[0]['release_authorized'])
        for field, value in (('head_sha', 'another-commit'), ('status', 'in_progress'), ('conclusion', 'failure')):
            changed = copy.deepcopy(model)
            changed['delivery']['push_workflows'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'delivery-snapshot-not-green'):
                render(changed)

    def test_carddemo_counts_come_from_the_dated_receipt(self):
        model=load();value,text=render(model)
        self.assertIn('27/40 corpus cases matched, 13 unsupported',text)
        self.assertEqual(500000,value['carddemo']['volume']['records'])
        changed=copy.deepcopy(model)
        changed['carddemo']['migrated_ims']['matched']=26
        changed['carddemo']['screens']['api_sessions_compared']=17
        _,text=render(changed)
        self.assertIn('26/40 corpus cases matched',text)
        self.assertIn('sessions: 17/0',text)
        self.assertIn('Overall incomplete',text)

    def test_carddemo_receipt_rejects_tampering_or_hidden_unsupported_cases(self):
        import json
        from hashlib import sha256
        from tools import carddemo_status_record as records
        source=Path(__file__).resolve().parents[1]
        record=records.load(source);record.pop('path')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'docs/modernization';directory.mkdir(parents=True)
            path=directory/'carddemo-slice-1-2026-10-17.json'
            record['migrated_ims']['matched']=40
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'receipt-hash'):records.load(root)
            record['content_sha256']=sha256(json.dumps({k:v for k,v in record.items() if k!='content_sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'denominator'):records.load(root)
