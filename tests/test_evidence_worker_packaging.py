"""Standalone source directory can import the shared content module without src/."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path
from tools.b06_image_artifacts.runtime_practice import prepare, WORKER, EXTRA

class WorkerPackagingTests(unittest.TestCase):
 def test_preparation_binds_and_packages_importable_shared_module(self):
  repo=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for name in WORKER|EXTRA:
    rel=Path('tools')/(name if name in EXTRA else 'b06_image_artifacts/'+name)
    p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((repo/rel).read_bytes())
   for original in (repo/'src/lightyear_evidence').rglob('*.py'):
    p=root/original.relative_to(repo);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(original.read_bytes())
   out=root/'work/practice';plan=prepare(root,out)
   self.assertIn('lightyear_evidence/content.py',plan['source_sha256'])
   env=dict(os.environ,PYTHONPATH=str(out/'source'),PYTHONDONTWRITEBYTECODE='1')
   subprocess.run([sys.executable,'-B','-S','-c','import bundle_content; assert callable(bundle_content.bundle_content_view)'],cwd=out,env=env,check=True,capture_output=True)

 def test_single_file_native_mount_contains_shared_reader_and_same_policy(self):
  import io, zipfile, json
  from tools.b06_image_artifacts.standalone_content import reader_bytes
  from tools.b06_image_artifacts.bundle_content import bundle_content_view
  raw=io.BytesIO()
  with zipfile.ZipFile(raw,'w') as z:
   z.writestr('META-INF/MANIFEST.MF',b'public');z.writestr('a.class',b'class bytes');z.writestr('target/work/x',b'omitted')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'bundle_content.py').write_bytes(reader_bytes());(root/'fixture.zip').write_bytes(raw.getvalue())
   env=dict(os.environ,PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1')
   result=subprocess.run([sys.executable,'-B','-S','-c',"import bundle_content,json; print(json.dumps(bundle_content.bundle_content_view('fixture.zip',kind='folder-archive')))"] ,cwd=root,env=env,check=True,capture_output=True)
   self.assertEqual(json.loads(result.stdout),bundle_content_view(raw.getvalue(),kind='folder-archive'))
