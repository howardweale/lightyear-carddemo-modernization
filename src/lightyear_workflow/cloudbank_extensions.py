"""Additional fixed actions over the published synthetic CloudBank evidence.

No new capture or runtime is inferred from an archival record. Derived artifacts
are embedded in the engine journal; source receipts and ledgers stay immutable.
"""
from __future__ import annotations

import json
from pathlib import Path

from lightyear_data.cloudbank_publication import BUNDLE, load_publication
from lightyear_data.contracts import content_hash, seal
from .policy import _unique_object

KINDS = ("reparse", "extend-corpus", "rerun", "apply-ledger-entry")
DEPENDENCIES = {"reparse": (), "extend-corpus": ("reparse",),
                "rerun": ("extend-corpus",), "apply-ledger-entry": ("rerun",)}
PLATFORM = BUNDLE / "receipts/platform-observation.json"
EQUIVALENCE = BUNDLE / "receipts/prerequisite-ms61-equivalence.receipt.json"
LEDGER = Path("factory/cloudbank/oracle-equivalence/compatibility-ledger.json")
WORKLOAD = "cloudbank:retained-value-conservation"
ENTRY_ID = "successful-value-conservation"
GRAMMAR = "cloudbank-platform-scenarios/2"
PREVIOUS_GRAMMAR = "cloudbank-platform-scenarios/1"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)


def parse_scenarios(value: dict, grammar: str) -> list[dict]:
    """V1 indexes scenario names; V2 also admits typed status/evidence bindings."""
    if grammar not in {PREVIOUS_GRAMMAR, GRAMMAR}:
        raise ValueError("Unregistered scenario grammar")
    if value.get("observation_type") != "lightyear-cloudbank-ms67-platform-observation":
        raise ValueError("Unsupported platform observation")
    rows = value.get("scenarios")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise ValueError("Scenario count outside grammar bounds")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "status", "evidence_sha256"}:
            raise ValueError("Unknown or missing scenario fields")
        if not isinstance(row["id"], str) or not row["id"] or len(row["id"]) > 200:
            raise ValueError("Invalid scenario identity")
        digest = row["evidence_sha256"]
        if row["status"] not in {"passed", "failed"} or not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid typed scenario evidence")
        result.append({"id": row["id"]} if grammar == PREVIOUS_GRAMMAR else dict(row))
    if len({r["id"] for r in result}) != len(result):
        raise ValueError("Duplicate scenario identity")
    return result


def reparsed(root: Path) -> dict:
    value = read_json(root / PLATFORM)
    before = parse_scenarios(value, PREVIOUS_GRAMMAR)
    after = parse_scenarios(value, GRAMMAR)
    return seal({"artifact_type": "cloudbank-reparsed-scenarios", "source": PLATFORM.as_posix(),
                 "source_sha256": value["content_sha256"], "previous_grammar": PREVIOUS_GRAMMAR,
                 "grammar": GRAMMAR, "previous_projection_sha256": content_hash({"records": before}),
                 "previous_projection_origin": "reconstructed-v1-baseline-not-a-prior-run",
                 "records": after, "new_fields": ["status", "evidence_sha256"]})


def extended(root: Path) -> dict:
    from .cloudbank import SERVICES
    parsed = reparsed(root)
    baseline = [{"id": "service:" + name, "kind": "service-contract"} for name in SERVICES]
    added = [{**row, "id": "scenario:" + row["id"], "kind": "retained-platform-scenario",
              "source": PLATFORM.as_posix()} for row in parsed["records"]]
    return seal({"artifact_type": "cloudbank-extended-evidence-corpus",
                 "capture_authority": "owner-published-synthetic-ms67-bundle",
                 "scope": "local-retained-platform-scenarios-only", "new_external_capture": False,
                 "parser_receipt_sha256": parsed["content_sha256"],
                 "previous_corpus_sha256": content_hash({"records": baseline}), "previous_count": len(baseline),
                 "added_count": len(added), "records": baseline + added})


