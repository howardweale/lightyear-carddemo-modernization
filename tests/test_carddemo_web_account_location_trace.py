import json
from pathlib import Path
import shutil
import tempfile
import unittest
from tools.check_carddemo_java_trace import check, JAVA

ROOT=Path(__file__).resolve().parents[1]
SCOPE='spec/modernization/carddemo-screens/idiomatic-account-location-scope.json'

class AccountLocationTraceTests(unittest.TestCase):
    def fixture(self, root):
        scope=json.loads((ROOT/SCOPE).read_bytes())
        for name in [SCOPE,scope['source']['path'],JAVA+'/AccountLocationRules.java']:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,path)
        return scope

    def test_two_rules_map_to_original_state_and_zip_paragraphs(self):
        value=check(ROOT,SCOPE)
        self.assertEqual(2,value['rules'])
        self.assertEqual({'state','stateZip'},{r['method'] for r in value['methods']})
        self.assertEqual({'1270-EDIT-US-STATE-CD','1280-EDIT-US-STATE-ZIP-CD'},
                         {r['paragraph'] for r in value['methods']})
        self.assertIn('COACTUPC',value['remaining_statement_engine_programs'])

    def test_scope_missing_rule_and_source_tampering_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);scope=self.fixture(root)
            scope['rule_methods'].append('unmappedRule')
            (root/SCOPE).write_text(json.dumps(scope))
            with self.assertRaisesRegex(ValueError,'unmapped-rule'):check(root,SCOPE)
            scope=self.fixture(root)
            source=root/scope['source']['path'];source.write_bytes(source.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'source-hash'):check(root,SCOPE)

    def test_crossing_range_and_unmapped_record_method_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);path=root/JAVA/'AccountLocationRules.java'
            original=path.read_text()
            path.write_text(original.replace('2493-2513','2493-2514'))
            with self.assertRaisesRegex(ValueError,'paragraph-range'):check(root,SCOPE)
            path.write_text(original+'\nrecord Extra(int value) { public int untraced() { return value; } }\n')
            with self.assertRaisesRegex(ValueError,'unmapped-method'):check(root,SCOPE)
