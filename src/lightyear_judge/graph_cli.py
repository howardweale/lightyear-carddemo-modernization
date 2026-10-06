"""Operator commands. No graph is visible until a separate Tower decision."""
import json
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest, verify_envelope
from lightyear_control_tower.status_export import atomic_new
from lightyear_mainframe.zos_evidence import Signer
from .graph_projection import read, build, watch_values, leak_check, sources, sha


def parsers(commands):
    p = commands.add_parser("graph-project")
    for name in ("graph", "evidence", "policy", "source-root", "signing-key", "out"):
        p.add_argument("--"+name, type=Path, required=True)
    for name in ("lane", "customer-id"):
        p.add_argument("--"+name, required=True)
    p.add_argument("--mode", choices=("field","confidential"), required=True)
    p.add_argument("--hybrid",action="store_true")
    p.add_argument("--annotation-ledger",type=Path)
    p.add_argument("--annotation-trust",type=Path)
    p.add_argument("--include-inferred",action="store_true")
    p = commands.add_parser("graph-leak-check")
    for name in ("projection","policy","source-root","evaluation","signing-key","operator-public-key"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--lane",required=True)
    p.add_argument("--tower-root",type=Path)
    p.add_argument("--scope")


def execute(args):
    signer = Signer(args.signing_key)
    if args.command == "graph-project":
        ledger=None
        if args.annotation_ledger:
            from lightyear_factory.annotations import AnnotationLedger
            c=read(args.annotation_trust)
            keys={k:Path(c[k]).read_bytes() for k in ("ledger_key","tower_key","judge_key")}
            ledger=AnnotationLedger(args.annotation_ledger,**keys,scope=c["scope"],inventory_sha256=c["inventory_sha256"])
        return build(args.graph,args.evidence,args.policy,args.lane,args.mode,args.customer_id,
            args.out,signer,source_root=args.source_root,hybrid=args.hybrid,annotation_ledger=ledger,include_inferred=args.include_inferred)
    root=args.projection
    manifest=read(root/"projection-manifest.json")
    lane=read(args.policy)["lanes"][args.lane]
    if (not verify_envelope(manifest,args.operator_public_key.read_bytes()) or
            manifest["lane_sha256"] != digest(lane) or
            manifest["policy_sha256"] != sha(args.policy.read_bytes()) or
            manifest["projection_sha256"] != sha((root/"projection.json.gz").read_bytes())):
        raise ValueError("graph-leak-input-binding")
    text="\n".join("\n".join(v) for v in sources(lane,args.source_root).values())
    from .service import inventory
    before=inventory(args.evaluation)
    watch=watch_values(args.evaluation,args.lane)
    if inventory(args.evaluation) != before:
        raise ValueError("graph-evaluation-changed-during-scan")
    report=leak_check(root,digest(lane),watch,signer,approved_source=text,
                     evaluation_inventory_sha256=digest(before))
    if args.tower_root:
        if not args.scope or any(m["classification"]!="source-literal" for m in report["matches"]):
            raise ValueError("graph-request-refused-protected-matches-or-scope")
        request(args.tower_root,args.scope,root,args.policy,lane,manifest,report)
    return report


def request(tower, scope, root, policy, lane, manifest, report):
    from lightyear_control_tower.requests import identifier
    identifier(scope)
    assets={"projection":(root/"projection.json.gz").read_bytes(),
            "policy":policy.read_bytes(),"lane":canonical(lane),
            "leak_check":(root/"leak-check.json").read_bytes(),
            "manifest":(root/"projection-manifest.json").read_bytes()}
    bound={k:sha(v) for k,v in assets.items()}
    evidence={k:"evidence/verify-graph/"+h+".asset" for k,h in bound.items()}
    for k,v in assets.items():
        target=Path(tower)/evidence[k]
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=v: raise ValueError("graph-evidence-conflict")
        else:
            with target.open("xb") as f: f.write(v)
    exceptions=sorted({m["value_sha256"] for m in report["matches"]})
    summary="Approve public graph context; exceptions require explicit reason tokens: "+(", ".join("source-literal:"+h for h in exceptions) or "none")
    name="graph-"+manifest["projection_sha256"][:24]
    atomic_new(Path(tower)/"work/control-tower/requests"/scope/(name+".json"),
        dict(schema="tower-request/1",id=name,scope=scope,kind="verify-graph-projection",
             bound=bound,evidence=evidence,proposed_by="verify-operator",
             authored_by=["verify-operator"],summary=summary))
