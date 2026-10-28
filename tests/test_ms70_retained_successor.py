"""CI-only successor-record negatives; no historical evidence rewrite."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from lightyear_data import idempiere_triage as triage
from lightyear_data.contracts import seal
from test_ms70_retained_rebinding import RetainedRebindingTests, ROOT, RECORD

SUCCESSOR=triage.ROOT_PATH/'stage3-retained-rebinding-2026-10-28.json'

class RetainedSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RetainedRebindingTests.setUpClass()
        cls.actual=RetainedRebindingTests.actual
        cls.expected=RetainedRebindingTests.expected
        cls.record=json.loads((ROOT/SUCCESSOR).read_text(encoding='utf-8'))

    def test_successor_preserves_originals_and_predecessor(self):
        paths=[ROOT/RECORD,*(ROOT/triage.ROOT_PATH/n for n in self.record['original_artifacts'])]
        before={str(p):p.read_bytes() for p in paths}
        actual=copy.deepcopy(self.actual)
        self.assertEqual(triage._retained_stage3_projection(ROOT,actual,self.expected),self.expected)
        self.assertEqual(actual,self.actual)
        self.assertEqual(before,{str(p):p.read_bytes() for p in paths})

    def test_resealed_successor_lineage_source_projection_and_claim_changes_refuse(self):
        variants=[]
        for field,value in [('supersedes',{}),('original_artifacts',{}),('new_execution',True),('model_calls',1),('claims',{})]:
            changed=copy.deepcopy(self.record);changed[field]=value;variants.append(changed)
        changed=copy.deepcopy(self.record);changed['implementation_logical_sha256']['src/lightyear_factory/providers.py']='0'*64;variants.append(changed)
        changed=copy.deepcopy(self.record);changed['projected_content_sha256'][triage.RECEIPT_PATH.name]='0'*64;variants.append(changed)
        read=triage._read
        for changed in variants:
            with self.subTest(changed=changed):
                def substituted(path):return seal(changed) if path==ROOT/SUCCESSOR else read(path)
                with patch.object(triage,'_read',side_effect=substituted),self.assertRaises(ValueError):
                    triage._retained_stage3_projection(ROOT,self.actual,self.expected)

    def test_missing_successor_does_not_silently_accept_new_provider(self):
        exists=Path.exists
        def present(path):return False if path==ROOT/SUCCESSOR else exists(path)
        with patch.object(Path,'exists',present),self.assertRaisesRegex(ValueError,'identity mismatch'):
            triage._retained_stage3_projection(ROOT,self.actual,self.expected)

if __name__=='__main__':unittest.main()
