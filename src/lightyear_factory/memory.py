from __future__ import annotations

import gzip
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ContractError, WorkOrder, canonical_hash, write_json


MEMORY_SCHEMA_VERSION = "1.0"
EXPERIENCE_TYPE = "lightyear-verified-semantic-experience"
SNAPSHOT_TYPE = "lightyear-semantic-memory-snapshot"
RETRIEVAL_TYPE = "lightyear-semantic-memory-retrieval"
SEALED_CLASS = "sealed-holdout"
TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_.:-]{2,80}")


@dataclass(frozen=True)
class MemoryPolicy:
    maximum_results: int = 5
    maximum_context_bytes: int = 24_000
    minimum_score: int = 10
    maximum_lessons: int = 12
    maximum_edit_templates: int = 8
    allow_negative_memory: bool = True
    allowed_evidence_classes: tuple[str, ...] = (
        "factory-run",
        "public-calibration",
        "production-observed",
    )

    @classmethod
    def load(cls, path: Path | None) -> "MemoryPolicy":
        if path is None or not path.is_file():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != MEMORY_SCHEMA_VERSION:
            raise ContractError("Unsupported semantic-memory policy schema")
        policy = cls(
            maximum_results=int(payload.get("maximum_results", 5)),
            maximum_context_bytes=int(payload.get("maximum_context_bytes", 24_000)),
            minimum_score=int(payload.get("minimum_score", 10)),
            maximum_lessons=int(payload.get("maximum_lessons", 12)),
            maximum_edit_templates=int(payload.get("maximum_edit_templates", 8)),
            allow_negative_memory=bool(payload.get("allow_negative_memory", True)),
            allowed_evidence_classes=tuple(
                str(item) for item in payload.get(
                    "allowed_evidence_classes",
                    ["factory-run", "public-calibration", "production-observed"],
                )
            ),
        )
        if not 1 <= policy.maximum_results <= 50:
            raise ContractError("maximum_results must be between 1 and 50")
        if not 1_000 <= policy.maximum_context_bytes <= 500_000:
            raise ContractError("maximum_context_bytes must be between 1,000 and 500,000")
        if not 0 <= policy.minimum_score <= 10_000:
            raise ContractError("minimum_score must be between 0 and 10,000")
        if not 1 <= policy.maximum_lessons <= 100:
            raise ContractError("maximum_lessons must be between 1 and 100")
        if not 0 <= policy.maximum_edit_templates <= 100:
            raise ContractError("maximum_edit_templates must be between 0 and 100")
        if SEALED_CLASS in policy.allowed_evidence_classes:
            raise ContractError("sealed-holdout cannot be an implementer memory class")
        return policy

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "maximum_results": self.maximum_results,
            "maximum_context_bytes": self.maximum_context_bytes,
            "minimum_score": self.minimum_score,
            "maximum_lessons": self.maximum_lessons,
            "maximum_edit_templates": self.maximum_edit_templates,
            "allow_negative_memory": self.allow_negative_memory,
            "allowed_evidence_classes": list(self.allowed_evidence_classes),
        }


