"""Keyed, value-free comparisons and unapplied timestamp proposals."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

from lightyear_control_tower.decisions import canonical, digest
from .source import sha
from .zos_bindings import ROOT
from .zos_evidence import write_json
from .zos_intake import decode_run

TIMESTAMP = r"\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d{6}"


def is_timestamp(value):
    if not re.fullmatch(TIMESTAMP, value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d-%H.%M.%S.%f")
        return True
    except ValueError:
        return False


def fields(record):
    return {f["path"]: f for f in record["fields"]}


def compare_records(left, right, binding, *, base_rules=False, ignored=()):
    keys = binding["keys"]

    def index(records):
        result = {}
        for n, r in enumerate(records):
            fs = fields(r)
            key = tuple(fs[p]["value"] for p in keys) if keys else (n,)
            if key in result:
                raise ValueError("Duplicate record keys; comparison is indeterminate")
            result[key] = fs
        return result

    a, b = index(left), index(right)
    counts, patterns, changed = Counter(), {}, 0
    for key in a.keys() & b.keys():
        different = False
        for path in sorted(a[key].keys() | b[key].keys()):
            fa, fb = a[key].get(path), b[key].get(path)
            if fa is None or fb is None:
                raise ValueError("Field layouts differ")
            if path in ignored or (base_rules and fa["filler"]):
                continue
            x, y = fa["value"], fb["value"]
            if base_rules:
                x, y = x.rstrip(), y.rstrip()
            if x != y:
                counts[path] += 1
                different = True
                timestamp = (
                    path in binding["timestamp_fields"]
                    and is_timestamp(x)
                    and is_timestamp(y)
                )
                patterns[path] = patterns.get(path, True) and timestamp
        changed += different
    return dict(
        added=len(b.keys() - a.keys()),
        deleted=len(a.keys() - b.keys()),
        changed=changed,
        before_records=len(left),
        after_records=len(right),
        fields=[
            dict(
                path=p,
                records=n,
                kind="declared-timestamp-pattern" if patterns[p] else "field-value",
            )
            for p, n in sorted(counts.items())
        ],
        identical=not counts and a.keys() == b.keys(),
    )


def afters(decoded, phase):
    return {
        key.rsplit("/", 1)[0]: value
        for key, value in decoded["datasets"].items()
        if value["descriptor"]["phase"] == phase
    }


def compare_runs(first, second, public_key):
    run_a, a = decode_run(first, public_key)
    run_b, b = decode_run(second, public_key)
    findings = []
    if run_a["job"] != run_b["job"] or run_a["findings"] or run_b["findings"]:
        findings.append(
            "Run identities or intake findings prevent a complete determinism claim."
        )
    before_a, before_b = afters(a, "before"), afters(b, "before")
    if {k: v["descriptor"]["sha256"] for k, v in before_a.items()} != {
        k: v["descriptor"]["sha256"] for k, v in before_b.items()
    }:
        findings.append(
            "Before-images differ; same restored starting state is not established."
        )
    if run_a["processing_date"] != run_b["processing_date"]:
        findings.append("Processing parameters differ.")
    for run in (run_a, run_b):
        if run["observation"].get("missing"):
            findings.append(
                "Runtime/clock/compiler fingerprint has missing observations."
            )
    if run_a["observation"].get("fingerprint") != run_b["observation"].get(
        "fingerprint"
    ):
        findings.append("Runtime/compiler fingerprints differ.")
    outputs_a, outputs_b = afters(a, "after"), afters(b, "after")
    comparisons, proposals = {}, []
    for key in sorted(outputs_a.keys() | outputs_b.keys()):
        if key not in outputs_a or key not in outputs_b:
            findings.append("An after-dataset is missing from one run.")
            continue
        x, y = outputs_a[key], outputs_b[key]
        if x["descriptor"]["binding"] != y["descriptor"]["binding"]:
            findings.append("Dataset bindings differ.")
            continue
        binding = x["descriptor"]["binding"]
        try:
            diff = compare_records(x["records"], y["records"], binding)
        except ValueError:
            findings.append(
                "Duplicate or incompatible records prevent keyed comparison."
            )
            continue
        comparisons[key] = diff
        if diff["added"] or diff["deleted"]:
            findings.append(
                "Record keys or counts differ; investigate before drafting a rule."
            )
        for change in diff["fields"]:
            if change["kind"] != "declared-timestamp-pattern":
                findings.append(
                    "A non-timestamp field differs; investigate before drafting a rule."
                )
                continue
            # Plant a change in a non-key, non-timestamp business field in the same record.
            import copy

            mutant = copy.deepcopy(x["records"])
            targets = (
                [
                    f
                    for f in mutant[0]["fields"]
                    if not f["filler"]
                    and f["path"] not in binding["keys"] + binding["timestamp_fields"]
                ]
                if mutant
                else []
            )
            if not targets:
                findings.append(
                    "No still-caught business field is available for a rule proposal."
                )
                continue
            targets[0]["value"] += "!"
            caught = compare_records(
                x["records"], mutant, binding, ignored=[change["path"]]
            )
            rule = dict(
                id="zos-timestamp-"
                + digest(dict(dataset=key, path=change["path"]))[:16],
                schema="zos-normalization-proposal/1",
                workload="workload:carddemo-intcalc",
                dataset=key,
                field=change["path"],
                pattern=TIMESTAMP,
                reason="Repeated runs differ in a declared processing timestamp field; no rule is applied until an exact signed approval.",
                owner="Howard Weale (pending assignment/approval)",
                review_after=(
                    datetime.now(timezone.utc).date() + timedelta(days=30)
                ).isoformat(),
                status="draft",
                still_caught=dict(
                    field=targets[0]["path"], detected=not caught["identical"]
                ),
                runs=[a["run_sha256"], b["run_sha256"]],
            )
            proposals.append(rule)
    if findings:
        proposals = []  # Resolve other differences before proposing any normalization.
    result = dict(
        schema="zos-determinism/1",
        runs=[a["run_sha256"], b["run_sha256"]],
        datasets=comparisons,
        findings=sorted(set(findings)),
        normalizations_applied=[],
        proposals=proposals,
    )
    target = Path(first) / ("determinism-" + b["run_sha256"][:12] + ".json")
    write_json(target, result)
    if proposals:
        ledger = dict(
            schema="zos-normalization-proposals/1",
            workload="workload:carddemo-intcalc",
            rules=proposals,
        )
        write_json(Path(first) / "normalization-proposals.json", ledger)
        safe_dir = ROOT / "work/mainframe/review" / a["run_sha256"]
        safe_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = safe_dir / "ledger.json"
        ledger_path.write_bytes(canonical(ledger) + b"\n")
        inbox = ROOT / "work/control-tower/requests/carddemo-zos"
        inbox.mkdir(parents=True, exist_ok=True)
        for rule in proposals:
            entry_path = safe_dir / (rule["id"] + ".json")
            entry_path.write_bytes(canonical(rule) + b"\n")
            request = dict(
                schema="tower-request/1",
                scope="carddemo-zos",
                id=rule["id"] + "-" + a["run_sha256"][:12],
                kind="normalization",
                bound={
                    "entry": sha(entry_path.read_bytes()),
                    "ledger": sha(ledger_path.read_bytes()),
                },
                evidence={
                    "entry": entry_path.relative_to(ROOT).as_posix(),
                    "ledger": ledger_path.relative_to(ROOT).as_posix(),
                },
                summary="Draft processing-timestamp rule with a still-caught non-timestamp mutation. Operator review required.",
                proposed_by="zos-intake",
                authored_by=["zos-intake"],
                workload="workload:carddemo-intcalc",
            )
            (inbox / (request["id"] + ".json")).write_bytes(canonical(request) + b"\n")
    return result


def delta(path, public_key):
    run, decoded = decode_run(path, public_key)
    before, after = afters(decoded, "before"), afters(decoded, "after")
    result = dict(
        schema="zos-delta/1", run_sha256=decoded["run_sha256"], datasets={}, findings=[]
    )
    for key in sorted(before.keys() | after.keys()):
        if key not in before or key not in after:
            result["findings"].append(
                dict(
                    dataset=key,
                    reason="Before or after image missing; additions/deletions cannot be inferred.",
                )
            )
            continue
        try:
            result["datasets"][key] = compare_records(
                before[key]["records"],
                after[key]["records"],
                before[key]["descriptor"]["binding"],
            )
        except ValueError:
            result["findings"].append(
                dict(
                    dataset=key,
                    reason="Duplicate or incompatible record keys; delta unavailable.",
                )
            )
    write_json(Path(path) / "delta.json", result)
    return result
