"""Real host JVM capture lifecycle, with synthetic OSGi interfaces; no Docker."""
import hashlib,json,os,shutil,subprocess,tempfile,unittest,zipfile
from pathlib import Path

class TransientAgentTests(unittest.TestCase):
 def test_agent_copies_before_delete_on_exit(self):
  java_bin=Path('C:/Program Files/Amazon Corretto/jdk21.0.10_7/bin') if os.name=='nt' else Path(shutil.which('javac') or '/missing').parent
  suffix='.exe' if os.name=='nt' else ''
  javac=java_bin/('javac'+suffix);java=java_bin/('java'+suffix);jar=java_bin/('jar'+suffix)
  if not javac.is_file():self.skipTest('host JDK required for synthetic agent lifecycle')
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);src=root/'src';classes=root/'classes';src.mkdir();classes.mkdir()
   sources={
    'org/osgi/framework/Bundle.java': 'package org.osgi.framework; public interface Bundle {long getBundleId(); int getState(); String getLocation(); String getSymbolicName(); String getVersion(); java.util.Dictionary<String,String> getHeaders(String locale); BundleContext getBundleContext();}',
    'org/osgi/framework/BundleContext.java':'package org.osgi.framework; public interface BundleContext {Bundle[] getBundles();}',
    'org/osgi/framework/FrameworkUtil.java': 'package org.osgi.framework; public class FrameworkUtil { public static Bundle owner; public static Bundle getBundle(Class<?> c) {return owner;} }',
    'org/junit/platform/engine/support/hierarchical/NodeTestTask.java':'package org.junit.platform.engine.support.hierarchical; public class NodeTestTask {}',
    'org/junit/platform/launcher/core/ExecutionListenerAdapter.java':'package org.junit.platform.launcher.core; public class ExecutionListenerAdapter {}',
    'Main.java': r"""import org.osgi.framework.*; import java.nio.file.*; import java.util.*;
public class Main implements BundleContext {
 static String location; static Main ctx=new Main();
 public static class B implements Bundle {
  long id; B(long i){id=i;} public long getBundleId(){return id;} public int getState(){return id==0?32:2;}
  public String getLocation(){return id==0?"system":location;} public String getSymbolicName(){return id==0?"system":"example.source";}
  public String getVersion(){return "1.2.3";} public Dictionary<String,String> getHeaders(String locale){ Hashtable<String,String> h=new Hashtable<>(); if(id!=0)h.put("Eclipse-SourceBundle","example");return h;}
  public BundleContext getBundleContext(){return ctx;}
 }
 public Bundle[] getBundles(){return new Bundle[]{new B(0),new B(1)};}
 public static void main(String[] args)throws Exception {
  Path tmp=Path.of(args[0]);Path original=tmp.resolve("tycho_wrapped_source123.jar");
  Files.write(original,new byte[]{1,2,3});original.toFile().deleteOnExit();location=original.toUri().toString();
  Files.write(tmp.resolve("application-jar-copy"),RuntimeClosureAgent.applicationBytes(original));
  Path app=tmp.resolve("synthetic-application");Files.createDirectories(app.resolve("META-INF"));
  Files.writeString(app.resolve("META-INF/MANIFEST.MF"),"Manifest-Version: 1.0\r\n");
  Files.write(app.resolve("resource"),new byte[]{4,5});
  Files.write(tmp.resolve("application-folder-copy.jar"),RuntimeClosureAgent.applicationBytes(app));
  System.setProperty("java.io.tmpdir",tmp.toString());System.setProperty("osgi.install.area",tmp.toUri().toString());
  System.setProperty("osgi.configuration.area",tmp.toUri().toString());FrameworkUtil.owner=new B(0);
  Class.forName("org.junit.platform.engine.support.hierarchical.NodeTestTask");Class.forName("org.junit.platform.launcher.core.ExecutionListenerAdapter");
 }
}"""}
   for name,body in sources.items():p=src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body,encoding='utf-8')
   agent=Path(__file__).resolve().parents[1]/'tools/b06_image_artifacts/RuntimeClosureAgent.java'
   def run(args):
    r=subprocess.run(list(map(str,args)),capture_output=True,timeout=35);self.assertEqual(r.returncode,0,r.stderr.decode(errors='replace'));return r
   run([javac,'-d',classes,agent,*src.rglob('*.java')])
   manifest=root/'MANIFEST.MF';manifest.write_text('Premain-Class: RuntimeClosureAgent\n',encoding='ascii')
   agentjar=root/'agent.jar';run([jar,'cfm',agentjar,manifest,'-C',classes,'.'])
   out=root/'closure-observation.json';result=run([java,'-javaagent:'+str(agentjar)+'='+str(out),'-cp',classes,'Main',root])
   self.assertFalse((root/'tycho_wrapped_source123.jar').exists())
   raw=(root/'runtime-transient/1.jar').read_bytes()
   self.assertEqual(raw,bytes([1,2,3]))
   self.assertEqual((root/'application-jar-copy').read_bytes(),raw)
   with zipfile.ZipFile(root/'application-folder-copy.jar') as z:
    self.assertEqual(set(z.namelist()),{'META-INF/','META-INF/MANIFEST.MF','resource'});self.assertEqual(z.read('resource'),bytes([4,5]))
   self.assertTrue((root/'runtime-catalogue.tsv').stat().st_size)
   if os.name=='nt' and not out.exists():
    # Windows ProcessHandle.Info lacks argv on this host. Capture completed,
    # then the production observer correctly refused to fabricate its fork.
    self.assertIn('java.util.NoSuchElementException',result.stderr.decode(errors='replace'))
    return
   self.assertTrue(out.exists(),result.stderr.decode(errors='replace'))
   o=json.loads(out.read_bytes());self.assertEqual(o['schema'],'b06-runtime-launch-observation/4')
   b=o['bundles'][1]
   self.assertEqual(raw,bytes([1,2,3]));self.assertEqual(b['preserved_copy']['sha256'],hashlib.sha256(raw).hexdigest())
   self.assertEqual(b['preserved_copy']['bytes'],3);self.assertTrue(b['eclipse_source_bundle']);self.assertEqual(b['version'],'1.2.3')
   self.assertTrue((root/'runtime-catalogue.tsv').stat().st_size);self.assertTrue(o['loaded_bundle_classes'])
