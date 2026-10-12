"""One read model for the Factory Status API, Markdown and unresolved register."""
from datetime import datetime, timezone
from .decisions import digest
from .factory_evidence import PROGRAMS, for_service, decision_view
from .factory_policy import require


def unresolved(evidence, *, overlays=(), pending=(), program=None, kind=None):
    require(program is None or program in PROGRAMS, "unknown-program-filter")
    kinds={"survivor","evidence-gap","twin-limit","pending-review","invalidated-argument","divergence","disagreement"}
    require(kind is None or kind in kinds, "unknown-kind-filter")
    rows=[]
    for name in PROGRAMS:
        prefix="tower-run-38198096890/"+name+"/"
        scopes=evidence.read(prefix+"threshold.json")
        found={}
        for scope,threshold in scopes.items():
            for row in threshold["mutation"]["unresolved_survivors"]:
                item=found.setdefault(row["id"],dict(id=row["id"],program=name,kind="evidence-gap" if "gap" in row["reason"] else "pending-review" if "review" in row["reason"] else "survivor",reason=row["reason"],claim_scopes=[],source=evidence.sources[prefix+"threshold.json"]))
                item["claim_scopes"].append(scope)
        rows.extend(found.values())
        for number,line in enumerate(evidence.read("twin-limits.md").splitlines(),1):
            if line.startswith("| ") and any(word in line.lower() for word in ("unknown","different","unconfirmed","unresolved")):
                rows.append(dict(id="twin-limit-"+str(number),program=name,kind="twin-limit",reason=line.strip("| "),line=number,source=evidence.sources["twin-limits.md"]))
    cases=evidence.read("generated-review311-classification.json")
    for row in cases.get("cases",[]):
        if row.get("classification") not in {"byte-agreement", "equivalent"}:
            rows.append(dict(id=row["id"],program=row["job"],kind="divergence",reason="Historical generated comparison: "+row["classification"],source=evidence.sources["generated-review311-classification.json"]))
    for item in pending:
        rows.append(dict(id=item["id"],program=item["program"],kind="invalidated-argument" if item["kind"]=="invalidated-or-stale-review" else "pending-review",reason=item["kind"],source=dict(sha256=item["source_sha256"],path="Work queue request")))
    for item in overlays:
        if item["kind"]=="legacy-behaviour-disposition" and item["outcome"]=="fix":
            for argument in item["details"]["dependent_arguments"]:
                rows.append(dict(id=argument,program=item["program"],kind="invalidated-argument",reason="Signed legacy fix invalidated this dependent argument",source=dict(sha256=item["source_sha256"],path="Signed Factory journal")))
    rows=[r for r in rows if (program is None or r["program"]==program) and (kind is None or r["kind"]==kind)]
    return dict(available=True,rows=rows,count=len(rows),index_sha256=evidence.sha256,filters=dict(program=program,kind=kind))


def status(evidence, *, overlays=(), pending=(), now=None):
    at=now or datetime.fromisoformat(evidence.index["created_at"])
    if at.tzinfo is None: raise ValueError("status-timezone-required")
    views=[evidence.program(n,overlays=[x for x in overlays if x["program"] in {n,"factory"}],pending=[x for x in pending if x["program"] in {n,"factory"}]) for n in PROGRAMS]
    programs=[]
    for view in views:
        programs.append(dict(program=view["id"],state="not releasable",observed_head=view["observed_head"],
            failed=[r["criterion"] for r in view["checklist"] if r["state"]=="failed"],
            pending=[r["criterion"] for r in view["checklist"] if r["state"]=="pending"],
            raw_kills=view["mutation"]["value"]["raw_kill_fraction"],sources=view["mutation"]["sources"]))
    historical=evidence.read("current-status-before-tower.json")
    ages=[]
    for item in pending:
        created=item.get("created_at")
        start=datetime.fromisoformat(created) if created else None
        if start is not None and start.tzinfo is None: raise ValueError("pending-timezone-required")
        ages.append({**item,"age_seconds":max(0,int((at-start).total_seconds())) if start else None})
    result=dict(schema="factory-status/1",available=True,last_evidence_commit=evidence.index["commit"],index_sha256=evidence.sha256,
        as_of=at.isoformat(),programs=programs,pending_decisions=ages,decision_overlays=list(overlays),
        campaigns=evidence.block(dict(B06=dict(state="engineering hold; no execution authority from this view",window=historical.get("b06_window"),request_due=historical.get("b06_request_due")),B07=dict(state="planning; no model-spend authority from this view",freeze_ready=historical.get("b07_freeze_ready"))),"current-status-before-tower.json"),
        unresolved=unresolved(evidence,overlays=overlays,pending=pending)["count"],
        execution_authorized=False,release_authorized=False,claim="Operator review; not independent attestation. Historical receipts and signed overlays stay separate.")
    result["content_sha256"]=digest(result)
    return result


def markdown(view):
    lines=["# Current factory status","",view["claim"],"",f"Evidence commit: `{view['last_evidence_commit']}`.",f"Snapshot as of: {view['as_of']}.","","| Program | Raw kills | State |","| --- | --- | --- |"]
    for row in view["programs"]:
        lines.append(f"| {row['program']} | {row['raw_kills']} | {row['state']} |")
    lines.append("")
    for row in view["programs"]:
        lines += [f"{row['program']} experiment: `{row['observed_head']}`. Failed: {', '.join(row['failed']) or 'none'}. Pending: {', '.join(row['pending']) or 'none'}."]
    lines += ["","## Campaigns",""]
    for name,row in view["campaigns"]["value"].items():lines.append(f"- {name}: {row['state']}." + (" Window: " + " to ".join(row["window"]) if row.get("window") else ""))
    lines += ["","## Decisions and unresolved evidence","",f"{len(view['pending_decisions'])} installed queue items pending; {view['unresolved']} unresolved rows. An offline documentation snapshot has no live queue installed; zero here does not imply all scientific reviews are complete.","","No execution, model-spend, Phase 2 or release authority follows from this status. Historical decisions stay in their original files and require signed Factory migration.","","## Source hashes",""]
    sources={s["path"]:s for row in view["programs"] for s in row["sources"]}
    sources.update({s["path"]:s for s in view["campaigns"]["sources"]})
    for path,source in sorted(sources.items()):lines.append(f"- `{path}`: `{source['sha256']}`.")
    lines += ["",f"View seal: `{view['content_sha256']}`.","","Generated by the same `factory_status.status` model as `/api/tower/status`. Regenerate with `python -B tools/build_factory_current_status.py`; CI uses `--check`. Operator-owned live installations supply their current signed overlays and pending queue. This committed snapshot has neither.",""]
    return "\n".join(lines)


def read(service,token,route,args):
    evidence=for_service(service)
    if evidence is None:return dict(available=False,reason="Factory public evidence index not installed",rows=[])
    overlays,pending=decision_view(service,token)
    if route=="unresolved":return unresolved(evidence,overlays=overlays,pending=pending,program=args.get("program"),kind=args.get("kind"))
    return status(evidence,overlays=overlays,pending=pending,now=datetime.now(timezone.utc))
