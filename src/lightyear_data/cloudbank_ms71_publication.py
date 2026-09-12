"""Verify the pinned MS71 export without cloud access or the operator's HMAC key."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lightyear_data.cloudbank_publication import ROOT, _digest, _require

BUNDLE = Path("docs/receipts/ms71-20260912a")
EXPORT_SHA256 = "863d6e8b6621551586aa6b8461a473b1fe699ad59a262e2371ee40021a0355a0"


def load_ms71_publication(root: Path = ROOT) -> dict:
    """Anchor original bytes to the export verified and signed by the live operator."""
    raw = (root / BUNDLE / "publication-export.json").read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == EXPORT_SHA256, "MS71 export bytes changed")
    manifest = json.loads(raw)
    _require(_digest(manifest) == manifest["content_sha256"], "MS71 export content changed")
    documents = {}
    for entry in manifest["files"]:
        raw = (root / BUNDLE / entry["name"]).read_bytes()
        _require(len(raw) == entry["size_bytes"] and hashlib.sha256(raw).hexdigest() == entry["file_sha256"],
                 f"MS71 {entry['name']} bytes changed")
        value = json.loads(raw)
        _require(_digest(value) == value["content_sha256"] == entry["content_sha256"],
                 f"MS71 {entry['name']} content changed")
        documents[entry["name"]] = value
    _require(len(documents) == 6, "MS71 incomplete export")
    receipt = documents[manifest["receipt_file"]]
    _require(receipt["content_sha256"] == manifest["receipt_content_sha256"] and
             receipt["campaign_id"] == manifest["campaign_id"] and
             receipt["controller_commit"] == manifest["controller_commit"], "MS71 receipt binding")
    _require(receipt["ms71_complete"] is True and receipt["status"] == "passed-two-target-equivalence" and
             receipt["scenarios_per_comparison"] == 18 and len(receipt["services"]) == 8,
             "MS71 acceptance incomplete")
    _require(receipt["production_ready"] is False and receipt["alloydb_platform_qualified"] is False and
             receipt["synthetic_data_only"] is True, "MS71 scope widened")
    expected = [documents[name] for name in ("sql-managed-comparison.json", "alloydb-managed-comparison.json")]
    _require(receipt["comparisons"] == expected, "MS71 comparison exports differ")
    reassembly = documents["sql-reassembly.json"]
    _require(reassembly["comparison_sha256"] == expected[0]["content_sha256"] and
             reassembly["original_failure_sha256"] == documents["sql-original-assembly-failure.json"]["content_sha256"],
             "MS71 reassembly provenance differs")
    return {"receipt": receipt, "manifest": manifest, "bundle": BUNDLE.as_posix()}
