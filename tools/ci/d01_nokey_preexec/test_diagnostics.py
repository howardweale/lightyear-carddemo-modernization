"""CI-only regressions for bounded diagnostic retention, not containment proof."""
import json
import os
import unittest

from diagnostics import BoundedStderr, LIMIT


class BoundedStderrTests(unittest.TestCase):
    def setUp(self):
        self.capture = BoundedStderr()
        self.addCleanup(self.capture.close)

    def test_fragmented_bytes_are_preserved_and_json_escaped(self):
        raw = b"dyld:" + bytes((255, 27, 10))
        os.write(self.capture.write_fd, raw[:3])
        self.capture.check()
        os.write(self.capture.write_fd, raw[3:])
        self.capture.close_writer()
        self.capture.check(final=True)
        fields = self.capture.fields()
        self.assertEqual(bytes.fromhex(fields["stderr_hex"]), raw)
        self.assertTrue(fields["stderr_eof"])
        encoded = json.dumps(fields)
        self.assertNotIn(chr(27), encoded)
        self.assertNotIn(chr(10), encoded)
        self.assertEqual(json.loads(encoded), fields)

    def test_open_empty_writer_is_not_eof(self):
        self.capture.check()
        self.assertFalse(self.capture.eof)
        with self.assertRaisesRegex(ValueError, "incomplete EOF"):
            self.capture.check(final=True)

    def test_exact_limit_is_complete_only_after_eof(self):
        for _ in range(LIMIT // 256):
            os.write(self.capture.write_fd, b"x" * 256)
            self.capture.check()
        self.assertEqual(len(self.capture.data), LIMIT)
        self.assertFalse(self.capture.overflow)
        self.capture.close_writer()
        self.capture.check(final=True)

    def test_overflow_keeps_only_prefix_and_refuses(self):
        for _ in range(LIMIT // 256):
            os.write(self.capture.write_fd, b"x" * 256)
            self.capture.check()
        os.write(self.capture.write_fd, b"unexpected")
        with self.assertRaisesRegex(ValueError, "overflow"):
            self.capture.check()
        self.assertEqual(self.capture.data, b"x" * LIMIT)
        self.assertTrue(self.capture.overflow)
        self.capture.drain()
        self.assertEqual(len(self.capture.data), LIMIT)

    def test_empty_closed_writer_is_complete(self):
        self.capture.close_writer()
        self.capture.check(final=True)
        self.assertEqual(self.capture.fields()["stderr_hex"], "")

    def test_read_error_is_not_successful_eof(self):
        os.close(self.capture.read_fd)
        self.capture.read_fd = -1
        with self.assertRaisesRegex(ValueError, "read failure"):
            self.capture.check(final=True)
        self.assertTrue(self.capture.read_error)
        self.assertFalse(self.capture.eof)
        self.capture.read_fd = None


if __name__ == "__main__":
    unittest.main()
