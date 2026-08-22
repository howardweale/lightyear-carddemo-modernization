from __future__ import annotations

import unittest

from lightyear_factory.benchmark import benchmark_work_order
from lightyear_factory.contracts import ContractError, GateContract, WorkOrder
from lightyear_factory.gates import builder_failure_view


PRIVATE_SENTINEL = "PRIVATE-HOLDOUT-ANSWER-9F4C"


def gate_result(gate_id: str, expose: object = False) -> dict[str, object]:
    return {
        "id": gate_id,
        "status": "failed",
        "exit_code": 1,
        "timed_out": False,
        "duration_ms": 19,
        "command": ["python", "private_gate.py"],
        "stdout": PRIVATE_SENTINEL,
        "stderr": "expected=42 actual=41",
        "output_sha256": "a" * 64,
        "expose_output_to_builder": expose,
        "execution": {"backend": "oci-docker", "secret": PRIVATE_SENTINEL},
        "future_private_field": PRIVATE_SENTINEL,
    }


class HoldoutBoundaryTests(unittest.TestCase):
    def test_default_view_is_an_exact_allowlist(self) -> None:
        view = builder_failure_view({"status": "failed", "gates": [gate_result("private")]})
        public = view["gates"][0]
        self.assertEqual(
            {"id", "status", "exit_code", "timed_out", "output_sha256"}, set(public)
        )
        self.assertNotIn(PRIVATE_SENTINEL, repr(view))

    def test_explicit_exposure_has_a_positive_control_but_still_excludes_metadata(self) -> None:
        view = builder_failure_view({"status": "failed", "gates": [gate_result("public", True)]})
        public = view["gates"][0]
        self.assertEqual(PRIVATE_SENTINEL, public["stdout"])
        self.assertIn("stderr", public)
        self.assertNotIn("command", public)
        self.assertNotIn("duration_ms", public)
        self.assertNotIn("execution", public)
        self.assertNotIn("future_private_field", public)

    def test_exposure_is_scoped_per_gate(self) -> None:
        report = {
            "status": "failed",
            "gates": [gate_result("lint", True), gate_result("holdout", False)],
        }
        view = builder_failure_view(report)
        by_id = {item["id"]: item for item in view["gates"]}
        self.assertEqual(PRIVATE_SENTINEL, by_id["lint"]["stdout"])
        self.assertNotIn("stdout", by_id["holdout"])

    def test_truthy_string_cannot_open_a_deserialized_report(self) -> None:
        view = builder_failure_view(
            {"status": "failed", "gates": [gate_result("private", "false")]}
        )
        self.assertNotIn("stdout", view["gates"][0])
        self.assertNotIn(PRIVATE_SENTINEL, repr(view))

    def test_missing_or_null_gate_flag_defaults_closed(self) -> None:
        base = {"id": "gate", "command": ["python", "gate.py"], "timeout_seconds": 30}
        self.assertFalse(GateContract.from_dict(base).expose_output_to_builder)
        self.assertFalse(GateContract.from_dict({**base, "expose_output_to_builder": None}).expose_output_to_builder)

    def test_quoted_and_numeric_gate_booleans_are_rejected(self) -> None:
        base = {"id": "gate", "command": ["python", "gate.py"], "timeout_seconds": 30}
        for unsafe in ("false", "False", "no", "0", 0, 1):
            with self.subTest(value=unsafe), self.assertRaisesRegex(ContractError, "JSON boolean"):
                GateContract.from_dict({**base, "expose_output_to_builder": unsafe})

    def test_policy_booleans_are_strict(self) -> None:
        for field, location in (("baseline_first", "acceptance"), ("allow_network", "policy")):
            for unsafe in ("false", "False", "no", "0", 0, 1):
                with self.subTest(field=field, value=unsafe):
                    payload = benchmark_work_order("rounding-mode").to_dict()
                    payload[location][field] = unsafe
                    with self.assertRaisesRegex(ContractError, "JSON boolean"):
                        WorkOrder.from_dict(payload)

    def test_real_boolean_policy_values_round_trip(self) -> None:
        payload = benchmark_work_order("rounding-mode").to_dict()
        payload["acceptance"]["baseline_first"] = False
        payload["policy"]["allow_network"] = True
        order = WorkOrder.from_dict(payload)
        self.assertFalse(order.baseline_first)
        self.assertTrue(order.allow_network)


if __name__ == "__main__":
    unittest.main()
