import unittest
from tools.b06_image_artifacts.resolved_runtime import file_path
from tools.b06_image_artifacts.runtime_worker import launch_arguments
from tools.ms94_b06_observed_worker import maven_arguments

class RuntimeShapeTests(unittest.TestCase):
 def test_equinox_location_normalization(self):
  self.assertEqual(file_path('initial@reference:file:/app/plugins/bundle/'),'/app/plugins/bundle')
  for value in ('initial@reference:http:/bad','initial@reference:file:/app/../secret/','file://host/app','file:/app/%2e%2e/private'):
   with self.assertRaises(ValueError):file_path(value)
 def test_closure_keeps_instrumentation_disabled_and_binds_measured_arguments(self):
  measured,closure=launch_arguments();self.assertEqual(measured,maven_arguments())
  for value in ('-Djacoco.skip=true','-Dtycho.testArgLine='):self.assertIn(value,closure)
  self.assertNotIn('-verbose:class',' '.join(closure));self.assertEqual(sum('-javaagent:' in arg for arg in closure),1)
 def test_worker_requires_native_test_case_and_class_capture(self):
  import tempfile,json
  from pathlib import Path
  from tools.b06_image_artifacts.runtime_worker import accept
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'loaded').mkdir();(p/'loaded/loaded.tsv').write_text('')
   with self.assertRaisesRegex(ValueError,'Incomplete'):accept(p,0)
   with self.assertRaisesRegex(ValueError,'failed'):accept(p,1)

 def test_worker_accepts_one_complete_bound_output_and_rejects_changed_bytes(self):
  import tempfile,hashlib
  from pathlib import Path
  from tools.b06_image_artifacts.runtime_worker import accept,TARGETS
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'loaded').mkdir();(p/'runtime').mkdir();rows=[]
   for name in sorted(TARGETS):
    raw=('synthetic-unit-class:'+name).encode();h=hashlib.sha256(raw).hexdigest();(p/'loaded'/(h+'.class')).write_bytes(raw)
    rows.append('\t'.join((name,h,'/application/pinned.jar','fixture-loader')))
   (p/'loaded/loaded.tsv').write_text('\n'.join(rows));(p/'runtime/config.ini').write_text('fixture')
   (p/'runtime/TEST-fixture.xml').write_text('<testsuite><testcase classname="org.idempiere.test.B06RuntimeCatalogTest" name="catalog"/></testsuite>')
   self.assertEqual(len(accept(p,0)),6)
   (p/'loaded'/(h+'.class')).write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'byte binding'):accept(p,0)
 def test_runtime_inventory_rejects_non_file_location_before_starting_tool(self):
  from unittest.mock import patch
  import tempfile
  from pathlib import Path
  from tools.b06_image_artifacts.runtime_inventory import measure
  with tempfile.TemporaryDirectory() as tmp,patch('tools.b06_image_artifacts.runtime_inventory.subprocess.run') as run:
   with self.assertRaisesRegex(ValueError,'file-url'):
    measure(dict(java_home='/pinned/jdk',bundles=[dict(id=1,location='https://unbound/example.jar')]),Path(tmp)/'out')
   run.assert_not_called()
