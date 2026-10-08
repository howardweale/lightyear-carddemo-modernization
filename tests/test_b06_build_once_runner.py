import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.b06_image_artifacts import build_once_practice as p

class BuildOnceRunnerTests(unittest.TestCase):
 def exercise(self,fail=False):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan=root/'plan.json';plan.write_text(json.dumps(dict(source_commit='a'*40,snapshot_sha256='b'*64,content_sha256='c'*64)))
   states={};calls=[];active=None;derived='sha256:built';owner=None
   manifest=p.seal(dict(config_path=p.TEST_ROOT+'/target/work/configuration',data_path=p.TEST_ROOT+'/target/work/data'))
   def command(argv,**kw):
    nonlocal active,owner
    self.assertEqual(argv[0],'docker');a=argv[1:];calls.append(a);out=b'';code=0;error=b''
    if a[0]=='create':
     name=a[a.index('--name')+1];owner=a[a.index('--label')+1].split('=',1)[1]
     image=a[a.index('--entrypoint')+2];states[name]=dict(Name='/'+name,Image=image,Config=dict(Labels={'lightyear.b06.build-once':owner}),State=dict(Running=False,ExitCode=0))
     mounts=[a[i+1] for i,x in enumerate(a) if x=='--mount'];output=Path(next(x.split(',src=')[1].split(',dst=')[0] for x in mounts if ',dst=/results' in x))
     if name.endswith('-builder'):
      (output/'configuration-seed').mkdir();(output/'configuration-seed/config.ini').write_bytes(b'config')
      for v in ('1','2'):(output/('variant-'+v+'.class')).write_bytes(v.encode())
      (output/'layer-manifest.json').write_text(json.dumps(manifest))
     else:
      self.assertIn('--read-only',a);self.assertIn('type=bind,src='+str(root/'out/builder'/('variant-'+('1' if name.endswith('-1') else '2')+'.class'))+',dst='+p.CLASS_PATH+',readonly',mounts)
     self.assertIn('--network',a);self.assertEqual(a[a.index('--network')+1],'none')
    elif a[0]=='start':
     active=a[-1]
     if fail:code=1;error=b'specific worker failure'
    elif a[0]=='logs':out=b'specific worker failure' if fail else b'finished'
    elif a[:2]==['container','inspect']:out=json.dumps([states[a[2]]]).encode()
    elif a[:2]==['image','inspect']:out=json.dumps([dict(Id=a[2],Config=dict(Labels={'lightyear.b06.build-once':owner}) if a[2]==derived else {})]).encode()
    elif a[0]=='commit':out=derived.encode();self.assertTrue(a[-2].endswith('-builder'))
    elif a[0]=='ps' and '--filter' in a:
     filt=a[a.index('--filter')+1]
     if filt.startswith('name=^/'):
      name=filt.removeprefix('name=^/').removesuffix('$');out=name.encode() if name in states else b''
    elif a[0]=='rm':self.assertIn(a[-1],states);del states[a[-1]]
    return type('Result',(),dict(stdout=out,stderr=error,returncode=code))()
   with patch.object(p,'validate',return_value=Path.cwd()),patch.object(p,'window',return_value=3600),patch('tools.b06_image_artifacts.runtime_launch.publication'),patch.object(p,'checks',return_value={}),patch.object(p,'audit',return_value={'synthetic':True}),patch.object(p.subprocess,'run',side_effect=command):
    result=p.run(plan,Path.cwd(),root/'out','unused','unused','d'*40)
   self.assertFalse(states);self.assertTrue(result['cleanup_passed']);self.assertEqual(result['passed'],not fail,result['failure'])
   self.assertEqual(sum(a[0]=='create' for a in calls),1 if fail else 3)
   if fail:
    self.assertIn('specific worker failure',result['failure']);self.assertEqual((root/'out/builder.container.log').read_bytes(),b'specific worker failure');self.assertFalse(any(a[0]=='commit' for a in calls))
   else:self.assertEqual(sum(a[0]=='commit' for a in calls),1)
 def test_one_build_two_readonly_consumers_owned_cleanup(self):self.exercise()
 def test_builder_failure_preserved_without_retry_or_consumer(self):self.exercise(True)
if __name__=='__main__':unittest.main()
