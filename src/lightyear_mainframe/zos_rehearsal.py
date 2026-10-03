"""Public-data rehearsal only. No real z/OS execution or equivalence claim."""

import json
import subprocess
from pathlib import Path

from .records import load_copybook, to_ascii_fixed
from .source import sha
from .zos_bindings import ROOT, load_bindings, dataset_binding
from .zos_bridge import INPUTS, prepare, run_candidate, verdict, replay
from .zos_compare import compare_runs, delta
from .zos_evidence import read_json, write_json
from .zos_intake import intake, decode_run


def verify_fixtures():
    provenance = read_json(ROOT / "tests/mainframe/fixtures/PROVENANCE.json")
    for path, expected in provenance["files"].items():
        if sha((ROOT / path).read_bytes()) != expected:
            raise ValueError("Public fixture bytes changed")
    return provenance


def bridge_self_test():
    provenance = verify_fixtures()
    bindings = load_bindings()
    folder = ROOT / "tests/mainframe/fixtures/public-bridge"
    results = {}
    # Source fixtures disagree at these exact fields. Never alter bridge values.
    expected_differences = {
        "ACCTFILE": [(49, "ACCOUNT-RECORD.ACCT-ADDR-ZIP")],
        "DISCGRP": [(34, "DIS-GROUP-RECORD.DIS-INT-RATE")],
        "TCATBALF": [],
        "XREFFILE": [],
    }
    for dd, file in INPUTS.items():
        b = dataset_binding(bindings, "INTCALC", "STEP15", dd)
        layout = load_copybook(ROOT / b["copybook"])
        source = (folder / (dd + ".ebcdic")).read_bytes()
        actual = to_ascii_fixed(layout, source)
        expected = (folder / file).read_bytes()
        actual_lines = actual.splitlines()
        lines = expected.splitlines()
        if len(lines) != len(actual_lines) or any(
            len(line) > layout.record_length for line in lines
        ):
            raise ValueError("Public ASCII fixture framing mismatch")
        differences = []
        for n, (a, e) in enumerate(zip(actual_lines, lines), 1):
            e = e.ljust(layout.record_length, b" ")
            for f in layout.fields:
                if (
                    a[f.offset : f.offset + f.length]
                    != e[f.offset : f.offset + f.length]
                ):
                    differences.append((n, f.path))
        if differences != expected_differences[dd]:
            raise ValueError("Unexpected bridge mismatch; review source fixture pair")
        # Prove the bridge is precisely transcoding the original, including overpunch.
        if b"".join(actual_lines).decode("ascii").encode("cp037") != source:
            raise ValueError("Bridge lost EBCDIC bytes")
        results[dd] = dict(
            records=len(lines),
            source_sha256=sha(source),
            ascii_fixture_sha256=sha(expected),
            bridge_sha256=sha(actual),
            exact_bytes=actual == expected,
            line_delimiters_normalized=any(b"\r" in x for x in expected.split(b"\n")),
            trailing_blanks_omitted_in_public_ascii=sum(
                len(x) < layout.record_length for x in lines
            ),
            documented_source_disagreements=[
                dict(record=n, field=f) for n, f in differences
            ],
            ebcdic_roundtrip_exact=True,
        )
    return dict(
        schema="zos-bridge-self-test/1",
        status="passed-with-documented-public-fixture-exceptions",
        source_commit=provenance["commit"],
        datasets=results,
        values_rewritten=False,
    )


def rehearse(signer, jar):
    self_test = bridge_self_test()
    arrival, safe = intake(
        ROOT / "tests/mainframe/fixtures/arrival-rehearsal",
        "Synthetic public-data rehearsal, not Maintec/zOS evidence",
        signer,
    )
    runs = sorted((arrival / "runs").iterdir())
    if safe["findings"]:
        raise ValueError(
            "Rehearsal intake unexpectedly has findings; inspect local gaps"
        )
    for run in runs:
        decode_run(run, signer.public)
        delta(run, signer.public)
    deterministic = compare_runs(runs[0], runs[1], signer.public)
    prepare(runs[0], signer.public, signer)
    execution = run_candidate(runs[0], jar, signer.public, signer)
    result = verdict(runs[0], signer.public, signer)
    replayed = replay(runs[0], signer.public)
    if (
        execution["return_code"] != 0
        or result["verdict"] != "equivalent"
        or replayed["status"] != "verified"
    ):
        raise ValueError(
            "Public rehearsal did not reproduce the expected equivalent verdict"
        )
    ignored = (
        subprocess.run(
            ["git", "check-ignore", "--quiet", str(arrival / "manifest.json")],
            cwd=ROOT,
            check=False,
        ).returncode
        == 0
    )
    if not ignored:
        raise ValueError("Arrival data is not git-ignored")
    report = dict(
        schema="zos-rehearsal/1",
        evidence_class="synthetic-public-rehearsal",
        arrival_id=arrival.name,
        intake=safe,
        bridge=self_test,
        determinism_findings=len(deterministic["findings"]),
        timestamp_proposals=len(deterministic["proposals"]),
        java_execution_sha256=execution["content_sha256"],
        verdict_sha256=result["content_sha256"],
        verdict=result["verdict"],
        replay=replayed,
        arrival_ignored=True,
        model_calls=0,
        docker_calls=0,
        native_zos_runs=0,
    )
    write_json(arrival / "rehearsal.json", signer.sign(report))
    return report
