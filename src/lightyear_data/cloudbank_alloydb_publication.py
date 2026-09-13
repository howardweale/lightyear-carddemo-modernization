"""Read an operator-verified AlloyDB export anchored by a committed byte hash.

Public readers do not hold the HMAC key. The caller supplies the reviewed export
hash; original bytes, content hashes and receipt bindings are then checked here.
"""
import hashlib
import json
from pathlib import Path
import re

from .cloudbank_publication import ROOT, _digest, _require
from .cloudbank_ms71_publication import load_ms71_publication

PHASE_NAMES = {"current-controls", "runtime-identity", "image-security", "secret-rotation",
               "log-correlation", "alert-drill", "network-enforcement", "sustained-load",
               "database-recovery", "ha", "drills"}
BOUNDARY_NAMES = {"secret-rotation", "log-correlation", "alert-drill", "network-enforcement", "sustained-load"}


def load_alloydb_publication(bundle, expected_export_sha256, root=ROOT):
    bundle, root = Path(bundle), Path(root)
    _require(not bundle.is_absolute() and ".." not in bundle.parts
             and bundle.parts[:2] == ("docs", "receipts")
             and re.fullmatch(r"[0-9a-f]{64}", expected_export_sha256), "AlloyDB publication anchor required")
    raw = (root / bundle / "publication-export.json").read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == expected_export_sha256, "AlloyDB export bytes changed")
    manifest = json.loads(raw)
    _require(_digest(manifest) == manifest["content_sha256"]
             and manifest.get("record_type") == "lightyear-alloydb-platform-publication-export"
             and all(manifest.get(k) is True for k in
                     ("operator_signatures_verified", "complete_gate_reconstructed", "original_bytes_preserved")),
             "AlloyDB export admission missing")
    expected_files = {"campaign-context.json", "ms71-business-equivalence.receipt.json", "alloydb-platform.receipt.json",
                      *(p + ".json" for p in PHASE_NAMES),
                      *(p + ".managed-boundary.json" for p in BOUNDARY_NAMES)}
    _require(len(manifest["files"]) == len(expected_files)
             and {entry["name"] for entry in manifest["files"]} == expected_files, "AlloyDB export incomplete")
    documents = {}
    for entry in manifest["files"]:
        name = entry["name"]
        raw = (root / bundle / name).read_bytes()
        _require(len(raw) == entry["size_bytes"] and hashlib.sha256(raw).hexdigest() == entry["file_sha256"],
                 f"AlloyDB {name} bytes changed")
        value = json.loads(raw)
        _require(_digest(value) == value["content_sha256"] == entry["content_sha256"], f"AlloyDB {name} content changed")
        documents[name] = value
    _require(manifest["receipt_file"] == "alloydb-platform.receipt.json", "AlloyDB receipt file changed")
    receipt = documents[manifest["receipt_file"]]
    _require(receipt["content_sha256"] == manifest["receipt_content_sha256"]
             and receipt["campaign_id"] == manifest["campaign_id"], "AlloyDB receipt binding changed")
    _require(receipt.get("receipt_type") == "lightyear-alloydb-nonproduction-platform-qualification"
             and receipt.get("status") == "passed-alloydb-nonproduction-platform-qualification"
             and receipt.get("alloydb_platform_qualified") is True and receipt.get("synthetic_data_only") is True
             and all(receipt.get(k) is False for k in ("production_ready", "production_deployed",
                 "customer_certification_complete", "unplanned_region_failure_qualified")), "AlloyDB qualification scope changed")
    _require(receipt.get("scenario_count") == 29 and len(receipt.get("scenarios", [])) == 29
             and len({row["id"] for row in receipt["scenarios"]}) == 29
             and all(row.get("status") == "passed" for row in receipt["scenarios"]), "AlloyDB scenarios incomplete")
    _require(receipt["context"] == documents["campaign-context.json"]
             and receipt["ms71_receipt"] == documents["ms71-business-equivalence.receipt.json"]
             == load_ms71_publication(root)["receipt"], "AlloyDB original business acceptance changed")
    _require(receipt["phases"] == {p: documents[p + ".json"] for p in PHASE_NAMES}
             and receipt["managed_boundaries"] == {p: documents[p + ".managed-boundary.json"] for p in BOUNDARY_NAMES},
             "AlloyDB exported phase bindings changed")
    return {"receipt": receipt, "manifest": manifest, "bundle": bundle.as_posix()}
