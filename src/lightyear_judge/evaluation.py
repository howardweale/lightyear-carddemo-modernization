"""Adapt sandboxed execution to the existing signed INTCALC verdict and replay."""

import time
from pathlib import Path
from lightyear_mainframe import zos_evidence as evidence
from lightyear_mainframe.zos_intake import intake
from lightyear_mainframe.zos_bridge import (
    prepare,
    compute_verdict,
    replay,
    implementation_hashes,
    OUTPUTS,
)
from lightyear_mainframe.zos_bindings import ROOT, load_bindings, dataset_binding
from lightyear_mainframe.records import load_copybook
from lightyear_toolkit.workspace import sha
from .sandbox import run


def fields():
    bindings = load_bindings()
    return {
        "STEP15/"
        + dd: {
            f.path
            for f in load_copybook(
                ROOT / dataset_binding(bindings, "INTCALC", "STEP15", dd)["copybook"]
            ).fields
        }
        for dd in OUTPUTS
    }


def band(n):
    return "1" if n == 1 else "2-10" if n <= 10 else ">10"


def diagnostics(verdict, execution, *, counts=False):
    """Only the comparator's pinned dataset/field allowlist can enter a response."""
    allowed, result = fields(), []

    def add(dataset, field, kind, count=1):
        if dataset not in allowed or (
            field != "$record" and field not in allowed[dataset]
        ):
            raise ValueError("diagnostic-identity-unbound")
        result.append(
            {
                "dataset": dataset,
                "field": field,
                "kind": kind,
                **({"count": count} if counts else {"count_band": band(count)}),
            }
        )

    if execution["return_code"] != 0 or execution["status"] != "completed":
        add(
            "STEP15/ACCTFILE",
            "$record",
            (
                "abend"
                if execution["return_code"] is None or execution["return_code"] < 0
                else "nonzero-return-code"
            ),
        )
    for dataset, diff in verdict["datasets"].items():
        for f in diff["fields"]:
            add(dataset, f["path"], "value-differs", f["records"])
        for key, kind in (("deleted", "missing-record"), ("added", "extra-record")):
            if diff[key]:
                add(dataset, "$record", kind, diff[key])
        count = abs(diff["before_records"] - diff["after_records"])
        if count:
            add(dataset, "$record", "count-differs", count)
    if verdict["verdict"] == "indeterminate" and not result:
        add("STEP15/ACCTFILE", "$record", "type-or-format")
    return sorted(result, key=lambda x: (x["dataset"], x["field"], x["kind"]))


def summarize(runs):
    """Derive exactly the same closed result during execution and offline replay."""
    totals, verdicts = {}, []
    for item in runs:
        path = Path(item["path"])
        verdict = evidence.read_json(path / "verdict.json")
        execution = evidence.read_json(path / "candidate/execution.json")
        if (item["sha256"], item["verdict"]) != (
            verdict["content_sha256"],
            verdict["verdict"],
        ):
            raise ValueError("private-verdict-binding-failed")
        verdicts.append(verdict["verdict"])
        for d in diagnostics(verdict, execution, counts=True):
            key = (d["dataset"], d["field"], d["kind"])
            totals[key] = totals.get(key, 0) + d["count"]
    outcome = (
        "indeterminate"
        if "indeterminate" in verdicts
        else "divergent" if "divergent" in verdicts else "equivalent"
    )
    closed = [
        dict(dataset=d, field=f, kind=k, count_band=band(n))
        for (d, f, k), n in sorted(totals.items())
    ]
    return outcome, closed


def evaluate(root, delivery, jar, signer, *, review_root):
    # This process owns one task and never changes the comparator or its predicates.
    evidence.ARRIVALS = Path(root) / "arrivals"
    arrival, summary = intake(
        delivery, "judge evaluation inputs", signer, review_root=review_root
    )
    runs = sorted((arrival / "runs").iterdir())
    if summary["findings"] or not runs:
        raise ValueError("evaluation-intake-unready")
    completed = []
    tick = time.monotonic()
    for path in runs:
        manifest = prepare(path, signer.public, signer)
        start = evidence.now()
        args = [
            "--carddemo.input-dir=/inputs",
            "--carddemo.output-dir=/outputs",
            "--carddemo.processing-date=" + manifest["processing_date"],
            "--carddemo.timestamp=" + manifest["candidate_timestamp"],
            "--carddemo.final-account-policy=source-faithful",
        ]
        remaining = 300 - (time.monotonic() - tick)
        if remaining <= 0:
            raise ValueError("attempt-deadline")
        rc, status = run(
            jar,
            path / "candidate/inputs",
            path / "candidate/outputs",
            args,
            path / "candidate/execution.log",
            timeout=remaining,
        )
        files = {
            n: sha((path / "candidate/outputs" / n).read_bytes())
            for n in [*OUTPUTS.values(), "candidate-receipt.json"]
            if (path / "candidate/outputs" / n).is_file()
        }
        import shutil

        execution = signer.sign(
            dict(
                schema="zos-intcalc-execution/1",
                input_manifest_sha256=manifest["content_sha256"],
                jar_sha256=sha(jar.read_bytes()),
                java_sha256=sha(Path(shutil.which("java")).read_bytes()),
                started_at_utc=start,
                ended_at_utc=evidence.now(),
                elapsed_seconds=time.monotonic() - tick,
                status=status,
                return_code=rc,
                outputs=files,
                log_sha256=sha((path / "candidate/execution.log").read_bytes()),
                implementation=implementation_hashes(),
            )
        )
        evidence.write_json(path / "candidate/execution.json", execution)
        result = signer.sign(compute_verdict(path, signer.public))
        evidence.write_json(path / "verdict.json", result)
        replay(path, signer.public)
        completed.append(
            {
                "path": str(path),
                "verdict": result["verdict"],
                "sha256": result["content_sha256"],
            }
        )
    outcome, closed = summarize(completed)
    return outcome, closed, completed
