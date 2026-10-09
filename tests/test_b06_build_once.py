import copy,datetime as dt,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.b06_image_artifacts import build_once as b
from tools.b06_image_artifacts import build_once_practice as p

class BuildOnceTests(unittest.TestCase):
 def maps(self):
  entries={'META-INF/MANIFEST.MF':dict(kind='file',**b.descriptor(b'manifest')),b.TEST_ENTRY:dict(kind='file',**b.descriptor(b'class-1')),
    'target/test.jar':dict(kind='file',**b.descriptor(b'opaque jar')),'OSGI-INF/l10n/x.properties':dict(kind='file',**b.descriptor(b'#timestamp'))}
  return {'org.idempiere.test':dict(path=b.TEST_ROOT,version='1.0.0.qualifier',kind='folder-archive',jar_sha256=None,entries=entries)}
 def test_only_exact_probe_class_may_vary(self):
  base=self.maps();new=copy.deepcopy(base);new['org.idempiere.test']['entries'][b.TEST_ENTRY]=dict(kind='file',**b.descriptor(b'class-2'))
  self.assertTrue(b.compare_applications(base,new,b.descriptor(b'class-2')))
  with self.assertRaisesRegex(ValueError,'captured-class'):b.compare_applications(base,new,b.descriptor(b'class-1'))
 def test_all_other_entries_including_nested_jar_and_metadata_stay_exact(self):
  base=self.maps()
  for field in ('META-INF/MANIFEST.MF','target/test.jar','OSGI-INF/l10n/x.properties','other.class'):
   new=copy.deepcopy(base);new['org.idempiere.test']['entries'][field]=dict(kind='file',**b.descriptor(b'changed'))
   with self.subTest(field=field),self.assertRaisesRegex(ValueError,'non-candidate-layer'):b.compare_applications(base,new,b.descriptor(b'class-1'))
  new=copy.deepcopy(base);new['org.idempiere.test']['version']='1.0.0.other'
  with self.assertRaises(ValueError):b.compare_applications(base,new,b.descriptor(b'class-1'))
 def test_wrong_or_missing_test_origin_refused(self):
  for change in ('missing','jar','path'):
   base=self.maps();new=copy.deepcopy(base)
   if change=='missing':new['org.idempiere.test']['entries'].pop(b.TEST_ENTRY)
   elif change=='jar':new['org.idempiere.test']['kind']='jar'
   else:new['org.idempiere.test']['path']='/other'
   with self.subTest(change=change),self.assertRaises(ValueError):b.compare_applications(base,new,b.descriptor(b'class-1'))
 def fork(self):
  return ['/opt/java/openjdk/bin/java','-jar','/root/.m2/launcher.jar','-install',b.TEST_ROOT+'/target/work','-configuration',b.TEST_ROOT+'/target/work/configuration','-data',b.TEST_ROOT+'/target/work/data','-testproperties',b.TEST_ROOT+'/target/surefire.properties']
 def test_direct_launch_preserves_original_paths_and_has_no_build(self):
  old=self.fork();new=b.direct_command(old)
  self.assertEqual(new[:1]+new[3:],old);self.assertEqual(len(new),len(old)+2)
  for field,value in [(0,'mvn'),(old.index('-testproperties')+1,'/other')]:
   bad=old.copy();bad[field]=value
   with self.assertRaises(ValueError):b.direct_command(bad)
  with self.assertRaises(ValueError):b.direct_command(new)
 def test_live_checks_exact_dependency_source_and_config(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   files={'/root/.m2/a.jar':b'jar','/tmp/tycho_wrapped_source123.jar':b'source','/sealed/dev.properties':b'dev'}
   for n,raw in files.items():q=root/n.lstrip('/');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(raw)
   manifest=b.seal(dict(base_applications={},artifacts={'/root/.m2/a.jar':b.descriptor(b'jar')},source_files={'/tmp/tycho_wrapped_source123.jar':b.descriptor(b'source')},sealed_files={'/sealed/dev.properties':b.descriptor(b'dev')}))
   resolve=lambda n:root/n.lstrip('/')
   self.assertTrue(b.verify_live(manifest,{},resolve=resolve))
   for n,raw in files.items():
    resolve(n).write_bytes(b'different')
    with self.subTest(n=n),self.assertRaises(ValueError):b.verify_live(manifest,{},resolve=resolve)
    resolve(n).write_bytes(raw)
 def test_windows_and_ownership_fail_closed(self):
  now=dt.datetime(2026,10,9,17,tzinfo=dt.timezone.utc)
  self.assertEqual(p.window('2026-10-09T17:00:00Z','2026-10-09T18:00:00Z',now),3600)
  for n in (now-dt.timedelta(seconds=1),now+dt.timedelta(minutes=6)):
   with self.assertRaises(ValueError):p.window('2026-10-09T17:00:00Z','2026-10-09T18:00:00Z',n)
  item=dict(Name='/ours',Image='sha256:ours',Config=dict(Labels={'lightyear.b06.build-once':'owner'}))
  p.inspect_owned(item,'ours','sha256:ours','owner')
  for field in ('Name','Image'):
   bad=copy.deepcopy(item);bad[field]='someone-else'
   with self.assertRaises(ValueError):p.inspect_owned(bad,'ours','sha256:ours','owner')
 def test_prepare_reads_only_committed_bytes_and_run_is_not_authorized(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);sources={}
   for n in p.WORKER|p.EXTRA:sources['tools/'+n if n in p.EXTRA else 'tools/b06_image_artifacts/'+n]=b'fixture'
   sources[p.BASELINE]=b'baseline';sources['tools/b06_image_artifacts/build_once_practice.py']=b'code'
   def git(argv,**kwargs):
    args=argv[3:]
    if args[0]=='rev-parse':return b'a'*40+b'\n'
    if args[0]=='ls-tree':return '\n'.join(sources).encode()
    if args[0]=='cat-file':return sources[args[2].split(':',1)[1]]
    raise AssertionError(args)
   with patch.object(p.subprocess,'check_output',side_effect=git),patch.object(p.subprocess,'run',side_effect=AssertionError('No process in preparation')):
    value=p.prepare(root,'a'*40,root/'snapshot',root/'public/plan.json')
    self.assertFalse(value['run_authorized']);self.assertFalse(value['native_admission']);self.assertIsNone(value['window']);p.validate(root/'snapshot',value)
    self.assertEqual((root/'public/plan.json').read_bytes(),b.canonical(value))
    (root/'snapshot/runtime_worker.py').write_bytes(b'changed')
    with self.assertRaisesRegex(ValueError,'frozen-bytes'):p.validate(root/'snapshot',value)

if __name__=='__main__':unittest.main()
