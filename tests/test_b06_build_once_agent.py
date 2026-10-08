import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path

class BuildOnceAgentTests(unittest.TestCase):
 def test_actual_defined_bytes_and_duplicate_definition_error(self):
  # Host JVM only. A tiny public fixture, no Equinox, Docker or models.
  javac=shutil.which('javac') or 'C:/Program Files/Amazon Corretto/jdk21.0.10_7/bin/javac.exe'
  if not Path(javac).is_file():self.skipTest('Host JDK unavailable')
  bin=Path(javac).parent;suffix='.exe' if os.name=='nt' else ''
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);classes=r/'classes';classes.mkdir();probe=r/'probe';probe.mkdir()
   agent=Path('tools/b06_image_artifacts/B06PerRunClassAgent.java').resolve()
   (r/'B06RuntimeCatalogTest.java').write_text('package org.idempiere.test; public class B06RuntimeCatalogTest {}',encoding='utf-8')
   (r/'Main.java').write_text('import java.net.*; import java.nio.file.*; public class Main {public static void main(String[] a)throws Exception { for(int i=0;i<Integer.parseInt(a[1]);i++) {try(URLClassLoader l=new URLClassLoader(new URL[]{Path.of(a[0]).toUri().toURL()},null)){Class.forName("org.idempiere.test.B06RuntimeCatalogTest",true,l);}}}}',encoding='utf-8')
   def run(args):subprocess.run(list(map(str,args)),check=True,capture_output=True,timeout=45)
   run([javac,'-d',classes,agent,r/'Main.java']);run([javac,'-d',probe,r/'B06RuntimeCatalogTest.java'])
   (r/'MANIFEST.MF').write_text('Premain-Class: B06PerRunClassAgent\n',encoding='ascii')
   run([bin/('jar'+suffix),'cfm',r/'agent.jar',r/'MANIFEST.MF','-C',classes,'.'])
   for count in (1,2):
    out=r/str(count);out.mkdir();record=out/'per-run-class.json'
    run([bin/('java'+suffix),'-javaagent:'+str(r/'agent.jar')+'='+str(record),'-cp',classes,'Main',probe,count])
    value=json.loads(record.read_bytes());raw=(probe/'org/idempiere/test/B06RuntimeCatalogTest.class').read_bytes()
    self.assertEqual(value['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(value['bytes'],len(raw));self.assertNotEqual(value['loader'],'bootstrap')
    self.assertEqual((out/'per-run-class-error.json').exists(),count==2)
if __name__=='__main__':unittest.main()
