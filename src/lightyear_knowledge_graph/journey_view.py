"""Read-only projection of native journey journals anchored to the local authority."""
from contextlib import closing
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, verify
from lightyear_calibration.journey_order import RUNS
from lightyear_control_tower.decisions import verify_envelope
from lightyear_workflow.campaign_journals import check
from lightyear_workflow.run_store import RunStore
from lightyear_execution.journey_network import InternalOnlyNetwork

CONTROL = Path("work/ms87/operator")


def safe(root, relative):
    path = root / relative
    require(path.resolve().is_relative_to(root.resolve()) and not any(p.is_symlink() for p in (path, *path.parents)), "Unsafe journey path")
    return path


def authority(root):
    return safe(root, CONTROL / "authority.public.pem").read_bytes()


def read_run(root, run_id):
    empty = {"estate_id": "idempiere", "estate_name": "iDempiere", "source": "native-journey-journal", "read_only": True, "run_id": run_id}
    try:
        InternalOnlyNetwork(run_id)
        run = safe(root, RUNS / run_id)
        key = authority(root)
        auth = read_json(safe(root, RUNS / run_id / "authorization.json"))
        plan = read_json(safe(root, RUNS / run_id / "plan.json")); verify(plan)
        require(verify_envelope(auth, key) and auth["run_id"] == run_id and auth["plan"]["plan_sha256"] == plan["content_sha256"], "Authorization differs")
        safe(root, RUNS / run_id / "journal/events.sqlite3")
        with closing(RunStore(run / "journal", read_only=True)) as store:
            events = check(store.events(), auth, key, "journey")
        receipt = None
        if (run / "receipt.json").exists():
            receipt = read_json(safe(root, RUNS / run_id / "receipt.json"))
            require(verify_envelope(receipt, key) and receipt["run_id"] == run_id and receipt["plan_sha256"] == plan["content_sha256"], "Run receipt differs")
            require(events and events[-1]["type"] == "halted", "Missing terminal journal event")
            require(all(events[-1]["payload"].get(k) == v for k,v in receipt.items() if k not in ("signature", "content_sha256")), "Terminal receipt differs from journal")
        return {**empty, "status": receipt["status"] if receipt else "running", "events": events,
                "receipt": receipt, "mode": plan.get("mode", "replay"), "model_calls": plan.get("model_calls", 0), "journal_head_sha256": events[-1]["content_sha256"] if events else None,
                "signature_verified": True, "independently_attested": False,
                "started_at": events[0]["at"] if events else None,
                "requests": pending(root, run_id)}
    except (ValueError, OSError, KeyError, TypeError):
        return {**empty, "status": "invalid", "reason": "The native journey journal could not be verified.", "events": []}


def pending(root, run_id=None):
    key = authority(root); output = []
    folder = safe(root, CONTROL / "requests")
    for path in sorted(folder.glob("*.json")):
        value = read_json(safe(root, path.relative_to(root)))
        require(verify_envelope(value, key), "Decision request signature differs")
        if run_id and value["run_id"] != run_id: continue
        decision_path = safe(root, CONTROL / "decisions" / (value["id"] + ".json"))
        decision = read_json(decision_path) if decision_path.exists() else None
        if decision:
            require(verify_envelope(decision, key) and decision["request_sha256"] == value["content_sha256"], "Decision signature differs")
        output.append({**value, "decision": decision, "status": "recorded" if decision else "awaiting-human"})
    return output


def read_runs(root):
    rows = []
    for run in safe(root, RUNS).glob("journey-*"):
        if not (run / "journal/events.sqlite3").exists(): continue
        result = read_run(root, run.name)
        if result["status"] == "invalid": continue
        rows.append({"run_id": run.name, "started_at": result["started_at"], "terminal": result["status"],
                     "actions_completed": sum(e["type"] == "result" for e in result["events"]), "journal_pruned_at": None})
    rows.sort(key=lambda row: row["started_at"] or "", reverse=True)
    return {"estate": "idempiere", "read_only": True, "runs": rows[:100], "reason": None if rows else "no-runs-recorded"}


def selected(root, run_id=None):
    if not run_id or run_id == "current":
        runs = read_runs(root)["runs"]
        if not runs: return {"status": "unavailable", "reason": "No native journeys recorded for iDempiere."}
        run_id = runs[0]["run_id"]
    return read_run(root, run_id)
