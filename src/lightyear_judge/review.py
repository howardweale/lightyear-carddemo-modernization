"""Operator-only Tower proof import. No approval RPC exists on the agent API."""

import re
from pathlib import Path
from lightyear_control_tower.decisions import verify_envelope, digest
from lightyear_control_tower.status_export import atomic_new
from lightyear_control_tower.verification import verify_decision
from lightyear_mainframe.zos_evidence import Signer, read_json, now
from lightyear_toolkit.workspace import sha


def verify_review(root, config, bundle):
    key = config.get("tower_public_key", "").encode()
    if not isinstance(bundle["trusted_head"], str) or not re.fullmatch(
        r"[a-f0-9]{64}", bundle["trusted_head"]
    ):
        raise ValueError("trusted-head-required")
    if not key:
        raise ValueError("tower-authority-not-bound")
    attempt = bundle["attempt_id"]
    if not isinstance(attempt, str) or not re.fullmatch(
        r"attempt-[a-f0-9]{32}", attempt
    ):
        raise ValueError("attempt-invalid")
    receipt = read_json(root / "receipts" / (attempt + ".json"))
    public_path = root / "public-receipts" / (attempt + ".json")
    public = read_json(public_path)
    producer_key = (root / "authority.public.pem").read_bytes()
    if (
        not verify_envelope(receipt, producer_key)
        or not verify_envelope(public, producer_key)
        or receipt["status"] == "completed"
        or receipt["task_sha256"] != config["content_sha256"]
        or receipt["content_sha256"] != bundle["receipt_sha256"]
        or any(public[k] != receipt[k] for k in ("attempt_id", "task_sha256", "status"))
    ):
        raise ValueError("review-requires-bound-noncompleted-receipt")
    proof = bundle["proof"]
    event = next(
        e
        for e in proof["journal"]["events"]
        if e["content_sha256"] == proof["decision_sha256"]
    )
    bound = event["payload"]["bound"]
    if bound.get("receipt") != sha(public_path.read_bytes()):
        raise ValueError("review-receipt-mismatch")
    decision = verify_decision(
        proof,
        key,
        "verify-attempt-review",
        bound,
        expected_head=bundle["trusted_head"],
        scope=config["task_id"],
        outcomes=["continue", "void"],
    )
    if not decision.get("reason", "").strip():
        raise ValueError("review-reason-required")
    return decision


def queue_decision(root, attempt, proof, expected_head):
    root = Path(root)
    signer = Signer(root / "authority.pem")
    config = read_json(root / "task.json")
    if not verify_envelope(config, signer.public):
        raise ValueError("task-binding-failed")
    # Validate the ID before constructing paths.
    if not re.fullmatch(r"attempt-[a-f0-9]{32}", attempt):
        raise ValueError("attempt-invalid")
    bundle = dict(
        attempt_id=attempt,
        receipt_sha256=read_json(root / "receipts" / (attempt + ".json"))[
            "content_sha256"
        ],
        proof=proof,
        trusted_head=expected_head,
        imported_at_utc=now(),
    )
    verify_review(root, config, bundle)
    atomic_new(root / "operator-decisions" / (attempt + ".json"), signer.sign(bundle))


def request_review(root, tower, task_id, attempt):
    public = read_json(root / "public-receipts" / (attempt + ".json"))
    mirror = "evidence/verify/" + public["content_sha256"] + ".json"
    if not (tower / mirror).exists():
        atomic_new(tower / mirror, public)
    request = dict(
        schema="tower-request/1",
        scope=task_id,
        id="review-" + attempt,
        kind="verify-attempt-review",
        bound={"receipt": sha((tower / mirror).read_bytes())},
        evidence={"receipt": mirror},
        proposed_by="lightyear-verify",
        authored_by=["lightyear-verify"],
        summary="Non-completed attempt requires operator continue or void; attempt remains consumed.",
    )
    path = tower / "work/control-tower/requests" / task_id / (request["id"] + ".json")
    if not path.exists():
        atomic_new(path, request)


def inventory_budget(root, new_limit, *, proof=None, expected_head=None):
    """Prepare a Tower request, or import its exact approved proof, as the operator."""
    from .ledger import Ledger
    from lightyear_control_tower.decisions import ZERO

    root = Path(root)
    config = read_json(root / "task.json")
    if not verify_envelope(config, (root / "authority.public.pem").read_bytes()):
        raise ValueError("task-binding-failed")
    ledger = Ledger(config["evaluation_inventory_sha256"], config["attempt_slots"])
    if ledger.signer.public.decode() != config["inventory_ledger_public_key"]:
        raise ValueError("inventory-authority-changed")
    if proof is not None:
        ledger.grant(new_limit, proof, expected_head, config["task_id"])
        return {"status": "budget-increase-imported"}
    with ledger.locked():
        policy, events = ledger.read()
        if (
            not policy["tower_public_key"]
            or type(new_limit) is not int
            or not policy["effective_limit"] < new_limit <= 100
        ):
            raise ValueError("budget-increase-invalid")
        assets = {
            "inventory": {"inventory_sha256": ledger.inventory_hash},
            "budget": {
                "limit": policy["effective_limit"],
                "used": policy["used"],
                "head": events[-1]["content_sha256"] if events else ZERO,
            },
            "new_limit": {"attempt_slots": new_limit},
        }
    tower = Path(config["tower_workspace"])
    paths = {}
    for name, value in assets.items():
        paths[name] = "evidence/verify/" + digest(value) + ".json"
        if not (tower / paths[name]).exists():
            atomic_new(tower / paths[name], value)
    request_id = "budget-" + digest(assets)
    body = dict(
        schema="tower-request/1",
        scope=config["task_id"],
        id=request_id,
        kind="verify-budget-increase",
        bound={k: digest(v) for k, v in assets.items()},
        evidence=paths,
        proposed_by="lightyear-verify",
        authored_by=["lightyear-verify"],
        summary="Operator proposes a cumulative inventory budget increase; task limits stay unchanged.",
    )
    path = (
        tower
        / "work/control-tower/requests"
        / config["task_id"]
        / (request_id + ".json")
    )
    if not path.exists():
        atomic_new(path, body)
    return {"status": "budget-increase-requested", "request_id": request_id}
