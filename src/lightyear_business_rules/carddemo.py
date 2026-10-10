"""Adapt public captured fixed records, never fabricate candidate outputs.

Derived input joins are explicit. Rate selection is tested through the observed
transaction amount, not by asserting that a computed rate was observed.
"""
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from carddemo_oracle.records import Account, CategoryBalance, Disclosure, CardXref, Transaction
from .language import require

TYPES = {"ACCTFILE": Account, "TCATBALF": CategoryBalance, "DISCGRP": Disclosure,
         "XREFFILE": CardXref, "TRANSACT": Transaction}


def captured_records(directory):
    directory = Path(directory).resolve()
    require("arrivals" not in directory.parts, "private-arrivals-adapter-refused")
    manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    require(manifest.get("evidence_class") in {"synthetic-public-rehearsal", "synthetic-public-reference-model"}, "public-fixture-required")
    streams, hashes = {}, {}
    for item in manifest["datasets"]:
        path = (directory / item["file"]).resolve()
        require(directory in path.parents and item["recfm"] == "F" and item["codec"] == "cp037", "capture-descriptor")
        raw = path.read_bytes()
        cls = TYPES[item["dd"]]
        require(item["lrecl"] == cls.LENGTH and len(raw) % cls.LENGTH == 0, "record-length")
        key = (item["phase"], item["dd"])
        require(key not in streams, "duplicate-stream")
        streams[key] = [cls.parse(raw[i:i+cls.LENGTH].decode("cp037")) for i in range(0, len(raw), cls.LENGTH)]
        hashes[item["file"]] = sha256(raw).hexdigest()
    rows = adapt(streams)
    for row in rows:
        row["meta"]["evidence_class"] = manifest["evidence_class"]
    return rows, dict(evidence_class=manifest["evidence_class"], dataset_hashes=hashes,
                      run_sha256=sha256((directory / "run.json").read_bytes()).hexdigest(),
                      limitation="Stored synthetic public rehearsal outputs; not a native mainframe observation.")


def adapt(streams):
    before = streams["before", "ACCTFILE"]
    after = streams["after", "ACCTFILE"]
    require(len({a.account_id for a in before}) == len(before) and len({a.account_id for a in after}) == len(after), "duplicate-account")
    accounts = {a.account_id: a for a in before}
    outputs = {a.account_id: a for a in after}
    rates = {(d.group_id.strip(), d.type_code, d.category_code): d.annual_rate for d in streams["before", "DISCGRP"]}
    xrefs = {x.account_id: x.card_number for x in streams["before", "XREFFILE"]}
    old = Counter(t.render() for t in streams["before", "TRANSACT"])
    transactions = []
    for t in streams["after", "TRANSACT"]:
        if old[t.render()]:
            old[t.render()] -= 1
        else:
            transactions.append(t)
    require(not any(old.values()), "preexisting-transaction-removed")
    balances = streams["before", "TCATBALF"]
    # The source emits ordered transactions for nonzero-rate categories. A missing
    # or extra transaction is retained as a disagreement, never silently filtered.
    cursor, rows = 0, []
    totals = {}
    for i, balance in enumerate(balances):
        a = accounts[balance.account_id]
        key = (a.group_id.strip(), balance.type_code, balance.category_code)
        fallback = key not in rates
        rate = rates.get(key, rates.get(("DEFAULT", balance.type_code, balance.category_code)))
        require(rate is not None, "missing-disclosure-capture")
        tx = transactions[cursor] if rate != 0 and cursor < len(transactions) else None
        if rate != 0:
            cursor += 1
        if tx:
            totals[a.account_id] = totals.get(a.account_id, Decimal(0)) + tx.amount
        out = outputs.get(a.account_id)
        row = dict(key=f"category-{i+1}", input=dict(account=a.account_id, balance=str(balance.balance), rate=str(rate),
                   fallback=fallback, before_balance=str(a.current_balance), before_credit=str(a.current_cycle_credit),
                   before_debit=str(a.current_cycle_debit), card=xrefs[a.account_id],
                   boundary=i+1 < len(balances) and balances[i+1].account_id != a.account_id),
                   output=dict(present=tx is not None, amount=str(tx.amount) if tx else "0.00",
                   account_present=out is not None, balance=str(out.current_balance) if out else None,
                   credit=str(out.current_cycle_credit) if out else None, debit=str(out.current_cycle_debit) if out else None,
                   card=tx.card_number if tx else "", type=tx.type_code if tx else "", category=tx.category_code if tx else "",
                   source=tx.source.strip() if tx else "", description=tx.description.strip() if tx else "",
                   contract=out is not None and (not tx or len(tx.render()) == 350) and len(after) == len(before)),
                   meta=dict(evidence_class="synthetic-public-rehearsal"))
        rows.append(row)
    for row in rows:
        row["input"]["total"] = str(totals.get(row["input"]["account"], Decimal(0)))
        row["output"]["contract"] &= cursor == len(transactions)
    return rows