class SemanticMemoryStore:
    """Controller-owned, content-addressed memory of verified factory outcomes."""

    def __init__(self, root: Path, policy: MemoryPolicy | None = None) -> None:
        self.root = root.resolve()
        self.policy = policy or MemoryPolicy()
        self.experiences_root = self.root / "experiences"
        self.snapshot_path = self.root / "memory.snapshot.json.gz"

    @classmethod
    def from_policy_path(cls, root: Path, policy_path: Path | None) -> "SemanticMemoryStore":
        return cls(root, MemoryPolicy.load(policy_path))

    def observe_run(
        self,
        run_dir: Path,
        order: WorkOrder,
        run_projection: dict[str, Any],
        context: dict[str, Any],
        artifact_references: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Promote a safe experience or return an explicit exclusion decision."""
        evidence_class = str(order.metadata.get("evaluation_class") or "factory-run")
        decision = {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "memory_type": "lightyear-semantic-memory-decision",
            "run_id": run_projection["run_id"],
            "evidence_class": evidence_class,
            "graph_content_sha256": context.get("graph_content_sha256"),
            "evidence_pack_sha256": context.get("evidence_pack_sha256"),
        }
        if evidence_class == SEALED_CLASS:
            decision.update({
                "disposition": "excluded",
                "reason": "sealed-holdout-is-never-implementer-memory",
                "experience_sha256": None,
            })
            decision["content_sha256"] = canonical_hash(decision)
            return decision
        if evidence_class not in self.policy.allowed_evidence_classes:
            decision.update({
                "disposition": "quarantined",
                "reason": "evidence-class-not-admitted",
                "experience_sha256": None,
            })
            decision["content_sha256"] = canonical_hash(decision)
            return decision
        status = str(run_projection.get("status"))
        verification_status = str(run_projection.get("verification", {}).get("status"))
        if status not in {"passed", "blocked"} or verification_status == "not_run":
            decision.update({
                "disposition": "quarantined",
                "reason": "outcome-not-independently-verifiable",
                "experience_sha256": None,
            })
            decision["content_sha256"] = canonical_hash(decision)
            return decision
        if status == "blocked" and not self.policy.allow_negative_memory:
            decision.update({
                "disposition": "quarantined",
                "reason": "negative-memory-disabled",
                "experience_sha256": None,
            })
            decision["content_sha256"] = canonical_hash(decision)
            return decision

        artifacts = self._public_artifacts(run_dir, artifact_references)
        record = self._experience(order, run_projection, context, artifacts, evidence_class)
        self.experiences_root.mkdir(parents=True, exist_ok=True)
        path = self.experiences_root / f"{record['content_sha256']}.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != record:
                raise ContractError("Semantic memory hash collision")
        else:
            write_json(record, path)
        snapshot = self.rebuild_snapshot()
        decision.update({
            "disposition": (
                "promoted-positive" if record["outcome"]["class"] != "verified_failure"
                else "promoted-negative"
            ),
            "reason": "verified-controller-observation",
            "experience_id": record["experience_id"],
            "experience_sha256": record["content_sha256"],
            "snapshot_sha256": snapshot["content_sha256"],
        })
        decision["content_sha256"] = canonical_hash(decision)
        return decision

    def ingest_run_dir(self, run_dir: Path) -> dict[str, Any]:
        """Promote an existing run using only its content-addressed controller artifacts."""
        run_dir = run_dir.resolve()
        receipt_path = run_dir / "receipt.json"
        order_path = run_dir / "work-order.json"
        if not receipt_path.is_file() or not order_path.is_file():
            raise ContractError("Run directory requires receipt.json and work-order.json")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if canonical_hash(receipt, {"content_sha256"}) != receipt.get("content_sha256"):
            raise ContractError("Run receipt failed content hash validation")
        order = WorkOrder.load(order_path)
        references = list(receipt.get("artifacts", []))
        context_reference = next(
            (
                item for item in references
                if item.get("artifact_type") == "implementer-context"
                and item.get("visibility") == "implementer"
            ),
            None,
        )
        if context_reference is None:
            raise ContractError("Run has no implementer context artifact")
        context_path = (run_dir / str(context_reference.get("path", ""))).resolve()
        if run_dir not in context_path.parents or not context_path.is_file():
            raise ContractError("Run implementer context path is invalid")
        envelope = json.loads(context_path.read_text(encoding="utf-8"))
        if envelope.get("content_sha256") != context_reference.get("content_sha256"):
            raise ContractError("Run implementer context identity mismatch")
        context = envelope.get("content", {})
        return self.observe_run(run_dir, order, receipt, context, references)

    def retrieve(
        self,
        order: WorkOrder,
        graph_content_sha256: str | None,
        evidence_pack_sha256: str | None,
    ) -> dict[str, Any]:
        query_tokens = _tokens(" ".join((order.title, order.goal, *order.allowed_paths)))
        candidates: list[tuple[int, dict[str, Any], list[str]]] = []
        stale = 0
        for record in self.records():
            binding = record.get("graph_binding", {})
            if (
                binding.get("graph_content_sha256") != graph_content_sha256
                or binding.get("evidence_pack_sha256") != evidence_pack_sha256
            ):
                stale += 1
                continue
            reasons: list[str] = []
            record_nodes = set(record.get("scope", {}).get("graph_node_ids", []))
            record_paths = set(record.get("scope", {}).get("paths", []))
            node_overlap = sorted(record_nodes & set(order.graph_node_ids))
            path_overlap = sorted(record_paths & set(order.allowed_paths))
            word_overlap = sorted(set(record.get("keywords", [])) & query_tokens)
            score = 40 * len(node_overlap) + 20 * len(path_overlap) + 2 * len(word_overlap)
            outcome_class = record.get("outcome", {}).get("class")
            score += {"verified_success": 5, "accept_unchanged": 4, "verified_failure": 3}.get(
                str(outcome_class), 0
            )
            if node_overlap:
                reasons.append("same graph entity")
            if path_overlap:
                reasons.append("same approved path")
            if word_overlap:
                reasons.append("shared task vocabulary")
            if score >= self.policy.minimum_score:
                candidates.append((score, record, reasons))
        candidates.sort(
            key=lambda item: (-item[0], item[1]["experience_id"], item[1]["content_sha256"])
        )

        cards: list[dict[str, Any]] = []
        truncated = False
        for score, record, reasons in candidates[: self.policy.maximum_results]:
            card = {
                "experience_id": record["experience_id"],
                "experience_sha256": record["content_sha256"],
                "score": score,
                "match_reasons": reasons,
                "outcome": record["outcome"],
                "summary": record["knowledge"]["summary"],
                "lessons": record["knowledge"]["lessons"],
                "edit_templates": record["knowledge"].get("edit_templates", []),
                "graph_node_ids": record["scope"]["graph_node_ids"],
                "evidence_capsule_ids": record["scope"]["evidence_capsule_ids"],
                "paths": record["scope"]["paths"],
                "run_binding": record["run_binding"],
            }
            projected = {
                "schema_version": MEMORY_SCHEMA_VERSION,
                "retrieval_type": RETRIEVAL_TYPE,
                "cards": [*cards, card],
            }
            if len(_canonical_bytes(projected)) > self.policy.maximum_context_bytes:
                truncated = True
                break
            cards.append(card)
        payload = {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "retrieval_type": RETRIEVAL_TYPE,
            "audience": "implementer",
            "query": {
                "work_order_sha256": order.content_sha256,
                "graph_node_ids": list(order.graph_node_ids),
                "paths": list(order.allowed_paths),
                "graph_content_sha256": graph_content_sha256,
                "evidence_pack_sha256": evidence_pack_sha256,
            },
            "cards": cards,
            "statistics": {
                "records_considered": len(self.records()),
                "records_returned": len(cards),
                "stale_records": stale,
                "context_bytes": 0,
                "maximum_context_bytes": self.policy.maximum_context_bytes,
            },
            "truncated": truncated or len(candidates) > len(cards),
            "limitations": [
                "Memory is advisory and cannot replace graph, source, or acceptance-gate evidence.",
                "Sealed-holdout runs are excluded from implementer memory.",
            ],
        }
        payload["statistics"]["context_bytes"] = len(_canonical_bytes(payload))
        payload["content_sha256"] = canonical_hash(payload)
        return payload

    def summary(self) -> dict[str, Any]:
        records = self.records()
        outcomes: dict[str, int] = {}
        paths: set[str] = set()
        nodes: set[str] = set()
        for record in records:
            outcome = str(record.get("outcome", {}).get("class", "unknown"))
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            paths.update(record.get("scope", {}).get("paths", []))
            nodes.update(record.get("scope", {}).get("graph_node_ids", []))
        snapshot = self.load_snapshot()
        return {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "memory_type": "lightyear-semantic-memory-summary",
            "statistics": {
                "experience_count": len(records),
                "outcomes": dict(sorted(outcomes.items())),
                "covered_paths": len(paths),
                "covered_graph_nodes": len(nodes),
            },
            "experiences": [self._summary_record(item) for item in records],
            "graph_content_sha256": sorted({
                item.get("graph_binding", {}).get("graph_content_sha256")
                for item in records
                if item.get("graph_binding", {}).get("graph_content_sha256")
            }),
            "evidence_pack_sha256": sorted({
                item.get("graph_binding", {}).get("evidence_pack_sha256")
                for item in records
                if item.get("graph_binding", {}).get("evidence_pack_sha256")
            }),
            "snapshot_sha256": snapshot.get("content_sha256") if snapshot else None,
            "policy": self.policy.to_dict(),
        }

    def experience(self, selector: str) -> dict[str, Any]:
        matches = [
            record for record in self.records()
            if selector in {record["experience_id"], record["content_sha256"]}
        ]
        if len(matches) != 1:
            raise KeyError(selector)
        return matches[0]

    def records(self) -> list[dict[str, Any]]:
        if not self.experiences_root.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.experiences_root.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            records.append(record)
        return records

    def rebuild_snapshot(self) -> dict[str, Any]:
        records = self.records()
        outcomes: dict[str, int] = {}
        for record in records:
            outcome = str(record.get("outcome", {}).get("class", "unknown"))
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        payload = {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "snapshot_type": SNAPSHOT_TYPE,
            "policy_sha256": canonical_hash(self.policy.to_dict()),
            "experiences": [self._summary_record(item) for item in records],
            "graph_content_sha256": sorted({
                item.get("graph_binding", {}).get("graph_content_sha256")
                for item in records
                if item.get("graph_binding", {}).get("graph_content_sha256")
            }),
            "evidence_pack_sha256": sorted({
                item.get("graph_binding", {}).get("evidence_pack_sha256")
                for item in records
                if item.get("graph_binding", {}).get("evidence_pack_sha256")
            }),
            "statistics": {
                "experience_count": len(records),
                "positive_count": sum(
                    item.get("outcome", {}).get("class") != "verified_failure"
                    for item in records
                ),
                "negative_count": sum(
                    item.get("outcome", {}).get("class") == "verified_failure"
                    for item in records
                ),
                "outcomes": dict(sorted(outcomes.items())),
            },
        }
        payload["content_sha256"] = canonical_hash(payload)
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_gzip(payload, self.snapshot_path)
        return payload

    def load_snapshot(self) -> dict[str, Any]:
        if not self.snapshot_path.is_file():
            return {}
        with gzip.open(self.snapshot_path, "rt", encoding="utf-8") as handle:
            return json.load(handle)

    def validate(self) -> dict[str, Any]:
        errors: list[str] = []
        records = self.records()
        for record in records:
            if record.get("schema_version") != MEMORY_SCHEMA_VERSION:
                errors.append("unsupported experience schema")
                continue
            expected = canonical_hash(record, {"content_sha256"})
            if record.get("content_sha256") != expected:
                errors.append(f"experience hash mismatch: {record.get('experience_id')}")
            serialized = json.dumps(record, sort_keys=True)
            if SEALED_CLASS in serialized:
                errors.append(f"sealed holdout contamination: {record.get('experience_id')}")
            if "verification-report" in serialized or '"visibility": "verifier_private"' in serialized:
                errors.append(f"private verifier contamination: {record.get('experience_id')}")
            if record.get("outcome", {}).get("class") == "verified_failure" and record.get(
                "knowledge", {}
            ).get("edit_templates"):
                errors.append(f"negative memory contains executable edits: {record.get('experience_id')}")
        rebuilt = self.rebuild_snapshot()
        loaded = self.load_snapshot()
        if rebuilt != loaded:
            errors.append("semantic memory snapshot is not deterministic")
        result = {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "experience_count": len(records),
            "snapshot_sha256": rebuilt["content_sha256"],
        }
        result["content_sha256"] = canonical_hash(result)
        return result

    def _experience(
        self,
        order: WorkOrder,
        run_projection: dict[str, Any],
        context: dict[str, Any],
        artifacts: list[dict[str, Any]],
        evidence_class: str,
    ) -> dict[str, Any]:
        plans = [item["content"] for item in artifacts if item["artifact_type"] == "plan"]
        proposals = [
            item["content"] for item in artifacts if item["artifact_type"] == "build-proposal"
        ]
        tasks = [task for plan in plans for task in plan.get("tasks", [])]
        selected_nodes = sorted({
            str(item) for task in tasks for item in task.get("graph_node_ids", [])
        } | set(order.graph_node_ids))
        selected_capsules = sorted({
            str(item) for task in tasks for item in task.get("evidence_capsule_ids", [])
        })
        paths = sorted({
            str(item) for task in tasks for item in task.get("paths", [])
        } | set(order.allowed_paths))
        outcome_class = (
            "accept_unchanged"
            if run_projection["status"] == "passed" and not run_projection.get("changed_paths")
            else "verified_success"
            if run_projection["status"] == "passed"
            else "verified_failure"
        )
        lessons = []
        for plan in plans:
            lessons.extend(str(task.get("objective", ""))[:1_000] for task in plan.get("tasks", []))
        for proposal in proposals:
            lessons.append(str(proposal.get("summary", ""))[:1_000])
            lessons.extend(
                str(edit.get("rationale", ""))[:1_000]
                for edit in proposal.get("edits", [])
            )
        lessons = [item for item in dict.fromkeys(lessons) if item][: self.policy.maximum_lessons]
        edit_templates = []
        edit_fingerprints = []
        for proposal in proposals:
            for edit in proposal.get("edits", []):
                before = str(edit.get("find", ""))
                after = str(edit.get("replace", ""))
                fingerprint = {
                    "path": str(edit.get("path", "")),
                    "find_sha256": hashlib.sha256(before.encode()).hexdigest(),
                    "replace_sha256": hashlib.sha256(after.encode()).hexdigest(),
                    "rationale": str(edit.get("rationale", ""))[:1_000],
                }
                edit_fingerprints.append(fingerprint)
                if outcome_class != "verified_failure" and len(edit_templates) < self.policy.maximum_edit_templates:
                    edit_templates.append({
                        **fingerprint,
                        "find": before[:2_000],
                        "replace": after[:2_000],
                    })
        summary = next(
            (str(plan.get("summary", "")) for plan in reversed(plans) if plan.get("summary")),
            order.goal,
        )[:2_000]
        identity = canonical_hash({
            "run_id": run_projection["run_id"],
            "work_order_sha256": order.content_sha256,
            "ledger_head_sha256": run_projection.get("ledger_head_sha256"),
            "outcome_class": outcome_class,
        })
        record = {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "experience_type": EXPERIENCE_TYPE,
            "experience_id": f"experience:{identity[:24]}",
            "state": "active",
            "evidence_class": evidence_class,
            "run_binding": {
                "run_id": run_projection["run_id"],
                "work_order_id": order.order_id,
                "work_order_sha256": order.content_sha256,
                "ledger_head_sha256": run_projection.get("ledger_head_sha256"),
                "initial_snapshot_sha256": run_projection.get("initial_snapshot_sha256"),
                "final_snapshot_sha256": run_projection.get("final_snapshot_sha256"),
            },
            "graph_binding": {
                "graph_content_sha256": context.get("graph_content_sha256"),
                "evidence_pack_sha256": context.get("evidence_pack_sha256"),
            },
            "scope": {
                "graph_node_ids": selected_nodes,
                "evidence_capsule_ids": selected_capsules,
                "paths": paths,
            },
            "outcome": {
                "class": outcome_class,
                "status": run_projection["status"],
                "attempts": run_projection.get("attempts", 0),
                "changed_paths": list(run_projection.get("changed_paths", [])),
                "gates": list(run_projection.get("verification", {}).get("gates", [])),
            },
            "knowledge": {
                "summary": summary,
                "lessons": lessons,
                "edit_templates": edit_templates,
                "edit_fingerprints": edit_fingerprints,
            },
            "keywords": sorted(_tokens(" ".join((order.title, order.goal, summary, *lessons))))[:200],
            "privacy": {
                "audience": "implementer",
                "verifier_private_artifacts_excluded": True,
                "sealed_holdout_content_included": False,
                "executable_negative_edits_included": False,
            },
            "limitations": [
                "Memory is derived from controller-observed artifacts and does not replace source evidence.",
                "A verified local gate does not prove z/OS equivalence.",
            ],
        }
        record["content_sha256"] = canonical_hash(record)
        return record

    @staticmethod
    def _public_artifacts(
        run_dir: Path, references: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        allowed_types = {"plan", "build-proposal", "change-set"}
        result = []
        resolved_run = run_dir.resolve()
        for reference in references:
            if (
                reference.get("visibility") != "implementer"
                or reference.get("artifact_type") not in allowed_types
            ):
                continue
            path = (run_dir / str(reference.get("path", ""))).resolve()
            if resolved_run not in path.parents or not path.is_file():
                raise ContractError("Semantic memory artifact path is invalid")
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if envelope.get("content_sha256") != reference.get("content_sha256"):
                raise ContractError("Semantic memory artifact identity mismatch")
            if canonical_hash(envelope, {"content_sha256"}) != envelope.get("content_sha256"):
                raise ContractError("Semantic memory artifact failed hash validation")
            result.append({
                "artifact_type": envelope["artifact_type"],
                "content": envelope.get("content", {}),
            })
        return result

    @staticmethod
    def _summary_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "experience_id": record["experience_id"],
            "content_sha256": record["content_sha256"],
            "state": record["state"],
            "evidence_class": record["evidence_class"],
            "outcome_class": record["outcome"]["class"],
            "run_id": record["run_binding"]["run_id"],
            "work_order_id": record["run_binding"]["work_order_id"],
            "graph_node_ids": record["scope"]["graph_node_ids"],
            "paths": record["scope"]["paths"],
            "summary": record["knowledge"]["summary"],
        }

    @staticmethod
    def _write_gzip(payload: dict[str, Any], path: Path) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
                handle.write(encoded)
        temporary.replace(path)


def _tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in TOKEN_PATTERN.findall(value)
        if token.casefold() not in {
            "and", "the", "for", "from", "this", "that", "with", "using", "into",
            "then", "only", "every", "factory", "lightyear",
        }
    }


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
