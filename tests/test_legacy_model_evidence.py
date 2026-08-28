from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.legacy_evidence import verify_legacy_model_archive
from lightyear_factory.store import EvaluationStore


ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / "factory/qualification/history/v0.12-live-smoke.manifest.json"


def hashed(payload: dict) -> dict:
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def artifact(
    run_id: str,
    sequence: int,
    artifact_type: str,
    role: str,
    visibility: str,
    content: dict,
) -> dict:
    return hashed(
        {
            "schema_version": "1.0",
            "artifact_type": artifact_type,
            "run_id": run_id,
            "sequence": sequence,
            "role": role,
            "visibility": visibility,
            "content": content,
        }
    )


def build_legacy_archive(
    root: Path,
    *,
    evaluation_class: str = "public-calibration",
    raw_request: bool = False,
    nested_raw_request: bool = False,
    tamper_artifact: bool = False,
) -> tuple[Path, Path]:
    archive_root = root / "source" / "model-evaluation-test"
    run_id = "eval-category-balance-length"
    run_dir = archive_root / "runs" / run_id
    relative = "factory/benchmarks/intcalc_candidate.py"
    before = b"CATEGORY_BALANCE_LENGTH = 49\n"
    after = b"CATEGORY_BALANCE_LENGTH = 50\n"
    workspace = run_dir / "workspace" / relative
    workspace.parent.mkdir(parents=True)
    workspace.write_bytes(after)
    seed = archive_root / "seed" / relative
    seed.parent.mkdir(parents=True)
    seed.write_bytes(after)
    work_order = {
        "schema_version": "1.0",
        "id": "evaluation:carddemo:category-balance-length",
        "title": "Repair layout regression",
        "goal": "Restore the 50-byte record contract.",
        "non_goals": ["Do not access private verifier content."],
        "scope": {
            "allowed_paths": [relative],
            "graph_node_ids": ["workload:carddemo-intcalc"],
        },
        "acceptance": {
            "baseline_first": True,
            "max_attempts": 3,
            "gates": [
                {
                    "id": "private-carddemo-policy",
                    "command": ["python3", "-m", "lightyear_factory.private_benchmark"],
                    "timeout_seconds": 30,
                    "expose_output_to_builder": False,
                }
            ],
        },
        "policy": {
            "audience": "implementer",
            "allow_network": False,
            "max_files_changed": 1,
            "max_patch_bytes": 8192,
            "max_changed_lines": 80,
            "max_context_bytes": 200000,
            "max_file_bytes": 250000,
            "max_model_calls": 10,
            "max_model_input_bytes": 2000000,
            "max_model_output_bytes": 500000,
            "max_model_tokens": 250000,
            "max_model_cost_usd": 25.0,
            "max_elapsed_seconds": 1800,
        },
        "metadata": {
            "evaluation_case_id": "category-balance-length",
            "evaluation_category": "copybook-layout",
        },
    }
    write_json(run_dir / "work-order.json", work_order)
    call_content = hashed(
        {
            "schema_version": "1.0",
            "evidence_type": "lightyear-model-call",
            "provider": "openai-responses",
            "model": "test-live-model",
            "role": "builder",
            "call_sequence": 1,
            "request_sha256": "1" * 64,
            "response_sha256": "2" * 64,
            "request_bytes": 100,
            "response_bytes": 20,
            "input_tokens": 50,
            "output_tokens": 10,
            "estimated_cost_usd": 0.01,
            "cost_estimate_available": True,
            "elapsed_ms": 25,
            "store": False,
            "strict_schema": True,
            **({"request": "raw secret payload"} if raw_request else {}),
            **({"metadata": {"request": "nested raw payload"}} if nested_raw_request else {}),
        }
    )
    artifacts = [
        artifact(run_id, 1, "model-call-evidence", "builder", "implementer", call_content),
        artifact(
            run_id,
            2,
            "verification-report",
            "controller",
            "verifier_private",
            {"status": "failed", "gates": []},
        ),
        artifact(
            run_id,
            3,
            "build-proposal",
            "builder",
            "implementer",
            {
                "summary": "Correct the fixed-width value.",
                "blocked_reason": None,
                "edits": [
                    {
                        "path": relative,
                        "find": "CATEGORY_BALANCE_LENGTH = 49",
                        "replace": "CATEGORY_BALANCE_LENGTH = 50",
                        "rationale": "The pinned record length is 50.",
                    }
                ],
            },
        ),
        artifact(
            run_id,
            4,
            "change-set",
            "controller",
            "implementer",
            hashed(
                {
                    "broker": "lightyear-constrained-patch-broker",
                    "files_changed": 1,
                    "changed_lines": 2,
                    "patch_bytes": 56,
                    "changes": [
                        {
                            "path": relative,
                            "before_sha256": hashlib.sha256(before).hexdigest(),
                            "after_sha256": hashlib.sha256(after).hexdigest(),
                            "diff_sha256": "3" * 64,
                            "changed_lines": 2,
                            "rationales": ["The pinned record length is 50."],
                        }
                    ],
                }
            ),
        ),
        artifact(
            run_id,
            5,
            "verification-report",
            "controller",
            "verifier_private",
            {"status": "passed", "gates": []},
        ),
    ]
    references = []
    for index, payload in enumerate(artifacts, 1):
        name = f"{index:04d}-{payload['artifact_type']}.json"
        if tamper_artifact and payload["artifact_type"] == "model-call-evidence":
            payload["content"]["input_tokens"] = 999
        write_json(run_dir / "artifacts" / name, payload)
        references.append(
            {
                "artifact_type": payload["artifact_type"],
                "content_sha256": payload["content_sha256"],
                "path": f"artifacts/{name}",
                "role": payload["role"],
                "visibility": payload["visibility"],
            }
        )
    event = {
        "sequence": 1,
        "occurred_at": "2026-08-13T07:26:24+00:00",
        "previous_sha256": None,
        "state": "VERIFIED",
        "kind": "acceptance_gates_passed",
        "payload": {"status": "passed"},
    }
    event["event_sha256"] = canonical_hash(event)
    (run_dir / "events.jsonl").write_text(
        json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    intelligence = hashed(
        {
            "mode": "model-backed",
            "provider": "openai-responses",
            "model": "test-live-model",
            "calls": 1,
            "input_bytes": 100,
            "output_bytes": 20,
            "input_tokens": 50,
            "output_tokens": 10,
            "estimated_cost_usd": 0.01,
            "cost_estimate_available": True,
            "elapsed_ms": 25,
            "call_evidence_sha256": [call_content["content_sha256"]],
            "budgets": {},
        }
    )
    run_receipt = hashed(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-autonomous-factory-run",
            "run_id": run_id,
            "work_order_id": work_order["id"],
            "work_order_sha256": canonical_hash(work_order),
            "status": "passed",
            "attempts": 1,
            "changed_paths": [relative],
            "started_at": "2026-08-13T07:26:24+00:00",
            "completed_at": "2026-08-13T07:26:35+00:00",
            "initial_snapshot_sha256": canonical_hash(
                {relative: hashlib.sha256(before).hexdigest()}
            ),
            "final_snapshot_sha256": canonical_hash(
                {relative: hashlib.sha256(after).hexdigest()}
            ),
            "event_count": 1,
            "ledger_head_sha256": event["event_sha256"],
            "artifacts": references,
            "intelligence": intelligence,
            "verification": {"status": "passed", "gates": []},
            "execution_security": {
                "status": "advisory",
                "backend": "host-process",
                "production_ready": False,
                "secrets_persisted": False,
                "gaps": ["hardened-execution-not-configured"],
            },
            "limitations": [],
        }
    )
    write_json(run_dir / "receipt.json", run_receipt)
    result = {
        "case_id": "category-balance-length",
        "category": "copybook-layout",
        "status": "passed",
        "attempts": 1,
        "baseline_rejected": True,
        "autonomously_repaired": True,
        "false_acceptance": False,
        "model_calls": 1,
        "input_tokens": 50,
        "output_tokens": 10,
        "estimated_cost_usd": 0.01,
        "cost_estimate_available": True,
        "receipt_sha256": run_receipt["content_sha256"],
    }
    evaluation = hashed(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-model-workcell-evaluation",
            "evaluation_id": "legacy-test-smoke",
            "evaluation_class": evaluation_class,
            "catalog_sha256": "4" * 64,
            "catalog_validation_sha256": "5" * 64,
            "cases": 1,
            "categories": {"copybook-layout": 1},
            "baselines_rejected": 1,
            "autonomously_repaired": 1,
            "repair_rate": 1.0,
            "minimum_repair_rate": 1.0,
            "false_acceptances": 0,
            "status": "passed",
            "results": [result],
            "totals": {
                "model_calls": 1,
                "input_tokens": 50,
                "output_tokens": 10,
                "estimated_cost_usd": 0.01,
                "cost_estimate_available": True,
            },
            "limitations": [],
        }
    )
    write_json(archive_root / "evaluation.receipt.json", evaluation)
    archive = root / "legacy.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(archive_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(archive_root.parent).as_posix())
    manifest = {
        "schema_version": "1.0",
        "manifest_type": "lightyear-historical-model-evidence-manifest",
        "evidence_id": "legacy:test:smoke",
        "source_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "evaluation_receipt_sha256": evaluation["content_sha256"],
        "expected": {
            "evaluation_id": "legacy-test-smoke",
            "evaluation_class": evaluation_class,
            "workload_id": "INTCALC",
            "provider": "openai-responses",
            "model": "test-live-model",
            "cases": 1,
            "model_calls": 1,
            "input_tokens": 50,
            "output_tokens": 10,
            "estimated_cost_usd": 0.01,
            "cost_estimate_available": True,
        },
        "current_policy": {
            "maximum_average_input_tokens": 75_000,
            "minimum_runs_per_workload": 2,
            "required_workloads": 4,
        },
        "qualification_eligible": False,
    }
    manifest["content_sha256"] = canonical_hash(manifest)
    manifest_path = root / "manifest.json"
    write_json(manifest_path, manifest)
    return archive, manifest_path


