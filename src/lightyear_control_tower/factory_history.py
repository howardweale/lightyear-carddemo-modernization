"""Closed inventory of historical Factory decision records, with original dates."""
from datetime import datetime
from pathlib import PurePosixPath

HISTORY_PATTERNS = (
    "howard-decisions-*.json",
    "equivalence-operator-acceptance-*.json",
    "intcalc-duplicate-category-approval-*.json",
    "posttran-phase1-rerun-authorization-*.json",
    "b06-afternoon-preparation-*.json",
    "merge-hold-lift-*.json",
)


def historical_path(path):
    p = PurePosixPath(path)
    return str(p.parent) == "docs/factory" and any(p.match(pattern) for pattern in HISTORY_PATTERNS)


def original_date(path, record):
    value = record.get("decided_at", record.get("decided_on"))
    if value is None:
        field = {
            "factory-scoped-domain-approval/1": "approved_on",
            "posttran-phase1-compile-authorization/1": "authorized_on",
        }.get(record.get("schema"))
        if field:
            value = record.get(field)
        elif PurePosixPath(path).match("b06-afternoon-preparation-*.json"):
            # This is the recorded preparation date, not a new assertion about
            # when an approval happened or proof of a signed B06 attempt.
            assets = record.get("assets", {})
            if assets.get("artifact_type") == "b06-engineering-assets/1":
                recorded = assets.get("created_at_utc")
                if isinstance(recorded, str):
                    datetime.fromisoformat(recorded)
                    value = recorded[:10]
    if not isinstance(value, str) or value[:10] < "2026-10-10":
        raise ValueError("backfill-original-date-required")
    datetime.fromisoformat(value)
    return value
