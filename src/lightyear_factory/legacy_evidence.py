from __future__ import annotations

import hashlib
import json
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import ContractError, canonical_hash, safe_relative_path, write_json


LEGACY_EVALUATION_SCHEMA = "1.0"
HISTORICAL_EVIDENCE_SCHEMA = "1.0"
MAX_ARCHIVE_FILES = 1_000
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILE_BYTES = 20 * 1024 * 1024
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
SECRET_PATTERN = re.compile(rb"sk-[A-Za-z0-9_-]{20,}")
RAW_MODEL_FIELDS = {"input", "messages", "output", "prompt", "request", "response"}
WORKLOAD_NODES = {
    "workload:carddemo-intcalc": "INTCALC",
    "workload:carddemo-posttran": "POSTTRAN",
    "workload:carddemo-create-statement": "CREASTMT",
    "workload:carddemo-acctpl1": "ACCTPL1",
}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_hash(payload: dict[str, Any], label: str) -> None:
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        raise ContractError(f"{label} content hash is invalid")


def _contains_raw_model_field(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in RAW_MODEL_FIELDS or _contains_raw_model_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_raw_model_field(item) for item in value)
    return False


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{label} must be a JSON object")
    return payload


def _extract_archive(archive: Path, destination: Path) -> Path:
    if not archive.is_file() or not zipfile.is_zipfile(archive):
        raise ContractError("Legacy evidence must be supplied as a ZIP archive")
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        files = [item for item in infos if not item.is_dir()]
        if not files or len(files) > MAX_ARCHIVE_FILES:
            raise ContractError("Legacy evidence archive file count is invalid")
        if sum(item.file_size for item in files) > MAX_ARCHIVE_BYTES:
            raise ContractError("Legacy evidence archive exceeds the uncompressed size limit")
        seen: set[str] = set()
        for item in infos:
            name = item.filename
            path = PurePosixPath(name)
            mode = (item.external_attr >> 16) & 0xFFFF
            if (
                not name
                or "\\" in name
                or path.is_absolute()
                or ".." in path.parts
                or "." in path.parts
                or (mode and stat.S_ISLNK(mode))
                or item.file_size > MAX_ARCHIVE_FILE_BYTES
            ):
                raise ContractError(f"Unsafe legacy evidence archive member: {name!r}")
            normalized = path.as_posix().rstrip("/")
            if normalized in seen:
                raise ContractError("Legacy evidence archive contains duplicate members")
            seen.add(normalized)
            target = destination.joinpath(*path.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
    receipts = list(destination.rglob("evaluation.receipt.json"))
    if len(receipts) != 1:
        raise ContractError("Legacy archive must contain exactly one evaluation receipt")
    root = receipts[0].parent.resolve()
    if any(
        root not in item.resolve().parents and item.resolve() != root
        for item in destination.rglob("*")
    ):
        raise ContractError("Legacy archive contains files outside its evaluation root")
    return root


def _artifact(run_dir: Path, reference: dict[str, Any]) -> dict[str, Any]:
    relative = safe_relative_path(str(reference.get("path", "")))
    path = (run_dir / relative).resolve()
    if run_dir.resolve() not in path.parents or not path.is_file():
        raise ContractError("Legacy run artifact is missing or escapes the run directory")
    payload = _load_json(path, "Legacy run artifact")
    _valid_hash(payload, "Legacy run artifact")
    if payload.get("content_sha256") != reference.get("content_sha256"):
        raise ContractError("Legacy run artifact reference is stale")
    if payload.get("artifact_type") != reference.get("artifact_type"):
        raise ContractError("Legacy run artifact type disagrees with its reference")
    content = payload.get("content")
    if isinstance(content, dict) and "content_sha256" in content:
        _valid_hash(content, "Legacy artifact content")
    return payload


def _verify_ledger(run_dir: Path, receipt: dict[str, Any]) -> int:
    path = run_dir / "events.jsonl"
    try:
        events = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("Legacy event ledger is invalid") from exc
    previous = None
    for sequence, event in enumerate(events, 1):
        if not isinstance(event, dict):
            raise ContractError("Legacy event ledger contains a non-object event")
        if event.get("sequence") != sequence or event.get("previous_sha256") != previous:
            raise ContractError("Legacy event ledger sequence or chain is invalid")
        if event.get("event_sha256") != canonical_hash(event, {"event_sha256"}):
            raise ContractError("Legacy event ledger event hash is invalid")
        previous = event["event_sha256"]
    if len(events) != receipt.get("event_count") or previous != receipt.get(
        "ledger_head_sha256"
    ):
        raise ContractError("Legacy event ledger disagrees with the run receipt")
    return len(events)


def _snapshot_hashes(
    run_dir: Path,
    receipt: dict[str, Any],
    work_order: dict[str, Any],
    artifacts: dict[str, list[dict[str, Any]]],
) -> tuple[bool, list[str]]:
    allowed = [
        safe_relative_path(str(item))
        for item in work_order.get("scope", {}).get("allowed_paths", [])
    ]
    if not allowed:
        raise ContractError("Legacy work order has no allowed paths")
    workspace = run_dir / "workspace"
    final_bytes: dict[str, bytes] = {}
    for relative in allowed:
        path = (workspace / relative).resolve()
        if workspace.resolve() not in path.parents or not path.is_file():
            raise ContractError("Legacy final workspace does not contain every allowed file")
        final_bytes[relative] = path.read_bytes()
    final_snapshot = {
        relative: hashlib.sha256(content).hexdigest()
        for relative, content in sorted(final_bytes.items())
    }
    if canonical_hash(final_snapshot) != receipt.get("final_snapshot_sha256"):
        raise ContractError("Legacy final workspace snapshot is invalid")

    proposals = artifacts.get("build-proposal", [])
    changes = artifacts.get("change-set", [])
    if len(proposals) != 1 or len(changes) != 1:
        raise ContractError("Legacy repair evidence requires one proposal and one change set")
    edits = proposals[0].get("content", {}).get("edits", [])
    change_rows = changes[0].get("content", {}).get("changes", [])
    initial_bytes = dict(final_bytes)
    for edit in reversed(edits):
        relative = safe_relative_path(str(edit.get("path", "")))
        if relative not in initial_bytes:
            raise ContractError("Legacy edit targets a file outside the allowed snapshot")
        try:
            text = initial_bytes[relative].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError("Legacy exact edit targets a non-text file") from exc
        before = str(edit.get("find", ""))
        after = str(edit.get("replace", ""))
        if not before or not after or text.count(after) != 1:
            raise ContractError("Legacy exact edit cannot reconstruct the initial file")
        initial_bytes[relative] = text.replace(after, before, 1).encode("utf-8")
    change_by_path = {str(item.get("path")): item for item in change_rows}
    changed_paths = sorted(str(item) for item in receipt.get("changed_paths", []))
    if sorted(change_by_path) != changed_paths:
        raise ContractError("Legacy change set disagrees with changed paths")
    for relative, row in change_by_path.items():
        if relative not in initial_bytes or relative not in final_bytes:
            raise ContractError("Legacy change set targets an unresolved file")
        if hashlib.sha256(initial_bytes[relative]).hexdigest() != row.get("before_sha256"):
            raise ContractError("Legacy reconstructed before-file hash is invalid")
        if hashlib.sha256(final_bytes[relative]).hexdigest() != row.get("after_sha256"):
            raise ContractError("Legacy final-file hash is invalid")
    initial_snapshot = {
        relative: hashlib.sha256(content).hexdigest()
        for relative, content in sorted(initial_bytes.items())
    }
    if canonical_hash(initial_snapshot) != receipt.get("initial_snapshot_sha256"):
        raise ContractError("Legacy reconstructed initial snapshot is invalid")
    return True, changed_paths


def _verify_model_run(
    run_dir: Path, receipt: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    _valid_hash(receipt, "Legacy factory run receipt")
    if receipt.get("schema_version") != "1.0" or receipt.get(
        "receipt_type"
    ) != "lightyear-autonomous-factory-run":
        raise ContractError("Unsupported legacy factory run receipt")
    if receipt.get("content_sha256") != result.get("receipt_sha256"):
        raise ContractError("Legacy evaluation result targets a different factory run")
    if receipt.get("status") != result.get("status") or receipt.get("attempts") != result.get(
        "attempts"
    ):
        raise ContractError("Legacy evaluation result disagrees with its factory run")
    work_order = _load_json(run_dir / "work-order.json", "Legacy work order")
    if canonical_hash(work_order) != receipt.get("work_order_sha256"):
        raise ContractError("Legacy work-order identity is invalid")
    if work_order.get("id") != receipt.get("work_order_id"):
        raise ContractError("Legacy work order disagrees with the run receipt")
    event_count = _verify_ledger(run_dir, receipt)

    by_type: dict[str, list[dict[str, Any]]] = {}
    for reference in receipt.get("artifacts", []):
        payload = _artifact(run_dir, reference)
        by_type.setdefault(str(reference.get("artifact_type")), []).append(payload)
    calls = by_type.get("model-call-evidence", [])
    if not calls:
        raise ContractError("Legacy run contains no model-call evidence")
    intelligence = receipt.get("intelligence", {})
    _valid_hash(intelligence, "Legacy model intelligence")
    if intelligence.get("mode") != "model-backed":
        raise ContractError("Legacy historical evidence is not model-backed")
    provider = str(intelligence.get("provider", ""))
    model = str(intelligence.get("model", ""))
    if not provider or not model or provider in {"local-reference", "scripted-test"}:
        raise ContractError("Legacy model provider identity is not eligible for history")
    inner_hashes: list[str] = []
    roles: list[str] = []
    for artifact in calls:
        if artifact.get("schema_version") != "1.0" or artifact.get(
            "run_id"
        ) != receipt.get("run_id"):
            raise ContractError("Legacy model-call envelope targets a different run")
        content = artifact.get("content", {})
        if content.get("schema_version") != "1.0" or content.get(
            "evidence_type"
        ) != "lightyear-model-call":
            raise ContractError("Unsupported legacy model-call evidence")
        if content.get("provider") != provider or content.get("model") != model:
            raise ContractError("Legacy model-call identity disagrees with run intelligence")
        if _contains_raw_model_field(content):
            raise ContractError("Legacy evidence contains a raw model request or response")
        if content.get("store") is not False or content.get("strict_schema") is not True:
            raise ContractError("Legacy model call did not disable storage and require strict output")
        for field in ("request_sha256", "response_sha256"):
            if not HASH_PATTERN.fullmatch(str(content.get(field, ""))):
                raise ContractError("Legacy model-call request/response provenance is incomplete")
        inner_hashes.append(str(content["content_sha256"]))
        roles.append(str(content.get("role", "")))
    if sorted(inner_hashes) != sorted(
        str(item) for item in intelligence.get("call_evidence_sha256", [])
    ):
        raise ContractError("Legacy model-call evidence disagrees with run intelligence")
    metric_fields = {
        "model_calls": "calls",
        "input_tokens": "input_tokens",
        "output_tokens": "output_tokens",
        "estimated_cost_usd": "estimated_cost_usd",
        "cost_estimate_available": "cost_estimate_available",
    }
    for result_field, intelligence_field in metric_fields.items():
        if result.get(result_field) != intelligence.get(intelligence_field):
            raise ContractError(f"Legacy result {result_field} disagrees with model intelligence")
    reports = sorted(by_type.get("verification-report", []), key=lambda item: item.get("sequence", 0))
    if len(reports) < 2:
        raise ContractError("Legacy repair does not contain baseline and final verification")
    baseline_status = reports[0].get("content", {}).get("status")
    final_status = reports[-1].get("content", {}).get("status")
    if bool(result.get("baseline_rejected")) != (baseline_status == "failed"):
        raise ContractError("Legacy baseline decision disagrees with verifier evidence")
    if bool(result.get("autonomously_repaired")) != (final_status == "passed"):
        raise ContractError("Legacy repair decision disagrees with verifier evidence")
    snapshots_valid, changed_paths = _snapshot_hashes(run_dir, receipt, work_order, by_type)
    nodes = set(str(item) for item in work_order.get("scope", {}).get("graph_node_ids", []))
    workloads = {value for node, value in WORKLOAD_NODES.items() if node in nodes}
    if len(workloads) != 1:
        raise ContractError("Legacy work order does not resolve to exactly one trusted workload")
    return {
        "provider": provider,
        "model": model,
        "roles": sorted(roles),
        "call_evidence_sha256": sorted(inner_hashes),
        "elapsed_ms": int(intelligence.get("elapsed_ms", 0)),
        "event_count": event_count,
        "artifact_count": len(receipt.get("artifacts", [])),
        "workload_id": workloads.pop(),
        "changed_paths": changed_paths,
        "snapshots_valid": snapshots_valid,
        "execution_security": receipt.get("execution_security", {}),
        "request_manifest_available": all(
            isinstance(item.get("content", {}).get("request_manifest"), dict) for item in calls
        ),
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json(path, "Historical evidence manifest")
    _valid_hash(payload, "Historical evidence manifest")
    if payload.get("schema_version") != "1.0" or payload.get(
        "manifest_type"
    ) != "lightyear-historical-model-evidence-manifest":
        raise ContractError("Unsupported historical evidence manifest")
    if payload.get("qualification_eligible") is not False:
        raise ContractError("Historical evidence manifest cannot allow qualification")
    return payload


def verify_legacy_model_archive(
    archive_path: Path,
    manifest_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    archive = archive_path.resolve()
    manifest = _load_manifest(manifest_path.resolve())
    archive_sha256 = _file_hash(archive) if archive.is_file() else ""
    if archive_sha256 != manifest.get("source_archive_sha256"):
        raise ContractError("Legacy evidence archive identity does not match the manifest")
    with tempfile.TemporaryDirectory(prefix="lightyear-legacy-evidence-") as directory:
        root = _extract_archive(archive, Path(directory))
        for path in root.rglob("*"):
            if path.is_file() and SECRET_PATTERN.search(path.read_bytes()):
                raise ContractError("Legacy evidence archive contains an API-key-shaped value")
        evaluation = _load_json(root / "evaluation.receipt.json", "Legacy evaluation receipt")
        _valid_hash(evaluation, "Legacy evaluation receipt")
        if evaluation.get("schema_version") != LEGACY_EVALUATION_SCHEMA or evaluation.get(
            "receipt_type"
        ) != "lightyear-model-workcell-evaluation":
            raise ContractError("Unsupported legacy evaluation receipt")
        if evaluation.get("evaluation_class") != "public-calibration":
            raise ContractError("Legacy evidence bridge accepts public calibration only")
        if evaluation.get("status") != "passed":
            raise ContractError("Legacy historical evaluation did not pass")
        results = evaluation.get("results", [])
        if not isinstance(results, list) or not results or evaluation.get("cases") != len(results):
            raise ContractError("Legacy evaluation case count is invalid")
        result_hashes = [str(item.get("receipt_sha256", "")) for item in results]
        if len(set(result_hashes)) != len(result_hashes):
            raise ContractError("Legacy evaluation results are not uniquely receipted")
        receipt_rows = [
            (path.parent, _load_json(path, "Legacy factory run receipt"))
            for path in (root / "runs").glob("*/receipt.json")
        ]
        receipt_hashes = [str(payload.get("content_sha256", "")) for _, payload in receipt_rows]
        if len(receipt_hashes) != len(set(receipt_hashes)):
            raise ContractError("Legacy archive contains duplicate factory run receipts")
        receipts = {
            payload["content_sha256"]: (run_dir, payload)
            for run_dir, payload in receipt_rows
        }
        if set(receipts) != set(result_hashes):
            raise ContractError("Legacy evaluation does not resolve to exact factory runs")
        runs = [
            _verify_model_run(*receipts[str(result["receipt_sha256"])], result)
            for result in results
        ]
        providers = {item["provider"] for item in runs}
        models = {item["model"] for item in runs}
        workloads = {item["workload_id"] for item in runs}
        if len(providers) != 1 or len(models) != 1 or len(workloads) != 1:
            raise ContractError("Legacy evaluation mixes provider, model, or workload identities")
        totals = evaluation.get("totals", {})
        expected_totals = {
            "model_calls": sum(int(item.get("model_calls", 0)) for item in results),
            "input_tokens": sum(int(item.get("input_tokens", 0)) for item in results),
            "output_tokens": sum(int(item.get("output_tokens", 0)) for item in results),
            "estimated_cost_usd": round(
                sum(float(item.get("estimated_cost_usd", 0)) for item in results), 8
            ),
            "cost_estimate_available": all(
                bool(item.get("cost_estimate_available")) for item in results
            ),
        }
        for field, value in expected_totals.items():
            if totals.get(field) != value:
                raise ContractError(f"Legacy evaluation total {field} is invalid")
        expected = manifest.get("expected", {})
        observed = {
            "evaluation_id": evaluation.get("evaluation_id"),
            "evaluation_class": evaluation.get("evaluation_class"),
            "workload_id": next(iter(workloads)),
            "provider": next(iter(providers)),
            "model": next(iter(models)),
            "cases": len(results),
            **expected_totals,
        }
        for field, value in expected.items():
            if observed.get(field) != value:
                raise ContractError(f"Legacy evidence manifest expected a different {field}")
        if evaluation.get("content_sha256") != manifest.get("evaluation_receipt_sha256"):
            raise ContractError("Legacy evaluation receipt identity does not match the manifest")
        average_input_tokens = round(expected_totals["input_tokens"] / len(results))
        repaired = sum(bool(item.get("autonomously_repaired")) for item in results)
        first_attempt = sum(
            bool(item.get("autonomously_repaired")) and int(item.get("attempts", 0)) == 1
            for item in results
        )
        current_policy = manifest.get("current_policy", {})
        integrity = {
            "archive_identity": True,
            "content_hashes": True,
            "artifact_references": True,
            "ledger_chain": True,
            "model_call_provenance": True,
            "no_raw_model_payloads": True,
            "no_secret_patterns": True,
            "snapshots_reconstructed": all(item["snapshots_valid"] for item in runs),
        }
        checks = {
            **integrity,
            "public_evidence_only": True,
            "current_schema": False,
            "sealed_evidence": False,
            "request_manifest": all(item["request_manifest_available"] for item in runs),
            "token_efficiency": average_input_tokens
            <= int(current_policy.get("maximum_average_input_tokens", 0)),
            "multi_workload_repetition": False,
            "approved_portfolio": False,
        }
        quality = {
            "schema_version": "1.0",
            "decision_type": "lightyear-historical-model-evidence-decision",
            "status": "historical-only",
            "metrics": {
                "repair_rate": round(repaired / len(results), 6),
                "correct_no_change_rate": 0.0,
                "first_attempt_repair_rate": round(first_attempt / len(results), 6),
                "evidence_selection_precision": 0.0,
                "average_input_tokens": average_input_tokens,
                "estimated_cost_usd": expected_totals["estimated_cost_usd"],
            },
            "checks": checks,
        }
        quality["content_sha256"] = canonical_hash(quality)
        payload = {
            "schema_version": HISTORICAL_EVIDENCE_SCHEMA,
            "receipt_type": "lightyear-historical-model-evidence",
            "evidence_id": manifest["evidence_id"],
            "evaluation_id": evaluation["evaluation_id"],
            "evaluation_class": "public-calibration",
            "workload_id": next(iter(workloads)),
            "status": "verified",
            "cases": len(results),
            "baselines_rejected": int(evaluation.get("baselines_rejected", 0)),
            "autonomously_repaired": repaired,
            "repair_rate": round(repaired / len(results), 6),
            "correct_no_change_rate": 0.0,
            "false_acceptances": int(evaluation.get("false_acceptances", 0)),
            "qualification_eligible": False,
            "promotion_allowed": False,
            "production_ready": False,
            "mainframe_equivalent": False,
            "source": {
                "archive_sha256": archive_sha256,
                "manifest_sha256": manifest["content_sha256"],
                "evaluation_receipt_sha256": evaluation["content_sha256"],
                "legacy_schema_version": evaluation["schema_version"],
                "catalog_sha256": evaluation.get("catalog_sha256"),
                "catalog_validation_sha256": evaluation.get("catalog_validation_sha256"),
                "catalog_resolvable": False,
            },
            "model": {
                "provider": next(iter(providers)),
                "model": next(iter(models)),
                "roles": sorted(role for item in runs for role in item["roles"]),
                "model_calls": expected_totals["model_calls"],
                "input_tokens": expected_totals["input_tokens"],
                "output_tokens": expected_totals["output_tokens"],
                "estimated_cost_usd": expected_totals["estimated_cost_usd"],
                "cost_estimate_available": expected_totals["cost_estimate_available"],
                "elapsed_ms": sum(item["elapsed_ms"] for item in runs),
                "call_evidence_sha256": sorted(
                    value for item in runs for value in item["call_evidence_sha256"]
                ),
            },
            "execution": {
                "run_receipts": len(runs),
                "events": sum(item["event_count"] for item in runs),
                "artifacts": sum(item["artifact_count"] for item in runs),
                "changed_paths": sorted(
                    {path for item in runs for path in item["changed_paths"]}
                ),
                "security_status": sorted(
                    {str(item["execution_security"].get("status", "unreported")) for item in runs}
                ),
            },
            "integrity": integrity,
            "compatibility": {
                "current_evaluation_schema": "2.0",
                "current_qualification_admission": "blocked",
                "blocking_reasons": [
                    "legacy-evaluation-schema",
                    "public-calibration-not-sealed",
                    "independent-sealed-binding-absent",
                    "current-request-manifest-absent",
                    "four-workload-repetition-absent",
                    "approved-portfolio-run-absent",
                ],
            },
            "quality_gate": quality,
            "totals": expected_totals,
            "limitations": [
                "This verifies retained first-party model evidence, not an OpenAI-signed attestation.",
                "Public calibration cannot satisfy sealed-holdout qualification.",
                "The original catalog is hash-bound but is not retained in this archive.",
                "The historical host-process gate was advisory rather than OCI-enforced.",
                "This single INTCALC case does not establish multi-workload qualification.",
            ],
        }
        payload["content_sha256"] = canonical_hash(payload)
        if output_path:
            write_json(payload, output_path.resolve())
        return payload
