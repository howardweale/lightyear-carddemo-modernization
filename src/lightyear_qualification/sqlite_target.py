"""Integer/SQL implementation. Deliberate faults change execution, not receipts.

This executable must not import the comparator, adapters, or expected observations.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path


FAULTS = ("wrong-recipient", "round-down", "duplicate-effect", "partial-commit",
          "lost-on-restart", "wrong-date", "unauthorized", "lost-update")


def cents(text: str, fault: str) -> int:
    # Integer arithmetic, including ties-to-even, independent of Decimal target.
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,4})?", text):
        raise ValueError("amount")
    whole, _, fraction = text.partition(".")
    digits = fraction.ljust(4, "0")
    value = int(whole) * 100 + int(digits[:2])
    tail = int(digits[2:])
    if fault != "round-down" and (tail > 50 or (tail == 50 and value % 2)):
        value += 1
    if value <= 0:
        raise ValueError("amount")
    return value


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.execute("PRAGMA synchronous=FULL")
    return db


def transfer(path: Path, op: dict, fault: str) -> dict:
    db = connect(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            amount = cents(op["amount"], fault)
            day = date.fromisoformat(op["date"]).isoformat()
            if day != op["date"] or op["from"] == op["to"]:
                raise ValueError("fields")
        except (ValueError, KeyError, TypeError):
            return {"id": op["id"], "status": "invalid"}
        source = db.execute("SELECT owner,cents FROM accounts WHERE id=?", (op["from"],)).fetchone()
        target = db.execute("SELECT owner,cents FROM accounts WHERE id=?", (op["to"],)).fetchone()
        if source is None or target is None:
            return {"id": op["id"], "status": "invalid"}
        if source[0] != op["actor"] and fault != "unauthorized":
            return {"id": op["id"], "status": "forbidden"}
        identity = json.dumps([op["from"], op["to"], amount, day, op["actor"]])
        prior = db.execute("SELECT identity FROM operations WHERE id=?", (op["id"],)).fetchone()
        if prior:
            if prior[0] != identity:
                return {"id": op["id"], "status": "conflict"}
            if fault != "duplicate-effect":
                return {"id": op["id"], "status": "replayed"}
        if source[1] < amount:
            return {"id": op["id"], "status": "insufficient"}
        db.execute("UPDATE accounts SET cents=cents-? WHERE id=?", (amount, op["from"]))
        if op.get("crash_after_debit"):
            if fault == "partial-commit":
                db.execute("COMMIT")
            # Actual process death: SQLite rolls an uncommitted transaction back.
            os._exit(75)
        recipient = "C" if fault == "wrong-recipient" else op["to"]
        db.execute("UPDATE accounts SET cents=cents+? WHERE id=?", (amount, recipient))
        actual_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat() if fault == "wrong-date" else day
        db.execute("INSERT OR REPLACE INTO operations VALUES (?,?,?,?,?,?)",
                   (op["id"], identity, op["from"], recipient, amount, actual_day))
        db.execute("COMMIT")
        return {"id": op["id"], "status": "applied"}
    finally:
        db.close()


def run(request: dict, directory: Path, fault: str = "") -> dict:
    path = directory / "accounts.sqlite3"
    db = connect(path)
    db.executescript("CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, owner TEXT, cents INTEGER);"
                     "CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, identity TEXT, src TEXT, dst TEXT, cents INTEGER, day TEXT);")
    command = request["command"]
    if command["kind"] == "initialize":
        if db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
            raise ValueError("already initialized")
        db.executemany("INSERT INTO accounts VALUES (?,?,?)", [(a["id"], a["owner"], a["cents"]) for a in command["accounts"]])
    if fault == "lost-on-restart" and command["kind"] == "observe":
        # Simulates a target that forgot its persistent replay registry at startup.
        db.execute("DELETE FROM operations")
    outcomes = []
    if command["kind"] == "transfer":
        outcomes = [transfer(path, command, fault)]
    elif command["kind"] == "concurrent":
        before = dict(db.execute("SELECT id,cents FROM accounts"))
        with ThreadPoolExecutor(max_workers=len(command["operations"])) as pool:
            outcomes = list(pool.map(lambda op: transfer(path, op, fault), command["operations"]))
        if fault == "lost-update":
            # An intentionally stale read/modify/write persisted by the application.
            last = command["operations"][-1]
            amount = cents(last["amount"], "")
            db.execute("UPDATE accounts SET cents=? WHERE id=?", (before[last["from"]] - amount, last["from"]))
            db.execute("UPDATE accounts SET cents=? WHERE id=?", (before[last["to"]] + amount, last["to"]))
    elif command["kind"] not in {"initialize", "observe"}:
        raise ValueError("unsupported command")
    result = {
        "encoding": "integer-cents-v1", "outcomes": sorted(outcomes, key=lambda x: x["id"]),
        "accounts": [{"id": i, "owner": o, "cents": c} for i, o, c in db.execute("SELECT * FROM accounts ORDER BY id")],
        "operations": [{"id": i, "from": s, "to": t, "cents": c, "date": d}
                       for i, s, t, c, d in db.execute("SELECT id,src,dst,cents,day FROM operations ORDER BY id")],
    }
    db.close()
    return result


if __name__ == "__main__":
    selected = sys.argv[2] if len(sys.argv) > 2 else ""
    if selected and selected not in FAULTS:
        raise SystemExit("unknown fault")
    print(json.dumps(run(json.load(sys.stdin), Path(sys.argv[1]), selected), sort_keys=True))
