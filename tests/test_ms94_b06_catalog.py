import hashlib
from pathlib import Path
import tempfile
import unittest
from tests.test_ms94_b06_classfile import u2,u4,utf8
from tools.ms94_b06_catalog import select_runtime, source_classes, FRAMEWORK, TERMINAL


def empty_class(name, minor=0):
    pool=utf8(name.replace('.','/'))+b'\x07'+u2(1)
    return u4(0xCAFEBABE)+u2(minor)+u2(65)+u2(3)+pool+u2(0x21)+u2(2)+u2(0)*5


class CatalogTests(unittest.TestCase):
    def test_application_identity_not_arbitrary_maven_cache_version(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'class-bytes').mkdir()
            def item(name,origin,minor=0):
                raw=empty_class(name,minor); sha=hashlib.sha256(raw).hexdigest()
                (root/'class-bytes'/(sha+'.class')).write_bytes(raw)
                return {'origin':origin,'sha256':sha,'member':name.replace('.','/')+'.class'}
            rows=[item(n,'/application/pinned.jar') for n in FRAMEWORK|TERMINAL]
            other=item('org.compiere.acct.Doc','/root/.m2/unrelated.jar',1)
            extraction={'classes':rows+[other],'java_sha256':'j'}
            catalog=select_runtime(root,extraction)
            self.assertEqual(len(catalog['classes_sha256']),len(FRAMEWORK|TERMINAL))
            with self.assertRaisesRegex(ValueError,'conflicting-application-class-versions'):
                select_runtime(root,{**extraction,'classes':rows+[{**other,'origin':'/application/other.jar'}]})
            with self.assertRaisesRegex(ValueError,'incomplete-application-framework-catalog'):
                select_runtime(root,{**extraction,'classes':rows[:-1]})
            (root/'class-bytes'/(rows[0]['sha256']+'.class')).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'bound-file-changed'):select_runtime(root,extraction)

    def test_successful_compile_without_both_candidate_and_support_is_not_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); items=[]
            for name in ('org.idempiere.test.LightyearOperationsTest','org.idempiere.test.JourneySupport'):
                raw=empty_class(name); sha=hashlib.sha256(raw).hexdigest();(root/(sha+'.class')).write_bytes(raw)
                items.append({'sha256':sha})
            record={'exit_code':0,'tests_run':0,'model_calls':0,'native_pairs':0,'classes':items}
            self.assertEqual(len(source_classes(root,record)),2)
            for changed in ({**record,'exit_code':1},{**record,'tests_run':1},{**record,'classes':items[:1]}):
                with self.assertRaises(ValueError):source_classes(root,changed)


if __name__=='__main__':unittest.main()
