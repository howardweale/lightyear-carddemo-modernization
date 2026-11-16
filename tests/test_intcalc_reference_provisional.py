"""Synthetic provisional contracts: no Docker, compiler, oracle or provider."""
import ast
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import intcalc_reference_execution as ref
from tools import intcalc_reference_provisional as provisional
from tools import intcalc_reference_provisional_container as host


def sample_inventory():
    return {"schema": "reference-inventory/1", "compiler": "compiler",
            "runtime": "runtime", "packages": "package\t1\tamd64\n",
            "copyright_files": {"package/copyright": "a" * 64},
            "libcob_inventory": {"libcob.so": {"sha256": "b" * 64,
                "dynamic_dependencies": "libdb.so => /lib/libdb.so (0x123)\n"}},
            "isam_backend_review": "PENDING", "qualified": False}


class ProvisionalTests(unittest.TestCase):
    def reviewed_fixture(self):
        inventory = ref.canonical(sample_inventory())
        original = [{"id": "original-" + str(n), "source": {"path": "probe-" + str(n), "sha256": "a" * 64}} for n in range(7)]
        expanded = original + [{"id": n, "source": {"path": n, "sha256": "a" * 64}} for n in provisional.NEW_PROBES]
        probes = ref.canonical({"probes": expanded})
        suite = ref.canonical({"schema": "intcalc-claude-public-suite/1", "author": "Claude", "visibility": "public", "cases": [{"id": n} for n in ref.IDS]})
        row = {"flags": ref.FLAGS, "platform": "linux/amd64", "compiler_package": "3.1.2-5.1ubuntu1", "case_ids": ref.IDS, "case_author": "Claude", "freeze_enabled": False, "hidden_generation_enabled": False, "sources": [], "public_suite_sha256": ref.sha(suite), "probes": {"path": "original", "sha256": "a" * 64}}
        inv_review = {"schema": "reference-provisional-inventory-review/1", "reviewer": "Claude", "accepted_for_provisional": True, "inventory_sha256": ref.sha(inventory), "package_library_sha256": provisional.inventory_digest(sample_inventory())}
        probe_review = {"schema": "reference-nine-probe-review/1", "reviewer": "Claude", "accepted": True, "probes_sha256": ref.sha(probes)}
        files = {"inventory": inventory, "inventory-review": ref.canonical(inv_review), "probe-review": ref.canonical(probe_review), provisional.BASE_BINDING: ref.canonical(row), "suite": suite, "probes": probes, "original": ref.canonical({"probes": original})}
        for probe in expanded: files[probe["source"]["path"]] = b"public probe"
        request = {"schema": "reference-provisional-request/1", "provisional": True, "qualified": False, "freeze_enabled": False}
        for key, path in (("expected_inventory", "inventory"), ("inventory_review", "inventory-review"), ("probe_review", "probe-review"), ("source_binding", provisional.BASE_BINDING), ("suite", "suite"), ("probes", "probes")):
            request[key] = {"path": path, "sha256": ref.sha(files[path])}
        return request, files

    def check_fixture(self, request, files):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                patch.object(ref, "bounded", return_value=ref.canonical(request)), \
                patch.object(ref, "joined", side_effect=lambda root, record: files[record["path"]]):
            return provisional.check_inputs(Path("request"))

    def test_all_nine_probes_use_reviewed_expectations(self):
        path = ref.ROOT / "spec/reference-provisional/2026-11-15/PROBES.json"
        rows = ref.strict(ref.bounded(path))["probes"]
        with tempfile.TemporaryDirectory() as folder, patch.object(ref, "checked") as compile_, \
                patch.object(ref, "run", return_value=(0, b"", b"")) as run:
            observations = provisional.run_probes(Path(folder), 123, rows)
            for row in rows:
                observed = Path(folder) / ("probe-" + row["id"]) / "observations"
                self.assertEqual((observed / "stdout").read_bytes(), b"")
                self.assertEqual((observed / "stderr").read_bytes(), b"")
        self.assertEqual(compile_.call_count, 9)
        self.assertEqual(run.call_count, 9)
        self.assertEqual([o["id"] for o in observations], [p["id"] for p in rows])
        self.assertTrue(all(o["match"] for o in observations))
        with self.assertRaisesRegex(ref.Refused, "nine-probe-set"):
            provisional.run_probes(Path("unused"), 123, rows[:7])

    def test_reviewed_inputs_accept_without_execution(self):
        request, files = self.reviewed_fixture()
        self.assertEqual(self.check_fixture(request, files)[4], provisional.inventory_digest(sample_inventory()))

    def test_inventory_review_wrong_hash_refuses(self):
        request, files = self.reviewed_fixture()
        review = ref.strict(files["inventory-review"]); review["inventory_sha256"] = "0" * 64
        files["inventory-review"] = ref.canonical(review)
        with self.assertRaisesRegex(ref.Refused, "inventory-review"):
            self.check_fixture(request, files)

    def test_probe_review_cannot_cover_different_sources(self):
        request, files = self.reviewed_fixture()
        review = ref.strict(files["probe-review"]); review["probes_sha256"] = "0" * 64
        files["probe-review"] = ref.canonical(review)
        with self.assertRaisesRegex(ref.Refused, "nine-probe-review"):
            self.check_fixture(request, files)

    def test_qualification_or_freeze_flags_refuse(self):
        for key in ("qualified", "freeze_enabled"):
            request, files = self.reviewed_fixture(); request[key] = True
            with self.subTest(key=key), self.assertRaisesRegex(ref.Refused, "provisional-only"):
                self.check_fixture(request, files)

    def test_nine_probe_set_is_mandatory(self):
        request, files = self.reviewed_fixture()
        value = ref.strict(files["probes"]); value["probes"].pop()
        files["probes"] = ref.canonical(value)
        with self.assertRaisesRegex(ref.Refused, "nine-probe-set"):
            self.check_fixture(request, files)

    def test_addresses_only_are_ignored(self):
        first = sample_inventory()
        second = copy.deepcopy(first)
        second["libcob_inventory"]["libcob.so"]["dynamic_dependencies"] = "libdb.so => /lib/libdb.so (0x987ABC)\n"
        self.assertEqual(provisional.inventory_digest(first), provisional.inventory_digest(second))
        self.assertIn("0x123", first["libcob_inventory"]["libcob.so"]["dynamic_dependencies"])

    def test_package_change_refuses_equality(self):
        first = sample_inventory(); second = copy.deepcopy(first)
        second["packages"] = "package\t2\tamd64\n"
        self.assertNotEqual(provisional.inventory_digest(first), provisional.inventory_digest(second))

    def test_library_path_and_hash_are_compared(self):
        for key, value in (("sha256", "c" * 64), ("dynamic_dependencies", "libdb.so => /other/libdb.so (0x123)\n")):
            first = sample_inventory(); second = copy.deepcopy(first)
            second["libcob_inventory"]["libcob.so"][key] = value
            with self.subTest(key=key):
                self.assertNotEqual(provisional.inventory_digest(first), provisional.inventory_digest(second))

    def test_licence_hash_is_compared(self):
        first = sample_inventory(); second = copy.deepcopy(first)
        second["copyright_files"]["package/copyright"] = "c" * 64
        self.assertNotEqual(provisional.inventory_digest(first), provisional.inventory_digest(second))

    def test_unresolved_library_refuses(self):
        row = sample_inventory()
        row["libcob_inventory"]["libcob.so"]["dynamic_dependencies"] = "libdb.so => not found\n"
        with self.assertRaisesRegex(ref.Refused, "inventory-unresolved-library"):
            provisional.inventory_digest(row)

    def test_no_broad_address_or_path_removal(self):
        row = sample_inventory()
        row["libcob_inventory"]["libcob.so"]["dynamic_dependencies"] = "/lib/0x123.so (0x123) extra\n"
        value = provisional.inventory_projection(row)["libcob_inventory"]["libcob.so"]["dynamic_dependencies"]
        self.assertEqual(value, "/lib/0x123.so (0x123) extra\n")

    def test_missing_inventory_fields_refuse(self):
        for key in ("compiler", "runtime", "packages", "copyright_files", "libcob_inventory"):
            row = sample_inventory(); del row[key]
            with self.subTest(key=key), self.assertRaisesRegex(ref.Refused, "inventory-fields"):
                provisional.inventory_digest(row)

    def test_report_cannot_claim_qualification_or_freeze(self):
        cases = [{"freeze_criterion_met": True, "all_modelled_channels_match": True}]
        report = provisional.make_report("a", "b", "c", "d", [{"match": True}], cases)
        self.assertTrue(report["comparison_criterion_met"])
        self.assertTrue(report["provisional"])
        for key in ("qualified", "freeze_performed", "freeze_criterion_met", "image_digest_bound"):
            self.assertIs(report[key], False)
        self.assertIsNone(report["binding_sha256"])
        self.assertIs(report["cases"][0]["freeze_criterion_met"], False)
        self.assertTrue(cases[0]["freeze_criterion_met"])

    def test_discrepancy_stays_visible(self):
        report = provisional.make_report("a", "b", "c", "d", [{"match": True}],
            [{"freeze_criterion_met": False, "all_modelled_channels_match": False}])
        self.assertFalse(report["comparison_criterion_met"])
        self.assertFalse(report["all_three_way_match"])

    def test_probe_failure_stays_visible(self):
        report = provisional.make_report("a", "b", "c", "d", [{"match": False}],
            [{"freeze_criterion_met": True, "all_modelled_channels_match": True}])
        self.assertFalse(report["comparison_criterion_met"])

    def test_unreviewed_request_refuses(self):
        path = ref.ROOT / "spec/reference-provisional/2026-11-15/REQUEST.json"
        request = ref.strict(ref.bounded(path))
        request["inventory_review"] = None
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                patch.object(ref, "bounded", return_value=ref.canonical(request)):
            with self.assertRaisesRegex(ref.Refused, "unbound-inventory_review"):
                provisional.check_inputs(path)

    def test_delivered_reviews_and_pinned_sources_join(self):
        path = ref.ROOT / "spec/reference-provisional/2026-11-15/REQUEST.json"
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            request, row, suite, probes, digest = provisional.check_inputs(path)
        self.assertEqual(len(probes), 9)
        self.assertEqual(len(suite["cases"]), 16)
        self.assertEqual(digest, "8496a8c754b0a179888561be69aa06d4655d15e0c54decb891c757bb190d960d")

    def test_local_execution_refuses_before_read(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), patch.object(ref, "bounded") as read:
            with self.assertRaisesRegex(ref.Refused, "provisional-ci-only"):
                provisional.check_inputs(Path("missing"))
            read.assert_not_called()

    def test_inventory_mismatch_precedes_compile(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fresh"
            def record(path): path.write_bytes(ref.canonical(sample_inventory()) + b"\n")
            with patch.object(provisional, "check_inputs", return_value=({}, {}, {}, [], "0" * 64)), \
                    patch.object(ref, "native"), patch.object(ref, "inventory", side_effect=record), \
                    patch.object(ref, "compile_reference") as compile_:
                with self.assertRaisesRegex(ref.Refused, "provisional-inventory-mismatch"):
                    provisional.compare(Path("request"), output)
                compile_.assert_not_called()

    def test_windows_host_refuses_cleanly(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                patch.object(host.platform, "system", return_value="Windows"), \
                patch.object(host, "call") as docker:
            with self.assertRaisesRegex(ref.Refused, "native-amd64-ci-only"):
                host.execute(Path("request"), "sha256:" + "a" * 64, Path("output"))
            docker.assert_not_called()

    def test_original_probe_rows_unchanged(self):
        original = ref.strict(ref.bounded(ref.ROOT / "spec/reference-execution/2026-11-15/PROBES.json"))["probes"]
        expanded = ref.strict(ref.bounded(ref.ROOT / "spec/reference-provisional/2026-11-15/PROBES.json"))["probes"]
        self.assertEqual(expanded[:7], original)
        self.assertEqual([p["id"] for p in expanded[7:]], list(provisional.NEW_PROBES))
        for p in expanded: ref.joined(ref.ROOT, p["source"])

    def test_qualified_binding_still_requires_image(self):
        raw = ref.bounded(ref.ROOT / "spec/reference-execution/2026-11-15/BINDING.json")
        with self.assertRaisesRegex(ref.Refused, "unbound-image_manifest"):
            ref.binding(raw)


if __name__ == "__main__":
    unittest.main()
