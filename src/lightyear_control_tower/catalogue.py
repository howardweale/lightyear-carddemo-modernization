"""Read signed catalogue records. Status belongs to the engine publisher."""

import hashlib
from pathlib import Path
from .decisions import digest, verify_envelope
from .requests import confined, read_json
from .verification import verify_decision, check

STATUSES = {"qualified", "qualified-limited", "in-qualification", "roadmap", "expired"}


def read_catalogue(root, key, *, scope=None):
    root = Path(root)
    path = root / "catalog/lanes.json"
    if not path.exists():
        return {
            "schema": "tower-catalogue-view/1",
            "available": False,
            "entries": [],
            "limitation": "Lane Adapter Standard catalogue is not installed; no qualification claims.",
        }
    record = read_json(path)
    check(
        record.get("schema") == "lane-catalogue/1" and verify_envelope(record, key),
        "invalid-catalogue-signature",
    )
    if scope is not None:
        check(record.get("scope") == scope, "catalogue-scope-mismatch")
    entries = []
    ids = set()
    for entry in record["entries"]:
        check(
            entry["id"] not in ids and entry["status"] in STATUSES,
            "invalid-catalogue-entry",
        )
        ids.add(entry["id"])
        raw = confined(root, entry["record"]).read_bytes()
        check(
            hashlib.sha256(raw).hexdigest() == entry["record_sha256"],
            "catalogue-record-hash-mismatch",
        )
        qualification = read_json(confined(root, entry["record"]))
        check(verify_envelope(qualification, key), "invalid-qualification-signature")
        check(qualification.get("scope") == record["scope"], "catalogue-scope-mismatch")
        # The publisher embeds proofs so the consumer can independently verify
        # acceptance and supersession at the exact declared publication head.
        proof = entry["acceptance"]
        p = entry["acceptance_bound"]
        verify_decision(
            proof,
            key,
            "qualification-acceptance",
            p,
            scope=record["scope"],
            expected_head=record["decision_head_sha256"],
            outcomes=("accepted",),
        )
        check(
            p["qualification"] == entry["record_sha256"], "acceptance-record-mismatch"
        )
        entries.append(
            {k: v for k, v in entry.items() if k not in {"record", "acceptance_bound"}}
            | {"qualification": qualification}
        )
    return {
        "schema": "tower-catalogue-view/1",
        "available": True,
        "catalogue_sha256": record["content_sha256"],
        "scope": record["scope"],
        "entries": entries,
        "status_source": "signed engine catalogue",
    }


def consistency(root, key, public_path, website_path, *, scope=None):
    view = read_catalogue(root, key, scope=scope)
    check(view.get("available"), "catalogue-unavailable")
    expected = {e["id"]: e["status"] for e in view["entries"]}
    for path in (public_path, website_path):
        p = read_json(path)
        check(
            p.get("catalogue_sha256") == view["catalogue_sha256"],
            "projection-catalogue-hash-mismatch",
        )
        rows = p.get("entries", [])
        check(
            len(rows) == len(expected)
            and {e["id"]: e["status"] for e in rows} == expected,
            "projection-status-mismatch",
        )
    return {
        "status": "verified",
        "catalogue_sha256": view["catalogue_sha256"],
        "entries": len(expected),
    }


def publish_record(entries, *, scope, decision_head, signer, current_bindings):
    """Engine-side generator, not reachable from Tower HTTP/MCP.

    Caller supplies already verified accepted records. Compare LAS expiry inputs
    here, not in the UI; the signed result is authoritative for every projection.
    """
    output = []
    for entry in entries:
        row = dict(entry)
        check(row["status"] in STATUSES, "invalid-catalogue-status")
        required = {
            "platform_major",
            "adapter_sha256",
            "judge_version",
            "rule_register_major",
        }
        check(
            required <= set(row["bindings"])
            and required <= set(current_bindings[row["id"]]),
            "incomplete-expiry-bindings",
        )
        verify_decision(
            row["acceptance"],
            signer.public_key,
            "qualification-acceptance",
            row["acceptance_bound"],
            scope=scope,
            expected_head=decision_head,
            outcomes=("accepted",),
        )
        check(
            row["acceptance_bound"]["qualification"] == row["record_sha256"],
            "acceptance-record-mismatch",
        )
        expired = [
            k
            for k in (
                "platform_major",
                "adapter_sha256",
                "judge_version",
                "rule_register_major",
            )
            if row["bindings"].get(k) != current_bindings[row["id"]].get(k)
        ]
        if expired:
            row.update(status="expired", expiry_triggers=expired)
        output.append(row)
    return signer.sign(
        {
            "schema": "lane-catalogue/1",
            "scope": scope,
            "decision_head_sha256": decision_head,
            "entries": sorted(output, key=lambda r: r["id"]),
        }
    )
