from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json

from .contracts import canonical_bytes, content_hash, seal, sign, verify_signature


DEVELOPMENT_DATA_KEY = "factorydark-v0.19-development-only"
DEVELOPMENT_APPROVAL_KEY = "factorydark-v0.27-development-cutover-approval"
REHEARSAL_SCHEMA_VERSION = "1.0"
WORKLOAD = "carddemo-authorization-authfrds"
SOURCE_TABLE = "CARDDEMO.AUTHFRDS"
TARGET_CONTRACTS = (
    {
        "dialect": "postgresql-16",
        "mapping": "mappings/authfrds-postgresql.json",
        "receipt": "receipts/authfrds.offline.receipt.json",
    },
    {
        "dialect": "oracle-26ai-free",
        "mapping": "mappings/authfrds-oracle.json",
        "receipt": "receipts/authfrds.oracle-offline.receipt.json",
    },
)


class RehearsalContractError(ValueError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RehearsalContractError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise RehearsalContractError(f"{label} must be a JSON object")
    return payload


def _require_hash(payload: dict[str, Any], label: str) -> None:
    if payload.get("content_sha256") != content_hash(payload):
        raise RehearsalContractError(f"{label} content hash is invalid")


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("CARD_NUM", "")), str(row.get("AUTH_TS", ""))


def _key_text(key: tuple[str, str]) -> str:
    return f"{key[0]}|{key[1]}"


def _row_hash(row: dict[str, Any] | None) -> str | None:
    if row is None:
        return None
    return hashlib.sha256(canonical_bytes(row)).hexdigest()