def rerun(root: Path) -> dict:
    publication = load_publication(root)
    corpus = extended(root)
    known = {f["content_sha256"] for f in publication["files"]}
    checks = [{"id": row["id"], "passed": row["status"] == "passed" and row["evidence_sha256"] in known}
              for row in corpus["records"] if row["kind"] == "retained-platform-scenario"]
    if content_hash({"records": corpus["records"]}) == corpus["previous_corpus_sha256"]:
        raise ValueError("Rerun requires changed admitted inputs")
    return seal({"artifact_type": "cloudbank-expanded-corpus-rerun",
                 "observation": "local-scenario-status-and-evidence-closure",
                 "before_corpus_sha256": corpus["previous_corpus_sha256"],
                 "after_corpus_sha256": content_hash({"records": corpus["records"]}),
                 "corpus_receipt_sha256": corpus["content_sha256"], "checks": checks})


def decision_ledger(root: Path) -> dict:
    """Exact, reviewable terms for the existing ledger's value-conservation entry."""
    ledger = read_json(root / LEDGER)
    if content_hash(ledger) != ledger.get("content_sha256"):
        raise ValueError("CloudBank ledger content hash changed")
    entry = next(e for e in ledger["entries"] if e["capability"] == ENTRY_ID)
    if entry != {"capability": ENTRY_ID, "classification": "normalized-equivalent", "evidence": "native-dual-lane"}:
        raise ValueError("Unsupported CloudBank ledger entry")
    return {"schema_version": "1.0", "workload_id": WORKLOAD,
            "source_ledger": LEDGER.as_posix(), "source_ledger_sha256": content_hash(ledger),
            "rules": [{"id": ENTRY_ID, "source_entry": entry,
                       "scope": "Retained MS61 synthetic value-conservation observation identity only",
                       "behavior": "Compare the recorded Oracle and PostgreSQL observation_sha256 fields; retain both complete raw lane records and every declared implementation difference.",
                       "reason": "Apply the existing normalized-equivalent ledger entry to an additional local analysis, without changing the original receipt or accepting other differences.",
                       "owner": "CloudBank reference-estate owner", "review_after": "2027-09-13",
                       "operation": "equal-recorded-observation-digests", "source_receipt": EQUIVALENCE.as_posix(),
                       "claim_promotion": False, "suppressed_fields": [],
                       "maximum_application_count_per_run": 1}]}


def ledger_projection(root: Path) -> dict:
    terms = decision_ledger(root)
    receipt = read_json(root / EQUIVALENCE)
    ledger = read_json(root / LEDGER)
    if receipt["compatibility_ledger_sha256"] != ledger["content_sha256"]:
        raise ValueError("Original receipt and ledger binding changed")
    raw = {lane: receipt[lane] for lane in ("oracle_lane", "postgresql_lane")}
    normalized = {lane: value["observation_sha256"] for lane, value in raw.items()}
    return seal({"artifact_type": "cloudbank-approved-ledger-projection", "terms": terms,
                 "raw": raw, "raw_equal": raw["oracle_lane"] == raw["postgresql_lane"],
                 "raw_differences_retained": [e for e in ledger["entries"] if e["classification"] != "normalized-equivalent"],
                 "normalized": normalized,
                 "normalized_equal": normalized["oracle_lane"] == normalized["postgresql_lane"],
                 "source_receipt_sha256": receipt["content_sha256"], "suppressed_fields": []})


def observe_extension(root: Path, kind: str) -> dict:
    from .cloudbank import BOUNDARY
    if kind not in KINDS:
        raise ValueError("Unregistered extension action")
    errors, artifact, outcome = [], None, "verified"
    try:
        artifact = {"reparse": reparsed, "extend-corpus": extended,
                    "rerun": rerun, "apply-ledger-entry": ledger_projection}[kind](root)
        if kind == "rerun" and not all(c["passed"] for c in artifact["checks"]):
            errors.append("expanded-corpus-check-failed")
        if kind == "apply-ledger-entry" and not artifact["normalized_equal"]:
            errors.append("recorded-observation-identity-differs")
        if errors:
            outcome = "mismatch"
    except OSError:
        errors, outcome = ["extension-evidence-unavailable"], "unavailable"
    except (ValueError, KeyError, TypeError, StopIteration) as exc:
        errors, outcome = ["extension-evidence-invalid:" + str(exc)[:200]], "mismatch"
    return {"service": "estate", "lane": kind, "errors": errors, "outcome": outcome,
            "evidence": [p.as_posix() for p in ((LEDGER, EQUIVALENCE) if kind == "apply-ledger-entry" else (PLATFORM,))],
            "artifact": artifact, "boundary": BOUNDARY}
