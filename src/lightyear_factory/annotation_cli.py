"""Offline annotation operator commands; signing keys stay at their configured path."""

import json
from pathlib import Path
from .annotations import AnnotationLedger, annotation, health
from .annotation_tools import governor_requests, import_reviews, github_comments
from lightyear_mainframe.zos_evidence import Signer


def parser(subparsers):
    command = subparsers.add_parser("annotate")
    command.add_argument(
        "--ledger", type=Path, default=Path("factory/annotations/ledger.jsonl")
    )
    command.add_argument(
        "--trust",
        type=Path,
        required=True,
        help="Host-owned JSON: ledger_key, tower_key, judge_key PEM paths, scope, inventory_sha256",
    )
    command.add_argument("--signing-key", type=Path)
    subs = command.add_subparsers(dest="annotation_command", required=True)
    add = subs.add_parser("add")
    add.add_argument("--anchor", action="append", required=True)
    add.add_argument("--type", required=True)
    add.add_argument("--text", required=True)
    add.add_argument("--customer", required=True)
    add.add_argument("--review-after", required=True)
    add.add_argument("--scope", default="node")
    subs.add_parser("health")
    subs.add_parser("replay")
    subs.add_parser("refresh-revocations")
    live=subs.add_parser('subscribe-revocations')
    live.add_argument('--projection',type=Path,required=True)
    apply = subs.add_parser("apply")
    apply.add_argument(
        "--event",
        choices=["approve", "reject", "retire", "supersede", "outcome"],
        required=True,
    )
    apply.add_argument("--payload", type=Path, required=True)
    sync = subs.add_parser("review-requests")
    sync.add_argument("--tower-root", type=Path, required=True)
    sync.add_argument("--leak-checks", type=Path, required=True)
    reviews = subs.add_parser("import-reviews")
    reviews.add_argument("--repository", required=True)
    reviews.add_argument("--pr", type=int, required=True)
    reviews.add_argument("--source-commit", required=True)
    reviews.add_argument("--graph", type=Path, required=True)
    reviews.add_argument("--proposal", type=Path, required=True)
    sync = subs.add_parser("sync")
    sync.add_argument("--tower-root", type=Path, required=True)
    sync.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Host-private bundle of Tower proofs, replay attestations, leak checks and watch values",
    )
    status = subs.add_parser("status-export")
    status.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Host-owned JSON with admitted routing, run receipts and projection manifests",
    )
    status.add_argument("--output", type=Path, required=True)


def run(args):
    config = json.loads(args.trust.read_text(encoding="utf-8"))
    keys = {
        k: Path(config[k]).read_bytes()
        for k in ("ledger_key", "tower_key", "judge_key")
    }
    ledger = AnnotationLedger(
        args.ledger,
        **keys,
        scope=config["scope"],
        inventory_sha256=config["inventory_sha256"],
    )
    if args.annotation_command == "health":
        return health(ledger.replay())
    if args.annotation_command == "replay":
        return ledger.replay()
    if args.annotation_command == "review-requests":
        return governor_requests(
            ledger,
            args.tower_root,
            config["scope"],
            json.loads(args.leak_checks.read_bytes()),
        )
    signer = Signer(args.signing_key)
    if args.annotation_command=="refresh-revocations":
        from .revocations import refresh
        refresh(ledger,signer)
        return dict(status="refreshed",model_calls=0)
    if args.annotation_command=='subscribe-revocations':
        from .revocations import subscribe
        return subscribe(ledger,signer,args.projection)
    if args.annotation_command in {"sync", "status-export"}:
        from .knowledge_service import KnowledgeService

        service = KnowledgeService(ledger, signer, getattr(args, "tower_root", None))
        inputs = json.loads(args.input.read_bytes())
        if args.annotation_command == "sync":
            trust = dict(
                tower_key=keys["tower_key"].decode(),
                trusted_head=config["trusted_head"],
                scope=config["scope"],
            )
            return service.sync(trust=trust, **inputs)
        from lightyear_control_tower.status_export import atomic_new

        result = service.status(**inputs)
        atomic_new(args.output, result)
        return result
    if args.annotation_command == "add":
        a = annotation(
            dict(
                customer_id=args.customer,
                anchors=args.anchor,
                scope=args.scope,
                type=args.type,
                text=args.text,
                source="human-review",
                provenance="observed",
                evidence=[],
                visibility="implementer",
                portable=False,
                review_after=args.review_after,
                created_by="operator",
            )
        )
        return ledger.append("create", dict(annotation=a), signer)
    if args.annotation_command == "import-reviews":
        return import_reviews(
            ledger,
            signer,
            json.loads(args.graph.read_bytes()),
            github_comments(args.repository, args.pr),
            json.loads(args.proposal.read_bytes()),
            source_commit=args.source_commit,
        )
    payload = json.loads(args.payload.read_bytes())
    if args.event != "outcome" and payload["trusted_head"] != config["trusted_head"]:
        raise ValueError("fresh Tower head required")
    return ledger.append(
        args.event, payload, signer, expected_head=config.get("trusted_head")
    )
