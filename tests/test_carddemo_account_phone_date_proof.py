"""CI-only refusal fixtures for the additional phone/date proof gate."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from tools.carddemo_account_phone_date_proof import CLASSES,SCOPE,JAVA,check_scope,check_service_route,evaluate

class PhoneDateProofTests(unittest.TestCase):
    def report(self, statuses):
        root=ET.Element('mutations')
        for name,values in statuses.items():
            for value in values:
                node=ET.SubElement(root,'mutation',status=value)
                ET.SubElement(node,'mutatedClass').text='ai.lightyear.carddemo.'+name
        return ET.tostring(root)

    def test_each_class_needs_nonempty_ninety_percent_killed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mutations.xml'
            good={name:['KILLED']*9+['SURVIVED'] for name in CLASSES};path.write_bytes(self.report(good))
            self.assertTrue(evaluate(path)['passed'])
            for name in CLASSES:
                missing=copy.deepcopy(good);del missing[name];path.write_bytes(self.report(missing))
                self.assertFalse(evaluate(path)['passed'])
                bad=copy.deepcopy(good);bad[name]=['KILLED']*8+['TIMED_OUT','NO_COVERAGE'];path.write_bytes(self.report(bad))
                self.assertFalse(evaluate(path)['passed'])
            self.assertFalse(evaluate(Path(directory)/'absent.xml')['passed'])

    def test_scope_inventory_hash_routes_and_remaining_scope_fail_closed(self):
        root=Path(__file__).resolve().parents[1];scope=json.loads((root/SCOPE).read_bytes())
        self.assertEqual(3,len(check_scope(root)['retired_ranges']))
        for defect in ('missing-paragraph','hash','range','class','whole-screen','remaining','source-set'):
            bad=copy.deepcopy(scope)
            if defect=='missing-paragraph':bad['sources'][0]['paragraphs'].pop()
            elif defect=='hash':bad['sources'][0]['sha256']='0'*64
            elif defect=='range':bad['retired_ranges'].pop('EDIT-DATE-OF-BIRTH')
            elif defect=='class':bad['required_mutation_classes'].pop()
            elif defect=='whole-screen':bad['whole_screen_idiomatic']=True
            elif defect=='remaining':bad['remaining_statement_engine_programs'].remove('COACTUPC')
            else:bad['sources'].pop()
            with self.subTest(defect=defect),self.assertRaises(ValueError):check_scope(root,bad)


    def test_direct_and_exact_composed_service_routes_and_refusals(self):
        root=Path(__file__).resolve().parents[1]
        original=(root/JAVA/'AccountMapModel.java').read_bytes().replace(b'\r\n',b'\n')
        argument='bindings.root.path("account_update").path("validation")'
        direct='AccountPhoneDateModel.retire('+argument+')'
        composed='AccountMapModel.retire('+argument+')'
        with tempfile.TemporaryDirectory() as directory:
            sandbox=Path(directory);model=sandbox/JAVA/'AccountMapModel.java'
            model.parent.mkdir(parents=True)
            check_service_route(sandbox,direct)
            with self.assertRaisesRegex(ValueError,'phone-date-service-routing'):
                check_service_route(sandbox,composed)
            model.write_bytes(original)
            check_service_route(sandbox,composed)
            model.write_bytes(original.replace(b'\n',b'\r\n'))
            check_service_route(sandbox,composed)
            for service in ('',composed.replace('"validation"','"other"'),composed.replace('AccountMapModel','OtherModel')):
                with self.subTest(service=service),self.assertRaisesRegex(ValueError,'phone-date-service-routing'):
                    check_service_route(sandbox,service)
            for bad in (original.replace(b'AccountPhoneDateModel.retire(original)',b'original.deepCopy()'),
                        original.replace(b'retire(original)',b'retire(original.deepCopy())'),
                        original.replace(b'return model;',b'return original;'),
                        original+b'// AccountPhoneDateModel.retire(original)\n'):
                self.assertNotEqual(original,bad)
                model.write_bytes(bad)
                with self.subTest(model=bad),self.assertRaisesRegex(ValueError,'phone-date-composed-model-binding'):
                    check_service_route(sandbox,composed)


    def test_annotation_layout_preserves_values_and_refuses_changed_literals(self):
        import re
        from unittest.mock import patch
        root=Path(__file__).resolve().parents[1]
        expected=check_scope(root)
        read_text=Path.read_text
        pattern='@CobolSource\\s*\\(\\s*program\\s*=\\s*"([^"]+)"\\s*,\\s*paragraph\\s*=\\s*"([^"]+)"\\s*,\\s*lines\\s*=\\s*"([^"]+)"\\s*\\)'
        target='AccountPhoneRules.java'
        for layout in ('compact','multiline','crlf'):
            def rewritten(path,*args,**kwargs):
                text=read_text(path,*args,**kwargs)
                if path.name!=target:return text
                gap='' if layout=='compact' else ('\r\n  ' if layout=='crlf' else '\n  ')
                return re.sub(pattern,lambda match:'@CobolSource('+gap+'program = "'+match[1]+'",'+gap+'paragraph = "'+match[2]+'",'+gap+'lines = "'+match[3]+'"'+gap+')',text)
            with self.subTest(layout=layout),patch.object(Path,'read_text',rewritten):
                self.assertEqual(expected,check_scope(root))
        for defect in ('program','paragraph','range','missing'):
            def changed(path,*args,**kwargs):
                text=read_text(path,*args,**kwargs)
                if path.name!=target:return text
                def alter(match):
                    if defect=='missing':return ''
                    program,paragraph,span=match.groups()
                    if defect=='program':program='COACT UPC'
                    if defect=='paragraph':paragraph+=' '
                    if defect=='range':span='1-2'
                    return '@CobolSource(program="'+program+'", paragraph="'+paragraph+'", lines="'+span+'")'
                return re.sub(pattern,alter,text,count=1)
            with self.subTest(defect=defect),patch.object(Path,'read_text',changed),self.assertRaises(ValueError):
                check_scope(root)

if __name__=='__main__':unittest.main()
