"""Detached paired-run engine, signed journals and an archive-independent index."""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import uuid

from lightyear_control_tower.decisions import canonical, digest, verify_envelope
from lightyear_data.oracle_number_native import number_cases
from .campaigns import CAMPAIGN
from .paired_number import ROOT, plan
from .run_store import RunStore, utcnow
from . import paired_types, paired_types260, campaign_journals

AUTHORITY = ROOT / "operator/authority.json"
INDEX = ROOT / "run-index.sqlite3"


def campaign_plan(root, campaign=CAMPAIGN):
    if campaign == CAMPAIGN:
        return plan(root)
    if campaign == paired_types260.CAMPAIGN:
        return paired_types260.plan(root)
    if campaign == paired_types.CAMPAIGN:
        return paired_types.plan(root)
    raise ValueError('Unknown paired campaign')


def campaign_cases(root, campaign):
    if campaign == CAMPAIGN:
        return number_cases(root)
    if campaign == paired_types260.CAMPAIGN:
        return paired_types260.cases(root)
    if campaign == paired_types.CAMPAIGN:
        return paired_types.cases(root)
    raise ValueError('Unknown paired campaign')


def campaign_compare(case, source, target):
    return paired_types260.compare(case, source, target)


def run_path(root: Path, run_id: str) -> Path:
    if not re.fullmatch(r"(?:number|core100|types260)-[a-f0-9]{32}", run_id):
        raise ValueError("Invalid campaign run ID")
    path = root.resolve() / ROOT / "runs" / run_id
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic campaign run path")
    return path


def public_key(root: Path) -> bytes:
    path = root / AUTHORITY
    value = json.loads(path.read_text(encoding="utf-8"))
    name = value["public_key"]
    if Path(name).name != name:
        raise ValueError("Authority key must be adjacent to configuration")
    return path.with_name(name).read_bytes()


class Signer:
    def __init__(self, root):
        from cryptography.hazmat.primitives import serialization
        path = root / AUTHORITY
        config = json.loads(path.read_text(encoding="utf-8"))
        name = config["private_key"]
        if Path(name).name != name:
            raise ValueError("Invalid authority key path")
        self.public = public_key(root)
        self.key = serialization.load_pem_private_key(path.with_name(name).read_bytes(), password=None)
        if not verify_envelope(self.sign({"probe": "campaign-key"}), self.public):
            raise ValueError("Campaign signing key does not match trust")

    def sign(self, value):
        return {**value, "content_sha256": digest(value), "signature": {"algorithm": "Ed25519",
                "key_id": hashlib.sha256(self.public).hexdigest(),
                "value": base64.b64encode(self.key.sign(canonical(value))).decode()}}


def database(root: Path, *, read_only=False):
    path = root.resolve() / INDEX
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic campaign index path")
    if read_only:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        db.execute("PRAGMA query_only=ON")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=15)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, authorization TEXT NOT NULL, terminal TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS recoveries (sequence INTEGER PRIMARY KEY, run_id TEXT NOT NULL, envelope TEXT NOT NULL)")
        db.commit()
    db.row_factory = sqlite3.Row
    return db


def recovery_for(db, auth, key):
    row = db.execute("SELECT envelope FROM recoveries WHERE run_id=? ORDER BY sequence DESC LIMIT 1", (auth["run_id"],)).fetchone()
    if not row:
        return None
    value = json.loads(row[0])
    if not verify_envelope(value, key) or value.get("record_type") != "paired-campaign-recovery" or value.get("run_id") != auth["run_id"] or value.get("authorization_sha256") != auth["content_sha256"]:
        raise ValueError("Campaign recovery signature invalid")
    return value


