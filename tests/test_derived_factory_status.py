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
        if 'INTCALC' in changed['projections']:
            changed['projections']['INTCALC']['projected_thresholds']['twin']['kill_rate']='41/42'
        else:
            release['scopes']['twin']['projected']['kill_rate']='41/42'
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
        import json
        from tools.release_status_records import ROOT
        model['projections']['INTCALC']=json.loads((ROOT/'docs/factory/intcalc-review-verdict-2026-10-16.json').read_bytes())
        model['projection_paths']['INTCALC']='docs/factory/intcalc-review-verdict-2026-10-16.json'
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
        model["projections"].pop("INTCALC",None)
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

    def test_carddemo_b06_and_pr_states_are_evidence_driven(self):
        model=load(); before=render(model)[1]
        row=model['carddemo']['measured']['vsam'][0]
        row['round_trip'].update(matched=2,compared=7)
        row['browse_order'].update(matched=3,compared=8)
        model['carddemo']['measured']['screen_gates']['sessions_compared']=17
        model['b06']['root_accessible']=False
        model['b06']['criterion_b']['supported']=True
        next(r for r in model['delivery']['merges'] if r['number']==341)['state']='OPEN'
        text=render(model)[1]
        self.assertNotEqual(before,text)
        self.assertIn('Screen sessions compared: 17',text)
        self.assertIn('Windows metadata accessible: False',text)
        self.assertIn('Supported preregistered criteria: criterion_b',text)
        self.assertIn('#341: open',text)
        from tools.release_status_records import carddemo_text
        self.assertIn(carddemo_text(model['carddemo']),text)

    def test_verdict_link_date_matches_the_headline_record(self):
        import json
        from tools.release_status_records import ROOT
        model=load();value,text=render(model)
        path=ROOT/value['verdict_path']
        self.assertEqual(json.loads(path.read_bytes())['prepared_on'],value['as_of'])
        self.assertIn('[Measured verdict]('+path.with_suffix('.md').name+')',text)

    def test_projection_headline_distinguishes_raw_gaps_and_unresolved_mutants(self):
        from tools.build_oct16_review_projections import verdict
        report=dict(program='POSTTRAN',projected_thresholds={'twin':{'unresolved_survivors':list(range(10))}},
                    evidence_gaps=list(range(9)),business={'fraction':'3/4'},io={'fraction':'5/6'},
                    effective=False,release_authorized=False)
        self.assertIn('10 unresolved twin mutants; 9 raw campaign gaps',verdict(report))
        report['evidence_gaps'].pop();report['projected_thresholds']['twin']['unresolved_survivors'].pop()
        self.assertIn('9 unresolved twin mutants; 8 raw campaign gaps',verdict(report))
