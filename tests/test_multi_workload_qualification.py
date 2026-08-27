from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.agents import LocalAgentSet
from lightyear_factory.evals import (
    EvaluationPolicy,
    load_evaluation_catalog,
    run_model_evaluation,
    validate_evaluation_catalog,
)
from lightyear_factory.portfolio import (
    PortfolioManifest,
    PortfolioRunner,
    plan_portfolio,
    sign_portfolio_approval,
    verify_portfolio_approval,
)
from lightyear_factory.qualification import QualificationManifest, qualify_factory


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "knowledge/graph.snapshot.json.gz"
PORTFOLIO = ROOT / "factory/portfolio/carddemo-portfolio.json"
QUALIFICATION = ROOT / "factory/qualification/manifest.json"
KEY = b"qualification-test-key-material" * 2


def hashed(payload: dict) -> dict:
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def model_call(sequence: int) -> dict:
    content = hashed(
        {
            "schema_version": "1.0",
            "evidence_type": "lightyear-model-call",
            "provider": "openai-responses",
            "model": "qualification-model",
            "role": "builder",
            "request_manifest": {
                "instruction_sha256": f"{sequence:064x}"[-64:],
                "payload_sha256": f"{sequence + 1:064x}"[-64:],
                "schema_sha256": f"{sequence + 2:064x}"[-64:],
            },
            "input_tokens": 100,
            "output_tokens": 20,
            "estimated_cost_usd": 0.01,
            "cost_estimate_available": True,
            "elapsed_ms": 50,
        }
    )
    return hashed(
        {
            "schema_version": "1.0",
            "artifact_type": "model-call-evidence",
            "run_id": f"run-{sequence}",
            "sequence": 1,
            "role": "builder",
            "visibility": "implementer",
            "content": content,
        }
    )


