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
        from lightyear_calibration.journey_contracts import current_contract
        contract = current_contract(root)
        campaign = None
        campaign_progress = None
        controller_revisions = 0
        if plan.get("campaign_directory"):
            directory = safe(root, Path(plan["campaign_directory"]))
            campaign_plan = read_json(directory / "plan.json"); verify(campaign_plan)
            linked = campaign_plan
            matched = False
            for _ in range(20):
                matched = matched or linked["content_sha256"] == plan["campaign_plan_sha256"]
                controller_revisions += bool(linked.get('controller_revision'))
                predecessor = linked.get("prior_plan_sha256")
                if not predecessor: break
                require(predecessor and len(predecessor)==64 and all(c in '0123456789abcdef' for c in predecessor), "Campaign ancestry differs")
                linked = read_json(safe(root, (directory / "history" / (predecessor+'.json')).relative_to(root))); verify(linked)
                require(linked['content_sha256']==predecessor, "Campaign predecessor changed")
            require(matched and not linked.get('prior_plan_sha256'), "Campaign plan differs")
            campaign_auth = read_json(directory / "authorization.json")
            require(verify_envelope(campaign_auth,key) and campaign_auth['plan_sha256']==campaign_plan['content_sha256'], "Current campaign authorization differs")
            calls=[]
            for call_path in sorted((directory / "calls").glob('*/receipt.json')):
                call=read_json(safe(root,call_path.relative_to(root)))
                require(verify_envelope(call,key), "Agent call signature differs")
                calls.append(call)
            campaign_progress={'recorded_calls':len(calls),'call_limit':campaign_plan['max_client_invocations'],
                'latest_recorded_role':calls[-1]['role'] if calls else None,
                'calls_with_unknown_usage':sum(c.get('usage') is None for c in calls),
                'input_tokens':sum((c.get('usage') or {}).get('input_tokens',0) for c in calls),
                'output_tokens':sum((c.get('usage') or {}).get('output_tokens',0) for c in calls),
                'scope':'Signed completed-call records only; an in-flight call may have additional unreported usage.'}
            path = directory / "receipt.json"
            if path.exists():
                campaign = read_json(path)
                require(verify_envelope(campaign,key) and campaign["plan_sha256"]==campaign_plan["content_sha256"], "Campaign receipt differs")
                require(any(a["run_id"]==run_id and receipt and a["receipt_sha256"]==receipt["content_sha256"] for a in campaign["attempts"]), "Campaign does not bind this native run")
        return {**empty, "status": receipt["status"] if receipt else "running", "events": events,
                "receipt": receipt, "mode": plan.get("mode", "replay"), "model_calls": plan.get("model_calls", 0), "journal_head_sha256": events[-1]["content_sha256"] if events else None,
                "signature_verified": True, "independently_attested": False,
                "started_at": events[0]["at"] if events else None,
                "requests": pending(root, run_id), "timestamp_contract": contract, "campaign": campaign,
                "campaign_progress": campaign_progress,
                "campaign_controller_revisions": controller_revisions,
                "judge_sha256": plan.get("judge_sha256"), "builder_client": plan.get("builder_client")}
    except (ValueError, OSError, KeyError, TypeError):
        return {**empty, "status": "invalid", "reason": "The native journey journal could not be verified.", "events": []}


def pending(root, run_id=None):
    key = authority(root); output = []
    from lightyear_calibration.journey_contracts import current_contract
    contract = current_contract(root)
    folder = safe(root, CONTROL / "requests")
    for path in sorted(folder.glob("*.json")):
        value = read_json(safe(root, path.relative_to(root)))
        require(verify_envelope(value, key), "Decision request signature differs")
        if run_id and value["run_id"] != run_id: continue
        decision_path = safe(root, CONTROL / "decisions" / (value["id"] + ".json"))
        decision = read_json(decision_path) if decision_path.exists() else None
        if decision:
            require(verify_envelope(decision, key) and decision["request_sha256"] == value["content_sha256"], "Decision signature differs")
        applicable = contract if contract and value.get("action_kind")=="accept-contract-equivalence" and value.get("affected_cases")==["boundary"] else None
        output.append({**value, "decision": decision, "current_contract": applicable,
            "status": "accepted-scoped-contract" if applicable and applicable["effective"] else "review-due" if applicable else "recorded" if decision else "awaiting-human"})
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
