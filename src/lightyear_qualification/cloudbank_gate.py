"""Run existing CloudBank journey methods against executable local transfer stores.

This is an observation projection, not a CloudBank service or HTTP/auth emulator.
One target cent maps exactly to one integer journey unit. Transfer operations
project to paired journal entries; native participant journals remain out of scope.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit

from lightyear_data.cloudbank_journeys import Journeys, JourneyFailure, Response
from lightyear_data.service_journeys import cloudbank_pack
from lightyear_workflow.service_pack import validate_pack

from .campaign import builtin, invoke, fault_outcome
from .protocol import ObservationError, normalize

METHODS = ("success", "invalid", "insufficient", "concurrent", "account_restart")
FAULTS = {"wrong-recipient": "success", "lost-on-restart": "success", "lost-update": "concurrent"}
OPENING = [{"id": i, "owner": "alice", "cents": n} for i, n in zip("ABC", (1000, 250, 5))]


class ProcessRuntime:
    owner = "alice"

    def __init__(self, directory, adapter, missing=False):
        self.directory, self.adapter, self.missing = directory, adapter, missing
        self.evidence = []
        self.pending, self.results = [], None
        self.barrier, self.lock = threading.Barrier(2, timeout=10), threading.Lock()
        self.concurrent = False

    def close(self):
        # Each invocation has already exited its process and closed its handles.
        return {"status": "restored"}

    def initialize(self):
        initial = self.call({"kind": "initialize", "accounts": OPENING})
        if initial != {"accounts": OPENING, "operations": [], "outcomes": []}:
            raise ObservationError("initial state not established")

    def call(self, command):
        record = invoke(self.adapter, self.directory, command)
        self.evidence.append(record)
        if record.get("error"):
            raise ObservationError(record["error"])
        raw = record.get("raw")
        if self.missing and command["kind"] == "observe":
            # Explicit observation-loss challenge, not a target business fault.
            raw = None
            record["admitted_raw"] = None
        return normalize(raw)

    def restart(self, service):
        # Every invocation really starts a new process against persisted state.
        self.call({"kind": "observe"})

    def request(self, service, method, path, role, body=None, headers=None):
        if service == "transfer":
            query = parse_qs(urlsplit(path).query)
            amount = int(query["amount"][0])
            command = {"kind": "transfer", "id": headers["Idempotency-Key"],
                       "from": "ABC"[int(query["fromAccount"][0]) - 1],
                       "to": "ABC"[int(query["toAccount"][0]) - 1], "actor": self.owner,
                       "date": "2028-02-29", "amount": f"{amount // 100}.{amount % 100:02d}"}
            if self.concurrent:
                with self.lock:
                    self.pending.append(command)
                self.barrier.wait()
                with self.lock:
                    if self.results is None:
                        self.results = self.call({"kind": "concurrent", "operations": self.pending})
                    state = self.results
            else:
                state = self.call(command)
            outcomes = [o for o in state["outcomes"] if o["id"] == command["id"]]
            if len(outcomes) != 1:
                raise ObservationError("missing command outcome")
            status = {"applied": 200, "replayed": 200, "invalid": 400,
                      "insufficient": 409, "forbidden": 403, "conflict": 409}.get(outcomes[0]["status"])
            if status is None:
                raise ObservationError("unknown command outcome")
            return Response(status, b"{}", {})
        if service != "account" or method != "GET":
            raise ObservationError("unsupported journey interface")
        state = self.call({"kind": "observe"})
        account = int(path.split("/")[4])
        rows = [a for a in state["accounts"] if a["id"] == "ABC"[account - 1]]
        if len(rows) != 1 or {a["id"] for a in state["accounts"]} != set("ABC"):
            raise ObservationError("incomplete account observations")
        if path.endswith("/journal"):
            result = []
            for op in state["operations"]:
                # IDs depend on operation identity, never position or sorting.
                identity = int(hashlib.sha256(op["id"].encode()).hexdigest()[:14], 16) * 2
                for offset, (field, kind) in enumerate((("from", "WITHDRAW"), ("to", "DEPOSIT"))):
                    if op[field] == rows[0]["id"]:
                        result.append({"accountId": account, "journalId": identity + offset,
                                       "journalType": kind, "journalAmount": op["cents"]})
        else:
            result = {"accountId": account, "accountCustomerId": rows[0]["owner"],
                      "accountBalance": rows[0]["cents"], "accountOtherDetails": "lightyear-synthetic-journey:ms76"}
        return Response(200, json.dumps(result).encode(), {})


def persisted_witness(directory, fault):
    """Inspect actual SQLite state separately from adapters and journey assertions."""
    path = directory / "accounts.sqlite3"
    if not path.exists():
        return {"observed": False}
    try:
        from contextlib import closing
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            balances = dict(db.execute("SELECT id,cents FROM accounts"))
            operations = list(db.execute("SELECT src,dst,cents FROM operations"))
    except sqlite3.Error:
        return {"observed": False, "reason": "persisted-state-unavailable"}
    observed = False
    if fault == "wrong-recipient":
        observed = balances == {"A": 975, "B": 250, "C": 30}
    elif fault == "lost-on-restart":
        observed = balances == {"A": 975, "B": 275, "C": 5} and not operations
    elif fault == "lost-update":
        observed = len(operations) == 2 and balances != {"A": 1000, "B": 250, "C": 5}
    return {"observed": observed, "balances": balances, "operations": operations}


def run_challenge(method, target="sqlite", fault="", missing=False):
    runtime = None
    with tempfile.TemporaryDirectory(prefix="ms76-cloudbank-") as temporary:
        directory = Path(temporary)
        try:
            runtime = ProcessRuntime(directory, builtin(target, fault), missing)
            runtime.initialize()
            declaration = cloudbank_pack().raw
            declaration["journeys"] = [j for j in declaration["journeys"] if j["macro"] in METHODS]
            driver = Journeys(runtime, "ms76", timeout=0, pause=lambda _: None,
                              pack=validate_pack(declaration))
            driver.accounts = [1, 2, 3]
            if method == "account_restart":
                driver.success()
            runtime.concurrent = method == "concurrent"
            evidence = getattr(driver, method)()
            verdict, reason = "passed", None
        except ObservationError as exc:
            verdict, reason, evidence = "indeterminate", str(exc), None
        except JourneyFailure as exc:
            verdict, reason, evidence = "failed", str(exc), None
        except (OSError, ValueError, KeyError, TypeError, threading.BrokenBarrierError) as exc:
            verdict, reason, evidence = "indeterminate", type(exc).__name__, None
        witness = persisted_witness(directory, fault) if fault else {"observed": False}
        return {"method": method, "target": target, "fault": fault or None,
                "verdict": verdict, "reason": reason, "gate_evidence": evidence,
                "raw": runtime.evidence if runtime else [], "witness": witness,
                "fault_outcome": fault_outcome(witness["observed"], verdict) if fault else None}


def campaign():
    correct = [run_challenge(method, target) for target in ("sqlite", "journal") for method in METHODS]
    faults = [run_challenge(method, fault=fault) for fault, method in FAULTS.items()]
    missing = run_challenge("success", missing=True)
    control = run_challenge("success", fault="round-down")
    return {"gate": "lightyear_data.cloudbank_journeys.Journeys",
            "critical_methods": list(METHODS), "correct": correct, "faults": faults,
            "missing_observation": missing, "unexercised_control": control,
            "status": "passed" if (all(r["verdict"] == "passed" for r in correct)
                       and all(r["fault_outcome"] == "detected" for r in faults)
                       and missing["verdict"] == "indeterminate"
                       and control["fault_outcome"] == "not-exercised") else "failed",
            "excluded": ["HTTP transport and authentication", "native participant journals",
                         "messaging/deposits/clearance", "credit/chat", "distributed and host failures",
                         "decimal rounding, business dates and transfer replay (not asserted by these methods)"],
            "whole_journey_suite_qualified": False}
