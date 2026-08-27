from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ContractError


@dataclass(frozen=True)
class WorkloadProfile:
    workload_id: str
    target_path: str
    graph_node_ids: tuple[str, ...]
    gate_id: str
    gate_module: str
    risk: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workload_id": self.workload_id,
            "target_path": self.target_path,
            "graph_node_ids": list(self.graph_node_ids),
            "gate_id": self.gate_id,
            "gate_module": self.gate_module,
            "risk": self.risk,
        }


WORKLOAD_PROFILES = {
    "INTCALC": WorkloadProfile(
        "INTCALC",
        "factory/benchmarks/intcalc_candidate.py",
        ("workload:carddemo-intcalc",),
        "private-intcalc-policy",
        "lightyear_factory.private_benchmark",
        "medium",
    ),
    "POSTTRAN": WorkloadProfile(
        "POSTTRAN",
        "factory/benchmarks/posttran_candidate.py",
        (
            "legacy:jcl-job:POSTTRAN",
            "legacy:cobol-paragraph:CBTRN02C:2000-POST-TRANSACTION",
        ),
        "private-posttran-policy",
        "lightyear_factory.posttran_private",
        "high",
    ),
    "CREASTMT": WorkloadProfile(
        "CREASTMT",
        "factory/benchmarks/statement_candidate.py",
        (
            "legacy:jcl-job:CREASTMT",
            "legacy:cobol-paragraph:CBSTM03A:5000-CREATE-STATEMENT",
        ),
        "private-statement-policy",
        "lightyear_factory.statement_private",
        "medium",
    ),
    "ACCTPL1": WorkloadProfile(
        "ACCTPL1",
        "factory/benchmarks/pli_authorization_candidate.py",
        (
            "legacy:cobol-program:CBACT04C",
            "legacy:db2-table:CARDDEMO.AUTHFRDS",
        ),
        "private-acctpl1-policy",
        "lightyear_factory.pli_private",
        "high",
    ),
}


def workload_profile(workload_id: str | None, target_path: str) -> WorkloadProfile:
    selected = (workload_id or "INTCALC").strip().upper()
    profile = WORKLOAD_PROFILES.get(selected)
    if profile is None:
        raise ContractError(f"Unsupported qualification workload: {selected}")
    if target_path != profile.target_path:
        raise ContractError(
            f"Evaluation target does not match the trusted {selected} workload profile"
        )
    return profile
