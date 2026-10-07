"""Offline comparison primitives. A match is NOT an equivalence certificate."""
from collections import Counter
from lightyear_data.contracts import canonical_bytes, seal
from lightyear_data.semantic_core import CompatibilityClass, compare_normalized_rows
from .adapters import OBSERVABLES, Observation


def table_delta(before, after, primary_key=()):
    """Canonical typed rows; primary-key duplicates are evidence failures, not lost rows."""
    if not primary_key:
        b=Counter(canonical_bytes(r) for r in before); a=Counter(canonical_bytes(r) for r in after)
        return {"mode":"multiset","inserted":sorted((k.decode(),v) for k,v in (a-b).items()),
                "deleted":sorted((k.decode(),v) for k,v in (b-a).items())}
    def keyed(rows):
        out={}
        for row in rows:
            if any(k not in row or row[k] is None for k in primary_key): raise ValueError("primary-key-missing")
            key=canonical_bytes([row[k] for k in primary_key])
            if key in out: raise ValueError("duplicate-primary-key")
            out[key]=row
        return out
    b,a=keyed(before),keyed(after)
    return {"mode":"primary-key","inserted":[a[k] for k in sorted(a.keys()-b.keys())],
            "deleted":[b[k] for k in sorted(b.keys()-a.keys())],
            "changed":[{"key":k.decode(),"before":b[k],"after":a[k]} for k in sorted(a.keys()&b.keys()) if a[k]!=b[k]]}


def compare_observations(source: Observation, target: Observation, *, trap_family: int) -> dict:
    source.validate(); target.validate()
    if trap_family not in range(1,26): raise ValueError("unknown-trap")
    differences=[]
    def diff(observable, classification):
        differences.append({"observable":observable,"class":classification,"trap_family":trap_family})
    if trap_family in (18,25):
        diff("unordered-choice",CompatibilityClass.POLICY_DECISION_REQUIRED.value)
    if len(source.result_sets)!=len(target.result_sets):
        diff("result_sets",CompatibilityClass.LOSSY.value)
    else:
        for left,right in zip(source.result_sets,target.result_sets):
            if left["columns"]!=right["columns"] or left["ordered"]!=right["ordered"]:
                diff("result_sets",CompatibilityClass.LOSSY.value); continue
            if left["ordered"]:
                same=left["rows"]==right["rows"]
            else:
                # Reuse the semantic core multiset contract, preserving duplicates.
                l=[seal({"row":r}) for r in left["rows"]]; r=[seal({"row":r}) for r in right["rows"]]
                same=compare_normalized_rows(l,r)["status"] == "passed"
            if not same: diff("result_sets",CompatibilityClass.LOSSY.value)
    for name in OBSERVABLES:
        if name=="result_sets": continue
        if getattr(source,name)!=getattr(target,name):
            policy=name in {"error","row_count_messages","informational_messages"}
            diff(name,(CompatibilityClass.POLICY_DECISION_REQUIRED if policy else CompatibilityClass.LOSSY).value)
    return seal({"schema":"tsql-observation-comparison/1","differences":differences,
                 "observables_match":not differences,"native_receipt_verified":False,
                 "procedure_verdict":"insufficient-evidence","normalizations":[],
                 "note":"No native receipt, reset proof, ledger decision or coverage proof admitted by this primitive."})
