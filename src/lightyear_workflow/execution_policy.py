"""Code-owned execution bounds; configuration can only narrow them."""
from __future__ import annotations

import json
from pathlib import Path

from .policy import CATALOG, _unique_object, parse_policy

POLICY_PATH = Path("control-tower/execution-policy.json")


def default_execution_policy() -> dict:
    return {
        "schema_version": "1.0", "adapter": "cloudbank-evidence-actions-v2",
        "scope": "cloudbank-retained-evidence-and-approved-ledger-projection",
        "max_iterations": 8, "max_actions": 32, "max_attempts": 2,
        "max_seconds": 300, "action_timeout_seconds": 15,
        "max_input_bytes": 16777216, "max_output_bytes": 65536,
        "network_access": False, "model_calls": False,
    }


def parse_execution_policy(value: dict, action_policy: dict) -> dict:
    action_policy = parse_policy(action_policy)
    defaults = default_execution_policy()
    if not isinstance(value, dict) or set(value) != set(defaults):
        raise ValueError("Execution policy has unknown or missing fields")
    for key, maximum in defaults.items():
        if type(maximum) is int:
            limit = min(maximum, action_policy["max_autonomous_iterations"]) if key == "max_iterations" else maximum
            if type(value[key]) is not int or not 1 <= value[key] <= limit:
                raise ValueError(f"Invalid execution bound: {key}")
        elif type(value[key]) is not type(maximum) or value[key] != maximum:
            raise ValueError(f"Unsupported execution authority: {key}")
    if value["action_timeout_seconds"] > value["max_seconds"]:
        raise ValueError("Action timeout exceeds run budget")
    return json.loads(json.dumps(value))


def load_execution_policy(root: Path, action_policy: dict) -> dict:
    value = json.loads((root / POLICY_PATH).read_text(), object_pairs_hook=_unique_object)
    return parse_execution_policy(value, action_policy)


def permitted(kind: str, action_policy: dict) -> bool:
    spec = CATALOG.get(kind)
    return bool(spec and spec.action_class == "autonomous" and action_policy["autonomy"][kind] == spec.mode)
