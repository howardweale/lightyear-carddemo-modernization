"""CI-only contract and binding review checks; no command-sheet execution."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from tools import native_rehearsal_bind_review as binding
from tools.ci import native_rehearsal_packet_dryrun as dry


class BindingReviewTests(unittest.TestCase):
    def values(self):
        return dict(public_values=dict(MAC_HOSTNAME="PUBLIC-EXAMPLE.invalid",
            MAC_STD_USER="fixture_user", MAC_UID="501", MAC_OS_BUILD="FIXTURE",
            USB_WIN_ROOT="Z:\\", USB_MAC_VOLUME="/Volumes/PUBLIC FIXTURE",
            USB_VOLUME_LABEL="PUBLIC FIXTURE"), received_at="2030-03-09T18:00:00-08:00",
            slot_start="2030-03-10T10:00:00-07:00")

    def test_offset_aware_window_across_offset_change(self):
        self.assertEqual(binding.validate_values(self.values())["MAC_UID"], "501")

    def test_missing_extra_placeholder_and_shell_metacharacters(self):
        for key, value in (("MAC_HOSTNAME", "<<MAC_HOSTNAME>>"),
                ("MAC_STD_USER", "x'; touch x"), ("USB_VOLUME_LABEL", "$(id)"),
                ("USB_VOLUME_LABEL", "line\nline"), ("MAC_UID", "0"),
                ("USB_MAC_VOLUME", "/Volumes/../x")):
            with self.subTest(key=key, value=value):
                doc = self.values(); doc["public_values"][key] = value
                with self.assertRaises(ValueError):
                    binding.validate_values(doc)
        doc = self.values(); del doc["public_values"]["MAC_UID"]
        with self.assertRaises(ValueError):
            binding.validate_values(doc)
        doc = self.values(); doc["private_key"] = "not permitted"
        with self.assertRaises(ValueError):
            binding.validate_values(doc)

    def test_stale_early_future_and_naive_values_refuse(self):
        for value in ("2030-03-08T10:00:00-08:00", "2030-03-08T17:00:00-08:00",
                      "2030-03-10T10:00:00-07:00", "2030-03-09T18:00:00"):
            doc = self.values(); doc["received_at"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                binding.validate_values(doc)

    def test_render_retains_block_and_checklist_and_rejects_slot_drift(self):
        doc = self.values()
        sheet = "NOT RUNNABLE\nREHEARSAL_START = " + doc["slot_start"] + "\n"
        sheet += "\n".join("<<"+key+">>" for key in binding.KEYS)
        result, checklist = binding.render(sheet, "NOT RUNNABLE checklist", doc)
        self.assertIn("NOT RUNNABLE", result)
        self.assertNotIn("<<", result)
        self.assertEqual(checklist, "NOT RUNNABLE checklist")
        doc["slot_start"] = "2030-03-10T11:00:00-07:00"
        with self.assertRaises(ValueError):
            binding.render(sheet, checklist, doc)

    def test_dynamic_slot_review_draft_and_exact_freshness_boundary(self):
        doc = self.values()
        doc["received_at"] = "2030-03-09T09:00:00-08:00"
        binding.validate_values(doc)  # Exactly24 elapsed hours over DST transition.
        sheet = "NOT RUNNABLE\nREHEARSAL_START = <<REHEARSAL_START>>\nREHEARSAL_DATE = <<REHEARSAL_DATE>>\n"
        sheet += "\n".join("<<"+key+">>" for key in binding.KEYS)
        rendered, _ = binding.render(sheet, "NOT RUNNABLE checklist", doc)
        self.assertIn(doc["slot_start"], rendered)
        self.assertIn("NOT RUNNABLE", rendered)
        self.assertNotIn("<<", rendered)
        doc["received_at"] = "2030-03-09T08:59:59-08:00"
        with self.assertRaises(ValueError):
            binding.validate_values(doc)


class StopDecisionTests(unittest.TestCase):
    def test_boundaries_and_unknown_are_fail_closed(self):
        self.assertFalse(dry.acceptable("uid", True, 501))
        self.assertFalse(dry.acceptable("message_age_hours", -1, 24))
        self.assertFalse(dry.acceptable("message_age_hours", float("nan"), 24))
        self.assertFalse(dry.acceptable("available_kib", 1048575, 1048576))
        self.assertFalse(dry.acceptable("groups", [20, 80], [20]))
        self.assertFalse(dry.acceptable("groups", None, [20]))
        self.assertTrue(dry.acceptable("uid", 502, 501))
        result = dry.decide({}, [{"id":"missing", "field":"x", "good":True}])
        self.assertEqual(result["stops"], ["missing"])
        self.assertFalse(result["execution_authorized"])

    def test_report_never_converts_expected_fail_or_cleanup_to_pass(self):
        result = dry.report(dry.PACKET)
        self.assertEqual(result["placeholder_binding"], "REFUSED")
        self.assertEqual(result["cleanup"], "UNKNOWN")
        self.assertEqual(result["expected_case_classifications"]["S4"], "FAIL")
        self.assertEqual(result["expected_case_classifications"]["S7"], "CI ONLY")
        self.assertTrue(all(row["decision"] == "STOP" for row in result["rows"]))
        self.assertFalse(result["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
