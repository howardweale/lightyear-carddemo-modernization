"""Synthetic public harness tests. No compiler, Docker or case bundle."""
import copy
import json
import io
import tarfile
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import intcalc_reference_execution as ref
from tools import intcalc_reference_image_inventory as oci
from tools import intcalc_reference_container as boundary


def valid_binding():
    row = {k: "1" * 64 for k in ("image_manifest", "image_config",
        "isam_inventory_sha256", "licence_review_sha256", "public_suite_sha256",
        "profile_probe_review_sha256")}
    row.update(schema="intcalc-reference-binding/1", platform="linux/amd64",
               compiler_package="3.1.2-5.1ubuntu1", flags=ref.FLAGS,
               case_ids=ref.IDS, case_author="Claude",
               hidden_generation_enabled=False, freeze_enabled=False)
    return row


class ReferenceContractTests(unittest.TestCase):
    def test_oracle_record_error_is_modelled_failure(self):
        from carddemo_oracle.records import RecordError
        stderr = io.StringIO()
        with patch.dict(ref.os.environ, {"GITHUB_ACTIONS": "true"}), \
                patch("carddemo_oracle.oracle.run_directory",
                      side_effect=RecordError("synthetic field overflow")), \
                patch.object(ref.sys, "stderr", stderr):
            self.assertEqual(ref.main(["oracle", "--input", "synthetic-input",
                                       "--output", "synthetic-output"]), 2)
        self.assertEqual(stderr.getvalue(), "python-oracle-exception\n")
        self.assertNotIn("synthetic field overflow", stderr.getvalue())

    def test_oracle_unexpected_errors_remain_worker_faults(self):
        for error in (ValueError("unexpected value"), RuntimeError("worker bug")):
            with self.subTest(kind=type(error).__name__), \
                    patch.dict(ref.os.environ, {"GITHUB_ACTIONS": "true"}), \
                    patch("carddemo_oracle.oracle.run_directory", side_effect=error), \
                    patch.object(ref.sys, "stderr", io.StringIO()) as stderr:
                with self.assertRaises(type(error)) as caught:
                    ref.main(["oracle", "--input", "synthetic-input",
                              "--output", "synthetic-output"])
                self.assertIs(caught.exception, error)
                self.assertEqual(stderr.getvalue(), "")

    def test_binding_complete_is_not_qualification(self):
        row = ref.binding(ref.canonical(valid_binding()))
        self.assertFalse(row["freeze_enabled"])

    def test_every_blocking_binding_refuses(self):
        for key in ("image_manifest", "image_config", "isam_inventory_sha256",
                    "licence_review_sha256", "public_suite_sha256",
                    "profile_probe_review_sha256"):
            with self.subTest(key=key):
                row = valid_binding()
                row[key] = None
                with self.assertRaisesRegex(ref.Refused, "^unbound-" + key + "$"):
                    ref.binding(ref.canonical(row))

    def test_no_seed_or_freeze_mode(self):
        row = valid_binding()
        row["hidden_generation_enabled"] = True
        with self.assertRaisesRegex(ref.Refused, "no-freeze-authority"):
            ref.binding(ref.canonical(row))

    def test_wrong_platform(self):
        row = valid_binding()
        row["platform"] = "linux/arm64"
        with self.assertRaisesRegex(ref.Refused, "reference-platform"):
            ref.binding(ref.canonical(row))

    def test_no_case_selection_change(self):
        row = valid_binding()
        row["case_ids"] = ref.IDS[:-1]
        with self.assertRaisesRegex(ref.Refused, "public-case-inventory"):
            ref.binding(ref.canonical(row))

    def test_no_float_or_duplicates(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e400}', b'{"a":1.1}'):
            with self.subTest(raw=raw), self.assertRaises(ref.Refused):
                ref.strict(raw)

    def test_strict_utf8(self):
        with self.assertRaises(ref.Refused):
            ref.strict('{"a":1}'.encode("utf-16"))

    def test_roundtrip_and_key_order(self):
        raw = b"02ab01cd".decode("ascii").encode("cp037")
        self.assertEqual(ref.bridge(raw, 4, 2), b"02ab01cd")

    def test_mixed_collation_refuses(self):
        raw = "A 0 ".encode("cp037")
        with self.assertRaisesRegex(ref.Refused, "cp037-key-order"):
            ref.bridge(raw, 2, 1, order_observable=True)

    def test_actual_mixed_keys_same_order_accept_both_input_directions(self):
        for words in (("GOLD      010001", "GOLD      010002"),
                      ("GOLD      010002", "GOLD      010001")):
            raw = "".join(words).encode("cp037")
            self.assertEqual(ref.bridge(raw, 16, 16, order_observable=True), raw.decode("cp037").encode("ascii"))

    def test_actual_order_difference_refuses_both_input_directions(self):
        for text in ("A 0 ", "0 A "):
            with self.subTest(text=text), self.assertRaisesRegex(ref.Refused, "cp037-key-order"):
                ref.bridge(text.encode("cp037"), 2, 1, order_observable=True)

    def test_unobservable_key_order_and_uniqueness(self):
        self.assertEqual(ref.bridge("A 0 ".encode("cp037"), 2, 1), b"A 0 ")
        with self.assertRaisesRegex(ref.Refused, "duplicate-primary-key"):
            ref.bridge("A A ".encode("cp037"), 2, 1)

    def test_python_unmodelled_channels_do_not_differ(self):
        case = {"id": "PC-01"}
        hand = dict(ACCTFILE=b"a", TRANSACT=b"b", stdout=b"display\n", stderr=b"", exit=0)
        python = dict(hand, stdout=b"not-modelled", stderr=b"not-modelled")
        report = ref.compare_results(case, hand, hand, python, {})
        self.assertTrue(report["freeze_criterion_met"])
        for pair in report["comparisons"][1:]:
            for key in ("stdout", "stderr", "exit"):
                self.assertEqual(pair["channels"][key]["status"], "NOT_MODELLED")

    def test_preregistered_exact_discrepancy_and_no_blanket_waiver(self):
        hand = dict(ACCTFILE=b"a", TRANSACT=b"b", stdout=b"", stderr=b"", exit=0)
        python = dict(hand, TRANSACT=b"c")
        case = {"id": "PC-01"}
        self.assertFalse(ref.compare_results(case, hand, hand, python, {})["freeze_criterion_met"])
        difference = ref.first_difference(b"b", b"c", 350)
        case["python_findings"] = [dict(finding="O1", pair=p, channel="TRANSACT",
                                       difference_sha256=ref.sha(ref.canonical(difference)))
                                   for p in ("reference-python", "hand-python")]
        report = ref.compare_results(case, hand, hand, python, {})
        self.assertTrue(report["freeze_criterion_met"])
        self.assertFalse(report["all_modelled_channels_match"])
        self.assertFalse(ref.compare_results(case, hand, hand, dict(python, ACCTFILE=b"x"), {})["freeze_criterion_met"])
        self.assertFalse(ref.compare_results(case, hand, hand, dict(python, TRANSACT=b"d"), {})["freeze_criterion_met"])

    def test_reference_hand_never_waived(self):
        hand = dict(ACCTFILE=b"a", TRANSACT=b"b", stdout=b"", stderr=b"", exit=0)
        reference = dict(hand, stdout=b"wrong")
        self.assertFalse(ref.compare_results({"id":"PC-01"}, reference, hand, hand, {})["freeze_criterion_met"])

    def test_abend_ignores_files_and_python_exit_value(self):
        for case_id in ("PC-10", "PC-11", "PC-12"):
            case = {"id":case_id, "compare_output_files":False}
            hand = dict(stdout=b"program display\n", stderr=b"", exit=12)
            reference = dict(hand, ACCTFILE=b"undefined", TRANSACT=b"undefined")
            python = dict(stdout=b"not-modelled", stderr=b"not-modelled", exit=2)
            report = ref.compare_results(case, reference, hand, python, {})
            self.assertTrue(report["freeze_criterion_met"])
            for pair in report["comparisons"]:
                for dd in ("ACCTFILE", "TRANSACT"):
                    self.assertEqual(pair["channels"][dd]["status"], "NOT_COMPARED")
            self.assertFalse(ref.compare_results(case, reference, hand, dict(python, exit=0), {})["freeze_criterion_met"])

    def test_abend_policy_cannot_disable_normal_comparison(self):
        for case in ({"id":"PC-10"}, {"id":"PC-01", "compare_output_files":False},
                     {"id":"PC-01", "compare_output_files":0}):
            with self.subTest(case=case), self.assertRaises(ref.Refused):
                ref.comparison_policy(case)

    def test_shim_no_diagnostic_output(self):
        from tools.intcalc_reference_adapters import ABEND
        self.assertNotIn("display", ABEND.lower())
        self.assertIn("stop run returning 12", ABEND.lower())

    def test_duplicate_key_refuses(self):
        with self.assertRaisesRegex(ref.Refused, "duplicate-primary-key"):
            ref.bridge("01ab01cd".encode("cp037"), 4, 2)

    def test_partial_record_refuses(self):
        with self.assertRaisesRegex(ref.Refused, "partial-record"):
            ref.bridge(b"abc", 4, 0)

    def test_control_and_nonascii_refuse(self):
        for value in ("\n", "\u00a3"):
            with self.subTest(value=value), self.assertRaises(ref.Refused):
                ref.bridge(value.encode("cp037"), 1, 0)

    def test_output_preserves_spaces_and_sign_chars(self):
        raw = b"00{ 00}"
        self.assertEqual(ref.decode_output(raw, 7).decode("cp037"), raw.decode("ascii"))

    def test_first_difference_and_missing_record(self):
        self.assertIsNone(ref.first_difference(b"abcd", b"abcd", 2))
        self.assertEqual(ref.first_difference(b"abcd", b"abXd", 2)["record"], 2)
        self.assertEqual(ref.first_difference(b"abcd", b"ab", 2)["byte"], 2)

    def test_clock_keeps_fraction_for_probe(self):
        self.assertEqual(ref.clock_env("2026-11-14-12.34.56.789123", "2026111400")["COB_CURRENT_DATE"],
                         "2026/11/14 12:34:56.789123000")

    def test_invalid_date(self):
        with self.assertRaises(ref.Refused):
            ref.clock_env("2026-02-31-12.34.56.000000", "2026111400")

    def test_join_and_path_refusals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one").write_bytes(b"public")
            self.assertEqual(ref.joined(root, {"path": "one", "sha256": ref.sha(b"public")}), b"public")
            for name in ("../one", "/one", "C:/one", "a//one", "a\\one"):
                with self.subTest(name=name), self.assertRaises(ref.Refused):
                    ref.joined(root, {"path": name, "sha256": ref.sha(b"public")})

    def test_wrong_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one").write_bytes(b"public")
            with self.assertRaisesRegex(ref.Refused, "file-hash"):
                ref.joined(root, {"path": "one", "sha256": "0" * 64})

    def test_exclusive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one"
            ref.exclusive(path, b"first")
            with self.assertRaises(FileExistsError):
                ref.exclusive(path, b"second")
            self.assertEqual(path.read_bytes(), b"first")

    def test_no_exec_on_unbound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "binding.json"
            row = valid_binding()
            row["image_manifest"] = None
            path.write_bytes(ref.canonical(row))
            with patch.object(ref, "native") as native, self.assertRaises(ref.Refused):
                ref.qualify(path, Path(directory) / "absent", Path(directory) / "out")
            native.assert_not_called()

    def test_windows_clean_refusal(self):
        cwd = Path(".")
        with patch.object(ref.os, "name", "nt"), self.assertRaisesRegex(ref.Refused, "posix-required"):
            ref.run(["never"], cwd, 0)

    def test_probe_inventory_refuses_missing(self):
        with self.assertRaisesRegex(ref.Refused, "probe-inventory"):
            ref.probes(Path("."), 0, [])

    def test_host_refuses_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(boundary.platform, "system", return_value="Windows"), \
                 patch.object(boundary, "call") as call, self.assertRaises(ref.Refused):
                boundary.execute(root / "binding", root / "suite", root / "out")
            call.assert_not_called()

    def test_oci_hash_join(self):
        config = ref.canonical({"os": "linux", "architecture": "amd64"})
        config_hash = ref.sha(config)
        manifest = ref.canonical({"schemaVersion": 2, "config": {"digest": "sha256:" + config_hash}})
        manifest_hash = ref.sha(manifest)
        entries = {"index.json": ref.canonical({"manifests": [{"digest": "sha256:" + manifest_hash}]}),
                   "blobs/sha256/" + manifest_hash: manifest,
                   "blobs/sha256/" + config_hash: config}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.tar"
            with tarfile.open(path, "w") as archive:
                for name, content in entries.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
            result = oci.inventory(path)
            self.assertEqual(result["manifest"], "sha256:" + manifest_hash)
            self.assertEqual(result["config"], "sha256:" + config_hash)
            self.assertFalse(result["qualified"])

    def test_oci_duplicate_index_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.tar"
            with tarfile.open(path, "w") as archive:
                for _ in range(2):
                    member = tarfile.TarInfo("index.json")
                    member.size = 2
                    archive.addfile(member, io.BytesIO(b"{}"))
            with self.assertRaisesRegex(ValueError, "oci-entry"):
                oci.inventory(path)