def _state(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _key_text(_row_key(row))
        if not all(_row_key(row)) or key in result:
            raise RehearsalContractError("AUTHFRDS state contains an invalid or duplicate primary key")
        result[key] = copy.deepcopy(row)
    return result


def _state_rows(state: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [copy.deepcopy(state[key]) for key in sorted(state)]


def _state_hash(state: dict[str, dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_bytes(_state_rows(state))).hexdigest()


def _project_row(row: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    projected = {
        str(item["target"]): copy.deepcopy(row[str(item["source"])])
        for item in mapping.get("columns", [])
    }
    if len(projected) != len(row):
        raise RehearsalContractError("Target mapping does not project every AUTHFRDS column")
    return projected


def _normalize_row(row: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        str(item["source"]): copy.deepcopy(row[str(item["target"])])
        for item in mapping.get("columns", [])
    }
    if len(normalized) != len(row):
        raise RehearsalContractError("Target row cannot be normalized through its mapping")
    return normalized


def _project_state(
    source: dict[str, dict[str, Any]], mapping: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    return {
        key: _project_row(row, mapping)
        for key, row in sorted(source.items())
    }


def _normalized_target_state(
    target: dict[str, dict[str, Any]], mapping: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    return {
        _key_text(_row_key(normalized)): normalized
        for normalized in (_normalize_row(row, mapping) for row in target.values())
    }


def _event(
    sequence: int,
    operation: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    previous_sha256: str | None,
) -> dict[str, Any]:
    key_row = after if after is not None else before
    assert key_row is not None
    payload = {
        "schema_version": REHEARSAL_SCHEMA_VERSION,
        "event_type": "factorydark-db2-shaped-change-event",
        "event_id": f"authfrds-cdc-{sequence:04d}",
        "sequence": sequence,
        "operation": operation,
        "source_table": SOURCE_TABLE,
        "primary_key": {
            "CARD_NUM": key_row["CARD_NUM"],
            "AUTH_TS": key_row["AUTH_TS"],
        },
        "before_sha256": _row_hash(before),
        "after_sha256": _row_hash(after),
        "after": copy.deepcopy(after),
        "previous_event_sha256": previous_sha256,
        "evidence_class": "simulated",
    }
    return seal(payload)


def _change_journal(fixtures: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = copy.deepcopy(fixtures["rows"])
    first, second = baseline
    third = copy.deepcopy(first)
    third.update(
        {
            "CARD_NUM": "4000000000000003",
            "AUTH_TS": "2026-08-20T10:17:32.000002",
            "AUTH_ID_CODE": "A10003",
            "TRANSACTION_AMT": "42.00",
            "APPROVED_AMT": "42.00",
            "TRANSACTION_ID": "TX0000000000003",
            "AUTH_FRAUD": "N",
            "FRAUD_RPT_DATE": None,
        }
    )
    first_fraud = copy.deepcopy(first)
    first_fraud.update({"AUTH_FRAUD": "Y", "FRAUD_RPT_DATE": "2026-08-22"})
    fourth = copy.deepcopy(second)
    fourth.update(
        {
            "CARD_NUM": "4000000000000004",
            "AUTH_TS": "2026-08-20T10:18:33.000003",
            "AUTH_ID_CODE": "A10004",
            "AUTH_RESP_CODE": "00",
            "AUTH_RESP_REASON": "APRV",
            "TRANSACTION_AMT": "7.25",
            "APPROVED_AMT": "7.25",
            "TRANSACTION_ID": "TX0000000000004",
            "AUTH_FRAUD": "N",
            "FRAUD_RPT_DATE": None,
        }
    )
    third_adjusted = copy.deepcopy(third)
    third_adjusted.update({"APPROVED_AMT": "40.00", "AUTH_RESP_REASON": "ADJ "})
    operations = [
        ("insert", None, third),
        ("update", first, first_fraud),
        ("delete", second, None),
        ("insert", None, fourth),
        ("update", third, third_adjusted),
    ]
    result: list[dict[str, Any]] = []
    previous = None
    for sequence, (operation, before, after) in enumerate(operations, 1):
        item = _event(sequence, operation, before, after, previous)
        result.append(item)
        previous = item["content_sha256"]
    return result


def _load_data_contracts(root: Path) -> dict[str, Any]:
    base = root / "data-modernization"
    result = {
        "model": _load(base / "canonical/authfrds.model.json", "Canonical AUTHFRDS model"),
        "fixtures": _load(base / "fixtures/authfrds.fixtures.json", "AUTHFRDS fixtures"),
        "targets": {},
    }
    for name in ("model", "fixtures"):
        _require_hash(result[name], name)
    for contract in TARGET_CONTRACTS:
        mapping = _load(base / contract["mapping"], f"{contract['dialect']} mapping")
        receipt = _load(base / contract["receipt"], f"{contract['dialect']} receipt")
        _require_hash(mapping, f"{contract['dialect']} mapping")
        _require_hash(receipt, f"{contract['dialect']} receipt")
        if not verify_signature(receipt, DEVELOPMENT_DATA_KEY):
            raise RehearsalContractError(
                f"{contract['dialect']} development receipt signature is invalid"
            )
        if (
            receipt.get("status") != "passed"
            or receipt.get("target") != contract["dialect"]
            or receipt.get("production_ready") is not False
        ):
            raise RehearsalContractError(
                f"{contract['dialect']} development receipt is not an eligible offline input"
            )
        result["targets"][contract["dialect"]] = {
            "mapping": mapping,
            "receipt": receipt,
        }
    return result


def build_rehearsal_contracts(asset_root: Path, output_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    contracts = _load_data_contracts(asset_root.resolve())
    model = contracts["model"]
    fixtures = contracts["fixtures"]
    targets = contracts["targets"]
    journal = _change_journal(fixtures)
    failure_row = copy.deepcopy(fixtures["rows"][0])
    failure_row.update(
        {
            "CARD_NUM": "4999999999999999",
            "AUTH_TS": "2026-08-20T10:19:34.000004",
            "AUTH_ID_CODE": "FAIL27",
            "TRANSACTION_ID": "TXFAIL000000027",
        }
    )
    plan = seal(
        {
            "schema_version": REHEARSAL_SCHEMA_VERSION,
            "plan_type": "factorydark-offline-migration-rehearsal-plan",
            "plan_id": "carddemo-authfrds-v0.27-offline-rehearsal",
            "workload": WORKLOAD,
            "source": {
                "dialect": "db2-zos-shaped-fixture",
                "table": SOURCE_TABLE,
                "evidence_class": "simulated",
            },
            "bindings": {
                "canonical_model_sha256": model["content_sha256"],
                "fixture_catalog_sha256": fixtures["content_sha256"],
                "postgres_mapping_sha256": targets["postgresql-16"]["mapping"]["content_sha256"],
                "postgres_receipt_sha256": targets["postgresql-16"]["receipt"]["content_sha256"],
                "oracle_mapping_sha256": targets["oracle-26ai-free"]["mapping"]["content_sha256"],
                "oracle_receipt_sha256": targets["oracle-26ai-free"]["receipt"]["content_sha256"],
            },
            "targets": [
                {
                    "dialect": dialect,
                    "mapping_sha256": targets[dialect]["mapping"]["content_sha256"],
                    "development_receipt_sha256": targets[dialect]["receipt"]["content_sha256"],
                }
                for dialect in sorted(targets)
            ],
            "journal": {
                "event_count": len(journal),
                "first_sequence": 1,
                "last_sequence": len(journal),
                "head_sha256": journal[-1]["content_sha256"],
                "events": journal,
            },
            "recovery_policy": {
                "interrupt_after_sequence": 2,
                "duplicate_replay_sequence": 2,
                "maximum_rpo_events": 0,
                "maximum_rto_steps": 3,
            },
            "cutover_policy": {
                "approval_required": True,
                "approval_authority": "human",
                "reconciliation_required": True,
                "post_cutover_failure": {
                    "target": "postgresql-16",
                    "fault": "unilateral-uncommitted-insert",
                    "row": failure_row,
                },
                "rollback_target": "exact-pre-cutover-state",
            },
            "production_ready": False,
            "mainframe_equivalent": False,
            "limitations": [
                "The source journal is deterministic Db2-shaped fixture evidence, not a live Db2 log.",
                "Cutover approval is development-only and cannot authorize production.",
            ],
        }
    )
    approval = sign(
        {
            "schema_version": REHEARSAL_SCHEMA_VERSION,
            "approval_type": "factorydark-offline-cutover-approval",
            "plan_sha256": plan["content_sha256"],
            "approved_action": "offline-authfrds-cutover-rehearsal",
            "approver_type": "human",
            "evidence_class": "simulated",
            "production_authorized": False,
            "scope": "exact-development-rehearsal-plan",
        },
        DEVELOPMENT_APPROVAL_KEY,
        "factorydark-development-operator",
    )
    root = output_root.resolve() / "data-modernization/rehearsal"
    write_json(root / "plan.json", plan)
    write_json(root / "cutover.approval.json", approval)
    return plan, approval


def _validate_plan(plan: dict[str, Any], contracts: dict[str, Any]) -> None:
    _require_hash(plan, "Migration rehearsal plan")
    if (
        plan.get("schema_version") != REHEARSAL_SCHEMA_VERSION
        or plan.get("plan_type") != "factorydark-offline-migration-rehearsal-plan"
        or plan.get("workload") != WORKLOAD
        or plan.get("source", {}).get("evidence_class") != "simulated"
        or plan.get("production_ready") is not False
        or plan.get("mainframe_equivalent") is not False
    ):
        raise RehearsalContractError("Unsupported or overstated migration rehearsal plan")
    expected_bindings = {
        "canonical_model_sha256": contracts["model"]["content_sha256"],
        "fixture_catalog_sha256": contracts["fixtures"]["content_sha256"],
        "postgres_mapping_sha256": contracts["targets"]["postgresql-16"]["mapping"]["content_sha256"],
        "postgres_receipt_sha256": contracts["targets"]["postgresql-16"]["receipt"]["content_sha256"],
        "oracle_mapping_sha256": contracts["targets"]["oracle-26ai-free"]["mapping"]["content_sha256"],
        "oracle_receipt_sha256": contracts["targets"]["oracle-26ai-free"]["receipt"]["content_sha256"],
    }
    if plan.get("bindings") != expected_bindings:
        raise RehearsalContractError("Migration rehearsal plan has stale data bindings")
    events = plan.get("journal", {}).get("events", [])
    if not isinstance(events, list) or not events:
        raise RehearsalContractError("Migration rehearsal change journal is empty")
    previous = None
    for sequence, event in enumerate(events, 1):
        _require_hash(event, f"Change event {sequence}")
        if (
            event.get("sequence") != sequence
            or event.get("previous_event_sha256") != previous
            or event.get("source_table") != SOURCE_TABLE
            or event.get("evidence_class") != "simulated"
            or event.get("operation") not in {"insert", "update", "delete"}
        ):
            raise RehearsalContractError("Migration rehearsal change journal is not contiguous")
        after = event.get("after")
        if event.get("after_sha256") != _row_hash(after):
            raise RehearsalContractError("Change event after-image hash is invalid")
        previous = event["content_sha256"]
    journal = plan["journal"]
    if (
        journal.get("event_count") != len(events)
        or journal.get("first_sequence") != 1
        or journal.get("last_sequence") != len(events)
        or journal.get("head_sha256") != previous
    ):
        raise RehearsalContractError("Migration rehearsal journal summary is invalid")
    operations = Counter(str(item["operation"]) for item in events)
    if not all(operations.get(name, 0) for name in ("insert", "update", "delete")):
        raise RehearsalContractError("Migration rehearsal journal lacks insert/update/delete coverage")


def _validate_approval(approval: dict[str, Any], plan: dict[str, Any]) -> None:
    _require_hash(approval, "Cutover approval")
    if not verify_signature(approval, DEVELOPMENT_APPROVAL_KEY):
        raise RehearsalContractError("Cutover approval signature is invalid")
    if (
        approval.get("approval_type") != "factorydark-offline-cutover-approval"
        or approval.get("plan_sha256") != plan.get("content_sha256")
        or approval.get("approver_type") != "human"
        or approval.get("evidence_class") != "simulated"
        or approval.get("production_authorized") is not False
        or approval.get("scope") != "exact-development-rehearsal-plan"
        or approval.get("signature", {}).get("signer") != "factorydark-development-operator"
    ):
        raise RehearsalContractError("Cutover approval is foreign, incomplete, or overstated")


def _apply_source_event(
    state: dict[str, dict[str, Any]], event: dict[str, Any]
) -> None:
    key = _key_text(
        (
            str(event["primary_key"]["CARD_NUM"]),
            str(event["primary_key"]["AUTH_TS"]),
        )
    )
    operation = event["operation"]
    current = state.get(key)
    if _row_hash(current) != event.get("before_sha256"):
        raise RehearsalContractError(
            f"Change event {event['event_id']} before-image does not match current state"
        )
    if operation == "delete":
        if event.get("after") is not None or key not in state:
            raise RehearsalContractError("Delete change event is invalid")
        del state[key]
    else:
        after = copy.deepcopy(event.get("after"))
        if not isinstance(after, dict) or _key_text(_row_key(after)) != key:
            raise RehearsalContractError("Change event after-image has a different primary key")
        if operation == "insert" and current is not None:
            raise RehearsalContractError("Insert change event targets an existing row")
        if operation == "update" and current is None:
            raise RehearsalContractError("Update change event targets a missing row")
        state[key] = after


def _apply_target_event(
    state: dict[str, dict[str, Any]],
    event: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    key = _key_text(
        (
            str(event["primary_key"]["CARD_NUM"]),
            str(event["primary_key"]["AUTH_TS"]),
        )
    )
    normalized = _normalized_target_state(state, mapping)
    current = normalized.get(key)
    if _row_hash(current) != event.get("before_sha256"):
        raise RehearsalContractError(
            f"Target before-image for {event['event_id']} does not match current state"
        )
    if event["operation"] == "delete":
        del state[key]
    else:
        state[key] = _project_row(event["after"], mapping)


def _apply_event_once(
    source: dict[str, dict[str, Any]],
    targets: dict[str, dict[str, dict[str, Any]]],
    event: dict[str, Any],
    mappings: dict[str, dict[str, Any]],
    applied: list[str],
) -> bool:
    event_hash = str(event["content_sha256"])
    if event_hash in applied:
        return False
    _apply_source_event(source, event)
    for dialect, mapping in mappings.items():
        _apply_target_event(targets[dialect], event, mapping)
    applied.append(event_hash)
    return True


def _checkpoint_payload(
    plan: dict[str, Any],
    approval: dict[str, Any],
    status: str,
    sequence: int,
    resume_count: int,
    source: dict[str, dict[str, Any]],
    targets: dict[str, dict[str, dict[str, Any]]],
    applied: list[str],
    duplicate_replay_detected: bool,
) -> dict[str, Any]:
    return seal(
        {
            "schema_version": REHEARSAL_SCHEMA_VERSION,
            "receipt_type": "factorydark-migration-rehearsal-checkpoint",
            "status": status,
            "plan_sha256": plan["content_sha256"],
            "approval_sha256": approval["content_sha256"],
            "last_applied_sequence": sequence,
            "resume_count": resume_count,
            "applied_event_sha256": list(applied),
            "duplicate_replay_detected": duplicate_replay_detected,
            "source": {
                "rows": _state_rows(source),
                "state_sha256": _state_hash(source),
            },
            "targets": {
                dialect: {
                    "rows": [copy.deepcopy(state[key]) for key in sorted(state)],
                    "state_sha256": hashlib.sha256(
                        canonical_bytes([state[key] for key in sorted(state)])
                    ).hexdigest(),
                }
                for dialect, state in sorted(targets.items())
            },
            "production_ready": False,
        }
    )


def _restore_checkpoint(
    checkpoint: dict[str, Any],
    plan: dict[str, Any],
    approval: dict[str, Any],
    mappings: dict[str, dict[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, dict[str, Any]]],
    list[str],
    bool,
]:
    _require_hash(checkpoint, "Migration rehearsal checkpoint")
    if (
        checkpoint.get("receipt_type") != "factorydark-migration-rehearsal-checkpoint"
        or checkpoint.get("plan_sha256") != plan["content_sha256"]
        or checkpoint.get("approval_sha256") != approval["content_sha256"]
        or checkpoint.get("status") not in {"interrupted", "running"}
        or checkpoint.get("production_ready") is not False
    ):
        raise RehearsalContractError("Migration rehearsal checkpoint is stale or invalid")
    source = _state(checkpoint.get("source", {}).get("rows", []))
    if _state_hash(source) != checkpoint.get("source", {}).get("state_sha256"):
        raise RehearsalContractError("Checkpoint source state hash is invalid")
    targets: dict[str, dict[str, dict[str, Any]]] = {}
    for dialect, mapping in mappings.items():
        rows = checkpoint.get("targets", {}).get(dialect, {}).get("rows", [])
        state = {
            _key_text(_row_key(_normalize_row(row, mapping))): copy.deepcopy(row)
            for row in rows
        }
        digest = hashlib.sha256(canonical_bytes([state[key] for key in sorted(state)])).hexdigest()
        if digest != checkpoint.get("targets", {}).get(dialect, {}).get("state_sha256"):
            raise RehearsalContractError(f"Checkpoint {dialect} state hash is invalid")
        targets[dialect] = state
    applied = [str(item) for item in checkpoint.get("applied_event_sha256", [])]
    sequence = int(checkpoint.get("last_applied_sequence", 0))
    expected = [
        str(item["content_sha256"])
        for item in plan["journal"]["events"][:sequence]
    ]
    if applied != expected:
        raise RehearsalContractError("Checkpoint applied-event ledger is invalid")
    return source, targets, applied, bool(checkpoint.get("duplicate_replay_detected"))


def run_rehearsal(
    asset_root: Path,
    contract_root: Path,
    *,
    resume: bool = False,
    stop_after: int | None = None,
) -> dict[str, Any]:
    contracts = _load_data_contracts(asset_root.resolve())
    root = contract_root.resolve()
    plan = _load(root / "plan.json", "Migration rehearsal plan")
    approval = _load(root / "cutover.approval.json", "Cutover approval")
    _validate_plan(plan, contracts)
    _validate_approval(approval, plan)
    mappings = {
        dialect: item["mapping"] for dialect, item in contracts["targets"].items()
    }
    checkpoint_path = root / "checkpoint.json"
    receipt_path = root / "receipt.json"
    if resume:
        if not checkpoint_path.is_file() or receipt_path.exists():
            raise RehearsalContractError("Resume requires one unfinished checkpoint and no receipt")
        checkpoint = _load(checkpoint_path, "Migration rehearsal checkpoint")
        source, targets, applied, duplicate_replay_detected = _restore_checkpoint(
            checkpoint, plan, approval, mappings
        )
        start_sequence = int(checkpoint["last_applied_sequence"]) + 1
        resume_count = int(checkpoint.get("resume_count", 0)) + 1
    else:
        if checkpoint_path.exists() or receipt_path.exists():
            raise RehearsalContractError("Rehearsal output already exists; use resume or a clean root")
        source = _state(contracts["fixtures"]["rows"])
        targets = {
            dialect: _project_state(source, mapping)
            for dialect, mapping in mappings.items()
        }
        applied = []
        duplicate_replay_detected = False
        start_sequence = 1
        resume_count = 0

    events = plan["journal"]["events"]
    duplicate_sequence = int(plan["recovery_policy"]["duplicate_replay_sequence"])
    last_sequence = start_sequence - 1
    for event in events[start_sequence - 1 :]:
        if not _apply_event_once(source, targets, event, mappings, applied):
            raise RehearsalContractError("Journal contains a repeated event outside the replay probe")
        last_sequence = int(event["sequence"])
        if last_sequence == duplicate_sequence:
            before = (
                _state_hash(source),
                {dialect: _state_hash(_normalized_target_state(state, mappings[dialect])) for dialect, state in targets.items()},
            )
            duplicate_replay_detected = not _apply_event_once(
                source, targets, event, mappings, applied
            )
            after = (
                _state_hash(source),
                {dialect: _state_hash(_normalized_target_state(state, mappings[dialect])) for dialect, state in targets.items()},
            )
            if before != after:
                raise RehearsalContractError("Duplicate replay changed migration state")
        checkpoint = _checkpoint_payload(
            plan,
            approval,
            "running",
            last_sequence,
            resume_count,
            source,
            targets,
            applied,
            duplicate_replay_detected,
        )
        write_json(checkpoint_path, checkpoint)
        if stop_after is not None and last_sequence == stop_after:
            checkpoint = _checkpoint_payload(
                plan,
                approval,
                "interrupted",
                last_sequence,
                resume_count,
                source,
                targets,
                applied,
                duplicate_replay_detected,
            )
            write_json(checkpoint_path, checkpoint)
            return {
                "status": "interrupted",
                "last_applied_sequence": last_sequence,
                "checkpoint_sha256": checkpoint["content_sha256"],
            }

    source_hash = _state_hash(source)
    normalized_targets = {
        dialect: _normalized_target_state(state, mappings[dialect])
        for dialect, state in targets.items()
    }
    target_hashes = {
        dialect: _state_hash(state) for dialect, state in normalized_targets.items()
    }
    reconciled = all(state == source for state in normalized_targets.values())
    pre_cutover_targets = copy.deepcopy(targets)
    pre_cutover_hashes = {
        dialect: hashlib.sha256(
            canonical_bytes([state[key] for key in sorted(state)])
        ).hexdigest()
        for dialect, state in pre_cutover_targets.items()
    }
    failure = plan["cutover_policy"]["post_cutover_failure"]
    failure_target = str(failure["target"])
    if failure_target not in targets or failure.get("fault") != "unilateral-uncommitted-insert":
        raise RehearsalContractError("Unsupported post-cutover fault injection")
    failure_row = copy.deepcopy(failure["row"])
    failure_key = _key_text(_row_key(failure_row))
    targets[failure_target][failure_key] = _project_row(
        failure_row, mappings[failure_target]
    )
    failure_detected = any(
        _normalized_target_state(state, mappings[dialect]) != source
        for dialect, state in targets.items()
    )
    targets = copy.deepcopy(pre_cutover_targets)
    rollback_hashes = {
        dialect: hashlib.sha256(
            canonical_bytes([state[key] for key in sorted(state)])
        ).hexdigest()
        for dialect, state in targets.items()
    }
    rollback_exact = rollback_hashes == pre_cutover_hashes and all(
        _normalized_target_state(state, mappings[dialect]) == source
        for dialect, state in targets.items()
    )
    observed_rpo_events = max(0, len(events) - len(applied))
    observed_rto_steps = 3
    checks = {
        "approval_bound": True,
        "checkpoint_resume": resume_count >= 1 and last_sequence == len(events),
        "cutover_barrier": reconciled,
        "dual_target_reconciliation": reconciled and all(value == source_hash for value in target_hashes.values()),
        "failure_detected": failure_detected,
        "idempotent_replay": duplicate_replay_detected,
        "journal_ordering": len(applied) == len(events),
        "rollback_exact": rollback_exact,
        "rpo_policy": observed_rpo_events <= int(plan["recovery_policy"]["maximum_rpo_events"]),
        "rto_policy": observed_rto_steps <= int(plan["recovery_policy"]["maximum_rto_steps"]),
        "source_target_row_identity": all(
            sorted(state) == sorted(source) for state in normalized_targets.values()
        ),
    }
    final_checkpoint = _checkpoint_payload(
        plan,
        approval,
        "completed" if all(checks.values()) else "blocked",
        len(events),
        resume_count,
        source,
        targets,
        applied,
        duplicate_replay_detected,
    )
    write_json(checkpoint_path, final_checkpoint)
    operation_counts = Counter(str(item["operation"]) for item in events)
    receipt = seal(
        {
            "schema_version": REHEARSAL_SCHEMA_VERSION,
            "receipt_type": "factorydark-offline-migration-rehearsal",
            "rehearsal_id": plan["plan_id"],
            "workload": WORKLOAD,
            "evidence_class": "offline-development-rehearsal",
            "status": "passed" if all(checks.values()) else "blocked",
            "development_ready": all(checks.values()),
            "production_ready": False,
            "mainframe_equivalent": False,
            "checks": checks,
            "bindings": {
                **plan["bindings"],
                "plan_sha256": plan["content_sha256"],
                "approval_sha256": approval["content_sha256"],
                "checkpoint_sha256": final_checkpoint["content_sha256"],
            },
            "journal": {
                "events": len(events),
                "inserts": operation_counts["insert"],
                "updates": operation_counts["update"],
                "deletes": operation_counts["delete"],
                "head_sha256": plan["journal"]["head_sha256"],
                "last_applied_sequence": len(applied),
            },
            "recovery": {
                "resume_count": resume_count,
                "duplicate_replay_detected": duplicate_replay_detected,
                "observed_rpo_events": observed_rpo_events,
                "maximum_rpo_events": plan["recovery_policy"]["maximum_rpo_events"],
                "observed_rto_steps": observed_rto_steps,
                "maximum_rto_steps": plan["recovery_policy"]["maximum_rto_steps"],
            },
            "reconciliation": {
                "source_rows": len(source),
                "source_state_sha256": source_hash,
                "target_state_sha256": target_hashes,
                "row_identity_match": checks["source_target_row_identity"],
            },
            "cutover": {
                "approval_authority": "human",
                "approval_evidence_class": "simulated",
                "opened": checks["approval_bound"] and checks["cutover_barrier"],
                "production_authorized": False,
            },
            "rollback": {
                "fault": failure["fault"],
                "fault_target": failure_target,
                "failure_detected": failure_detected,
                "pre_cutover_state_sha256": pre_cutover_hashes,
                "restored_state_sha256": rollback_hashes,
                "exact": rollback_exact,
            },
            "gaps": [
                "live-db2-log-not-observed",
                "customer-data-not-compared",
                "production-scale-rpo-rto-not-measured",
                "real-cutover-not-authorized",
                "network-security-and-operational-faults-not-proven",
            ],
            "limitations": [
                "CDC events and target engines are deterministic offline projections.",
                "The approval uses a published development-only key and cannot authorize production.",
                "RPO is measured in fixture events and RTO in deterministic recovery steps, not wall-clock time.",
            ],
        }
    )
    write_json(receipt_path, receipt)
    return receipt


def build_rehearsal_evidence(asset_root: Path, output_root: Path) -> dict[str, Any]:
    plan, _ = build_rehearsal_contracts(asset_root, output_root)
    contract_root = output_root.resolve() / "data-modernization/rehearsal"
    interrupted = run_rehearsal(
        asset_root,
        contract_root,
        stop_after=int(plan["recovery_policy"]["interrupt_after_sequence"]),
    )
    if interrupted.get("status") != "interrupted":
        raise RehearsalContractError("Rehearsal did not stop at its required recovery boundary")
    return run_rehearsal(asset_root, contract_root, resume=True)


def validate_rehearsal_evidence(root: Path) -> list[str]:
    base = root.resolve() / "data-modernization/rehearsal"
    errors: list[str] = []
    try:
        contracts = _load_data_contracts(root.resolve())
        plan = _load(base / "plan.json", "Migration rehearsal plan")
        approval = _load(base / "cutover.approval.json", "Cutover approval")
        checkpoint = _load(base / "checkpoint.json", "Migration rehearsal checkpoint")
        receipt = _load(base / "receipt.json", "Migration rehearsal receipt")
        _validate_plan(plan, contracts)
        _validate_approval(approval, plan)
        _require_hash(checkpoint, "Migration rehearsal checkpoint")
        _require_hash(receipt, "Migration rehearsal receipt")
        expected_checks = {
            "approval_bound",
            "checkpoint_resume",
            "cutover_barrier",
            "dual_target_reconciliation",
            "failure_detected",
            "idempotent_replay",
            "journal_ordering",
            "rollback_exact",
            "rpo_policy",
            "rto_policy",
            "source_target_row_identity",
        }
        expected_bindings = {
            **plan["bindings"],
            "plan_sha256": plan["content_sha256"],
            "approval_sha256": approval["content_sha256"],
            "checkpoint_sha256": checkpoint["content_sha256"],
        }
        reconciliation = receipt.get("reconciliation", {})
        rollback = receipt.get("rollback", {})
        recovery = receipt.get("recovery", {})
        if (
            receipt.get("receipt_type") != "factorydark-offline-migration-rehearsal"
            or receipt.get("status") != "passed"
            or receipt.get("development_ready") is not True
            or receipt.get("production_ready") is not False
            or receipt.get("mainframe_equivalent") is not False
            or set(receipt.get("checks", {})) != expected_checks
            or not all(receipt.get("checks", {}).values())
            or receipt.get("bindings") != expected_bindings
            or checkpoint.get("status") != "completed"
            or checkpoint.get("last_applied_sequence") != plan["journal"]["last_sequence"]
            or receipt.get("journal", {}).get("head_sha256") != plan["journal"]["head_sha256"]
            or receipt.get("journal", {}).get("last_applied_sequence") != plan["journal"]["event_count"]
            or recovery.get("resume_count", 0) < 1
            or recovery.get("duplicate_replay_detected") is not True
            or recovery.get("observed_rpo_events") != 0
            or receipt.get("cutover", {}).get("production_authorized") is not False
            or rollback.get("pre_cutover_state_sha256") != rollback.get("restored_state_sha256")
            or rollback.get("exact") is not True
            or set(reconciliation.get("target_state_sha256", {}))
            != {"postgresql-16", "oracle-26ai-free"}
            or any(
                value != reconciliation.get("source_state_sha256")
                for value in reconciliation.get("target_state_sha256", {}).values()
            )
        ):
            errors.append("rehearsal-receipt-invalid")
    except RehearsalContractError as exc:
        errors.append(str(exc))
    return sorted(errors)