def evaluation_root(root: Path, workload: str, run_number: int) -> Path:
    evaluation = root / f"{workload.lower()}-{run_number}"
    results = []
    for case_index, expectation in enumerate(("reject-and-repair", "accept-unchanged"), 1):
        run_id = f"run-{workload.lower()}-{run_number}-{case_index}"
        run_dir = evaluation / "runs" / run_id
        artifact_dir = run_dir / "artifacts"
        artifact_dir.mkdir(parents=True)
        artifact = model_call(run_number * 10 + case_index)
        artifact["run_id"] = run_id
        artifact["content_sha256"] = canonical_hash(artifact, {"content_sha256"})
        artifact_path = artifact_dir / "0001-model-call-evidence.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        intelligence = hashed(
            {
                "mode": "model-backed",
                "provider": "openai-responses",
                "model": "qualification-model",
                "calls": 1,
                "provider_attempts": 1,
                "provider_retries": 0,
                "input_bytes": 1000,
                "output_bytes": 200,
                "input_tokens": 100,
                "output_tokens": 20,
                "estimated_cost_usd": 0.01,
                "cost_estimate_available": True,
                "elapsed_ms": 50,
                "call_evidence_sha256": [artifact["content_sha256"]],
                "budgets": {},
            }
        )
        run_receipt = hashed(
            {
                "schema_version": "1.0",
                "receipt_type": "lightyear-autonomous-factory-run",
                "run_id": run_id,
                "status": "passed",
                "attempts": 1 if expectation == "reject-and-repair" else 0,
                "artifacts": [
                    {
                        "artifact_type": "model-call-evidence",
                        "content_sha256": artifact["content_sha256"],
                        "path": "artifacts/0001-model-call-evidence.json",
                        "role": "builder",
                        "visibility": "implementer",
                    }
                ],
                "intelligence": intelligence,
            }
        )
        (run_dir / "receipt.json").write_text(json.dumps(run_receipt), encoding="utf-8")
        results.append(
            {
                "case_ref": f"case-{workload.lower()}-{run_number}-{case_index}",
                "expectation": expectation,
                "status": "passed",
                "attempts": run_receipt["attempts"],
                "baseline_rejected": expectation == "reject-and-repair",
                "autonomously_repaired": expectation == "reject-and-repair",
                "correct_no_change": expectation == "accept-unchanged",
                "false_acceptance": False,
                "first_attempt_repair": expectation == "reject-and-repair",
                "private_evidence_leaks": 0,
                "unauthorized_edit_attempts": 0,
                "model_calls": 1,
                "provider_attempts": 1,
                "provider_retries": 0,
                "input_tokens": 100,
                "output_tokens": 20,
                "estimated_cost_usd": 0.01,
                "cost_estimate_available": True,
                "elapsed_ms": 50,
                "receipt_sha256": run_receipt["content_sha256"],
            }
        )
    binding = hashed(
        {
            "schema_version": "1.0",
            "binding_type": "lightyear-sealed-evaluation-binding",
            "issuer": "independent-evaluator",
            "key_id": "holdout",
            "issued_at": "2026-08-27T00:00:00Z",
            "expires_at": "2026-08-28T00:00:00Z",
            "catalog_sha256": f"{run_number:064x}"[-64:],
            "envelope_sha256": f"{run_number + 100:064x}"[-64:],
            "signature_valid": True,
        }
    )
    quality = hashed(
        {
            "schema_version": "1.0",
            "decision_type": "lightyear-factory-quality-gate",
            "status": "qualified",
        }
    )
    receipt = hashed(
        {
            "schema_version": "2.0",
            "receipt_type": "lightyear-model-workcell-evaluation",
            "evaluation_id": f"sealed:{workload.lower()}-{run_number}",
            "evaluation_class": "sealed-holdout",
            "workload_id": workload,
            "catalog_sha256": binding["catalog_sha256"],
            "catalog_validation_sha256": f"{run_number + 200:064x}"[-64:],
            "planned_cases": 2,
            "completed_cases": 2,
            "cases": 2,
            "mutation_cases": 1,
            "clean_cases": 1,
            "baselines_rejected": 1,
            "autonomously_repaired": 1,
            "repair_rate": 1.0,
            "correct_no_changes": 1,
            "correct_no_change_rate": 1.0,
            "minimum_repair_rate": 0.8,
            "false_acceptances": 0,
            "status": "passed",
            "stopped_reason": None,
            "resume_count": run_number - 1,
            "policy": {},
            "quality_gate": quality,
            "sealed_binding": binding,
            "results": results,
            "totals": {
                "model_calls": 2,
                "provider_attempts": 2,
                "provider_retries": 0,
                "input_tokens": 200,
                "output_tokens": 40,
                "estimated_cost_usd": 0.02,
                "cost_estimate_available": True,
            },
            "limitations": [],
        }
    )
    path = evaluation / "evaluation.receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


class MultiWorkloadQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = QualificationManifest.load(QUALIFICATION)
        self.portfolio = PortfolioManifest.load(PORTFOLIO)
        self.plan, self.orders = plan_portfolio(self.portfolio, ROOT, GRAPH)

    def test_all_four_calibration_catalogs_are_bound_to_trusted_profiles(self) -> None:
        for name, workload in (
            ("intcalc-v0.26-public.json", "INTCALC"),
            ("posttran-v0.26-public.json", "POSTTRAN"),
            ("creastmt-v0.26-public.json", "CREASTMT"),
            ("acctpl1-v0.26-public.json", "ACCTPL1"),
        ):
            catalog = load_evaluation_catalog(ROOT / "factory/evals" / name)
            validation = validate_evaluation_catalog(ROOT, catalog)
            self.assertEqual(workload, validation["workload_id"])
            self.assertEqual("passed", validation["status"])
            self.assertGreaterEqual(validation["cases"], 7)

    def test_all_four_local_calibrations_repair_mutations_without_false_acceptance(self) -> None:
        for name in (
            "intcalc-v0.26-public.json",
            "posttran-v0.26-public.json",
            "creastmt-v0.26-public.json",
            "acctpl1-v0.26-public.json",
        ):
            with self.subTest(catalog=name), tempfile.TemporaryDirectory() as directory:
                receipt = run_model_evaluation(
                    ROOT,
                    Path(directory),
                    ROOT / "factory/evals" / name,
                    lambda _: LocalAgentSet(),
                    policy=EvaluationPolicy(pace_seconds=0),
                    sleep=lambda _: None,
                )
                self.assertEqual("passed", receipt["status"])
                self.assertEqual(receipt["mutation_cases"], receipt["autonomously_repaired"])
                self.assertEqual(receipt["clean_cases"], receipt["correct_no_changes"])
                self.assertEqual(0, receipt["false_acceptances"])

    def test_qualification_requires_repeated_sealed_model_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [
                evaluation_root(root, workload, run_number)
                for workload in self.manifest.required_workloads
                for run_number in (1, 2)
            ]
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
            cells = [
                {
                    "wave": 1,
                    "work_order_id": item["id"],
                    "status": "passed",
                    "run_id": item["id"],
                    "receipt_sha256": "a" * 64,
                }
                for item in self.plan["orders"]
            ]
            portfolio_run = hashed(
                {
                    "schema_version": "1.0",
                    "receipt_type": "lightyear-modernization-portfolio-run",
                    "portfolio_id": self.plan["portfolio_id"],
                    "plan_sha256": self.plan["content_sha256"],
                    "admission_sha256": "b" * 64,
                    "status": "passed",
                    "resume_count": 1,
                    "checkpoint_sha256": "c" * 64,
                    "cells": cells,
                }
            )
            run_path = root / "portfolio-run.json"
            run_path.write_text(json.dumps(portfolio_run), encoding="utf-8")
            receipt = qualify_factory(self.manifest, inputs, plan_path, run_path)
            self.assertEqual("qualified", receipt["status"])
            self.assertTrue(receipt["promotion_allowed"])
            self.assertEqual(8, receipt["metrics"]["evaluation_runs"])
            self.assertEqual(0, receipt["metrics"]["false_acceptances"])
            self.assertFalse(receipt["mainframe_equivalent"])

            unsafe_path = inputs[0]
            unsafe = json.loads(unsafe_path.read_text())
            unsafe["results"][0]["false_acceptance"] = True
            unsafe["false_acceptances"] = 1
            unsafe["content_sha256"] = canonical_hash(unsafe, {"content_sha256"})
            unsafe_path.write_text(json.dumps(unsafe), encoding="utf-8")
            blocked = qualify_factory(self.manifest, inputs, plan_path, run_path)
            self.assertEqual("blocked", blocked["status"])
            self.assertFalse(blocked["promotion_allowed"])

            unsafe["results"][0]["input_tokens"] = 999
            unsafe["content_sha256"] = canonical_hash(unsafe, {"content_sha256"})
            unsafe_path.write_text(json.dumps(unsafe), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "disagrees with model provenance"):
                qualify_factory(self.manifest, inputs, plan_path, run_path)

    def test_portfolio_checkpoint_resumes_without_repeating_passed_cells(self) -> None:
        now = datetime.now(timezone.utc)
        envelope = sign_portfolio_approval(
            self.plan, KEY, approver_id="human", key_id="portfolio", issued_at=now
        )
        admission = verify_portfolio_approval(
            self.plan, envelope, {"portfolio": KEY}, now=now
        )
        calls: list[str] = []

        def first(order, run_id):
            calls.append(order.order_id)
            receipt = {
                "status": "blocked" if "posttran" in order.order_id else "passed",
                "run_id": run_id,
            }
            receipt["content_sha256"] = canonical_hash(receipt)
            return receipt

        def recovered(order, run_id):
            calls.append(order.order_id)
            receipt = {"status": "passed", "run_id": run_id}
            receipt["content_sha256"] = canonical_hash(receipt)
            return receipt

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked = PortfolioRunner(first).run(
                self.plan, self.orders, root, admission
            )
            resumed = PortfolioRunner(recovered).run(
                self.plan, self.orders, root, admission, resume=True
            )
        self.assertEqual("blocked", blocked["status"])
        self.assertEqual("passed", resumed["status"])
        self.assertEqual(1, resumed["resume_count"])
        self.assertEqual(1, calls.count("carddemo:acctpl1:portfolio-cell"))
        self.assertEqual(2, calls.count("carddemo:posttran:portfolio-cell"))

    def test_qualification_schemas_are_versioned(self) -> None:
        for name in (
            "qualification-manifest.schema.json",
            "multi-workload-qualification.schema.json",
            "portfolio-checkpoint.schema.json",
        ):
            schema = json.loads((ROOT / "factory/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
