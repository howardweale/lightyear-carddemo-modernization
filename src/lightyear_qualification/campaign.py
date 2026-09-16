"""Execute synthetic programs and preserve raw observations before comparing them."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

from lightyear_common.io import normalize_logical_source, write_json, write_text
from lightyear_data.contracts import seal

from .corpus import FAULT_CASES, cases, fault_witness
from .protocol import ObservationError, compare, normalize, strict_json


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
CONTRACT = ROOT / "factory/verifier-qualification/contract.json"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def frozen_files():
    paths = sorted(PACKAGE.glob("*.py")) + [CONTRACT]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(normalize_logical_source(p.read_bytes())).hexdigest() for p in paths}


def freeze():
    return seal({"kind": "verifier-qualification-freeze-v1", "files": frozen_files(),
                 "public_corpus_sha256": digest(cases()), "independent_review": "pending"})


def check_freeze(record):
    if record != freeze():
        raise ValueError("qualification code, contract, corpus or freeze identity changed")


def builtin(name, fault=""):
    path = PACKAGE / ("sqlite_target.py" if name == "sqlite" else "journal_target.py")
    return {"id": name + ("-" + fault if fault else ""),
            "argv": [sys.executable, str(path)], "fault": fault,
            "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def invoke(adapter, state, command):
    request = {"protocol": "transfer-request-v1", "command": command}
    argv = [*adapter["argv"], str(state)]
    if adapter.get("fault"):
        argv.append(adapter["fault"])
    # Do not propagate API/cloud credentials to the synthetic target process.
    environment = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR") if k in os.environ}
    evidence = {"request": request, "request_sha256": digest(request)}
    try:
        process = subprocess.run(argv, input=json.dumps(request), text=True, encoding="utf-8",
                                 capture_output=True, timeout=15, cwd=state, env=environment)
        evidence.update(exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr)
        if len(process.stdout.encode()) > 1_000_000:
            evidence["error"] = "observation exceeds one megabyte"
        elif process.returncode == 0:
            try:
                evidence["raw"] = strict_json(process.stdout)
            except ObservationError as exc:
                evidence["error"] = str(exc)
        elif process.returncode != 75 or not command.get("crash_after_debit"):
            evidence["error"] = "target invocation failed"
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        evidence.update(error=type(exc).__name__, exit_code=None, stdout="", stderr="")
    return evidence


def run_case(adapter, case):
    with tempfile.TemporaryDirectory(prefix="qualification-") as temporary:
        state = Path(temporary)
        initial = invoke(adapter, state, {"kind": "initialize", "accounts": case["accounts"]})
        opening = {"accounts": sorted(case["accounts"], key=lambda x: x["id"]), "outcomes": [], "operations": []}
        admission = compare(opening, initial.get("raw"))
        records = []
        if initial.get("error") or admission["verdict"] != "passed":
            return {"case_id": case["id"], "behavior": case["behavior"], "verdict": "indeterminate",
                    "required_steps": len(case["steps"]), "initialization": initial, "records": [], "reason": "initial state not established"}
        for index, step in enumerate(case["steps"]):
            execution = invoke(adapter, state, step["command"])
            execution["step"] = index
            execution["expected"] = step["expected"]
            if execution.get("exit_code") == 75 and step["command"].get("crash_after_debit"):
                recovery = invoke(adapter, state, {"kind": "observe"})
                execution["recovery"] = recovery
                try:
                    # Recovery must itself conform; injected outcome is a harness observation.
                    normalize(recovery.get("raw"))
                    raw = deepcopy(recovery["raw"])
                    if raw["outcomes"]:
                        raise ObservationError("recovery observation has unexpected outcomes")
                    raw["outcomes"] = [{"id": step["command"]["id"], "status": "interrupted"}]
                    execution["raw"] = raw
                except (ObservationError, TypeError, KeyError) as exc:
                    execution["error"] = "invalid recovery: " + str(exc)
            result = compare(step["expected"], execution.get("raw"))
            if execution.get("error"):
                result = {"verdict": "indeterminate", "reason": execution["error"], "differences": []}
            execution["comparison"] = result
            records.append(execution)
        verdicts = {r["comparison"]["verdict"] for r in records}
        verdict = "failed" if "failed" in verdicts else "indeterminate" if "indeterminate" in verdicts else "passed"
        return {"case_id": case["id"], "behavior": case["behavior"], "verdict": verdict,
                "required_steps": len(case["steps"]), "initialization": initial, "records": records}


def fault_outcome(witness, verdict):
    if not witness:
        return "not-exercised"
    return {"failed": "detected", "passed": "missed", "indeterminate": "blocked-indeterminate"}[verdict]


def normalization_challenges():
    base = {"encoding": "integer-cents-v1", "accounts": [{"id": "A", "owner": "alice", "cents": 100}],
            "outcomes": [], "operations": []}
    expected = normalize(base)
    variants = []

    def add(name, raw, wanted):
        result = compare(expected, raw)
        variants.append({"id": name, "raw": raw, "expected_verdict": wanted,
                         "actual_verdict": result["verdict"], "passed": result["verdict"] == wanted})

    decimal = {**base, "encoding": "decimal-journal-v1", "accounts": [{"id": "A", "owner": "alice", "amount": "1.0000"}]}
    add("decimal-formatting", decimal, "passed")
    add("one-cent-change", {**decimal, "accounts": [{"id": "A", "owner": "alice", "amount": "1.01"}]}, "failed")
    add("sub-cent-not-rounded", {**decimal, "accounts": [{"id": "A", "owner": "alice", "amount": "1.001"}]}, "indeterminate")
    add("owner-change", {**base, "accounts": [{"id": "A", "owner": "bob", "cents": 100}]}, "failed")
    add("identity-padding-not-erased", {**base, "accounts": [{"id": "A ", "owner": "alice", "cents": 100}]}, "indeterminate")
    add("missing-recipient-observation", {**base, "accounts": []}, "indeterminate")
    add("duplicate-account-not-collapsed", {**base, "accounts": base["accounts"] * 2}, "indeterminate")
    add("additional-field-not-ignored", {**base, "claimed_verdict": "passed"}, "indeterminate")
    add("unknown-encoding", {**base, "encoding": "vendor-unrecognized"}, "indeterminate")
    add("float-not-coerced", {**base, "accounts": [{"id": "A", "owner": "alice", "cents": 100.0}]}, "indeterminate")
    return variants


def metrics(runs):
    total = len(runs)
    counts = {v: sum(r["verdict"] == v for r in runs) for v in ("passed", "failed", "indeterminate")}
    attempted = sum(len(r["records"]) for r in runs)
    observed = sum("raw" in step and not step.get("error") for r in runs for step in r["records"])
    return {"cases_in_scope": total, **counts, "steps_attempted": attempted, "steps_observed": observed,
            "steps_required": sum(r["required_steps"] for r in runs),
            "behaviors": {name: {"cases_required": sum(r["behavior"] == name for r in runs),
                                  "cases_decided": sum(r["behavior"] == name and r["verdict"] != "indeterminate" for r in runs)}
                          for name in sorted({r["behavior"] for r in runs})},
            "decided_cases": counts["passed"] + counts["failed"],
            "decision_rate": (counts["passed"] + counts["failed"]) / total if total else None}


def development_campaign():
    initial_freeze = freeze()
    corpus = cases()
    correct = []
    for name in ("sqlite", "journal"):
        adapter = builtin(name)
        results = [run_case(adapter, case) for case in corpus]
        correct.append({"adapter": adapter["id"], "artifact_sha256": adapter["artifact_sha256"],
                        "metrics": metrics(results), "runs": results})
    faults = []
    for fault, case_id in FAULT_CASES.items():
        case = next(c for c in corpus if c["id"] == case_id)
        run = run_case(builtin("sqlite", fault), case)
        witness = fault_witness(fault, run["records"])
        faults.append({"fault": fault, "witness_observed": witness,
                       "outcome": fault_outcome(witness, run["verdict"]), "run": run})
    # A deliberate no-trigger control prevents unexercised mutants inflating detection.
    control = run_case(builtin("sqlite", "round-down"), corpus[0])
    no_trigger = {"fault": "round-down", "case_id": "transfer", "run": control,
                  "outcome": fault_outcome(fault_witness("round-down", control["records"]), control["verdict"])}
    normalizations = normalization_challenges()
    fault_counts = {name: sum(f["outcome"] == name for f in faults)
                    for name in ("detected", "blocked-indeterminate", "missed", "not-exercised")}
    source_unchanged = initial_freeze == freeze()
    passed = (source_unchanged and all(c["metrics"]["passed"] == len(corpus) for c in correct)
              and fault_counts["detected"] == len(faults)
              and no_trigger["outcome"] == "not-exercised"
              and all(c["passed"] for c in normalizations))
    return seal({"kind": "verifier-development-qualification-v1", "status": "passed" if passed else "failed",
                 "scope": "synthetic-account-transfer-development", "freeze": initial_freeze,
                 "source_unchanged_during_campaign": source_unchanged,
                 "runtime": {"python": platform.python_version(), "system": platform.system()},
                 "contract": strict_json(CONTRACT.read_text(encoding="utf-8")),
                 "correct_implementations": correct, "faults": faults, "fault_counts": fault_counts,
                 "unexercised_control": no_trigger, "normalization_challenges": normalizations,
                 "claims": {"partner_qualified": False, "cloudbank_runtime_requalified": False,
                            "independent_blind_validation": False, "production_ready": False,
                            "evidence_authenticated": False}})


def markdown(report):
    lines = ["# Verifier qualification — public development campaign", "",
             f"Result: **{report['status']}**. Synthetic local account transfers only.", "",
             "| Implementation | Cases | Passed | Failed | Indeterminate |",
             "|---|---:|---:|---:|---:|"]
    for impl in report["correct_implementations"]:
        m = impl["metrics"]
        lines.append(f"| {impl['adapter']} | {m['cases_in_scope']} | {m['passed']} | {m['failed']} | {m['indeterminate']} |")
    lines += ["", "| Injected fault | Outcome | Raw witness (separate assertion) |", "|---|---|---|"]
    for f in report["faults"]:
        lines.append(f"| {f['fault']} | {f['outcome']} | {f['witness_observed']} |")
    lines += ["", f"Normalization/admission challenges: {sum(c['passed'] for c in report['normalization_challenges'])}/{len(report['normalization_challenges'])} passed.",
              f"No-trigger control: {report['unexercised_control']['outcome']} (excluded from the fault denominator).",
              "", "Both implementations, tests and fault witnesses were authored in the same development session.",
              "Different implementation structures do not establish independent authorship or blind validation.",
              "Raw requests, stdout, stderr, exit codes and recovery observations are retained in report.json.",
              "Hashes bind content, not truth or signer identity. No partner, existing CloudBank gate, cloud runtime,",
              "distributed concurrency, host-crash durability, messaging system, or production qualification is claimed.",
              "", f"Report content SHA-256: `{report['content_sha256']}`", ""]
    return "\n".join(lines)


def save_report(report, output):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "report.json", report)
    write_text(output / "report.md", markdown(report))
    write_json(output / "freeze.json", report["freeze"])
    write_json(output / "public-cases.json", cases())
