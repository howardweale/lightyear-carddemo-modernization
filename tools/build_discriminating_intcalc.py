"""New public reference-model fixtures. Never legacy execution or an intake tool."""
import argparse
from dataclasses import replace
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path
from carddemo_oracle.records import Account, CategoryBalance, Disclosure, CardXref
from carddemo_oracle.oracle import run_intcalc, OracleExecutionError

ROOT = Path(__file__).resolve().parents[1]
DATE = "2022071800"
STAMP = "2022-07-18-00.00.00.000000"


def build(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    # Fixed seed is a versioned case matrix; no external or customer records.
    seed = "intcalc-discriminating-public-v1"
    accounts, balances, xrefs = [], [], []
    matrix = [("DIRECT", ["0.39", "0.40", "0.41", "0.79", "0.80", "0.81"]),
              ("MISSING", ["123.45", "9876543.21", "-123.45"]),
              ("OTHER", ["10.01", "2500.99"]), ("FINAL", ["321.67", "15.99"])]
    for i, (group, amounts) in enumerate(matrix, 1):
        aid = f"{i:011d}"
        accounts.append(Account(aid, "Y", D(i*100), D(99999999), D(99999),
            "2020-01-01", "2030-01-01", "2025-01-01", D(i), D(i*2), "00000", group.ljust(10)))
        xrefs.append(CardXref(f"{i:016d}", f"{i:09d}", aid))
        for j, amount in enumerate(amounts, 1):
            balances.append(CategoryBalance(aid, "01", f"{j:04d}", D(amount)))
        balances.append(CategoryBalance(aid, "01", "0099", D("499.95")))
    disclosures = []
    for group, rate in [("DEFAULT", "15.00"), ("DIRECT", "15.00"), ("OTHER", "7.25"), ("FINAL", "22.99")]:
        for category in range(1, 7):
            disclosures.append(Disclosure(group.ljust(10), "01", f"{category:04d}", D(rate)))
        disclosures.append(Disclosure(group.ljust(10), "01", "0099", D(0)))
    before = dict(ACCTFILE=accounts, TCATBALF=balances, DISCGRP=disclosures, XREFFILE=xrefs, TRANSACT=[])
    result = run_intcalc(balances, disclosures, xrefs, accounts, DATE, STAMP, "source-faithful")
    images = dict(before=before, after={**before, "ACCTFILE": result.accounts, "TRANSACT": result.transactions})
    datasets = []
    lengths = dict(ACCTFILE=300, TCATBALF=50, DISCGRP=50, XREFFILE=50, TRANSACT=350)
    for phase, streams in images.items():
        (destination/phase).mkdir()
        for dd, rows in streams.items():
            raw = "".join(row.render() for row in rows).encode("cp037")
            file = f"{phase}/{dd}.bin"
            (destination/file).write_bytes(raw)
            datasets.append(dict(file=file, phase=phase, dd=dd, recfm="F", lrecl=lengths[dd], codec="cp037", sha256=sha256(raw).hexdigest()))
    # Separate failure fixture: both the account group and DEFAULT are missing.
    failure = destination/"missing-disclosure"
    failure.mkdir()
    failure_inputs = {**before, "DISCGRP": []}
    failures = []
    for dd, rows in failure_inputs.items():
        raw = "".join(row.render() for row in rows).encode("cp037")
        (failure/(dd+".bin")).write_bytes(raw)
        failures.append(dict(file=f"missing-disclosure/{dd}.bin", sha256=sha256(raw).hexdigest(), lrecl=lengths[dd]))
    try:
        run_intcalc(balances, [], xrefs, accounts, DATE, STAMP)
        raise AssertionError("Missing disclosure unexpectedly succeeded")
    except OracleExecutionError as exc:
        expected_failure = dict(status="execution-failure", message=str(exc), datasets=failures)
    manifest = dict(schema="public-intcalc-reference/1", evidence_class="synthetic-public-reference-model",
        seed=seed, generator="tools/build_discriminating_intcalc.py", generator_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        reference_sha256=sha256((ROOT/"src/carddemo_oracle/oracle.py").read_bytes()).hexdigest(),
        processing_date=DATE, candidate_timestamp=STAMP, datasets=datasets, expected_failure=expected_failure,
        observations=result.observations, limitation="Python source-faithful reference model, not legacy execution.")
    (destination/"run.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True)
    print(json.dumps(build(p.parse_args().output)))
