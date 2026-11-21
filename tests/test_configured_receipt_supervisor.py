"""CI-only original OS process observations, never configured admission proof."""
import io,os,sys,tempfile,unittest
from pathlib import Path
from tools.ci.p5_configured_receipt_supervisor import _launch_and_wait,main

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true', 'CI-only native child observations')
class OriginalChildObservations(unittest.TestCase):
    def observe(self,code):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'observation.txt'
            with path.open('x',encoding='ascii') as stream:
                result=_launch_and_wait([sys.executable,'-B','-c',code],directory,stream)
            return result,path.read_text(encoding='ascii')
    def test_original_success_is_reaped(self):
        result,text=self.observe('raise SystemExit(0)')
        self.assertEqual(result,0)
        self.assertEqual(text.count('event=original-child-reaped '),1)
        self.assertIn('returncode=0',text)
        created=text.split('event=child-created ',1)[1].splitlines()[0]
        reaped=text.split('event=original-child-reaped ',1)[1].splitlines()[0]
        self.assertEqual(created.split('pid=')[1].split()[0],reaped.split('pid=')[1].split()[0])
    def test_original_failure_is_not_success(self):
        result,text=self.observe('raise SystemExit(19)')
        self.assertEqual(result,19);self.assertIn('returncode=19',text)
        self.assertEqual(text.count('event=launch-intent '),1)
    def test_abrupt_os_exit_is_observed_without_fabricated_terminal(self):
        result,text=self.observe('import os; os._exit(23)')
        self.assertEqual(result,23);self.assertIn('returncode=23',text)
        self.assertNotIn('admitted',text);self.assertNotIn('qualified',text)
    def test_failed_spawn_has_no_reaped_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'observation.txt'
            with path.open('x',encoding='ascii') as stream:
                with self.assertRaises(OSError):
                    _launch_and_wait([str(Path(directory)/'absent-program')],directory,stream)
            text=path.read_text(encoding='ascii')
            self.assertIn('event=launch-refused ',text)
            self.assertNotIn('event=child-created ',text)
            self.assertNotIn('event=original-child-reaped ',text)
    def test_failed_intent_persistence_prevents_child_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'unexpected-child'
            # StringIO cannot fsync. Failure must precede Popen; marker proves
            # no child launch, without replacing Popen with a fake object.
            with self.assertRaises(io.UnsupportedOperation):
                _launch_and_wait([sys.executable,'-B','-c',
                    'from pathlib import Path; Path('+repr(str(marker))+').touch()'],directory,io.StringIO())
            self.assertFalse(marker.exists())
