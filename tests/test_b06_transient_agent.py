"""Real Equinox / host JVM rehearsal, no Docker, database, network or authority."""
import hashlib,json,os,shutil,subprocess,tempfile,unittest,zipfile
from pathlib import Path

class EquinoxAgentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.repo=Path(__file__).resolve().parents[1]
  java_bin=Path('C:/Program Files/Amazon Corretto/jdk21.0.10_7/bin') if os.name=='nt' else Path(shutil.which('javac') or '/missing').parent
  cls.java=java_bin/('java.exe' if os.name=='nt' else 'java');cls.javac=java_bin/('javac.exe' if os.name=='nt' else 'javac')
  configured=os.environ.get('B06_REHEARSAL_EQUINOX')
  cls.equinox=Path(configured) if configured else Path('C:/Users/howar/OneDrive/Documents/ChatGPT/lightyear-carddemo-modernization/work/idempiere-runtime-evidence/work/idempiere-upstream/org.idempiere.p2.targetplatform/target/target-platform-repository/plugins/org.eclipse.osgi_3.18.500.v20230801-1826.jar')
  if not cls.java.exists() or not cls.equinox.exists():raise unittest.SkipTest('Host JDK and local Equinox jar required; no automatic download')
  cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);src=cls.root/'src';classes=cls.root/'classes';src.mkdir();classes.mkdir()
  sources={
   'Main.java': '''import org.osgi.framework.*;import org.osgi.framework.launch.*;import java.nio.file.*;import java.util.*;
public class Main {public static void main(String[] args)throws Exception {
 Framework f=ServiceLoader.load(FrameworkFactory.class).iterator().next().newFramework(Map.of(Constants.FRAMEWORK_STORAGE,args[0]+"/cache","osgi.install.area",Path.of(args[0]).toUri().toString()));
 f.start();BundleContext ctx=f.getBundleContext();Class.forName("org.osgi.framework.FrameworkUtil");
 System.setProperty("osgi.install.area",Path.of(args[0]).toUri().toString());System.setProperty("osgi.configuration.area",Path.of(args[0]).toUri().toString());
 for(Path p:Files.list(Path.of(args[0],"transient")).sorted().toList()){ctx.installBundle(p.toUri().toString());p.toFile().deleteOnExit();}
 if(args[1].equals("exit")){System.exit(0);}
 try {String bundle=args[1].equals("folder")?"reference:"+Path.of(args[0],"folder-bundle").toUri():Path.of(args[0],"bundle.jar").toUri().toString();ctx.installBundle(bundle).start();} finally {f.stop();f.waitForStop(10000);}
}}''',
   'rehearsal/Activator.java': '''package rehearsal;import org.osgi.framework.*;
public class Activator implements BundleActivator {
 public void start(BundleContext c)throws Exception {
  Class.forName("org.junit.platform.engine.support.hierarchical.NodeTestTask");Class.forName("org.junit.platform.launcher.core.ExecutionListenerAdapter");
  new org.idempiere.test.B06RuntimeCatalogTest().resolveWithoutDatabase();
 }
 public void stop(BundleContext c){}
}''',
   'org/junit/jupiter/api/Test.java':'package org.junit.jupiter.api;public @interface Test {}',
   'org/junit/platform/engine/support/hierarchical/NodeTestTask.java':'package org.junit.platform.engine.support.hierarchical;public class NodeTestTask {}',
   'org/junit/platform/launcher/core/ExecutionListenerAdapter.java':'package org.junit.platform.launcher.core;public class ExecutionListenerAdapter {}',
  }
  for c in ('org.compiere.acct.Doc','org.compiere.acct.DocManager','org.compiere.model.PO','org.compiere.util.DB'):
   package,name=c.rsplit('.',1);sources[c.replace('.','/')+'.java']='package '+package+';public class '+name+' {}'
  for name,body in sources.items():p=src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body,encoding='utf-8')
  args=[str(cls.javac),'-cp',str(cls.equinox),'-d',str(classes),str(cls.repo/'tools/b06_image_artifacts/RuntimeClosureAgent.java'),str(cls.repo/'tools/B06RuntimeCatalogTest.java'),*map(str,src.rglob('*.java'))]
  result=subprocess.run(args,capture_output=True,timeout=60)
  if result.returncode:raise AssertionError(result.stderr.decode(errors='replace'))
  cls.classes=classes
  cls.agent=cls.root/'agent.jar';cls.bundle=cls.root/'bundle.jar'
  with zipfile.ZipFile(cls.agent,'w') as z:
   z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\r\nPremain-Class: RuntimeClosureAgent\r\n\r\n')
   for p in classes.glob('RuntimeClosureAgent*.class'):z.write(p,p.name)
  with zipfile.ZipFile(cls.bundle,'w') as z:
   z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\r\nBundle-ManifestVersion: 2\r\nBundle-SymbolicName: rehearsal.test\r\nBundle-Version: 1.0.0\r\nBundle-Activator: rehearsal.Activator\r\nImport-Package: org.osgi.framework\r\n\r\n')
   for p in classes.rglob('*.class'):
    if not p.name.startswith(('RuntimeClosureAgent','Main')):z.write(p,p.relative_to(classes).as_posix())
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def run_case(self,name,count=1,abrupt=False,folder=False):
  root=self.root/name;root.mkdir();tmp=root/'transient';tmp.mkdir();shutil.copyfile(self.bundle,root/'bundle.jar')
  for n in range(count):
   with zipfile.ZipFile(tmp/f'tycho_wrapped_source{n}.jar','w') as z:
    z.writestr('META-INF/MANIFEST.MF',f'Manifest-Version: 1.0\r\nBundle-ManifestVersion: 2\r\nBundle-SymbolicName: rehearsal{n}.source\r\nBundle-Version: 1.0.0\r\nEclipse-SourceBundle: rehearsal{n}\r\n\r\n');z.writestr('source.txt',b'x'*262144)
  if folder:
   with zipfile.ZipFile(self.bundle) as z:z.extractall(root/'folder-bundle')
  out=root/'closure-observation.json'
  cmd=[str(self.java),'-Djava.io.tmpdir='+str(tmp),'-javaagent:'+str(self.agent)+'='+str(out),'-cp',str(self.equinox)+os.pathsep+str(self.classes),'Main',str(root),'exit' if abrupt else 'folder' if folder else 'wait']
  try:result=subprocess.run(cmd,capture_output=True,timeout=40)
  except subprocess.TimeoutExpired as e:raise AssertionError('Rehearsal timed out: '+(e.stderr or b'').decode(errors='replace'))
  error=root/'closure-error.json';marker=root/'closure-complete.json'
  self.assertTrue(marker.exists(),result.stderr.decode(errors='replace'))
  m=json.loads(marker.read_bytes())
  if error.exists():
   e=json.loads(error.read_bytes());self.assertTrue(e['exception_class']);self.assertTrue(e['stage']);self.assertTrue(e['stack_trace']);self.assertIn(m['status'],('failed','complete'))
   if abrupt:self.assertEqual(e['message'],'interrupted by JVM exit')
   else:
    # ProcessHandle.Info.arguments is unavailable on this host Windows JVM.
    self.assertEqual(e['stage'],'process-metadata');self.assertEqual(e['exception_class'],'java.util.NoSuchElementException')
    stages=list(root.glob('.runtime-transient-*'));self.assertEqual(len(stages),1);self.assertEqual(len(list(stages[0].glob('*.jar'))),count)
  else:
   self.assertEqual(m,{'status':'complete','observation_sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
   o=json.loads(out.read_bytes());self.assertEqual(o['schema'],'b06-runtime-launch-observation/5');self.assertEqual(len(o['bundles']),count+2)
   self.assertEqual(len(list((root/'runtime-transient').glob('*.jar'))),count)
  self.assertFalse((root/'runtime-application').exists())
  return root
 def test_immediate_test_body_waits_for_complete_or_specific_error(self):self.run_case('immediate')
 def test_large_transient_set(self):self.run_case('large',128)
 def test_jvm_exit_writes_specific_error(self):self.run_case('exit',abrupt=True)

 def test_real_folder_bundle_then_mutation_during_worker_capture(self):
  from tools.b06_image_artifacts import runtime_capture as cap
  from unittest.mock import patch
  root=self.run_case('folder',folder=True);folder=root/'folder-bundle';resource=folder/'resource.txt';resource.write_bytes(b'before')
  real=cap.stream_file
  def mutate(p,out):
   row=real(p,out)
   if p==resource:p.write_bytes(b'after')
   return row
  try:
   with patch.object(cap,'stream_file',mutate):cap.capture_folder(folder,root/'folder-copy.jar',[])
  except ValueError as error:cap.failure(root,'application-capture',error)
  else:self.fail('Changing folder accepted')
  value=json.loads((root/'worker-error.json').read_bytes());self.assertIn('changed-during-capture',value['message']);self.assertTrue(value['stack_trace'])
