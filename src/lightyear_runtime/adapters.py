from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from carddemo_oracle.demo import create_demo_inputs
from carddemo_oracle.oracle import run_directory

from .contracts import CaptureBundle


class RuntimeAdapter(Protocol):
    """Boundary implemented by local, replay, and future z/OS collectors."""

    def capture(self) -> CaptureBundle: ...


class FixtureAdapter:
    def __init__(self, path: Path) -> None:
        self.path = path

    def capture(self) -> CaptureBundle:
        return CaptureBundle.from_dict(json.loads(self.path.read_text(encoding="utf-8")))


class LocalOracleAdapter:
    """Executes the local oracle and converts its receipt into graph-addressed evidence."""

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir

    def capture(self) -> CaptureBundle:
        input_dir = self.work_dir / "input"
        output_dir = self.work_dir / "oracle-output"
        create_demo_inputs(input_dir)
        receipt = run_directory(
            input_dir,
            output_dir,
            "2022071800",
            "2022-07-18-00.00.00.000000",
            "source-faithful",
        )
        observations = receipt["observations"]
        artifacts = []
        for role, values in sorted((receipt.get("inputs", {}) | receipt.get("outputs", {})).items()):
            artifact: dict[str, Any] = {"role": role, "sha256": values["sha256"]}
            if "records" in values:
                artifact["records"] = values["records"]
            artifacts.append(artifact)
        payload = {
            "run_id": "local-oracle-intcalc-reference",
            "adapter_id": "lightyear.local-oracle.v1",
            "source_system": "carddemo-source-faithful-local-oracle",
            "captured_at": "2022-07-18T00:00:00Z",
            "evidence_class": "local_observed",
            "required_nodes": [
                "workload:carddemo-intcalc",
                "rule:intcalc:monthly-interest",
                "rule:intcalc:default-rate",
                "rule:intcalc:source-final-account",
            ],
            "required_edges": [],
            "artifacts": artifacts,
            "limitations": receipt["limitations"],
            "observations": [
                _observation("workload:carddemo-intcalc", "workload_executed", observations),
                _observation(
                    "modern:file:src/carddemo_oracle/oracle.py",
                    "oracle_executed",
                    {"receipt_sha256": _receipt_identity(receipt)},
                ),
                _observation(
                    "rule:intcalc:monthly-interest",
                    "business_rule_exercised",
                    {"transactions_created": observations["transactions_created"]},
                ),
                _observation(
                    "rule:intcalc:default-rate",
                    "fallback_path_exercised",
                    {"default_rates_used": observations["default_rates_used"]},
                ),
                _observation(
                    "rule:intcalc:source-final-account",
                    "source_behavior_exercised",
                    {
                        "final_account_policy": observations["final_account_policy"],
                        "known_behavior": observations["known_behavior"],
                    },
                ),
            ],
        }
        return CaptureBundle.from_dict(payload)


def _observation(entity_id: str, operation: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_kind": "node",
        "entity_id": entity_id,
        "assertion": "observed",
        "operation": operation,
        "details": details,
    }


def _receipt_identity(receipt: dict[str, Any]) -> str:
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
