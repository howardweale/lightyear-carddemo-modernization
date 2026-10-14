import io
import subprocess
import unittest
from unittest.mock import Mock,patch
from tools.ci_postgres_image import ensure_image, IMAGES, DIGEST
from tools.check_ms67_customer_startup import command

class CiPostgresImageTests(unittest.TestCase):
    def result(self,code,error=''):return subprocess.CompletedProcess(['docker','pull'],code,'',error)
    def test_mirror_success_returns_exact_selected_digest(self):
        run=Mock(return_value=self.result(0));sleep=Mock()
        self.assertEqual(IMAGES[0],ensure_image(run=run,sleep=sleep));sleep.assert_not_called()
        self.assertEqual(['docker','pull',IMAGES[0]],run.call_args.args[0])
    def test_missing_mirror_then_quota_falls_back_without_changing_digest(self):
        run=Mock(side_effect=[self.result(1,'manifest unknown'),self.result(1,'toomanyrequests: Data limit exceeded'),self.result(1,'429'),self.result(0)])
        sleep=Mock();self.assertEqual(IMAGES[2],ensure_image(run=run,sleep=sleep,stderr=io.StringIO()))
        refs=[c.args[0][-1] for c in run.call_args_list]
        self.assertEqual([IMAGES[0],IMAGES[1],IMAGES[1],IMAGES[2]],refs)
        self.assertTrue(all(x.endswith('@'+DIGEST) for x in refs));sleep.assert_called_once_with(2)
    def test_permanent_public_error_stops(self):
        run=Mock(side_effect=[self.result(1,'unauthorized'),self.result(1,'manifest unknown')])
        with self.assertRaises(subprocess.CalledProcessError):ensure_image(run=run,stderr=io.StringIO())
        self.assertEqual(2,run.call_count)
    def test_digest_integrity_error_never_falls_back(self):
        run=Mock(return_value=self.result(1,'digest mismatch'))
        with self.assertRaises(subprocess.CalledProcessError):ensure_image(run=run,stderr=io.StringIO())
        self.assertEqual(1,run.call_count)
    def test_all_transient_failures_are_bounded(self):
        run=Mock(return_value=self.result(1,'503 service unavailable'));sleep=Mock()
        with self.assertRaises(subprocess.CalledProcessError):ensure_image(run=run,sleep=sleep,stderr=io.StringIO())
        self.assertEqual(6,run.call_count);self.assertEqual(3,sleep.call_count)
    def test_timeouts_are_bounded(self):
        run=Mock(side_effect=subprocess.TimeoutExpired(['docker','pull'],180))
        with self.assertRaises(subprocess.TimeoutExpired):ensure_image(run=run,sleep=Mock(),stderr=io.StringIO())
        self.assertEqual(6,run.call_count)
    def test_workload_failure_is_never_retried(self):
        error=subprocess.CalledProcessError(125,['docker','run'],stderr='daemon refused startup')
        with patch('tools.check_ms67_customer_startup.subprocess.run',side_effect=error) as run,patch('sys.stderr',new_callable=io.StringIO) as log:
            with self.assertRaises(subprocess.CalledProcessError):command(['docker','run'])
            self.assertIn('daemon refused startup',log.getvalue());run.assert_called_once()