class RuntimeDiagnosticsTests(unittest.TestCase):
    LINES = (
        b"libcob: warning: implicit CLOSE of TRANSACT-FILE ('TRANSACT')\n",
        b"libcob: warning: implicit CLOSE of ACCOUNT-FILE ('ACCTFILE')\n",
        b"libcob: warning: implicit CLOSE of DISCGRP-FILE ('DISCGRP')\n",
        b"libcob: warning: implicit CLOSE of XREF-FILE ('XREFFILE')\n",
        b"libcob: warning: implicit CLOSE of TCATBAL-FILE ('TCATBALF')\n",
    )

    def test_exact_five_lines_separated_without_loss(self):
        raw = b"".join(self.LINES)
        compared, diagnostics = ref.split_runtime_diagnostics(raw)
        self.assertEqual(compared, b"")
        self.assertEqual(len(diagnostics), 5)
        self.assertEqual(b"".join(bytes.fromhex(d["line_hex"]) for d in diagnostics), raw)
        self.assertEqual([d["dd"] for d in diagnostics],
                         ["TRANSACT", "ACCTFILE", "DISCGRP", "XREFFILE", "TCATBALF"])

    def test_other_stderr_bytes_remain_in_order(self):
        raw = b"before\n" + self.LINES[0] + b"\xff\x00after\n" + self.LINES[1] + b"tail"
        compared, diagnostics = ref.split_runtime_diagnostics(raw)
        self.assertEqual(compared, b"before\n\xff\x00after\ntail")
        self.assertEqual(len(diagnostics), 2)

    def test_similar_messages_are_not_suppressed(self):
        line = self.LINES[0]
        variants = [line.replace(b"TRANSACT-FILE", b"OTHER-FILE"),
                    line.replace(b"('TRANSACT')", b"('ACCTFILE')"),
                    line.replace(b"warning", b"error"), b"prefix " + line,
                    line[:-1] + b" suffix\n", line.replace(b"\n", b"\r\n"),
                    line[:-1], line.replace(b"CLOSE", b"close"),
                    b"libcob: warning: another warning\n"]
        for raw in variants:
            with self.subTest(raw=raw):
                self.assertEqual(ref.split_runtime_diagnostics(raw), (raw, []))

    def test_empty_and_duplicate_diagnostics(self):
        self.assertEqual(ref.split_runtime_diagnostics(b""), (b"", []))
        compared, diagnostics = ref.split_runtime_diagnostics(self.LINES[0] * 2)
        self.assertEqual(compared, b"")
        self.assertEqual(len(diagnostics), 2)

    def test_abend_comparison_keeps_diagnostics_and_unknown_failure(self):
        for case_id in ("PC-10", "PC-11", "PC-12"):
            case = {"id": case_id, "compare_output_files": False}
            hand = dict(stdout=b"program display\n", stderr=b"", exit=12)
            reference = dict(hand, stderr=b"".join(self.LINES))
            python = dict(stdout=b"", stderr=b"", exit=2)
            report = ref.compare_results(case, reference, hand, python, {})
            self.assertTrue(report["freeze_criterion_met"])
            self.assertEqual(len(report["runtime_diagnostics"]), 5)
            self.assertEqual(reference["stderr"], b"".join(self.LINES))
            reference["stderr"] += b"unexpected\n"
            report = ref.compare_results(case, reference, hand, python, {})
            self.assertFalse(report["freeze_criterion_met"])
            self.assertEqual(report["comparisons"][0]["channels"]["stderr"]["status"], "DIFFERENT")

    def test_public_case_retains_raw_and_compared_stderr(self):
        raw = b"".join(self.LINES)
        record = {"path": "unused", "sha256": "0" * 64}
        case = {"id": "PC-10", "compare_output_files": False,
                "inputs": {dd: record for dd in ref.DDS if dd != "TRANSACT"},
                "hand_outputs": {"stdout": record, "stderr": record}, "hand_exit": 12,
                "timestamp": "2026-11-14-12.34.56.000000", "processing_date": "2026111400"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(ref, "joined", return_value=b""), \
                    patch.object(ref, "checked"), \
                    patch.object(ref, "run", side_effect=[(12, b"", raw), (2, b"", b"python-oracle-exception\n")]):
                report = ref.public_case(case, root, root, root, 123, {})
            self.assertTrue(report["freeze_criterion_met"])
            self.assertEqual((root / "observations/reference/stderr.raw").read_bytes(), raw)
            self.assertEqual((root / "observations/reference/stderr").read_bytes(), b"")
            self.assertEqual((root / "observations/python/stderr").read_bytes(), b"python-oracle-exception\n")


if __name__ == "__main__":
    unittest.main()
