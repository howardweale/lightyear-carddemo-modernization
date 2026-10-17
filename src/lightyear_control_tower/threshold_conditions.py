"""Threshold/2 prerequisites: exact inventory and content-bound evidence.

Historical conditional approvals remain readable. An effective approval must
prove every condition; an empty list can never turn into unconditional authority.
"""
from hashlib import sha256
from pathlib import Path

from .requests import confined, read_bytes, read_json

DECISIONS = "docs/factory/howard-decisions-2026-10-11b.json"
DECISIONS_SHA256 = "74fe7a1d88d8740a7f3ba147dfcad8d9355c27c439f02cc5a85f7704b453b0e4"
REPOSITORY = Path(__file__).resolve().parents[2]
REFUSAL = "threshold-conditions-unmet"


CONDITIONS = (
    "B1 compiler/class evidence and targeted attempts complete",
    "remaining individual reviews accepted",
    "fresh current-head compiled campaign",
    "register dependencies bound",
)


def condition_hashes():
    # Policy-owned inventory also works in a source-only Tower installation.
    # CI binds this exact transcription to the preserved dated decision file.
    return {sha256(text.encode("utf-8")).hexdigest() for text in CONDITIONS}


def validate_conditions(contract, root=None, *, check_evidence=True):
    if not isinstance(contract, dict) or not isinstance(contract.get("details"), dict):
        raise ValueError(REFUSAL)
    details = contract["details"]
    rows = details.get("conditions")
    effective = details["effective_condition"] == "unconditional"
    # Preserve the shape of earlier conditional decisions, without making them effective.
    if rows is None and not effective:
        return
    try:
        if not isinstance(rows, list) or len(rows) != len(condition_hashes()):
            raise ValueError(REFUSAL)
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"condition_sha256", "state", "evidence"}:
                raise ValueError(REFUSAL)
            if row["condition_sha256"] in seen or row["state"] not in {"met", "not-met"}:
                raise ValueError(REFUSAL)
            seen.add(row["condition_sha256"])
            evidence = row["evidence"]
            if row["state"] == "not-met":
                if effective or evidence is not None:
                    raise ValueError(REFUSAL)
                continue
            # Source validation checks the path, commit and SHA shape. Requiring an
            # exact source row also makes public Git import verify the commit blob.
            if not isinstance(evidence, dict) or evidence not in contract["sources"]:
                raise ValueError(REFUSAL)
            if check_evidence:
                raw = read_bytes(confined(root or REPOSITORY, evidence["path"]))
                if sha256(raw).hexdigest() != evidence["sha256"]:
                    raise ValueError(REFUSAL)
                from .threshold_evidence import typed
                typed(row['condition_sha256'], raw, contract, evidence)
        if seen != condition_hashes():
            raise ValueError(REFUSAL)
    except (KeyError, TypeError, OSError, ValueError) as error:
        if str(error) == 'threshold-condition-evidence-type': raise
        raise ValueError(REFUSAL) from error