def checked_authorization(value, key):
    if not verify_envelope(value, key) or value.get("record_type") != "paired-campaign-authorization" or value.get("campaign_id") not in (CAMPAIGN, paired_types.CAMPAIGN, paired_types260.CAMPAIGN):
        raise ValueError("Campaign authorization signature or scope invalid")
    run_path(Path("."), value["run_id"])
    bound = value["plan"]
    if bound.get('campaign_id') != value['campaign_id']:
        raise ValueError('Authorization and plan campaign differ')
    prefix = {CAMPAIGN: 'number-', paired_types.CAMPAIGN: 'core100-', paired_types260.CAMPAIGN: 'types260-'}[value['campaign_id']]
    if not value['run_id'].startswith(prefix):
        raise ValueError('Run ID differs from campaign scope')
    if bound["plan_sha256"] != digest({k: v for k, v in bound.items() if k != "plan_sha256"}):
        raise ValueError("Authorized plan digest invalid")
    return value


def records(root: Path, campaign=None) -> list[dict]:
    if not (root / INDEX).exists():
        return []
    key = public_key(root)
    with closing(database(root, read_only=True)) as db:
        rows = db.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT 100").fetchall()
    result = []
    for row in rows:
        auth = checked_authorization(json.loads(row["authorization"]), key)
        if auth["run_id"] != row["run_id"] or auth["request_id"] != row["request_id"]:
            raise ValueError("Campaign index identity mismatch")
        terminal = json.loads(row["terminal"]) if row["terminal"] else None
        if terminal and (not verify_envelope(terminal, key) or terminal.get("record_type") != "paired-campaign-summary" or terminal.get("run_id") != auth["run_id"] or terminal.get("authorization_sha256") != auth["content_sha256"]):
            raise ValueError("Campaign terminal summary invalid")
        with closing(database(root, read_only=True)) as db:
            recovery = recovery_for(db, auth, key)
        if campaign is None or auth['campaign_id'] == campaign:
            result.append({"authorization": auth, "terminal": terminal, "recovery": recovery})
    return result


