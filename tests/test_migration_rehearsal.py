from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lightyear_common.io import write_json
from lightyear_data.contracts import seal, sign
from lightyear_data.rehearsal import (
    DEVELOPMENT_APPROVAL_KEY,
    RehearsalContractError,
    build_rehearsal_contracts,
    build_rehearsal_evidence,
    run_rehearsal,
    validate_rehearsal_evidence,
)
from lightyear_knowledge_graph.explorer import ExplorerServer


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data-modernization/rehearsal"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resign_approval(root: Path, plan: dict) -> None:
    approval = sign(
        {
            "schema_version": "1.0",
            "approval_type": "factorydark-offline-cutover-approval",
            "plan_sha256": plan["content_sha256"],
            "approved_action": "offline-authfrds-cutover-rehearsal",
            "approver_type": "human",
            "evidence_class": "simulated",
            "production_authorized": False,
            "scope": "exact-development-rehearsal-plan",
        },
        DEVELOPMENT_APPROVAL_KEY,
        "factorydark-development-operator",
    )
    write_json(root / "cutover.approval.json", approval)


class MigrationRehearsalTests(unittest.TestCase):
    def test_committed_rehearsal_is_deterministic_and_valid(self) -> None:
        self.assertEqual([], validate_rehearsal_evidence(ROOT))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rebuilt = build_rehearsal_evidence(ROOT, output)
            for name in ("plan.json", "cutover.approval.json", "checkpoint.json", "receipt.json"):
                self.assertEqual(
                    (CANONICAL / name).read_bytes(),
                    (output / "data-modernization/rehearsal" / name).read_bytes(),
                    name,
                )
        self.assertEqual(load(CANONICAL / "receipt.json"), rebuilt)

    def test_receipt_proves_bounded_resume_cutover_and_exact_rollback(self) -> None:
        receipt = load(CANONICAL / "receipt.json")
        self.assertEqual("passed", receipt["status"])
        self.assertTrue(receipt["development_ready"])
        self.assertFalse(receipt["production_ready"])
        self.assertFalse(receipt["mainframe_equivalent"])
        self.assertTrue(all(receipt["checks"].values()), receipt["checks"])
        self.assertEqual({"events": 5, "inserts": 2, "updates": 2, "deletes": 1}, {
            key: receipt["journal"][key] for key in ("events", "inserts", "updates", "deletes")
        })
        self.assertEqual(1, receipt["recovery"]["resume_count"])
        self.assertEqual(0, receipt["recovery"]["observed_rpo_events"])
        self.assertEqual(3, receipt["recovery"]["observed_rto_steps"])
        self.assertEqual(
            receipt["rollback"]["pre_cutover_state_sha256"],
            receipt["rollback"]["restored_state_sha256"],
        )
        self.assertFalse(receipt["cutover"]["production_authorized"])

    def test_data_control_tower_exposes_rehearsal_without_overclaim(self) -> None:
        summary = ExplorerServer.data_summary(SimpleNamespace(project_root=ROOT))
        rehearsal = summary["operational_rehearsal"]
        self.assertEqual("passed", summary["status"])
        self.assertEqual("offline-development-rehearsal", summary["evidence_class"])
        self.assertEqual(5, rehearsal["events"])
        self.assertEqual(1, rehearsal["resume_count"])
        self.assertTrue(rehearsal["cutover_opened"])
        self.assertTrue(rehearsal["rollback_exact"])
        self.assertFalse(rehearsal["production_authorized"])
        self.assertFalse(summary["production_ready"])

    def test_interruption_checkpoint_resumes_without_reapplying_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_rehearsal_contracts(ROOT, root)
            contract_root = root / "data-modernization/rehearsal"
            stopped = run_rehearsal(ROOT, contract_root, stop_after=2)
            checkpoint = load(contract_root / "checkpoint.json")
            self.assertEqual("interrupted", stopped["status"])
            self.assertEqual(2, checkpoint["last_applied_sequence"])
            self.assertEqual(2, len(checkpoint["applied_event_sha256"]))
            receipt = run_rehearsal(ROOT, contract_root, resume=True)
            self.assertEqual("passed", receipt["status"])
            self.assertEqual(5, receipt["journal"]["last_applied_sequence"])
            self.assertTrue(receipt["recovery"]["duplicate_replay_detected"])
            with self.assertRaisesRegex(RehearsalContractError, "unfinished checkpoint"):
                run_rehearsal(ROOT, contract_root, resume=True)

    def test_gap_reordering_and_before_image_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_rehearsal_contracts(ROOT, root)
            contract_root = root / "data-modernization/rehearsal"
            plan = load(contract_root / "plan.json")
            plan["journal"]["events"][0]["sequence"] = 2
            plan["journal"]["events"][0] = seal(plan["journal"]["events"][0])
            plan = seal(plan)
            write_json(contract_root / "plan.json", plan)
            resign_approval(contract_root, plan)
            with self.assertRaisesRegex(RehearsalContractError, "not contiguous"):
                run_rehearsal(ROOT, contract_root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_rehearsal_contracts(ROOT, root)
            contract_root = root / "data-modernization/rehearsal"
            plan = load(contract_root / "plan.json")
            final_event = plan["journal"]["events"][-1]
            final_event["before_sha256"] = "f" * 64
            final_event = seal(final_event)
            plan["journal"]["events"][-1] = final_event
            plan["journal"]["head_sha256"] = final_event["content_sha256"]
            plan = seal(plan)
            write_json(contract_root / "plan.json", plan)
            resign_approval(contract_root, plan)
            run_rehearsal(ROOT, contract_root, stop_after=2)
            with self.assertRaisesRegex(RehearsalContractError, "before-image"):
                run_rehearsal(ROOT, contract_root, resume=True)

    def test_checkpoint_tamper_fails_even_when_outer_hash_is_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_rehearsal_contracts(ROOT, root)
            contract_root = root / "data-modernization/rehearsal"
            run_rehearsal(ROOT, contract_root, stop_after=2)
            checkpoint = load(contract_root / "checkpoint.json")
            checkpoint["source"]["rows"][0]["AUTH_FRAUD"] = "X"
            checkpoint = seal(checkpoint)
            write_json(contract_root / "checkpoint.json", checkpoint)
            with self.assertRaisesRegex(RehearsalContractError, "source state hash"):
                run_rehearsal(ROOT, contract_root, resume=True)

    def test_approval_cannot_authorize_production_or_another_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, approval = build_rehearsal_contracts(ROOT, root)
            contract_root = root / "data-modernization/rehearsal"
            approval["production_authorized"] = True
            approval = sign(
                approval,
                DEVELOPMENT_APPROVAL_KEY,
                "factorydark-development-operator",
            )
            write_json(contract_root / "cutover.approval.json", approval)
            with self.assertRaisesRegex(RehearsalContractError, "overstated"):
                run_rehearsal(ROOT, contract_root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_rehearsal_contracts(ROOT, root)
            contract_root = root / "data-modernization/rehearsal"
            approval = load(contract_root / "cutover.approval.json")
            approval["plan_sha256"] = "0" * 64
            approval = sign(
                approval,
                DEVELOPMENT_APPROVAL_KEY,
                "factorydark-development-operator",
            )
            write_json(contract_root / "cutover.approval.json", approval)
            with self.assertRaisesRegex(RehearsalContractError, "foreign"):
                run_rehearsal(ROOT, contract_root)

    def test_stale_target_mapping_and_unsupported_fault_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "data-modernization", root / "data-modernization")
            for name in ("checkpoint.json", "receipt.json"):
                path = root / "data-modernization/rehearsal" / name
                if path.exists():
                    path.unlink()
            mapping_path = root / "data-modernization/mappings/authfrds-postgresql.json"
            mapping = load(mapping_path)
            mapping["columns"][0]["target"] = "foreign_card_num"
            write_json(mapping_path, seal(mapping))
            with self.assertRaisesRegex(RehearsalContractError, "stale data bindings"):
                run_rehearsal(root, root / "data-modernization/rehearsal")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_rehearsal_contracts(ROOT, root)
            contract_root = root / "data-modernization/rehearsal"
            plan = load(contract_root / "plan.json")
            plan["cutover_policy"]["post_cutover_failure"]["fault"] = "silently-ignore-failure"
            plan = seal(plan)
            write_json(contract_root / "plan.json", plan)
            resign_approval(contract_root, plan)
            run_rehearsal(ROOT, contract_root, stop_after=2)
            with self.assertRaisesRegex(RehearsalContractError, "Unsupported post-cutover"):
                run_rehearsal(ROOT, contract_root, resume=True)

    def test_receipt_tamper_and_live_overclaim_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "data-modernization", root / "data-modernization")
            receipt_path = root / "data-modernization/rehearsal/receipt.json"
            receipt = load(receipt_path)
            receipt["checks"]["rollback_exact"] = False
            write_json(receipt_path, seal(receipt))
            self.assertIn("rehearsal-receipt-invalid", validate_rehearsal_evidence(root))

            receipt = load(CANONICAL / "receipt.json")
            receipt["mainframe_equivalent"] = True
            receipt["production_ready"] = True
            write_json(receipt_path, seal(receipt))
            self.assertIn("rehearsal-receipt-invalid", validate_rehearsal_evidence(root))

    def test_rehearsal_schemas_are_versioned(self) -> None:
        for name in (
            "migration-rehearsal-plan.schema.json",
            "cutover-approval.schema.json",
            "migration-rehearsal-checkpoint.schema.json",
            "migration-rehearsal-receipt.schema.json",
        ):
            schema = load(ROOT / "data-modernization/schema" / name)
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertRegex(schema["$id"], r"-1\.0\.json$")


if __name__ == "__main__":
    unittest.main()
