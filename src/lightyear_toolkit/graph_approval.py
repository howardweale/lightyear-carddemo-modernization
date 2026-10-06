"""Portable, fail-closed projection approval. No private graph/evidence access."""
import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from lightyear_control_tower.decisions import canonical, verify_envelope, digest
from lightyear_control_tower.verification import verify_decision
from lightyear_toolkit.workspace import Refused

SHA = re.compile(r"[a-f0-9]{64}")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_approved(directory, proof, trust, *, now=None):
    """Keys, lane/mode and current Tower head must come from trusted configuration."""
    root = Path(directory)
    for name, limit in (("projection-manifest.json", 1024*1024),
                        ("graph-leak-certificate.json", 1024*1024),
                        ("projection.json.gz", 64*1024*1024)):
        if (root/name).stat().st_size > limit:
            raise Refused("graph-too-large")
    manifest = json.loads((root / "projection-manifest.json").read_bytes())
    raw = (root / "projection.json.gz").read_bytes()
    leak = json.loads((root / "graph-leak-certificate.json").read_bytes())
    if not verify_envelope(manifest, trust["operator_key"].encode()):
        raise Refused("graph-manifest-signature")
    if not verify_envelope(leak, trust["judge_key"].encode()):
        raise Refused("graph-leak-signature")
    if (manifest["projection_sha256"] != sha(raw) or
            manifest["lane_sha256"] != trust["lane_sha256"] or
            manifest["mode"] != trust["mode"] or
            manifest["customer_id"] != trust["customer_id"] or
            leak["projection_sha256"] != sha(raw) or
            leak["lane_sha256"] != manifest["lane_sha256"]):
        raise Refused("graph-binding")
    expected = dict(projection=sha(raw), policy=manifest["policy_sha256"],
                 leak_check=leak["report_sha256"], lane=manifest["lane_sha256"],
                 manifest=sha((root / "projection-manifest.json").read_bytes()))
    event = next(e for e in proof["journal"]["events"] if e["content_sha256"] == proof["decision_sha256"])
    bound = event["payload"]["bound"]
    if {k:v for k,v in bound.items() if k != "request"} != expected:
        raise Refused("graph-decision-bindings")
    if not SHA.fullmatch(trust["trusted_head"]):
        raise Refused("graph-head-required")
    decision = verify_decision(proof, trust["tower_key"].encode(),
        "verify-graph-projection", bound, expected_head=trust["trusted_head"],
        scope=trust["scope"], outcomes=["approved"], now=now)
    if not decision.get("review_after"):
        raise Refused("graph-expiry-required")
    # Non-source matches cannot be waived. Explicit hash list is part of the
    # signed reason (the Tower's closed fields do not accept arbitrary extras).
    exceptions = leak["source_literal_exceptions"]
    if (leak.get("schema") != "verify-graph-leak-certificate/1" or leak.get("eligible") is not True or
            not SHA.fullmatch(leak.get("evaluation_inventory_sha256", "")) or
            any(not SHA.fullmatch(h) or "source-literal:" + h not in decision["reason"] for h in exceptions)):
        raise Refused("graph-leak-not-approved")
    with gzip.GzipFile(fileobj=__import__("io").BytesIO(raw)) as stream:
        data = stream.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise Refused("graph-too-large")
    projection = json.loads(data)
    if (projection["lane_sha256"] != manifest["lane_sha256"] or
            projection["mode"] != manifest["mode"] or
            projection["customer_id"] != manifest["customer_id"]):
        raise Refused("graph-payload-binding")
    return projection, manifest, decision


def receipt_context(receipt, config):
    """Old v1 bytes remain valid; v2 must carry the configured context identity."""
    expected = config.get("context_projection_sha256")
    if expected is not None and not SHA.fullmatch(expected):
        raise ValueError("context-hash-invalid")
    if receipt["schema"] == "lightyear-verify-receipt/1":
        if expected is not None or receipt.get("context_projection_sha256") is not None:
            raise ValueError("legacy-context-invalid")
        return None
    if (receipt["schema"] != "lightyear-verify-receipt/2" or
            "context_projection_sha256" not in receipt or
            receipt["context_projection_sha256"] != expected):
        raise ValueError("receipt-context-mismatch")
    return expected
