"""Pinned CardDemo bindings and deliberately bounded JCL inspection, never execution."""

import json
import re
from pathlib import Path

from .records import load_copybook
from .source import sha

ROOT = Path(__file__).resolve().parents[2]
BINDINGS = ROOT / "spec/mainframe/carddemo-bindings.json"


def jcl_records(text):
    records = []
    for line in text.splitlines():
        if not line.startswith("//") or line.startswith("//*"):
            continue
        body = line[2:72]
        match = re.match(r"(\S+)\s+(JOB|EXEC|DD|JCLLIB|PROC|SET)\b\s*(.*)", body)
        if match:
            records.append(
                dict(name=match[1], operation=match[2], parameters=match[3].strip())
            )
        elif body[:1].isspace() and records:
            records[-1]["parameters"] += body.strip()
    return records


def inspect_jcl(text):
    result, step, program = [], None, None
    for row in jcl_records(text):
        params = row["parameters"]
        if row["operation"] == "EXEC":
            step = row["name"]
            found = re.search(r"\bPGM=([A-Z0-9]+)", params)
            program = found[1] if found else None
        if row["operation"] != "DD":
            continue
        found = re.search(r"\bDSN=([^,\s]+)", params)
        if not found:
            continue
        dcb = {}
        for name in ("RECFM", "LRECL", "BLKSIZE"):
            m = re.search(r"\b" + name + r"=([A-Z0-9]+)", params)
            if m:
                dcb[name.lower()] = int(m[1]) if m[1].isdigit() else m[1]
        result.append(
            dict(
                step=step,
                dd=row["name"],
                program=program,
                dsn=found[1].strip("'"),
                dcb=dcb,
            )
        )
    return result


def load_bindings(path=BINDINGS):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for filename, expected in data["artifacts"].items():
        if sha((ROOT / filename).read_bytes()) != expected:
            raise ValueError(
                "Pinned binding artifact changed; rebuild and review bindings"
            )
    for item in data["datasets"].values():
        if item.get("copybook"):
            layout = load_copybook(ROOT / item["copybook"])
            if layout.record_length != item["record_length"]:
                raise ValueError("Binding length disagrees with the compiled copybook")
    return data


def dataset_binding(bindings, job, step, dd):
    rows = [
        r for r in bindings["jobs"].get(job, []) if r["step"] == step and r["dd"] == dd
    ]
    if len(rows) != 1 or not rows[0].get("dataset"):
        raise ValueError("Dataset has no unambiguous job/step/DD binding")
    row = rows[0]
    return {**bindings["datasets"][row["dataset"]], **row}


def compare_jcl(bindings, job, text):
    expected = bindings["jobs"].get(job, [])
    actual = inspect_jcl(text)
    findings = []
    for side, rows, other in [
        ("submitted", actual, expected),
        ("pinned", expected, actual),
    ]:
        for row in rows:
            matches = [
                r for r in other if (r["step"], r["dd"]) == (row["step"], row["dd"])
            ]
            if len(matches) != 1:
                findings.append(
                    dict(
                        code="jcl-binding",
                        step=row["step"],
                        dd=row["dd"],
                        reason=f"{side} JCL step/DD has no unique counterpart; supply expanded submitted JCL.",
                    )
                )
            elif side == "submitted":
                ref = matches[0]
                if (
                    row["dsn"] != ref["dsn"]
                    or row["program"] != ref["program"]
                    or row["dcb"] != ref["dcb"]
                ):
                    findings.append(
                        dict(
                            code="jcl-difference",
                            step=row["step"],
                            dd=row["dd"],
                            reason="Submitted JCL dataset, program or DCB differs from the pinned public binding; review the difference.",
                        )
                    )
    return findings
