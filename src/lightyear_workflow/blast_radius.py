"""Measured blast radius for a proposed normalization entry.

`planner.py` already declares this a prerequisite for signing:

    "signature_blocker": "Exact proposed terms, measured blast radius and the
                          bound decision workflow are required before signing."

and then emits:

    "suppressed_comparisons": 0, "suppression_estimate": "not-assessed"

This measures pattern reach over explicitly described comparison records.
It does not execute a normalization or prove a verdict transition. The planner
and signing workflow are unchanged; exact terms and independent evidence remain
required. Raw MS70 references must be hydrated before this function can measure them.

    from lightyear_workflow.blast_radius import blast_radius
    radius = blast_radius(entry["pattern"], indeterminate_register)
    plan["suppressed_comparisons"] = radius["suppressed_comparisons"]
    plan["suppression_estimate"]   = radius["suppression_estimate"]
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# A proposed entry that reaches this many comparisons is worth a second reader.
WIDE_REACH_FILES = 50


def blast_radius(pattern: str, register: Iterable[Mapping[str, Any]]) -> dict:
    """Count what approving `pattern` would stop comparing.

    register: an enriched comparison register (not raw MS70 pair references). Each entry needs a
    `file`, a `construct` or `reason`, and optionally a `comparison_count`
    (defaults to one comparison per entry).

    Returns `suppression_estimate: "measured"` only for a valid, nonempty
    comparison register. Raw MS70 pair-reference registers are unsupported. Anything else is reported as its own state
    rather than as a zero, because a zero and an unmeasured are not the same
    fact and must not be displayed as though they were.
    """
    if not isinstance(pattern, str) or not pattern.strip():
        return _result(0, set(), "invalid-pattern", error="A nonempty string pattern is required")
    try:
        matcher = re.compile(pattern, re.I)
    except re.error as exc:
        return _result(0, set(), "invalid-pattern", error=str(exc))

    entries = list(register)
    for entry in entries:
        if (not isinstance(entry, Mapping)
                or not isinstance(entry.get("file"), str) or not entry["file"].strip()
                or not any(isinstance(entry.get(k), str) and entry[k].strip()
                           for k in ("construct", "reason", "field"))
                or type(entry.get("comparison_count", 1)) is not int
                or entry.get("comparison_count", 1) < 1
                or ("files" in entry and (not isinstance(entry["files"], list) or not entry["files"]
                    or any(not isinstance(name, str) or not name.strip() for name in entry["files"])))):
            return _result(0, set(), "invalid-register",
                           error="Expected comparison records with file and construct/reason/field; "
                                 "resolve MS70 pair references against their bound comparison evidence first.")
    if not entries:
        return _result(0, set(), "empty-register")

    suppressed = 0
    files: set[str] = set()
    for entry in entries:
        haystack = " ".join(
            str(entry.get(field, "")) for field in ("construct", "reason", "field")
        )
        if not matcher.search(haystack):
            continue
        suppressed += int(entry.get("comparison_count", 1))
        name = entry.get("file")
        if name:
            files.add(str(name))
        files.update(entry.get("files", []))

    return _result(suppressed, files, "measured")


def _result(suppressed: int, files: set[str], estimate: str, **extra) -> dict:
    out = {
        "suppressed_comparisons": suppressed,
        "affected_files": len(files),
        "suppression_estimate": estimate,
        "sample_files": sorted(files)[:5],
        "wide_reach": len(files) >= WIDE_REACH_FILES,
    }
    out.update(extra)
    return out


def signature_blocker(radius: Mapping[str, Any]) -> str | None:
    """The radius prerequisite only; None does not grant signing authority.

    Enforces the requirement planner.py already states. An approval whose reach
    was never measured is refused rather than signed with a zero standing in for
    an unknown.
    """
    if radius.get("suppression_estimate") != "measured":
        return (
            "Blast radius is "
            f"{radius.get('suppression_estimate', 'unknown')}. An approval cannot "
            "be signed until the number of comparisons it suppresses has been "
            "measured."
        )
    return None
