"""CI-only synthetic compilation feedback tests; no compiler or provider."""
from dataclasses import replace
import json
import unittest
from unittest.mock import patch
from lightyear_factory import intcalc_preview_build_gate as b
from lightyear_factory import intcalc_preview_composition as c
import test_intcalc_preview_composition as fixture


class CompilationFeedbackTests(unittest.TestCase):
    def setUp(self):
        for name, value in (('CONTEXT_HASH', c.digest(fixture.PUBLIC)),
                            ('ALLOWLIST_HASH', c.digest(fixture.ALLOWLIST))):
            change = patch.object(c, name, value)
            change.start()
            self.addCleanup(change.stop)
        self.ports = fixture.FakePorts([('MATCH',) * 10, ('MATCH',) * 10])
        self.number = 0

    def failure(self, built):
        return replace(built, artifact_sha256=None, compile_failed=True,
            compiler_exit_code=1, compiler_stderr='/source/Main.java:1: error: expected',
            compiler_stderr_truncated=False)

    def run_session(self):
        return c.Composition(fixture.packet(), fixture.PUBLIC, fixture.ALLOWLIST,
            self.ports, clock=lambda: self.ports.now).run()

    def test_first_compile_failure_allows_exactly_one_repair(self):
        def first(built):
            self.number += 1
            return self.failure(built) if self.number == 1 else built
        self.ports.mutate_build = first
        result = self.run_session()
        self.assertEqual(result['status'], 'MATCH_AFTER_REPAIR')
        self.assertNotIn('gate1', self.ports.events)
        self.assertIn('gate2', self.ports.events)
        self.assertEqual(result['reserved_microdollars'], 9458636)
        c.verify_result(result)

    def test_repair_compile_failure_terminal_without_gate(self):
        self.ports.mutate_build = self.failure
        result = self.run_session()
        self.assertEqual(result['status'], 'CANDIDATE_FAIL')
        self.assertEqual(result['feedback_observations'], 2)
        self.assertNotIn('gate1', self.ports.events)
        self.assertNotIn('gate2', self.ports.events)
        c.verify_result(result)

    def test_feedback_frozen_and_no_build_receipt_or_stdout(self):
        self.ports.mutate_build = self.failure
        self.run_session()
        left = json.loads(self.ports.projections['analysis-attempt1']['input'])['feedback']
        right = json.loads(self.ports.projections['builder-repair1']['input'])['feedback']
        self.assertEqual(left, right)
        self.assertEqual(set(left), {'schema', 'kind', 'javac_stderr', 'stderr_truncated'})
        self.assertEqual(left['kind'], 'compilation-failed')

    def test_infrastructure_cleanup_fault_has_no_repair(self):
        self.ports.mutate_build = lambda v: replace(self.failure(v), cleanup_confirmed=False)
        with self.assertRaises(c.CompositionRefused):
            self.run_session()
        self.assertNotIn('analysis-attempt1', self.ports.events)

    def test_launch_or_signal_exit_is_not_compile_failure(self):
        for code in (0, 2, 3, 4, 5, 125, 126, 127, 137, 255, True):
            with self.subTest(code=code):
                self.ports = fixture.FakePorts()
                self.ports.mutate_build = lambda v: replace(self.failure(v), compiler_exit_code=code)
                with self.assertRaises(c.CompositionRefused):
                    self.run_session()
                self.assertNotIn('analysis-attempt1', self.ports.events)

    def test_javac_source_excerpt_slashes_never_refused(self):
        lines = ['... String p = dir + "/" + name;', "... char c = '/';", 'a/b; // ratio', '</b>']
        for line in lines:
            with self.subTest(line=line):
                text, cut = b.compile_diagnostic(line.encode())
                self.assertEqual(text, line)
                self.assertFalse(cut)
                c.validate_compile_feedback(dict(schema=c.COMPILE_SCHEMA, kind='compilation-failed',
                    javac_stderr=text, stderr_truncated=cut))

    def test_all_ascii_punctuation_survives(self):
        raw = bytes(range(32, 127))
        self.assertEqual(b.compile_diagnostic(raw), (raw.decode(), False))

    def test_utf8_boundary_truncation(self):
        text, cut = b.compile_diagnostic(b'x' * 4095 + '\u00e9'.encode())
        self.assertEqual(text, 'x' * 4095)
        self.assertTrue(cut)

    def test_malformed_utf8_refuses(self):
        for raw in (b'bad\xff',):
            with self.subTest(raw=raw), self.assertRaises((ValueError, UnicodeError)):
                b.compile_diagnostic(raw)

    def test_c0_is_normalized_not_forwarded_or_refused(self):
        text, cut = b.compile_diagnostic(b'bad\x00\x1b')
        self.assertEqual(text, 'bad\\u0000\\u001b')
        self.assertFalse(cut)

    def test_exact_4096_bytes_not_truncated(self):
        self.assertEqual(b.compile_diagnostic(b'x' * 4096), ('x' * 4096, False))

    def test_diagnostic_extra_fields_rejected(self):
        value = dict(schema=c.COMPILE_SCHEMA, kind='compilation-failed', javac_stderr='',
                     stderr_truncated=False, stdout='must not cross')
        with self.assertRaises(c.CompositionRefused):
            c.validate_feedback(value)

    def test_verifier_feedback_remains_counts(self):
        value = c.feedback(('DIFFERENT',) * 10)
        self.assertEqual(set(c.validate_feedback(value)), {'schema', 'verdict_counts'})

    def test_successful_build_cannot_smuggle_diagnostic(self):
        self.ports.mutate_build = lambda v: replace(v, compiler_stderr='unexpected')
        with self.assertRaises(c.CompositionRefused):
            self.run_session()
        self.assertNotIn('gate1', self.ports.events)
