"""CI-only coverage for immutable MS70 records and explicit binding projections."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import lightyear_data.idempiere_triage as triage
from lightyear_data.contracts import seal


ROOT = Path(__file__).resolve().parents[1]
RECORD = triage.ROOT_PATH / "stage3-retained-rebinding-2026-10-27.json"
PATHS = (
    triage.POLICY_PATH, triage.WORK_PACKAGE_PATH, triage.CALIBRATION_PATH,
    triage.COVERAGE_PATH, triage.DIVERGENCE_PATH, triage.INDETERMINATE_PATH,
    triage.PROVENANCE_PATH, triage.RECEIPT_PATH,
)


class RetainedRebindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.actual = {
            p.name: json.loads((ROOT / p).read_text(encoding="utf-8"))
            for p in PATHS
        }
        cls.expected = triage.build_stage3_artifacts(ROOT)
        cls.record = json.loads((ROOT / RECORD).read_text(encoding="utf-8"))

    def test_current_projection_preserves_every_retained_byte_and_payload(self) -> None:
        before = {str(p): hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PATHS}
        actual_before = copy.deepcopy(self.actual)
        projected = triage._retained_stage3_projection(ROOT, self.actual, self.expected)
        self.assertEqual(self.expected, projected)
        self.assertEqual(actual_before, self.actual)
        self.assertEqual(before, {
            str(p): hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PATHS
        })
        for name, original in self.actual.items():
            self.assertEqual(
                {k: v for k, v in original.items() if k not in ("bindings", "content_sha256")},
                {k: v for k, v in projected[name].items() if k not in ("bindings", "content_sha256")},
            )

    def test_resealed_caller_claim_tampering_is_not_projected_away(self) -> None:
        actual = copy.deepcopy(self.actual)
        name = triage.RECEIPT_PATH.name
        actual[name]["claims"]["audit_complete"] = True
        actual[name] = seal(actual[name])
        projected = triage._retained_stage3_projection(ROOT, actual, self.expected)
        self.assertEqual(actual[name], projected[name])
        self.assertNotEqual(self.expected[name], projected[name])
        self.assertIn("stage3-artifact-drift:" + name,
                      triage.validate_stage3_artifacts(ROOT, artifacts=actual))

    def test_resealed_record_drift_is_refused(self) -> None:
        mutations = []
        wrong_source = copy.deepcopy(self.record)
        wrong_source["implementation_logical_sha256"]["src/lightyear_factory/providers.py"] = "0" * 64
        mutations.append(wrong_source)
        wrong_original = copy.deepcopy(self.record)
        wrong_original["original_artifacts"][triage.RECEIPT_PATH.name]["logical_sha256"] = "0" * 64
        mutations.append(wrong_original)
        wrong_projection = copy.deepcopy(self.record)
        wrong_projection["projected_content_sha256"][triage.RECEIPT_PATH.name] = "0" * 64
        mutations.append(wrong_projection)
        claimed_execution = copy.deepcopy(self.record)
        claimed_execution["new_execution"] = True
        mutations.append(claimed_execution)
        read = triage._read
        for changed in mutations:
            with self.subTest(record=changed):
                def read_changed(path: Path):
                    return seal(changed) if path == ROOT / RECORD else read(path)
                with patch.object(triage, "_read", side_effect=read_changed):
                    with self.assertRaises(ValueError):
                        triage._retained_stage3_projection(ROOT, self.actual, self.expected)

    def test_resealed_retained_record_tampering_is_refused(self) -> None:
        name = triage.RECEIPT_PATH.name
        changed = copy.deepcopy(self.actual[name])
        changed["statistics"]["model_calls"] = 1
        changed = seal(changed)
        read = triage._read
        def read_changed(path: Path):
            return changed if path == ROOT / triage.RECEIPT_PATH else read(path)
        with patch.object(triage, "_read", side_effect=read_changed):
            with self.assertRaises(ValueError):
                triage._retained_stage3_projection(ROOT, self.actual, self.expected)
