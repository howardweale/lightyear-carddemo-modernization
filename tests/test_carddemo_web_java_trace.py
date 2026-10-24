import json
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from tools.check_carddemo_java_trace import check, SCOPE, JAVA
from tools.carddemo_java_proof import summarize

ROOT=Path(__file__).resolve().parents[1]

class CardDemoJavaTraceTests(unittest.TestCase):
    def fixture(self,root):
        scope=json.loads((ROOT/SCOPE).read_bytes())
        for name in [SCOPE,scope['source']['path'],*[JAVA+'/'+f for f in scope['java_files']]]:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,path)

    def test_scoped_rules_have_real_pinned_source_ranges(self):
        value=check(ROOT);self.assertEqual(4,value['rules'])
        self.assertEqual({'PROCESS-ENTER-KEY','READ-USER-SEC-FILE'},
                         {r['paragraph'] for r in value['methods'] if r['file']=='SignonRules.java'})

    def test_unmapped_paragraph_out_of_range_and_interpreter_call_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            scope=json.loads((root/SCOPE).read_bytes());scope['validation_paragraphs'].append('MISSING-PARAGRAPH')
            (root/SCOPE).write_text(json.dumps(scope))
            with self.assertRaisesRegex(ValueError,'unmapped-validation-paragraph'):check(root)
            self.fixture(root);path=root/JAVA/'SignonRules.java';original=path.read_text()
            path.write_text(original.replace('117-130','117-99999'))
            with self.assertRaisesRegex(ValueError,'java-trace-range'):check(root)
            path.write_text(original+'\n// SourceEdits is forbidden in this completed group\n')
            with self.assertRaisesRegex(ValueError,'statement-engine'):check(root)
            path.write_text(original.replace('@CobolSource(program="COSGN00C", paragraph="PROCESS-ENTER-KEY", lines="117-130")',''))
            with self.assertRaisesRegex(ValueError,'unmapped-method'):check(root)

    def test_new_class_cannot_borrow_old_class_score_or_timeout_credit(self):
        def node(name,status):
            n=ET.Element('mutation',status=status);ET.SubElement(n,'mutatedClass').text='ai.lightyear.carddemo.'+name
            return n
        nodes=[node('SignonService','KILLED') for _ in range(100)]
        nodes += [node('SignonRules','KILLED') for _ in range(8)]
        nodes += [node('SignonRules','TIMED_OUT'),node('SignonRules','NO_COVERAGE')]
        value=summarize(nodes,('SignonService','SignonRules'))
        self.assertTrue(value['SignonService']['passed']);self.assertFalse(value['SignonRules']['passed'])
        self.assertEqual(10,value['SignonRules']['total']);self.assertEqual(8,value['SignonRules']['killed'])
        self.assertEqual(2,len(value['SignonRules']['non_killed']))
        self.assertFalse(summarize([],('SignonRules',))['SignonRules']['passed'])
        nodes[-1]=node('SignonRules','KILLED')
        self.assertTrue(summarize(nodes,('SignonRules',))['SignonRules']['passed'])

    def test_trace_annotations_allow_layout_but_preserve_exact_source_identity(self):
        import re
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            expected=check(root)['methods'];path=root/JAVA/'SignonRules.java';original=path.read_text()
            pattern='@CobolSource\\s*\\(\\s*program\\s*=\\s*"([^"]+)"\\s*,\\s*paragraph\\s*=\\s*"([^"]+)"\\s*,\\s*lines\\s*=\\s*"([^"]+)"\\s*\\)'
            for gap in ('','\n  ','\r\n  '):
                formatted=re.sub(pattern,lambda match:'@CobolSource('+gap+'program = "'+match[1]+'",'+gap+'paragraph = "'+match[2]+'",'+gap+'lines = "'+match[3]+'"'+gap+')',original)
                path.write_text(formatted,encoding='utf-8')
                self.assertEqual(expected,check(root)['methods'])
            for replacement in ('', '@CobolSource(program="WRONG", paragraph="PROCESS-ENTER-KEY", lines="117-130")',
                                '@CobolSource(program="COSGN00C", paragraph="PROCESS-ENTER-KEY ", lines="117-130")',
                                '@CobolSource(program="COSGN00C", paragraph="PROCESS-ENTER-KEY", lines="1-99999")'):
                path.write_text(re.sub(pattern,lambda match:replacement,original,count=1),encoding='utf-8')
                with self.assertRaises(ValueError):check(root)
