import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools import carddemo_web_gaps as gaps
from tools import carddemo_status_record as records
from tools.check_carddemo_sql_order import check, violations

ROOT=Path(__file__).resolve().parents[1]
RECEIPT='docs/modernization/carddemo-slice-1-2026-10-18.json'
ADDENDUM='docs/modernization/carddemo-slice-gaps-2026-10-18.json'


class CardDemoGapTests(unittest.TestCase):
    def fixture(self,root):
        for name in (RECEIPT,ADDENDUM,str(Path(ADDENDUM).with_suffix('.md')),records.web_packet_path(RECEIPT)):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())

    def test_dated_text_and_live_status_are_bound_to_original_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            value=records.load_web(root)
            self.assertTrue(value['work_order_acceptance_complete'])
            self.assertEqual(6,len(value['work_order_acceptance_items']))
            self.assertEqual(6,len(value['remaining_evidence_gaps']))
            self.assertIn('49 SURVIVED, 17 NO_COVERAGE, 1 TIMED_OUT',gaps.paragraph(value))
            self.assertEqual((root/ADDENDUM).with_suffix('.md').read_text(encoding='utf-8'),gaps.markdown(value))
            self.assertIn(gaps.paragraph(value),records.web_paragraph(value))

    def test_removing_gap_changes_rendered_status_without_changing_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            before=records.web_paragraph(records.load_web(root));original=(root/RECEIPT).read_bytes()
            value=json.loads((root/ADDENDUM).read_bytes());removed=value['remaining_evidence_gaps'].pop(0)
            (root/ADDENDUM).write_text(json.dumps(value))
            after=records.web_paragraph(records.load_web(root))
            self.assertNotEqual(before,after);self.assertNotIn(removed['description'],after)
            self.assertEqual(original,(root/RECEIPT).read_bytes())

    def test_mutation_counts_and_work_order_items_come_from_receipt(self):
        receipt=json.loads((ROOT/RECEIPT).read_bytes())
        before=gaps.project(ROOT,RECEIPT,receipt)
        changed=copy.deepcopy(receipt);changed['gates']['mutation']['status_counts']['SURVIVED']=50
        changed['gates']['browser']['passed']=False
        after=gaps.project(ROOT,RECEIPT,changed)
        self.assertNotEqual(gaps.markdown(before),gaps.markdown(after))
        self.assertIn('50 SURVIVED',gaps.paragraph(after));self.assertFalse(after['work_order_acceptance_complete'])
        self.assertIn('| browser | false |',gaps.markdown(after))

    def test_changed_receipt_binding_and_empty_gap_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            value=json.loads((root/ADDENDUM).read_bytes());value['receipt']['sha256']='0'*64
            (root/ADDENDUM).write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'gap-receipt-binding'):records.load_web(root)
            self.fixture(root);value=json.loads((root/ADDENDUM).read_bytes());value['remaining_evidence_gaps'][0]['description']=''
            (root/ADDENDUM).write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'empty-description'):records.load_web(root)

    def test_sql_key_order_guard_rejects_wrong_order_and_dynamic_sql(self):
        for sql in ('SELECT * FROM acctdata ORDER BY acct_id',
                    'SELECT * FROM pautdtl1 ORDER BY path_key,ebcdic_key',
                    'SELECT * FROM t ORDER BY lower(user_id)',
                    'SELECT * FROM t ORDER BY " + key',
                    'SELECT * FROM t ORDER\n BY path_key'):
            with self.subTest(sql=sql):self.assertTrue(violations(sql))
        for sql in ('SELECT * FROM t ORDER BY ebcdic_key,path_key LIMIT 1',
                    'SELECT * FROM t ORDER BY t.ebcdic_key DESC',
                    'SELECT tablename FROM pg_tables ORDER BY tablename',
                    "SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM t"):
            with self.subTest(sql=sql):self.assertEqual([],violations(sql))
        self.assertEqual([],check(ROOT))

    def test_current_addendum_retains_gaps_and_discloses_bounded_readers(self):
        value=records.load_web(ROOT)
        self.assertEqual('docs/modernization/carddemo-slice-gaps-2026-10-21.json',value['gap_addendum'])
        self.assertEqual(6,len(value['remaining_evidence_gaps']))
        self.assertIn('50 public and 950 disclosed synthetic',gaps.paragraph(value))
        self.assertIn('49 SURVIVED, 17 NO_COVERAGE, 1 TIMED_OUT',gaps.paragraph(value))
        self.assertTrue(value['work_order_acceptance_complete'])
