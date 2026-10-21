import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.release_status_records import load, render
from tools.build_release_packet import build


class DerivedStatusTests(unittest.TestCase):
    def test_retention_inventory_changes_status_text(self):
        model = load()
        value, text = render(model)
        path = 'docs/factory/evidence-retention-2026-10-18-intcalc.json'
        self.assertIn(path, value['retention_manifests'])
        self.assertIn(Path(path).name, text)
        changed = copy.deepcopy(model)
        changed['retention'].remove(path)
        new_value, new_text = render(changed)
        self.assertNotIn(path, new_value['retention_manifests'])
        self.assertNotIn(Path(path).name, new_text)
        self.assertNotEqual(text, new_text)


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

    def test_web_receipt_coexists_with_earlier_data_and_retains_all_mutants(self):
        model=load();value,text=render(model)
        self.assertEqual(500000,value['carddemo']['volume']['records'])
        self.assertEqual(701,value['carddemo_web']['killed'])
        self.assertEqual(768,value['carddemo_web']['total'])
        self.assertIn('701/768 KILLED (91.28%)',text)
        self.assertIn('49 survivors, 17 uncovered and 1 timeout',text)
        self.assertIn('Final publication-head CI and Howard merge approval are separate',text)

    def test_web_receipt_tampering_and_timeout_credit_are_refused(self):
        import json
        from hashlib import sha256
        from tools import carddemo_status_record as records
        source=Path(__file__).resolve().parents[1]
        receipt_path='docs/modernization/carddemo-slice-1-2026-10-18.json'
        packet_path=records.web_packet_path(receipt_path)
        original=json.loads((source/receipt_path).read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in (receipt_path,packet_path):
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/name).read_bytes())
            self.assertEqual(768,records.load_web(root)['total'])
            bad=copy.deepcopy(original);bad['gates']['mutation']['killed']+=1
            (root/receipt_path).write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'receipt-hash'):records.load_web(root)
            packet=json.loads((root/packet_path).read_bytes())
            packet['receipt']['sha256']=sha256((root/receipt_path).read_bytes()).hexdigest()
            (root/packet_path).write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError,'denominator'):records.load_web(root)
            bad=copy.deepcopy(original);bad['gates']['mutation']['total']-=17
            (root/receipt_path).write_text(json.dumps(bad))
            packet['receipt']['sha256']=sha256((root/receipt_path).read_bytes()).hexdigest()
            (root/packet_path).write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError,'denominator'):records.load_web(root)
    def test_carddemo_b06_and_pr_states_are_evidence_driven(self):
        model=load()
        model['carddemo']=copy.deepcopy(model['carddemo_historical'])
        before=render(model)[1]
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

    def test_projection_date_precedes_current_head_check_but_seals_still_apply(self):
        from tools.release_status_records import review_projection_applies
        from lightyear_control_tower.decisions import digest
        record = dict(prepared_on='2026-10-16', measurement_head='old')
        record['content_sha256'] = digest(record)
        release = dict(prepared_on='2026-10-18')
        self.assertFalse(review_projection_applies('INTCALC', record, release, 'new'))
        self.assertTrue(review_projection_applies('POSTTRAN', record, release, 'old'))
        record['prepared_on'] = '2026-10-18'
        record['content_sha256'] = digest({k:v for k,v in record.items() if k != 'content_sha256'})
        with self.assertRaisesRegex(ValueError, 'evidence-head'):
            review_projection_applies('INTCALC', record, release, 'new')
        record['measurement_head'] = 'new'
        with self.assertRaisesRegex(ValueError, 'seal'):
            review_projection_applies('INTCALC', record, release, 'new')

    def test_new_measurement_date_changes_headline_and_packet_link(self):
        model = load()
        model['projections'].pop('INTCALC', None)
        model['release'].update(schema='intcalc-releasability/3', prepared_on='2026-10-18')
        model['release_path'] = 'docs/factory/intcalc-releasability-2026-10-18.json'
        value, text = render(model)
        self.assertTrue(text.startswith('# Factory current status — 2026-10-18'))
        self.assertIn('[Measured verdict](intcalc-releasability-2026-10-18.md)', text)
        changed = copy.deepcopy(model)
        changed['release']['prepared_on'] = '2026-10-19'
        changed['release_path'] = 'docs/factory/intcalc-releasability-2026-10-19.json'
        self.assertNotEqual(text, render(changed)[1])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'docs/factory').mkdir(parents=True)
            with patch('tools.build_release_packet.load', return_value=changed):
                build(root=root)
            packet = next((root/'docs/factory').glob('howard-decision-packet-*.md')).read_text()
            self.assertIn('intcalc-releasability-2026-10-19.md', packet)
            self.assertIn('As of 2026-10-19', packet)