class LegacyModelEvidenceTests(unittest.TestCase):
    def test_recovered_manifest_is_pinned_and_non_promoting(self) -> None:
        manifest = json.loads(PINNED.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["content_sha256"], canonical_hash(manifest, {"content_sha256"})
        )
        self.assertEqual("gpt-5.6-terra", manifest["expected"]["model"])
        self.assertEqual(101127, manifest["expected"]["input_tokens"])
        self.assertFalse(manifest["qualification_eligible"])

    def test_valid_legacy_archive_emits_visible_non_promoting_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, manifest = build_legacy_archive(root)
            output = root / "work/history/historical-model-evidence.receipt.json"
            receipt = verify_legacy_model_archive(archive, manifest, output)
            store = EvaluationStore(root / "work")
            rows = store.list_evaluations()
            detail = store.evaluation(rows[0]["evaluation_key"])
        self.assertEqual("verified", receipt["status"])
        self.assertEqual("historical-only", receipt["quality_gate"]["status"])
        self.assertFalse(receipt["qualification_eligible"])
        self.assertFalse(receipt["promotion_allowed"])
        self.assertTrue(all(receipt["integrity"].values()))
        self.assertFalse(receipt["quality_gate"]["checks"]["sealed_evidence"])
        self.assertEqual("historical-only", rows[0]["quality_status"])
        self.assertEqual(receipt["evidence_id"], detail["evidence_id"])

    def test_tampered_model_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive, manifest = build_legacy_archive(
                Path(directory), tamper_artifact=True
            )
            with self.assertRaisesRegex(ContractError, "content hash"):
                verify_legacy_model_archive(archive, manifest)

    def test_raw_model_payload_fails_closed_even_when_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive, manifest = build_legacy_archive(Path(directory), raw_request=True)
            with self.assertRaisesRegex(ContractError, "raw model request"):
                verify_legacy_model_archive(archive, manifest)

        with tempfile.TemporaryDirectory() as directory:
            archive, manifest = build_legacy_archive(
                Path(directory), nested_raw_request=True
            )
            with self.assertRaisesRegex(ContractError, "raw model request"):
                verify_legacy_model_archive(archive, manifest)

    def test_legacy_sealed_label_cannot_gain_qualification_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive, manifest = build_legacy_archive(
                Path(directory), evaluation_class="sealed-holdout"
            )
            with self.assertRaisesRegex(ContractError, "public calibration only"):
                verify_legacy_model_archive(archive, manifest)

    def test_archive_path_traversal_and_manifest_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unsafe = root / "unsafe.zip"
            with zipfile.ZipFile(unsafe, "w") as bundle:
                bundle.writestr("../evaluation.receipt.json", "{}")
            manifest = {
                "schema_version": "1.0",
                "manifest_type": "lightyear-historical-model-evidence-manifest",
                "evidence_id": "unsafe",
                "source_archive_sha256": hashlib.sha256(unsafe.read_bytes()).hexdigest(),
                "evaluation_receipt_sha256": "0" * 64,
                "expected": {},
                "current_policy": {},
                "qualification_eligible": False,
            }
            manifest["content_sha256"] = canonical_hash(manifest)
            manifest_path = root / "unsafe-manifest.json"
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ContractError, "Unsafe legacy evidence archive"):
                verify_legacy_model_archive(unsafe, manifest_path)

            archive, good_manifest = build_legacy_archive(root / "drift")
            payload = json.loads(good_manifest.read_text(encoding="utf-8"))
            payload["source_archive_sha256"] = "f" * 64
            payload["content_sha256"] = canonical_hash(payload, {"content_sha256"})
            write_json(good_manifest, payload)
            with self.assertRaisesRegex(ContractError, "archive identity"):
                verify_legacy_model_archive(archive, good_manifest)

    def test_historical_evidence_schemas_are_versioned(self) -> None:
        for name in (
            "historical-model-evidence-manifest.schema.json",
            "historical-model-evidence.schema.json",
        ):
            schema = json.loads((ROOT / "factory/schema" / name).read_text())
            self.assertEqual(
                "https://json-schema.org/draft/2020-12/schema", schema["$schema"]
            )
            self.assertRegex(schema["$id"], r"-1\.0\.json$")


if __name__ == "__main__":
    unittest.main()
