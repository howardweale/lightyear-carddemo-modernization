"""Publish a dated assessment from retained CI receipts; never grants authority."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build(root, date):
    root = Path(root)
    relative = f"docs/factory/release-evidence-{date}"
    folder = root / relative
    index_bytes = (folder / "index.json").read_bytes()
    index = json.loads(index_bytes)
    if index["conclusion"] != "success":
        raise ValueError("fresh-main-campaign-not-green")
    for archive in index["sources"]:
        if archive["head"] != index["head"] or archive["run_id"] != index["run_id"]:
            raise ValueError("mixed-campaign-evidence")
        for path, expected in archive["files"].items():
            if sha256((root / path).read_bytes()).hexdigest() != expected:
                raise ValueError("release-evidence-hash:" + path)
    for archive in index.get("crosscheck_sources", []):
        for path, expected in archive["files"].items():
            if sha256((root/path).read_bytes()).hexdigest() != expected:
                raise ValueError("release-crosscheck-evidence-hash:" + path)
    if not index.get("pr_head_crosscheck") or not all(index["pr_head_crosscheck"].values()):
        raise ValueError("release-pr-head-crosscheck-disagrees")
    def read(name):
        path = folder / name
        # The retained index uses Git's forward-slash paths on every platform.
        if path.relative_to(root).as_posix() not in {p for a in index["sources"] + index.get("crosscheck_sources", []) for p in a["files"]}:
            raise ValueError("unindexed-release-evidence")
        return json.loads(path.read_bytes())
    projection = read("aggregate/INTCALC/loader-domain-review-projection.json")
    previous = read("pr-head-aggregate/INTCALC/loader-domain-review-projection.json")
    crosscheck = {k: projection[k] == previous[k] for k in ("projected_thresholds", "raw_thresholds", "independent_crosscheck")}
    if not all(crosscheck.values()):
        raise ValueError("release-pr-head-crosscheck-disagrees")
    if projection["head"] != index["head"] or not all(
            r["passed"] for r in projection["independent_crosscheck"].values()):
        raise ValueError("release-crosscheck-disagrees")
    assessments = {}
    for overlay in projection["overlays"]:
        if overlay["head"] != index["head"] or overlay["sites_removed"]:
            raise ValueError("loader-overlay-binding")
        for row in overlay["assessments"]:
            key = row["id"]
            stable = lambda r: {k:v for k,v in r.items() if k not in {"comparison_evidence_sha256", "raw_record_sha256"}}
            if key in assessments and stable(assessments[key]) != stable(row):
                raise ValueError("loader-shards-disagree:" + key)
            assessments[key] = row
    raw = read("intcalc-0/factory-review-INTCALC/mutation-receipt-summary.json")
    counts = Counter(r["status"] for r in raw["rows"])
    killed = sum(n for status, n in counts.items() if status in {"killed-failure", "killed-divergent"})
    eligible = len(raw["rows"]) - counts["not-compiled"]
    rate = f"{killed}/{eligible}"
    if any(t["kill_rate"] != rate for t in projection["raw_thresholds"].values()):
        raise ValueError("raw-threshold-count-mismatch")
    gap_ids = sorted(r["id"] for r in raw["rows"] if r["status"] == "evidence-gap")
    if set(gap_ids) != set(assessments):
        raise ValueError("loader-assessment-inventory")
    programs = {}
    for program in ("INTCALC", "POSTTRAN"):
        scopes = read(f"aggregate/{program}/threshold-2-by-scope.json")
        measured = scopes["twin"]
        reviews = read(f"aggregate/{program}/results.json")
        if measured["current_head"] != index["head"]:
            raise ValueError("threshold-head-mismatch")
        programs[program] = dict(business=measured["business"], io=measured["io"],
            diversity=measured["distinct_values_per_output_field"], below_two_values=measured["below_two_values"],
            targets=[{k:r[k] for k in ("id", "targeted_cases", "targeted_valid_comparisons", "targeted_evidence_complete")}
                     for r in reviews if "targeted_cases" in r], threshold_by_scope=scopes)
    supplement_path = root / "docs/factory/equivalence-operator-acceptance-2026-10-12.json"
    supplement = json.loads(supplement_path.read_bytes())
    by_line = defaultdict(list)
    for row in raw["rows"]:
        by_line[row["line"]].append(dict(id=row["id"], status=row["status"]))
    constants = []
    for row in supplement["constant_field_acceptances"]:
        if row["program"] != "INTCALC":
            continue
        source = (root / row["source_path"]).read_bytes().replace(b"\r\n", b"\n")
        line = source.decode().splitlines()[row["source_line"]-1]
        if sha256(source).hexdigest() != row["source_sha256"] or sha256(line.encode()).hexdigest() != row["source_line_sha256"]:
            raise ValueError("constant-source-hash")
        constants.append({**row, "compared": row["field"] in programs["INTCALC"]["diversity"],
                          "measured_values": programs["INTCALC"]["diversity"].get(row["field"]),
                          "mutants": by_line[row["source_line"]]})
    pending = [r for r in assessments.values() if r["assessment"] != "resolved-by-valid-comparisons"]
    groups = {}
    for scope, threshold in projection["projected_thresholds"].items():
        grouped = defaultdict(list)
        for row in threshold["excluded_equivalents"]:
            grouped[row["basis"]].append(row["id"])
        groups[scope] = dict(raw=projection["raw_thresholds"][scope], projected=threshold,
                            excluded_by_basis=dict(grouped), crosscheck=projection["independent_crosscheck"][scope])
    deficits = programs["INTCALC"]["below_two_values"]
    blockers = []
    if deficits:
        blockers.append("Output diversity: source-assigned constants cannot meet threshold/2 as written; Howard must decide an explicit policy change before a signing-only release path can be claimed.")
    if pending:
        blockers.append("Loader gaps remain; deterministic fixes and a fresh CI campaign are required.")
    if not index.get("retention_complete"):
        blockers.append("Large original mutation receipts await the designated retention store; local staging and artifact hashes are recorded in the index.")
    if not (ROOT/'src/lightyear_control_tower/threshold_evidence.py').is_file():
        blockers.append("Typed threshold-condition validation is not present in this checkout.")
    blockers.append("No effective signed threshold policy has been applied; provisional engineering evidence does not become release evidence through signatures.")
    verdict = "Not releasable: " + " ".join(blockers)
    measured = programs["INTCALC"]
    criteria = [
        dict(name="Business outcomes", measured=measured["business"]["fraction"], now="met" if measured["business"]["covered"] == measured["business"]["total"] else "failed", after_signatures="unchanged measured coverage"),
        dict(name="I/O outcomes", measured=measured["io"]["fraction"], now="exception pending", after_signatures="met only with the exact structurally unreachable edge accepted"),
        dict(name="Twin mutant kill rate", measured=rate, now="below threshold", after_signatures=groups["twin"]["projected"]["kill_rate"]),
        dict(name="Output diversity", measured=deficits, now="failed", after_signatures="still fails unchanged threshold/2"),
        dict(name="Effective threshold policy", measured=False, now="not effective", after_signatures="blocked until prerequisites and policy choice are resolved"),
    ]
    result = dict(schema="intcalc-releasability/2", prepared_on=date, head=index["head"], run_id=index["run_id"],
        evidence_index=dict(path=relative+"/index.json", sha256=sha256(index_bytes).hexdigest()),
        verdict=verdict, claim_scope="twin", effective=False, release_authorized=False, zos_confirmation=False,
        raw_mutation_counts=dict(counts), raw_kill_rate=rate, raw_receipt_sha256=raw["original_sha256"],
        programs=programs, constants=constants, criteria=criteria, scopes=groups,
        remaining_evidence_gaps=[r["id"] for r in pending], raw_evidence_gap_ids=gap_ids,
        loader_domain=dict(assessment_counts=dict(Counter(r["assessment"] for r in assessments.values())),
                           assessments=list(assessments.values()), effective=False, sites_removed=0),
        pr_head_crosscheck=crosscheck, blockers=blockers, six_request_path="stopped-policy-decision-required")
    result["content_sha256"] = digest(result)
    lines = ["# INTCALC releasability — " + date, "", "Twin-scoped engineering evidence only. No z/OS confirmation and no customer release.", "",
             f"Green main campaign {index['run_id']} at `{index['head']}`. Raw records are preserved.", "",
             "| Criterion | Measured | State now | After signatures alone |", "| --- | --- | --- | --- |"]
    for row in criteria:
        lines.append(f"| {row['name']} | {row['measured']} | {row['now']} | {row['after_signatures']} |")
    lines += ["", "| Scope | Raw kills / eligible | Projected kills / eligible | Independent cross-check |", "| --- | --- | --- | --- |"]
    for scope, row in groups.items():
        lines.append(f"| {scope} | {row['raw']['kill_rate']} | {row['projected']['kill_rate']} | {row['crosscheck']['passed']} |")
    lines += ["", "Loader assessments: " + str(result["loader_domain"]["assessment_counts"]) + ". No sites removed; no loader kill or coverage credit.",
              "", "The JSON lists every exclusion by basis, every unresolved ID, targeted comparison counts, and every constant's source and mutant bindings.",
              "", "Howard's choices: individual constant exceptions with an explicit policy decision, or a threshold/3 constant exemption. Neither is effective merely by accepting the existing threshold/2 request.",
              "", "The six-request signing simulation is paused at this criterion, as required by the supplied stop rule.", "", verdict, ""]
    return result, "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    value, text = build(ROOT, args.date)
    base = ROOT / "docs/factory" / ("intcalc-releasability-" + args.date)
    base.with_suffix(".json").write_text(json.dumps(value, indent=2)+"\n")
    base.with_suffix(".md").write_text(text)
