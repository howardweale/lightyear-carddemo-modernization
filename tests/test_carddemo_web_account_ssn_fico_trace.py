import json
from pathlib import Path
import shutil
import tempfile
import unittest
from tools.check_carddemo_java_trace import check, JAVA

ROOT=Path(__file__).resolve().parents[1]
SCOPE='spec/modernization/carddemo-screens/idiomatic-account-ssn-fico-scope.json'

class AccountSsnFicoTraceTests(unittest.TestCase):
    def test_three_rules_map_to_pinned_source(self):
        result=check(ROOT,SCOPE)
        self.assertEqual(3,result['rules'])
        self.assertEqual(set(json.loads((ROOT/SCOPE).read_bytes())['validation_paragraphs']),
                         {row['paragraph'] for row in result['methods']})

    def test_missing_paragraph_or_range_crossing_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);scope=json.loads((ROOT/SCOPE).read_bytes())
            for name in [SCOPE,scope['source']['path'],JAVA+'/AccountSsnRule.java',JAVA+'/AccountFicoRule.java']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
            scope['validation_paragraphs'].append('1260-EDIT-US-PHONE-NUM')
            (root/SCOPE).write_text(json.dumps(scope))
            with self.assertRaisesRegex(ValueError,'unmapped-validation-paragraph'):check(root,SCOPE)
            shutil.copyfile(ROOT/SCOPE,root/SCOPE)
            p=root/JAVA/'AccountSsnRule.java'
            p.write_text(p.read_text().replace('2431-2488','2431-2489'))
            with self.assertRaisesRegex(ValueError,'paragraph-range'):check(root,SCOPE)
