"""Action authority is code-owned; customer policy can only reduce autonomy."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class ActionSpec:
    action_class: str
    mode: str
    owner_role: str
    preconditions: tuple[str, ...] = ()


CATALOG = MappingProxyType({
    "rerun": ActionSpec("autonomous", "auto", "engineering", ("changed-inputs", "permitted-observation")),
    "escalate-lane": ActionSpec("autonomous", "auto", "engineering", ("available-next-lane", "permitted-observation")),
    "extend-corpus": ActionSpec("autonomous", "auto-within-declared-scope", "corpus-owner", ("authorized-capture", "declared-scope")),
    "reparse": ActionSpec("autonomous", "auto", "parser-maintainer", ("new-grammar-version",)),
    "widen-observation": ActionSpec("autonomous", "auto", "corpus-owner", ("authorized-capture", "declared-scope")),
    "apply-ledger-entry": ActionSpec("autonomous", "auto-if-unexpired", "engine", (
        "trusted-signature-and-continuous-journal", "current-nonrevoked-human-approval",
        "exact-entry-ledger-and-scope-binding", "unexpired-at-application-time",
        "retain-raw-divergence-and-human-decision-provenance")),
    "propose-normalization": ActionSpec("approval-required", "always-ask", "business-owner"),
    "classify-intentional-change": ActionSpec("approval-required", "always-ask", "business-owner"),
    "accept-contract-equivalence": ActionSpec("approval-required", "always-ask", "business-owner"),
    "promote-claim": ActionSpec("approval-required", "always-ask", "claim-owner"),
    "widen-scope": ActionSpec("approval-required", "always-ask", "customer-risk-owner"),
    "require-authorised-baseline": ActionSpec("blocked", "blocked", "baseline-owner"),
    "require-customer-authorization": ActionSpec("blocked", "blocked", "customer-risk-owner"),
    "require-approved-provider": ActionSpec("blocked", "blocked", "provider-owner"),
    "require-parser-work": ActionSpec("blocked", "blocked", "parser-maintainer"),
})
REQUIRED_HALTS = frozenset({"divergent", "scope-boundary", "budget"})


def default_policy() -> dict:
    return {"schema_version": "1.0", "mode": "emit-only",
            "autonomy": {kind: spec.mode for kind, spec in CATALOG.items()},
            "max_autonomous_iterations": 8, "halt_on": sorted(REQUIRED_HALTS),
            "owners": {"parser-maintainer": "LIGHTYEAR parser engineering"}}


def parse_policy(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != set(default_policy()):
        raise ValueError("Workflow policy must contain exactly the supported fields")
    if value["schema_version"] != "1.0" or value["mode"] != "emit-only":
        raise ValueError("Only emit-only workflow policy is supported")
    modes = value["autonomy"]
    if not isinstance(modes, dict) or set(modes) != set(CATALOG):
        raise ValueError("Autonomy policy must name every known action exactly once")
    for kind, spec in CATALOG.items():
        allowed = {spec.mode, "always-ask"} if spec.action_class == "autonomous" else {spec.mode}
        if not isinstance(modes[kind], str) or modes[kind] not in allowed:
            raise ValueError(f"{kind} cannot use {modes[kind]!r}; authority cannot be increased")
    cap = value["max_autonomous_iterations"]
    if type(cap) is not int or not 1 <= cap <= 8:
        raise ValueError("Iteration cap must be an integer from 1 to 8 (no iterations run in Step 1)")
    halts = value["halt_on"]
    if not isinstance(halts, list) or any(not isinstance(h, str) for h in halts) or len(halts) != 3 or set(halts) != REQUIRED_HALTS:
        raise ValueError("Divergence, scope and budget halt conditions are mandatory")
    owners = value["owners"]
    roles = {spec.owner_role for spec in CATALOG.values()}
    if not isinstance(owners, dict) or set(owners) - roles or any(not isinstance(n, str) or not n.strip() or len(n) > 200 for n in owners.values()):
        raise ValueError("Owners must map known roles to nonempty accountable names or teams")
    # Return independent data; callers cannot mutate parsed policy through the input.
    return json.loads(json.dumps(value))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate policy key: {key}")
        result[key] = value
    return result


def load_policy(path: Path) -> dict:
    return parse_policy(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object))
