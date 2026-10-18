import copy
import json
from pathlib import Path
import unittest
from tools.cms_draft_plan import RECORD,render

class CmsDraftPlanTests(unittest.TestCase):
    def test_committed_plan_and_changed_input_text(self):
        root=Path(__file__).resolve().parents[1];value=json.loads((root/RECORD).read_bytes())
        original=render(value)
        self.assertEqual(original,(root/RECORD).with_suffix('.md').read_text(encoding='utf-8'))
        for field,new in [('payment_equivalence','fixture verdict'),('ci_java_execution',True),('field_identifiers_under_review',46),('checked_at','fixture-time')]:
            changed=copy.deepcopy(value);changed[field]=new
            self.assertNotEqual(original,render(changed));self.assertIn(str(new),render(changed))
        changed=copy.deepcopy(value);changed['pull_requests'][0]['draft']=False
        self.assertNotEqual(original,render(changed))
