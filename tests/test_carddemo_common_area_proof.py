"""Synthetic CI fixtures; no private inputs."""
from pathlib import Path
import tempfile
import unittest
from tools.carddemo_common_area_proof import evaluate,restore_service
ROOT=Path(__file__).resolve().parents[1]
class CommonAreaProofTests(unittest.TestCase):
    def test_string_keys_and_changed_typed_routes_refuse(self):
        path=ROOT/'factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/AccountViewService.java'
        source=path.read_text(encoding='utf-8');restored=restore_service(ROOT,source)
        self.assertIn('area.get("CDEMO-FROM-PROGRAM")',restored)
        with self.assertRaisesRegex(ValueError,'string-key'):restore_service(ROOT,source+'// "CDEMO-UNKNOWN"')
        with self.assertRaisesRegex(ValueError,'service-route'):restore_service(ROOT,source.replace('constants.menuProgram()','constants.map()'))
    def test_each_new_class_requires_nonempty_ninety_percent_killed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'mutations.xml';self.assertFalse(evaluate(path)['passed'])
            good=''.join('<mutation status="KILLED"><mutatedClass>ai.lightyear.carddemo.'+name+'</mutatedClass></mutation>' for name in ('CommonArea','AccountViewConstants'))
            path.write_text('<mutations>'+good+'</mutations>',encoding='utf-8');self.assertTrue(evaluate(path)['passed'])
            for bad in (good.replace('KILLED','TIMED_OUT',1),good.replace('AccountViewConstants','Other')):
                path.write_text('<mutations>'+bad+'</mutations>',encoding='utf-8');self.assertFalse(evaluate(path)['passed'])
