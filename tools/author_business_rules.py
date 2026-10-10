"""Deterministic authoring of public source rules into the existing mappings."""
import json
from pathlib import Path
from lightyear_mainframe.records import load_copybook

ROOT = Path(__file__).resolve().parents[1]
F = lambda p: {"field": p}
N = lambda v: {"number": str(v)}
L = lambda v: {"literal": v}
O = lambda op, *args: {"op": op, "args": list(args)}


def main():
    path = ROOT / "knowledge/mappings/carddemo-intcalc.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    workload = manifest["workloads"][0]
    rules = workload["rules"]
    rules[:] = [r for r in rules if r["id"] != "rule:intcalc:nonzero-rate-emission"]
    rules.append(dict(id="rule:intcalc:nonzero-rate-emission", name="Emit for every nonzero rate",
        statement="A nonzero disclosure rate emits an interest transaction even when truncation makes its amount zero.",
        confidence="observed", derived_from=[dict(node="legacy:cobol-program:CBACT04C", path="app/cbl/CBACT04C.cbl", line_start=214, line_end=217)],
        implemented_by=rules[0]["implemented_by"], verified_by=["scenario:intcalc:synthetic-differential"]))
    bindings = {}
    def bind(names, copybook, field):
        layout = load_copybook(ROOT / f"spec/mainframe/copybooks/{copybook}.cpy")
        item = next(f for f in layout.fields if f.path.split(".")[-1] == field)
        for name in names.split():
            bindings[name] = dict(node=f"legacy:cobol-field:{copybook}:{field}:{item.line}", type={"pic": item.picture})
    bind("input.balance", "CVTRA01Y", "TRAN-CAT-BAL")
    bind("input.rate", "CVTRA02Y", "DIS-INT-RATE")
    bind("output.amount input.total", "CVTRA05Y", "TRAN-AMT")
    bind("input.before_balance output.balance", "CVACT01Y", "ACCT-CURR-BAL")
    bind("input.before_credit output.credit", "CVACT01Y", "ACCT-CURR-CYC-CREDIT")
    bind("input.before_debit output.debit", "CVACT01Y", "ACCT-CURR-CYC-DEBIT")
    # IDs and normalized strings are lexical keys, not arithmetic receiving fields.
    for name, node in {"input.account": "legacy:copybook:CVACT01Y", "input.card": "legacy:copybook:CVACT03Y",
            "input.fallback": "legacy:copybook:CVTRA02Y", "input.boundary": "legacy:copybook:CVTRA01Y",
            "output.account_present": "legacy:copybook:CVACT01Y", "position.last": "legacy:cobol-program:CBACT04C"}.items():
        bindings[name] = {"node": node}
    for name in "present card type category source description contract".split():
        bindings["output."+name] = {"node": "legacy:copybook:CVTRA05Y"}
    nonzero = O("ne", F("input.rate"), N(0))
    amount = O("div", O("mul", F("input.balance"), F("input.rate")), N(1200))
    monthly = dict(form="expression", when=nonzero, value=amount, output="output.amount", target_type={"pic": "S9(09)V99"}, rounding="truncate")
    persisted = O("and", F("output.account_present"), O("eq", F("output.balance"),
        {"assign": O("add", F("input.before_balance"), F("input.total")), "type": {"pic": "S9(10)V99"}, "rounding": "truncate"}),
        O("eq", F("output.credit"), N(0)), O("eq", F("output.debit"), N(0)))
    predicate = lambda when, condition, form="record_predicate": dict(form=form, when=when, condition=condition)
    forms = {
        "account-boundary": predicate(F("input.boundary"), persisted, "sequence_predicate"),
        "disclosure-rate": {**monthly, "when": O("and", nonzero, O("not", F("input.fallback")))},
        "default-rate": {**monthly, "when": O("and", nonzero, F("input.fallback"))},
        "zero-rate": predicate(O("eq", F("input.rate"), N(0)), O("and", O("not", F("output.present")), O("eq", F("output.amount"), N(0)))),
        "monthly-interest": monthly,
        "interest-transaction": predicate(nonzero, O("and", F("output.present"), O("eq", F("output.card"), F("input.card")),
            O("eq", F("output.type"), L("01")), O("eq", F("output.category"), L("0005")), O("eq", F("output.source"), L("System")),
            O("eq", F("output.description"), O("concat", L("Int. for a/c "), F("input.account"))))),
        "account-update": predicate(F("input.boundary"), persisted),
        "source-final-account": predicate(F("position.last"), O("and", F("output.account_present"),
            O("eq", F("output.balance"), F("input.before_balance")), O("eq", F("output.credit"), F("input.before_credit")),
            O("eq", F("output.debit"), F("input.before_debit"))), "sequence_predicate"),
        "fixed-width-contract": predicate(L(True), F("output.contract")),
        "nonzero-rate-emission": dict(form="decision_table", when=L(True), output="output.present",
            rows=[dict(when=O("eq", F("input.rate"), N(0)), then=L(False)), {"else": L(True)}]),
    }
    def fields(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k in {"field", "output"} and isinstance(v, str): yield v
                else: yield from fields(v)
        elif isinstance(value, list):
            for v in value: yield from fields(v)
    for r in rules:
        form = forms[r["id"].split(":")[-1]]
        used = sorted(set(fields(form)))
        r.update(schema="lightyear-business-rule/1", workload=workload["id"], kind="calculation" if form["form"] == "expression" else "decision",
            inputs=sorted({bindings[p]["node"] for p in used if not p.startswith("output.")}),
            outputs=sorted({bindings[p]["node"] for p in used if p.startswith("output.")}),
            bindings={p: bindings[p] for p in used}, executable=form, provenance="source-observed",
            legacy_behaviour="defect-candidate" if r["id"].endswith("source-final-account") else "faithful", decision_ref=None)
    path = ROOT / "knowledge/mappings/carddemo-intcalc-executable.json"
    path.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
