"""Fixed CloudBank observation lanes. No submitted commands, SQL, or providers.

These checks establish retained-evidence integrity, not current service health
or new semantic equivalence. Existing application verdicts are never rewritten.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from types import MappingProxyType

from lightyear_data.contracts import content_hash, seal
from lightyear_data.cloudbank_publication import BUNDLE, RUN_ID, load_publication
from .execution_policy import load_execution_policy
from .policy import load_policy
from .cloudbank_extensions import KINDS, observe_extension, GRAMMAR, PREVIOUS_GRAMMAR
from .ledger_gate import trust_config

SERVICES = MappingProxyType({
    "account": "cloudbank_transaction_core",
    "azn-server": "cloudbank_production_oauth",
    "chatbot": "cloudbank_edge_ai",
    "checks": "cloudbank_checks_messaging",
    "creditscore": "cloudbank_edge_ai",
    "customer": "cloudbank_customer_postgres",
    "testrunner": "cloudbank_whole_application_equivalence",
    "transfer": "cloudbank_native_wave",
})
LANES = ("contract", "retained-execution")
BOUNDARY = {
    "fresh_cloud_execution": False, "production_ready": False,
    "semantic_verdicts_changed": 0, "decisions_created": 0,
    "ledger_entries_created": 0, "ledger_entries_applied": 0, "model_calls": 0,
}


def input_manifest(root: Path, max_bytes: int) -> dict:
    """Bind the complete declared read scope; refuse links and unbounded input."""
    root = root.resolve()
    files = {}
    total = 0
    scopes = ("src", "factory/cloudbank", "reference-estates/cloudbank", BUNDLE.as_posix())
    for relative in scopes:
        directory = root / relative
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"Missing or symbolic input scope: {relative}")
        for path in sorted(directory.rglob("*")):
            if "__pycache__" in path.parts:
                continue
            if path.is_symlink():
                raise ValueError("Symbolic links are outside the execution scope")
            if not path.is_file() or (relative == "src" and path.suffix != ".py"):
                continue
            total += path.stat().st_size
            if total > max_bytes:
                raise ValueError("Input byte budget exceeded")
            raw = path.read_bytes()
            # Git text checkouts may differ in line endings. Original signed JSON
            # bytes are independently checked by the publication verifier.
            logical = raw.replace(b"\r\n", b"\n")
            files[path.relative_to(root).as_posix()] = hashlib.sha256(logical).hexdigest()
    return {"files": files, "logical_sha256": content_hash(files)}


def build_execution_plan(root: Path) -> dict:
    action_policy = load_policy(root / "control-tower/workflow-policy.json")
    policy = load_execution_policy(root, action_policy)
    inputs = input_manifest(root, policy["max_input_bytes"])
    return seal({
        "artifact_type": "lightyear-cloudbank-execution-plan", "schema_version": "1.0",
        "estate": "CloudBank", "services": list(SERVICES), "lanes": list(LANES),
        "scope": policy["scope"], "policy": policy, "action_policy": action_policy,
        "inputs": inputs, "boundary": BOUNDARY,
        "source_run_id": RUN_ID, "extension_kinds": list(KINDS),
        "grammar": GRAMMAR, "previous_grammar": PREVIOUS_GRAMMAR,
        "decision_trust": trust_config(root),
    })


def action_for(plan: dict, service: str, lane: str) -> dict:
    if not ((service in SERVICES and lane in LANES) or (service == "estate" and lane in KINDS)):
        raise ValueError("Unregistered service or observation lane")
    action = {"service": service, "lane": lane,
              "kind": lane if service == "estate" else "widen-observation" if lane == "contract" else "escalate-lane",
              "plan_sha256": plan["content_sha256"], "scope": plan["scope"]}
    return {**action, "id": content_hash(action)}


def observe(root: Path, service: str, lane: str) -> dict:
    """Deterministic observation only; the controller owns status transitions."""
    if service == "estate":
        return observe_extension(root, lane)
    if service not in SERVICES or lane not in LANES:
        raise ValueError("Unregistered service or lane")
    errors, evidence = [], []
    unavailable = False
    if lane == "contract":
        module = importlib.import_module("lightyear_data." + SERVICES[service])
        try:
            errors = module.validate_artifacts(root)
        except (OSError, ValueError, KeyError, TypeError):
            errors = ["service-contract-unavailable"]
            unavailable = True
        unavailable = unavailable or any("missing" in error or "invalid" in error for error in errors)
        evidence = [p.relative_to(root).as_posix() for p in sorted((root / module.OUTPUT_ROOT).glob("*")) if p.is_file()]
    else:
        try:
            publication = load_publication(root)
            receipt_path = root / publication["receipt_path"]
            receipt = json.loads(receipt_path.read_text())
            if set(receipt["services"]) != set(SERVICES) or service not in receipt["services"]:
                errors.append("retained-service-coverage-invalid")
            evidence = [entry["path"] for entry in publication["files"]]
        except OSError:
            errors.append("retained-publication-unavailable")
            unavailable = True
        except (ValueError, KeyError, TypeError) as exc:
            errors.append("retained-publication-invalid:" + str(exc)[:500])
    return {"service": service, "lane": lane, "errors": sorted(set(errors)),
            "outcome": "unavailable" if unavailable else "mismatch" if errors else "verified",
            "evidence": sorted(set(evidence)), "boundary": BOUNDARY}


def observed_status(observation: dict) -> str:
    if observation["outcome"] == "unavailable":
        return "unavailable"
    if observation["outcome"] == "mismatch":
        return "divergent"
    if observation["service"] == "estate":
        return "verified"
    return "contract-verified" if observation["lane"] == "contract" else "retained-evidence-verified"
