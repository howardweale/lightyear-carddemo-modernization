"""Decimal/event-journal implementation, separately structured from SQL target.

Uses a local process lock for concurrent commands and atomic journal replacement.
Does not import SQL target, comparator, adapters, or expected observations.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path


def run(request: dict, directory: Path) -> dict:
    path = directory / "journal.json"
    command = request["command"]
    if command["kind"] == "initialize":
        if path.exists():
            raise ValueError("already initialized")
        path.write_text(json.dumps({"opening": command["accounts"], "events": []}), encoding="utf-8")
    journal = json.loads(path.read_text(encoding="utf-8"))
    lock = threading.Lock()

    def balances() -> dict:
        result = {a["id"]: Decimal(a["cents"]) / 100 for a in journal["opening"]}
        for event in journal["events"]:
            result[event["from"]] -= Decimal(event["amount"])
            result[event["to"]] += Decimal(event["amount"])
        return result

    def transfer(op: dict) -> dict:
        with lock:
            outcome = {"id": op["id"], "status": "invalid"}
            amount_text = op.get("amount")
            if not isinstance(amount_text, str) or not re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,4})?", amount_text):
                return outcome
            amount = Decimal(amount_text).quantize(Decimal(".01"), rounding=ROUND_HALF_EVEN)
            try:
                day = datetime.strptime(op["date"], "%Y-%m-%d").strftime("%Y-%m-%d")
                assert day == op["date"]
            except (ValueError, KeyError, TypeError, AssertionError):
                return outcome
            owners = {a["id"]: a["owner"] for a in journal["opening"]}
            if amount <= 0 or op["from"] not in owners or op["to"] not in owners or op["from"] == op["to"]:
                return outcome
            if owners[op["from"]] != op["actor"]:
                return {**outcome, "status": "forbidden"}
            event = {"id": op["id"], "from": op["from"], "to": op["to"],
                     "amount": str(amount), "date": day, "actor": op["actor"]}
            previous = next((e for e in journal["events"] if e["id"] == op["id"]), None)
            if previous is not None:
                return {**outcome, "status": "replayed" if previous == event else "conflict"}
            if balances()[op["from"]] < amount:
                return {**outcome, "status": "insufficient"}
            if op.get("crash_after_debit"):
                # Staged changes are never made visible before atomic replacement.
                os._exit(75)
            journal["events"].append(event)
            pending = directory / "pending.json"
            with pending.open("w", encoding="utf-8") as stream:
                json.dump(journal, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, path)
            return {**outcome, "status": "applied"}

    outcomes = []
    if command["kind"] == "transfer":
        outcomes = [transfer(command)]
    elif command["kind"] == "concurrent":
        with ThreadPoolExecutor(max_workers=len(command["operations"])) as pool:
            outcomes = list(pool.map(transfer, command["operations"]))
    elif command["kind"] not in {"initialize", "observe"}:
        raise ValueError("unsupported command")
    values = balances()
    # Deliberately different wire shape, ordering and decimal notation.
    return {
        "encoding": "decimal-journal-v1", "outcomes": list(reversed(outcomes)),
        "accounts": [{"id": a["id"], "owner": a["owner"], "amount": format(values[a["id"]], ".3f")}
                     for a in reversed(journal["opening"])],
        "operations": [{k: v for k, v in event.items() if k != "actor"} for event in reversed(journal["events"])],
    }


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin), Path(sys.argv[1])), sort_keys=True))
