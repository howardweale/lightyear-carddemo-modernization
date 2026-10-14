"""Verify retained Phase 1 evidence; never compile or execute the candidate.

The report is an exact copy from GitHub artifact 11772401281 in run 38304981119.
Downloaded ZIP SHA256: 47758364746e38e72be59bb3fd21d1dd5945c43fe5aea4ffd1663ff0e2bef346.
This is historical evidence verification, not a new-head runtime result.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = "docs/factory/posttran-attempt1-phase1-compile2-2026-10-12.json"
AUTHORIZATION = "docs/factory/posttran-phase1-rerun-authorization-2026-10-12.json"
PINNED = {
    REPORT: "f0e919acc7f5d3a7623a2452a0c325ab30b3e9ecb0e2c38b3039f774988a1ab4",
    AUTHORIZATION: "3b729d9b7b07bf5d5df8d851cccc485681027c6e638aeb31f2eca1d28415ece0",
    "docs/factory/posttran-attempt1-phase1-2026-10-12.json":
        "d77d29ccea6c933ad242ec7e88024b0a3a18d7eeaaadde6345a691b244b16321",
}


def verify(root=ROOT):
    def checked(path, expected):
        candidate = root / path
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("missing-or-linked-evidence:" + path)
        raw = candidate.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("retained-binding-changed:" + path)
        return raw

    records = {path: json.loads(checked(path, digest)) for path, digest in PINNED.items()}
    authorization = records[AUTHORIZATION]
    for path, digest in authorization["bound_file_sha256"].items():
        checked(path, digest)
    report = records[REPORT]
    if (report["head"] != "1b1f31769eb85359ef4747258d214ac9bd6b48e9"
            or report["passed"] is not True or report["compile_ordinal"] != 2
            or len(report["cases"]) != 18 or report["phase2_authorized"] is not False):
        raise ValueError("retained-report-contract-invalid")
    for case in report["cases"]:
        if (case["passed"] is not True or case["repeatable"] is not True
                or len(case["runs"]) != 2
                or any(run["structural_passed"] is not True
                       or run["invariant_passed"] is not True or run["failures"]
                       for run in case["runs"])):
            raise ValueError("retained-case-contract-invalid")
    return {"schema": "posttran-retained-verification/1", "verified": True,
            "evidence_head": report["head"], "evidence_run": 38304981119,
            "evidence_artifact": 11772401281, "cases": 18, "repeats_per_case": 2,
            "new_compilations": 0, "new_candidate_executions": 0,
            "phase2_authorized": False}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