def authorize(root: Path, signer, actor: dict, request: dict) -> tuple[dict, bool]:
    campaign = request.get('campaign_id', CAMPAIGN)
    current = campaign_plan(root, campaign)
    if request.get("plan_sha256") != current["plan_sha256"] or request.get("accept_terms") is not True:
        raise ValueError("Review and accept the current exact campaign terms before starting")
    request_id = str(uuid.UUID(request["request_id"]))
    reason = request.get("reason", "").strip()
    if not 10 <= len(reason) <= 2000:
        raise ValueError("Record an authorization reason of 10–2000 characters")
    with closing(database(root)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT authorization FROM runs WHERE request_id=?", (request_id,)).fetchone()
        if old:
            existing = checked_authorization(json.loads(old[0]), public_key(root))
            if existing["plan"]["plan_sha256"] != current["plan_sha256"] or existing["actor"] != actor:
                raise ValueError("Request ID already belongs to a different authorization")
            return existing, False
        for row in db.execute("SELECT authorization, terminal FROM runs"):
            prior = checked_authorization(json.loads(row[0]), public_key(root))
            terminal = json.loads(row[1]) if row[1] else None
            recovered = recovery_for(db, prior, public_key(root))
            if not terminal or not verify_envelope(terminal, public_key(root)) or terminal.get("authorization_sha256") != prior["content_sha256"] or not (terminal.get("cleanup", {}).get("complete") or (recovered or {}).get("cleanup", {}).get("complete")):
                raise ValueError("Another campaign is active or requires cleanup recovery")
        auth = signer.sign({"record_type": "paired-campaign-authorization", "campaign_id": campaign,
                            "run_id": {CAMPAIGN: 'number-', paired_types.CAMPAIGN: 'core100-', paired_types260.CAMPAIGN: 'types260-'}[campaign] + uuid.uuid4().hex, "request_id": request_id, "actor": actor,
                            "authorized_at": utcnow(), "start_before": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                            "reason": reason, "plan": current})
        db.execute("INSERT INTO runs VALUES (?, ?, ?, NULL)", (auth["run_id"], request_id, canonical(auth).decode()))
    return auth, True


def get_authorization(root, run_id):
    key = public_key(root)
    with closing(database(root, read_only=True)) as db:
        row = db.execute("SELECT authorization FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        raise ValueError("Campaign run is not registered")
    auth = checked_authorization(json.loads(row[0]), key)
    if auth["run_id"] != run_id:
        raise ValueError("Campaign index run mismatch")
    return auth


def verified_events(root, auth):
    return campaign_journals.read(run_path(root, auth['run_id']), auth, public_key(root))


def project(root, auth, events):
    case_map = {c["id"]: c for c in campaign_cases(root, auth['campaign_id'])}
    if [c['id'] for c in auth['plan']['cases']] != list(case_map):
        raise ValueError('Authorized cases differ from the supported catalog')
    planned = len(case_map)
    source, target, comparisons = {}, {}, {}
    identity = None
    cleanup = None
    error = None
    terminal = None
    native = False
    for event in events:
        kind, p = event["type"], event["payload"]
        if terminal:
            raise ValueError("Events after campaign terminal")
        if kind == "identities":
            if identity is not None:
                raise ValueError("Duplicate database identities")
            identity = p["identities"]
            native = all(identity.get(lane, {}).get("evidence_class") == "native-database-observed" for lane in ("oracle", "alloydb"))
        elif kind == "observation":
            if identity is None or cleanup is not None:
                raise ValueError("Observation outside active identified run")
            lane = p["lane"]
            if lane not in ("oracle", "alloydb") or p["case_id"] not in case_map:
                raise ValueError("Unknown observation lane or case")
            bucket = source if lane == "oracle" else target
            if p["case_id"] in bucket:
                raise ValueError("Duplicate native observation")
            bucket[p["case_id"]] = p["observations"]
            native = native and p.get("evidence_class") == "native-database-observed"
        elif kind == "comparison":
            case_id = p["comparison"]["case_id"]
            if case_id in comparisons or case_id not in source or case_id not in target:
                raise ValueError("Comparison without a unique complete pair")
            expected = campaign_compare(case_map[case_id], source[case_id], target[case_id])
            if p["comparison"] != expected:
                raise ValueError("Comparator replay differs from published result")
            comparisons[case_id] = expected
        elif kind == "cleanup":
            if cleanup is not None:
                raise ValueError("Duplicate cleanup result")
            cleanup = p["cleanup"]
        elif kind == "error":
            error = p["message"]
        elif kind == "terminal":
            terminal = p
        elif kind not in {"started", "stage", "resource-state", "family-start", "family-finished"}:
            raise ValueError("Unknown campaign journal event")
    matched = sum(v["equivalent"] for v in comparisons.values())
    finished = len(source) == len(target) == len(comparisons) == matched == planned and not error
    result = {"campaign_id": auth['campaign_id'], "run_id": auth["run_id"], "authorization": auth,
              "source_completed": len(source), "target_completed": len(target), "comparisons_completed": len(comparisons),
              "matched": matched, "planned_cases": planned, "identities": identity, "cleanup": cleanup,
              "evidence_class": "native-database-observed" if native else "unclassified-or-simulated",
              "case_results": [{"case_id": c["id"], "oracle": source.get(c["id"]), "alloydb": target.get(c["id"]),
                                "comparison": comparisons.get(c["id"])} for c in auth["plan"]["cases"]],
              "error": error, "read_only": True, "events": events, "status": "running" if events else "queued",
              "last_event_at": events[-1]["at"] if events else None}
    if terminal:
        if cleanup is None:
            raise ValueError("Terminal run lacks a cleanup observation")
        status = "passed-bounded-native" if finished and native else "passed-simulated" if finished else "failed"
        if not cleanup["complete"]:
            status = "cleanup-required"
        if terminal["status"] != status:
            raise ValueError("Terminal verdict differs from replay")
        result["status"] = status
    elif events:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(events[-1]["at"])).total_seconds()
        result["activity"] = "recent" if age < 120 else "interrupted-or-unobserved"
    families = []
    for topic in dict.fromkeys(c['topic'] for c in case_map.values()):
        ids = {c['id'] for c in case_map.values() if c['topic'] == topic}
        observed_source = sum(i in source for i in ids)
        observed_target = sum(i in target for i in ids)
        decided = sum(i in comparisons for i in ids)
        equivalent = sum(comparisons[i]['equivalent'] for i in ids if i in comparisons)
        row = {'family': topic, 'planned': len(ids), 'source_completed': observed_source,
               'target_completed': observed_target, 'comparisons_completed': decided, 'matched': equivalent,
               'mismatched': decided - equivalent, 'blocked': len(ids) - decided if terminal else 0,
               'pending': 0 if terminal else len(ids) - decided}
        row['status'] = ('matched' if equivalent == len(ids) else 'mismatched' if row['mismatched'] else
                         'blocked' if terminal else 'running' if observed_source or observed_target else 'pending')
        families.append(row)
    result['families'] = families
    for event in events:
        if event['type'] == 'family-finished':
            actual = next(f for f in families if f['family'] == event['payload']['family'])
            if event['payload']['counts'] != {k: actual[k] for k in ('source_completed', 'target_completed', 'comparisons_completed', 'matched', 'mismatched')}:
                raise ValueError('Signed family summary differs from comparator replay')
    return result


def read_run(root, run_id=None, campaign=CAMPAIGN):
    try:
        rows = records(root, campaign)
        if run_id in (None, "", "current"):
            if not rows:
                return {"status": "unavailable", "reason": "Not run. No paired campaign has been authorized.", "items": []}
            run_id = rows[0]["authorization"]["run_id"]
        auth = get_authorization(root, run_id)
        if auth['campaign_id'] != campaign:
            raise ValueError('Selected run belongs to another campaign')
        events = verified_events(root, auth)
        row = next((r for r in rows if r["authorization"]["run_id"] == run_id), None)
        if row and row["terminal"] and not events:
            return {"status": "unavailable", "reason": "Recorded run journal is missing or pruned. Its signed terminal summary remains in Convergence.", "items": []}
        value = project(root, auth, events)
        value["recovery"] = next((r["recovery"] for r in rows if r["authorization"]["run_id"] == run_id), None)
        return value
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        return {"status": "invalid", "reason": "Campaign journal could not be verified; no result is assumed.", "items": []}


def finish_index(root, auth, result, signer):
    terminal = signer.sign({"record_type": "paired-campaign-summary", "authorization_sha256": auth["content_sha256"],
                           "run_id": auth["run_id"], "status": result["status"], "at": utcnow(),
                           "source_completed": result["source_completed"], "target_completed": result["target_completed"],
                           "matched": result["matched"], "evidence_class": result["evidence_class"], "cleanup": result["cleanup"],
                           "journal_head_sha256": result["events"][-1]["content_sha256"],
                           "families": result['families'], "planned_cases": result['planned_cases'],
                           "comparisons_completed": result['comparisons_completed']})
    with closing(database(root)) as db, db:
        row = db.execute("SELECT terminal FROM runs WHERE run_id=?", (auth["run_id"],)).fetchone()
        if row[0] is not None:
            raise ValueError("Terminal campaign summary is immutable")
        db.execute("UPDATE runs SET terminal=? WHERE run_id=?", (canonical(terminal).decode(), auth["run_id"]))


def execute(root: Path, run_id: str, *, runner_factory=None):
    from .campaign_gcp import GcpRunner
    auth = get_authorization(root, run_id)
    signer = Signer(root)
    directory = run_path(root, run_id)
    store = RunStore(directory)
    runner = None
    def emit(kind, payload):
        if auth['plan'].get('journal_layout') == 'family-v1':
            return campaign_journals.signed_append(store, signer, auth, kind, payload, 'campaign')
        previous = store.events()
        body = signer.sign({**payload, "run_id": run_id, "plan_sha256": auth["plan"]["plan_sha256"],
                            "event_type": kind, "previous_event_sha256": previous[-1]["content_sha256"] if previous else None})
        store.append(kind, body)
    try:
        registered = next(r for r in records(root) if r["authorization"]["run_id"] == run_id)
        if registered["terminal"] and not store.events():
            raise ValueError("A recorded terminal run cannot execute again without its journal")
        if store.events():
            # A process crash can occur after terminal publication but before
            # indexing. Repair that gap; never replay database SQL automatically.
            result = project(root, auth, verified_events(root, auth))
            if result["status"] not in {"running", "queued"}:
                if next(r for r in records(root) if r["authorization"]["run_id"] == run_id)["terminal"] is None:
                    finish_index(root, auth, result, signer)
                return result
            raise ValueError("Existing campaign journal requires explicit recovery, not a retry")
        emit("started", {"message": "Detached engine accepted the signed campaign authorization."})
        try:
            if datetime.now(timezone.utc) >= datetime.fromisoformat(auth["start_before"]):
                raise ValueError("Campaign authorization expired before execution")
            if campaign_plan(root, auth['campaign_id'])["plan_sha256"] != auth["plan"]["plan_sha256"]:
                raise ValueError("Authorized SQL, implementation or resource terms changed")
            runner = (runner_factory or GcpRunner)(root, run_id, auth["plan"], emit)
            runner.prepare()
            emit("identities", {"identities": runner.identities()})
            cases = campaign_cases(root, auth['campaign_id'])
            grouped = auth['plan'].get('families', ['number'])
            for topic in grouped:
                family = [c for c in cases if c['topic'] == topic]
                child = None
                if auth['plan'].get('journal_layout') == 'family-v1':
                    emit('family-start', {'family': topic})
                    child = RunStore(directory / 'families' / topic)
                def case_emit(kind, payload):
                    if child:
                        return campaign_journals.signed_append(child, signer, auth, kind, {**payload, 'family': topic}, topic)
                    return emit(kind, payload)
                source, target, decisions = {}, {}, []
                try:
                    for lane, bucket in (("oracle", source), ("alloydb", target)):
                        emit("stage", {"stage": lane, "message": f"Executing {topic}: {len(family)} bound {lane} cases."})
                        for case in family:
                            bucket[case["id"]] = runner.observe(lane, case)
                            case_emit("observation", {"lane": lane, "case_id": case["id"], "observations": bucket[case["id"]], "evidence_class": runner.evidence_class})
                    emit("stage", {"stage": "comparison", "message": f"Comparing the {topic} family."})
                    for case in family:
                        decision = campaign_compare(case, source[case['id']], target[case['id']])
                        decisions.append(decision)
                        case_emit('comparison', {'comparison': decision})
                    if child:
                        events = child.events()
                        matched = sum(d['equivalent'] for d in decisions)
                        emit('family-finished', {'family': topic, 'event_count': len(events), 'journal_head_sha256': events[-1]['content_sha256'],
                             'counts': {'source_completed': len(source), 'target_completed': len(target), 'comparisons_completed': len(decisions),
                                        'matched': matched, 'mismatched': len(decisions) - matched}})
                finally:
                    if child:
                        child.close()
        except (Exception, KeyboardInterrupt) as exc:
            # Preserve useful, bounded stage diagnostics without client stderr.
            message = str(exc)[:500] if isinstance(exc, (ValueError, TimeoutError, RuntimeError)) else type(exc).__name__
            emit("error", {"message": message})
        finally:
            emit("stage", {"stage": "cleanup", "message": "Restoring stopped resources and deleting owned runner resources."})
            try:
                cleanup = runner.cleanup() if runner else {"complete": True, "resources": {"all": "not-created"}}
            except Exception:
                cleanup = {"complete": False, "resources": {"all": "unconfirmed"}}
            emit("cleanup", {"cleanup": cleanup})
        interim = project(root, auth, verified_events(root, auth))
        good = interim["matched"] == interim["source_completed"] == interim["target_completed"] == interim['planned_cases'] and not interim["error"]
        status = "passed-bounded-native" if good and interim["evidence_class"] == "native-database-observed" else "passed-simulated" if good else "failed"
        if not cleanup["complete"]:
            status = "cleanup-required"
        emit("terminal", {"status": status})
        result = project(root, auth, verified_events(root, auth))
        finish_index(root, auth, result, signer)
        return result
    finally:
        store.close()


def dispatch(root, run_id):
    directory = run_path(root, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    kwargs = {"cwd": root, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "env": {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONUTF8": "1"}}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, "-m", "lightyear_workflow.campaign_engine", "run", "--root", str(root), "--run-id", run_id], **kwargs)


def recover(root, run_id):
    """Explicit operator recovery: stop owned resources; never retry test SQL."""
    from .campaign_gcp import GcpRunner
    auth = get_authorization(root, run_id)
    registered = next(r for r in records(root) if r["authorization"]["run_id"] == run_id)
    completed = registered["recovery"] or registered["terminal"]
    if completed and completed.get("cleanup", {}).get("complete"):
        # An old, already-clean run must never stop a later campaign's primary.
        return {"run_id": run_id, "status": "already-clean", "cleanup": completed["cleanup"], "sql_retried": False}
    signer = Signer(root)
    store = RunStore(run_path(root, run_id))  # Refuses recovery while worker owns it.
    try:
        events = verified_events(root, auth)
        prior = project(root, auth, events)
        terminal_exists = any(e["type"] == "terminal" for e in events)
        def emit(kind, payload):
            if terminal_exists:
                return
            if auth['plan'].get('journal_layout') == 'family-v1':
                return campaign_journals.signed_append(store, signer, auth, kind, payload, 'campaign')
            previous = store.events()
            body = signer.sign({**payload, "run_id": run_id, "plan_sha256": auth["plan"]["plan_sha256"],
                                "event_type": kind, "previous_event_sha256": previous[-1]["content_sha256"] if previous else None})
            store.append(kind, body)
        states = [e["payload"]["state"] for e in events if e["type"] == "resource-state"]
        cleanup = {"complete": True, "resources": {"all": "not-created"}}
        if states:
            runner = GcpRunner(root, run_id, auth["plan"], emit)
            recorded = states[-1]
            if any(recorded.get(k) != runner.state[k] for k in ("run_id", "vm", "firewall", "zone")):
                raise ValueError("Recovery resource ownership differs from authorization")
            runner.state = recorded
            cleanup = runner.cleanup()
        elif terminal_exists and prior["cleanup"]:
            cleanup = prior["cleanup"]
        recovery = signer.sign({"record_type": "paired-campaign-recovery", "authorization_sha256": auth["content_sha256"],
                                "run_id": run_id, "at": utcnow(), "cleanup": cleanup, "sql_retried": False})
        with closing(database(root)) as db, db:
            db.execute("INSERT INTO recoveries(run_id,envelope) VALUES (?,?)", (run_id, canonical(recovery).decode()))
        if not terminal_exists:
            emit("error", {"message": "Interrupted or unconfirmed dispatch recovered; test SQL was not retried."})
            if prior["cleanup"] is None:
                emit("cleanup", {"cleanup": cleanup})
            emit("terminal", {"status": "failed" if (prior["cleanup"] or cleanup)["complete"] else "cleanup-required"})
            result = project(root, auth, verified_events(root, auth))
            finish_index(root, auth, result, signer)
        return recovery
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "recover"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    def interrupted(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)
    if args.command == "recover":
        result = recover(args.root.resolve(), args.run_id)
        print(json.dumps(result))
        return 0 if result["cleanup"]["complete"] else 1
    result = execute(args.root.resolve(), args.run_id)
    print(json.dumps({k: result[k] for k in ("run_id", "status", "matched", "cleanup")}))
    return 0 if result["status"] == "passed-bounded-native" else 1


if __name__ == "__main__":
    raise SystemExit(main())
