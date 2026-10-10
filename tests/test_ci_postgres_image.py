import io
import subprocess
import unittest
from unittest.mock import Mock, patch
from tools.ci_postgres_image import ensure_image, POSTGRES_IMAGE
from tools.check_ms67_customer_startup import command

class CiPostgresImageTests(unittest.TestCase):
    def result(self, code, error=''):
        return subprocess.CompletedProcess(['docker','pull',POSTGRES_IMAGE],code,'',error)

    def test_exact_pinned_image_and_success_without_retry(self):
        run=Mock(return_value=self.result(0)); sleep=Mock()
        self.assertEqual(ensure_image(run=run,sleep=sleep),POSTGRES_IMAGE)
        self.assertEqual(run.call_args.args[0],['docker','pull',POSTGRES_IMAGE])
        sleep.assert_not_called()

    def test_transient_download_retries_preserve_digest(self):
        run=Mock(side_effect=[self.result(1,'429 Too Many Requests'), self.result(0)])
        sleep=Mock(); log=io.StringIO()
        self.assertEqual(ensure_image(run=run,sleep=sleep,stderr=log),POSTGRES_IMAGE)
        sleep.assert_called_once_with(2)
        self.assertIn('429',log.getvalue())
        self.assertEqual(run.call_args_list[0].args,run.call_args_list[1].args)

    def test_permanent_error_refused_once_and_reported(self):
        run=Mock(return_value=self.result(1,'manifest unknown')); log=io.StringIO()
        with self.assertRaises(subprocess.CalledProcessError): ensure_image(run=run,stderr=log)
        self.assertEqual(run.call_count,1)
        self.assertIn('manifest unknown',log.getvalue())

    def test_download_retry_cap(self):
        run=Mock(return_value=self.result(1,'503 Service Unavailable')); sleep=Mock()
        with self.assertRaises(subprocess.CalledProcessError):
            ensure_image(run=run,sleep=sleep,stderr=io.StringIO())
        self.assertEqual(run.call_count,3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[2,5])

    def test_container_failure_stderr_is_retained_without_retry(self):
        error=subprocess.CalledProcessError(125,['docker','run'],stderr='daemon refused startup')
        with patch('tools.check_ms67_customer_startup.subprocess.run',side_effect=error) as run, patch('sys.stderr',new_callable=io.StringIO) as log:
            with self.assertRaises(subprocess.CalledProcessError): command(['docker','run'])
            self.assertIn('daemon refused startup',log.getvalue())
            run.assert_called_once()
