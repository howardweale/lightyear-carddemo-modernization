"""CI-only real-clock diagnostic probes; no preflight, API or clock substitute."""
import io,os,time,unittest
from contextlib import redirect_stderr
from datetime import datetime,timezone
from tools.ci.p5_configured_receipt_supervisor import _observe_preflight_timing


class BrokenDiagnosticOutput:
    def write(self,value):raise OSError('public diagnostic output unavailable')
    def flush(self):raise OSError('public diagnostic output unavailable')


class PreflightTimingObservations(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
    def fields(self,text):
        lines=text.splitlines();self.assertEqual(len(lines),1)
        parts=lines[0].split();self.assertEqual(parts[0],'configured-preflight-timing')
        row=dict(item.split('=',1) for item in parts[1:])
        self.assertEqual(set(row),{'start_utc','end_utc','start_monotonic_ns','end_monotonic_ns','elapsed_ns','completed'})
        for key in ('start_utc','end_utc'):
            self.assertEqual(datetime.fromisoformat(row[key]).utcoffset(),timezone.utc.utcoffset(None))
        start=int(row['start_monotonic_ns']);end=int(row['end_monotonic_ns'])
        self.assertGreaterEqual(end,start);self.assertEqual(int(row['elapsed_ns']),end-start)
        return row
    def test_actual_clock_observation_brackets_body_once(self):
        stream=io.StringIO();calls=[];before=time.monotonic_ns()
        with redirect_stderr(stream):
            with _observe_preflight_timing():calls.append(time.monotonic_ns())
        after=time.monotonic_ns();row=self.fields(stream.getvalue())
        self.assertEqual(row['completed'],'True');self.assertEqual(len(calls),1)
        self.assertLessEqual(before,int(row['start_monotonic_ns']))
        self.assertLessEqual(int(row['start_monotonic_ns']),calls[0])
        self.assertLessEqual(calls[0],int(row['end_monotonic_ns']))
        self.assertLessEqual(int(row['end_monotonic_ns']),after)
    def test_original_exception_identity_and_private_message_preserved(self):
        stream=io.StringIO();original=ValueError('public-only sentinel excluded from diagnostic')
        with redirect_stderr(stream):
            with self.assertRaises(ValueError) as caught:
                with _observe_preflight_timing():raise original
        self.assertIs(caught.exception,original)
        self.assertEqual(self.fields(stream.getvalue())['completed'],'False')
        self.assertNotIn(str(original),stream.getvalue())
    def test_original_system_exit_is_not_completed_or_suppressed(self):
        stream=io.StringIO();original=SystemExit(23)
        with redirect_stderr(stream):
            with self.assertRaises(SystemExit) as caught:
                with _observe_preflight_timing():raise original
        self.assertIs(caught.exception,original);self.assertEqual(caught.exception.code,23)
        self.assertEqual(self.fields(stream.getvalue())['completed'],'False')
    def test_output_failure_preserves_original_result(self):
        def body():
            with _observe_preflight_timing():return 19
        with redirect_stderr(BrokenDiagnosticOutput()):self.assertEqual(body(),19)
    def test_output_failure_preserves_original_exception(self):
        original=RuntimeError('original public sentinel')
        with redirect_stderr(BrokenDiagnosticOutput()):
            with self.assertRaises(RuntimeError) as caught:
                with _observe_preflight_timing():raise original
        self.assertIs(caught.exception,original)
    def test_separate_observations_have_no_shared_completion_state(self):
        stream=io.StringIO()
        with redirect_stderr(stream):
            with self.assertRaises(ValueError):
                with _observe_preflight_timing():raise ValueError('public failure')
            with _observe_preflight_timing():pass
        lines=stream.getvalue().splitlines();self.assertEqual(len(lines),2)
        failed=self.fields(lines[0]);completed=self.fields(lines[1])
        self.assertEqual((failed['completed'],completed['completed']),('False','True'))
        self.assertLessEqual(int(failed['end_monotonic_ns']),int(completed['start_monotonic_ns']))
