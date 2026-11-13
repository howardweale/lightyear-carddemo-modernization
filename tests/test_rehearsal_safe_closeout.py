"""CI-only real fixed children and synthetic negative controls for D06 design."""
import json
import unittest
from unittest.mock import patch

from lightyear_execution import rehearsal_safe_closeout as closeout


class SeparateSafetyTests(unittest.TestCase):
    def assert_negative_preserved(self, result):
        self.assertEqual(closeout.S7, result["diagnostic"])
        self.assertFalse(result["native_proof"])
        self.assertFalse(result["admission_authorized"])
        self.assertFalse(result["restart_authorized"])
        self.assertFalse(result["operator_packet_bound"])
        self.assertEqual(5, result["cleanup_deadline"] - result["original_deadline"])

    def test_real_two_owned_children_exit_without_upgrading_s7(self):
        result = closeout.run_public_fixture()
        self.assert_negative_preserved(result)
        self.assertEqual("OBSERVED_EXIT", result["safety_status"])
        self.assertEqual({"worker", "observer"}, {p["role"] for p in result["processes"]})
        self.assertTrue(all(p["reaped"] and p["exitcode"] == 0 for p in result["processes"]))
        self.assertEqual([], result["forced_roles"])

    def test_partial_launch_still_reaps_first_owned_child(self):
        start = closeout._start
        def fail_second(role, deadline):
            if role == "observer":
                raise OSError("private exception text")
            return start(role, deadline)
        with patch.object(closeout, "_start", side_effect=fail_second):
            result = closeout.run_public_fixture()
        self.assert_negative_preserved(result)
        self.assertEqual("UNKNOWN", result["safety_status"])
        self.assertEqual("diagnostic-or-launch-failed", result["first_fault"])
        self.assertEqual(1, len(result["processes"]))
        self.assertTrue(result["processes"][0]["reaped"])
        self.assertNotIn("private exception text", json.dumps(result))

    def test_forged_diagnostic_pass_is_never_accepted(self):
        finish = closeout._finish
        def alter(process, deadline):
            raw = finish(process, deadline)
            return raw.replace(b'"FAIL"', b'"PASS"')
        with patch.object(closeout, "_finish", side_effect=alter):
            result = closeout.run_public_fixture()
        self.assert_negative_preserved(result)
        self.assertEqual("UNKNOWN", result["safety_status"])
        self.assertTrue(all(p["reaped"] for p in result["processes"]))

    def test_cancel_during_observation_retains_first_reason_and_reaps(self):
        finish = closeout._finish
        calls = []
        def cancel_once(process, deadline):
            calls.append(process.pid)
            if len(calls) == 1:
                raise KeyboardInterrupt
            return finish(process, deadline)
        with patch.object(closeout, "_finish", side_effect=cancel_once):
            result = closeout.run_public_fixture()
        self.assert_negative_preserved(result)
        self.assertEqual("cancelled", result["first_fault"])
        self.assertEqual("UNKNOWN", result["safety_status"])
        self.assertTrue(all(p["reaped"] for p in result["processes"]))

    def test_unknown_exit_cannot_be_observed_safety(self):
        finish = closeout._finish
        def lost_marker(process, deadline):
            raw = finish(process, deadline)
            return b"" if raw == b"PUBLIC-WORKER-EXIT\n" else raw
        with patch.object(closeout, "_finish", side_effect=lost_marker):
            result = closeout.run_public_fixture()
        self.assert_negative_preserved(result)
        self.assertEqual("UNKNOWN", result["safety_status"])

    def test_invalid_deadline_never_starts_any_process(self):
        with patch.object(closeout, "_start") as start:
            for duration in (0, 61, True, "5", float("inf"), float("nan")):
                with self.assertRaises(ValueError):
                    closeout.run_public_fixture(duration)
            start.assert_not_called()
