"""CI-only original OS subprocess probes with public bytes; no gh/API fixture.

These exercise collection/refusal, not authenticated artifacts or admission.
"""
import sys
import unittest
from tools.ci.operator_flow_download import _capture_bounded_stdout


class BoundedDownloadProcess(unittest.TestCase):
    def collect(self, source, limit=4096, timeout=10):
        return _capture_bounded_stdout([sys.executable, '-B', '-c', source],
            max_bytes=limit, timeout=timeout)

    def test_exact_limit_binary_bytes_preserved(self):
        result = self.collect('import sys; sys.stdout.buffer.write(bytes(range(256))*16)')
        self.assertEqual(result, bytes(range(256))*16)

    def test_short_and_empty_output_preserved(self):
        self.assertEqual(self.collect('import sys; sys.stdout.buffer.write(b"public")'), b'public')
        self.assertEqual(self.collect('pass'), b'')

    def test_one_byte_over_limit_refuses(self):
        with self.assertRaisesRegex(ValueError, '^handoff-download-overflow$'):
            self.collect('import sys; sys.stdout.buffer.write(b"x"*4097)')

    def test_continuous_stdout_refuses_without_waiting_for_eof(self):
        source = 'import os\nwhile True: os.write(1, b"x"*65536)'
        with self.assertRaisesRegex(ValueError, '^handoff-download-overflow$'):
            self.collect(source)

    def test_nonzero_after_output_refuses(self):
        with self.assertRaisesRegex(ValueError, '^handoff-download-exit$'):
            self.collect('import sys; sys.stdout.buffer.write(b"public"); sys.exit(7)')

    def test_open_pipe_timeout_refuses(self):
        with self.assertRaisesRegex(ValueError, '^handoff-download-timeout$'):
            self.collect('import time; time.sleep(30)', timeout=3)

    def test_stdout_closed_before_process_exit_still_times_out(self):
        with self.assertRaisesRegex(ValueError, '^handoff-download-timeout$'):
            self.collect('import os,time; os.close(1); time.sleep(30)', timeout=3)

    def test_large_stderr_does_not_block_or_enter_returned_bytes(self):
        source = ('import os\n'
                  'for _ in range(512): os.write(2, b"public-stderr"*1024)\n'
                  'os.write(1, b"public-stdout")')
        self.assertEqual(self.collect(source), b'public-stdout')

    def test_missing_or_skipped_download_step_refuses_prior_ci_records(self):
        # Relationship-only check. Original process tests above supply no
        # service identity, successful CI receipt or native admission authority.
        import test_operator_flow_ci_prerequisite as records
        fixture = records.PriorComponentRecords()
        fixture.setUp()
        name = 'Original subprocess download bounds and refusal checks'
        matches = [s for s in fixture.job['steps'] if s['name'] == name]
        self.assertEqual(len(matches), 1)
        matches[0]['conclusion'] = 'skipped'
        with self.assertRaisesRegex(ValueError, '^prior-ci-required-step$'):
            fixture.check()
        fixture.job['steps'].remove(matches[0])
        with self.assertRaisesRegex(ValueError, '^prior-ci-required-step$'):
            fixture.check()
