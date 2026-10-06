"""Host-side knowledge synchronization, after independent judge replay.

This service does not invoke models, change verdicts or sign judge attestations.
It ingests attested outcomes and verified Tower sources, then emits review requests.
"""

from collections import Counter
from datetime import datetime, timezone
from lightyear_control_tower.decisions import digest, canonical, verify_envelope
from .annotation_tools import governor_requests, tower_proposal
from .annotations import health
from .contracts import canonical_hash


class KnowledgeService:
    def __init__(self, ledger, signer, tower_root):
        self.ledger, self.signer, self.tower_root = ledger, signer, tower_root

    def sync(self, *, decisions=(), outcomes=(), trust, protected_values, leak_checks):
        states = self.ledger.replay()
        imported = {
            e["sha256"]
            for s in states.values()
            for e in s["annotation"]["evidence"]
            if e["kind"] == "tower-decision"
        }
        for row in decisions:
            if row["proof"]["decision_sha256"] in imported:
                continue
            tower_proposal(
                self.ledger,
                self.signer,
                row["proposal"],
                row["proof"],
                trust,
                row["kind"],
                row["bindings"],
                protected_values=protected_values,
            )
            imported.add(row["proof"]["decision_sha256"])
        for row in outcomes:
            receipt, context, attestation = (
                row["run_receipt"],
                row["context"],
                row["attestation"],
            )
            if (
                canonical_hash(receipt, {"content_sha256"}) != receipt["content_sha256"]
                or canonical_hash(context, {"content_sha256"})
                != context["content_sha256"]
                or not verify_envelope(attestation, self.ledger.judge_key)
                or attestation.get("run_receipt_sha256") != receipt["content_sha256"]
                or receipt["annotation_context"]["context_sha256"]
                != context["content_sha256"]
                or receipt["annotation_context"]["annotation_ids"]
                != context["annotation_ids"]
                or attestation["context"]["annotation_ids"] != context["annotation_ids"]
                or attestation["context"].get("full_context_sha256")
                != context["content_sha256"]
                or attestation["run_id"] != receipt["run_id"]
            ):
                raise ValueError(
                    "judge outcome is not bound to the recorded run context"
                )
            for a in context["annotation_ids"]:
                current = self.ledger.replay()[a]
                previous = current["outcomes"].get(attestation["run_id"])
                if previous:
                    if previous != attestation:
                        raise ValueError("conflicting outcome import")
                    continue
                self.ledger.append(
                    "outcome", dict(id=a, receipt=attestation), self.signer
                )
        return governor_requests(
            self.ledger, self.tower_root, self.ledger.scope, leak_checks
        )

    def status(self, *, routing=None, run_receipts=(), projections=()):
        counts = Counter(
            r["model"] for receipt in run_receipts for r in receipt.get("routing", [])
        )
        total = sum(counts.values())
        return self.signer.sign(
            dict(
                schema="factory-knowledge-status/1",
                scope=self.ledger.scope,
                time=datetime.now(timezone.utc).isoformat(),
                health=health(self.ledger.replay()),
                routing=dict(
                    policy=routing,
                    model_shares={k: v / total for k, v in counts.items()},
                ),
                search=[
                    dict(
                        projection_sha256=p["projection_sha256"],
                        search_index_sha256=p.get("search_index_sha256"),
                        provider=p.get("embedding_provider"),
                    )
                    for p in projections
                ],
            )
        )
