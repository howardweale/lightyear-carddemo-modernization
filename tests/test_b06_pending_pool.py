import os,subprocess,tempfile,unittest
from pathlib import Path
@unittest.skipUnless(os.environ.get("B06_HOST_JDK"),"host JDK explicitly enabled")
class PendingPoolTests(unittest.TestCase):
    def test_fixed_retained_storage_preserves_activation_identity(self):
        root=Path(__file__).resolve().parents[1];jdk=Path(os.environ["B06_HOST_JDK"])/"bin"
        suffix=".exe" if os.name=="nt" else ""
        with tempfile.TemporaryDirectory() as tmp:
            built=subprocess.run([str(jdk/("javac"+suffix)),"--add-modules","jdk.jdi","-d",tmp,
                str(root/"factory/idempiere/b06-observer/PostingObserver.java"),str(root/"tests/fixtures/B06PendingPoolProbe.java")],capture_output=True,text=True,timeout=60)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(jdk/("java"+suffix)),"--add-modules","jdk.jdi","-cp",tmp,"B06PendingPoolProbe"],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn("fixed_slots=256",result.stdout)
