"""Hand-authored public examples. Expectations are not produced by either target."""
from __future__ import annotations

from copy import deepcopy


DAY = "2028-02-29"
OPENING = [{"id": "A", "owner": "alice", "cents": 10000},
           {"id": "B", "owner": "bob", "cents": 2000},
           {"id": "C", "owner": "carol", "cents": 0}]


def op(identifier="x", value="12.50", **changes):
    return {"kind": "transfer", "id": identifier, "from": "A", "to": "B",
            "actor": "alice", "amount": value, "date": DAY, **changes}


def entry(identifier="x", cents=1250, **changes):
    return {"id": identifier, "from": "A", "to": "B", "cents": cents, "date": DAY, **changes}


def expected(a=10000, b=2000, c=0, operations=(), outcomes=()):
    return {"accounts": [{**row, "cents": value} for row, value in zip(OPENING, (a, b, c))],
            "operations": sorted(deepcopy(list(operations)), key=lambda x: x["id"]),
            "outcomes": [{"id": i, "status": s} for i, s in sorted(outcomes)]}


def cases():
    success = expected(8750, 3250, operations=[entry()], outcomes=[("x", "applied")])
    result = []

    def case(name, behavior, steps):
        result.append({"id": name, "behavior": behavior, "accounts": deepcopy(OPENING),
                       "steps": [{"command": cmd, "expected": exp} for cmd, exp in steps]})

    case("transfer", "recipient-and-exact-balances", [(op(), success)])
    case("round-up", "half-even-rounding", [(op(value="1.015"), expected(9898, 2102, operations=[entry(cents=102)], outcomes=[("x", "applied")]))])
    case("round-down-tie", "half-even-rounding", [(op(value="1.005"), expected(9900, 2100, operations=[entry(cents=100)], outcomes=[("x", "applied")]))])
    for name, amount in (("zero", "0"), ("negative", "-1"), ("nan", "NaN"), ("zero-after-rounding", "0.004")):
        case(name, "invalid-input-no-mutation", [(op(value=amount), expected(outcomes=[("x", "invalid")]))])
    case("bad-date", "calendar-semantics", [(op(date="2027-02-29"), expected(outcomes=[("x", "invalid")]))])
    case("insufficient", "insufficient-no-mutation", [(op(value="100.01"), expected(outcomes=[("x", "insufficient")]))])
    case("ownership", "authorization-no-mutation", [(op(actor="carol"), expected(outcomes=[("x", "forbidden")]))])
    case("replay", "persistent-idempotency", [(op(), success), (op(), expected(8750, 3250, operations=[entry()], outcomes=[("x", "replayed")]))])
    case("conflicting-replay", "idempotency-payload-binding", [(op(), success), (op(value="12.51"), expected(8750, 3250, operations=[entry()], outcomes=[("x", "conflict")]))])
    case("restart", "restart-preserves-state", [(op(), success), ({"kind": "observe"}, expected(8750, 3250, operations=[entry()]))])
    case("crash-retry", "crash-atomicity-and-retry", [(op(crash_after_debit=True), expected(outcomes=[("x", "interrupted")])), (op(), success)])
    case("concurrent", "concurrent-update-preservation", [({"kind": "concurrent", "operations": [op("x", "1.00"), op("y", "2.00")]},
         expected(9700, 2300, operations=[entry("x", 100), entry("y", 200)], outcomes=[("x", "applied"), ("y", "applied")]))])
    case("opposite", "concurrent-update-preservation", [({"kind": "concurrent", "operations": [op("x", "1.00"), op("y", "2.00", **{"from": "B", "to": "A", "actor": "bob"})]},
         expected(10100, 1900, operations=[entry("x", 100), entry("y", 200, **{"from": "B", "to": "A"})], outcomes=[("x", "applied"), ("y", "applied")]))])
    return result


FAULT_CASES = {"wrong-recipient": "transfer", "round-down": "round-up", "duplicate-effect": "replay",
               "partial-commit": "crash-retry", "lost-on-restart": "restart", "wrong-date": "transfer",
               "unauthorized": "ownership", "lost-update": "concurrent"}


def fault_witness(fault, runs):
    """Direct raw-application witnesses; no comparator or normalizer calls.

    Deliberately independent assertions about the seeded fixture, NOT a general
    correctness oracle. Return false if the fault was never observed executing.
    """
    for run in runs:
        raw = run.get("raw")
        if not isinstance(raw, dict) or raw.get("encoding") != "integer-cents-v1":
            continue
        values = {a["id"]: a["cents"] for a in raw["accounts"]}
        effects = raw["operations"]
        if fault == "wrong-recipient" and values["C"] == 1250 and values["B"] == 2000:
            return True
        if fault == "round-down" and any(e["cents"] == 101 for e in effects):
            return True
        if fault == "duplicate-effect" and values["A"] == 7500 and values["B"] == 4500:
            return True
        if fault == "partial-commit" and values["A"] == 8750 and values["B"] == 2000 and not effects:
            return True
        if fault == "lost-on-restart" and values["A"] == 8750 and not effects:
            return True
        if fault == "wrong-date" and any(e["date"] == "2028-03-01" for e in effects):
            return True
        if fault == "unauthorized" and values["A"] == 8750:
            return True
        if fault == "lost-update" and values["A"] == 9800 and values["B"] == 2200 and len(effects) == 2:
            return True
    return False
