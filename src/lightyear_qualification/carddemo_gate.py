"""Challenge the actual CardDemo compare CLI using persisted output mutations.

These are witnessed file mutations after real oracle execution, not claims about
independently authored faulty programs or native COBOL/Java execution.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile

from carddemo_oracle import cli
from carddemo_oracle.demo import create_demo_inputs
from carddemo_oracle.records import RecordError

from .campaign import fault_outcome

FILES = ("acctdata.txt", "transactions.txt")
# Copybook byte ranges; witnesses inspect these bytes without the comparator or parser.
FIELDS = {"balance": ("acctdata.txt", 12, 24), "amount": ("transactions.txt", 132, 143),
          "card-identity": ("transactions.txt", 262, 278), "date": ("transactions.txt", 304, 330),
          "description": ("transactions.txt", 32, 132)}
FAULTS = (*FIELDS, "duplicate", "missing")


def snapshot(directory):
    return {name: (directory / name).read_text(encoding="ascii").splitlines()
            if (directory / name).exists() else None for name in FILES}


def mutate(directory, fault):
    state = snapshot(directory)
    if fault in FIELDS:
        name, start, end = FIELDS[fault]
        record = state[name][0]
        # Replace one significant byte with another valid fixed-width byte.
        offset = end - 2 if fault in {"amount", "balance"} else start
        replacement = "9" if record[offset] != "9" else "8"
        state[name][0] = record[:offset] + replacement + record[offset + 1:]
    elif fault == "duplicate":
        state["transactions.txt"].append(state["transactions.txt"][0])
    elif fault == "missing":
        state["transactions.txt"].pop()
    elif fault == "representation":
        for name in FILES:
            start = 122 if name == "acctdata.txt" else 330
            state[name] = [row[:start] + "X" * (len(row) - start) for row in reversed(state[name])]
    elif fault == "malformed":
        state["transactions.txt"][0] += "TOO-LONG"
    elif fault == "empty":
        state = {name: [] for name in FILES}
    elif fault == "missing-file":
        (directory / "transactions.txt").unlink()
        return
    for name, rows in state.items():
        (directory / name).write_text("".join(row + "\n" for row in rows), encoding="ascii")


def witness(before, after, fault):
    if fault in FIELDS:
        name, start, end = FIELDS[fault]
        return {"observed": before[name][0][start:end] != after[name][0][start:end],
                "file": name, "byte_range": [start, end],
                "before": before[name][0][start:end], "after": after[name][0][start:end]}
    left, right = before["transactions.txt"], after["transactions.txt"]
    observed = ((fault == "duplicate" and right == left + [left[0]])
                or (fault == "missing" and right == left[:-1]))
    return {"observed": observed, "before_records": len(left), "after_records": len(right or [])}


def compare(expected, actual, report_path):
    output = StringIO()
    try:
        with redirect_stdout(output):
            code = cli.main(["compare", "--expected", str(expected), "--actual", str(actual),
                             "--report", str(report_path)])
        report = json.loads(report_path.read_text())
        verdict = report["status"]
        if code != {"passed": 0, "failed": 1, "indeterminate": 2}.get(verdict):
            raise ValueError("gate exit code does not match its verdict")
        return {"verdict": verdict, "exit_code": code, "report": report, "stdout": output.getvalue()}
    except (OSError, RecordError, ValueError) as exc:
        # Existing CLI raises on unavailable/malformed files. The harness records
        # incomplete comparison, never a detected business defect or a pass.
        return {"verdict": "indeterminate", "exit_code": None, "error": type(exc).__name__,
                "stdout": output.getvalue()}


def campaign():
    with tempfile.TemporaryDirectory(prefix="ms76-carddemo-") as temporary:
        root = Path(temporary)
        create_demo_inputs(root / "input")
        expected = root / "expected"
        with redirect_stdout(StringIO()):
            cli.main(["run", "--input", str(root / "input"), "--output", str(expected)])
        baseline = snapshot(expected)
        results = []
        for name in ("correct", "representation", *FAULTS, "malformed", "missing-file", "empty"):
            actual = root / name
            with redirect_stdout(StringIO()):
                cli.main(["run", "--input", str(root / "input"), "--output", str(actual)])
            before = snapshot(actual)
            if before != baseline:
                raise ValueError("correct candidate baseline not established")
            if name != "correct":
                mutate(actual, name)
            observed = snapshot(actual)
            compared = compare(expected, actual, root / (name + ".json"))
            direct = witness(before, observed, name)
            results.append({"id": name, **compared, "raw_expected": deepcopy(baseline),
                            "raw_actual": observed, "witness": direct,
                            "fault_outcome": fault_outcome(direct["observed"], compared["verdict"]) if name in FAULTS else None})
        # Both lanes empty must remain undecidable, even though they agree.
        empty = root / "empty"
        no_evidence = compare(empty, empty, root / "both-empty.json")
        correct = results[:2]
        faults = [r for r in results if r["id"] in FAULTS]
        admission = [r for r in results if r["id"] in {"malformed", "missing-file"}]
        missing_records = next(r for r in results if r["id"] == "empty")
        return {"gate": "carddemo_oracle.cli.main(compare)", "fault_mechanism": "persisted-output-mutation",
                "status": "passed" if (all(r["verdict"] == "passed" for r in correct)
                    and all(r["fault_outcome"] == "detected" for r in faults)
                    and all(r["verdict"] == "indeterminate" for r in admission)
                    and missing_records["verdict"] == "failed" and no_evidence["verdict"] == "indeterminate") else "failed",
                "correct": correct, "faults": faults, "admission": admission,
                "one_sided_empty": missing_records, "both_empty": no_evidence,
                "excluded": ["native COBOL/Java execution", "independent implementation authorship", "estate-wide input coverage"]}
