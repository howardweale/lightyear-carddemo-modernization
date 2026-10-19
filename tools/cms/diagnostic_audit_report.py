"""Render only allowlisted diagnostic audit metadata, never diagnostic text."""
import json
from pathlib import Path


def render(observation):
    receipt = observation["public_receipt"]
    rows = receipt["compile"]["diagnostic_audit"]
    flagged = [r for r in rows if r["possible_source_quote"]]
    if receipt["raw_diagnostics_uploaded"] or receipt["source_uploaded"] or any(
            r["raw_diagnostics_uploaded"] for r in rows):
        raise ValueError("cms-audit-publication-boundary")
    lines = ["# CMS diagnostic audit correction - 2026-10-18", "",
        "As of evidence run " + str(observation["run_id"]) + " at `" + observation["evidence_head"] + "`.", "",
        "Supersedes the diagnostic-audit interpretation in feasibility-ipps-fy2021.md; historical files remain unchanged.",
        "The earlier zero count covered a numbered-line formatting heuristic. It does not describe the later source-aware audit.", "",
        f"Source-aware audit: {len(flagged)} flagged attempts out of {len(rows)} attempts; {len({r['program'] for r in flagged})} programs.",
        "A flag means possible source quotation was detected, not that source was published. This report neither opens nor quotes diagnostics.",
        "The retained receipt reports raw_diagnostics_uploaded=false and source_uploaded=false; the later workflow uploads only its allowlisted metadata receipt.", "",
        "| Program | Dialect | Possible source quotation |", "| --- | --- | --- |"]
    lines += [f"| {r['program']} | {r['dialect']} | true |" for r in flagged]
    lines += ["", "Older artifacts have a different upload boundary; no claim about their contents follows from this metadata.",
        "Payment equivalence remains NO-GO. No signing, activation or Phase 2 authority.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("observation", type=Path)
    p.add_argument("--check", type=Path, required=True)
    args = p.parse_args()
    if render(json.loads(args.observation.read_bytes())) != args.check.read_text(encoding="utf-8"):
        raise SystemExit("cms-diagnostic-report-stale")
