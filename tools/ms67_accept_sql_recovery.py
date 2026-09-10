#!/usr/bin/env python3
"""Reassess the completed MS67 SQL attempt under the approved 630-second PITR policy.

Reads existing signed evidence, writes a separate signed assessment, and uploads
and reads it back. Starts no recovery drill, load test, deployment or MS65 build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cloudbank_sql_recovery import load_bound_inputs, upload
from lightyear_data.cloudbank_journeys import require
from lightyear_data.cloudbank_ms65_rehearsal_gke import (
    reassess_database_recovery, validate_database_recovery,
)
from lightyear_data.cloudbank_recovery_policy import recovery_acceptance_policy
from lightyear_data.cloudbank_sql_recovery import invoke, verified, write_signed

PROJECT = "lightyear-ms67-nonproduction"
ACCOUNT = "howard.weale@gmail.com"
BUCKET = "gs://lightyear-ms67-nonproduction-ms67-evidence"
IMAGE_BUILD = "a4997e85-7244-4cf3-bed3-6756d34391ce"
LOAD_RUN = "ms67-load-cba87eec3dfc4c3582902a0072bc544a"


def load(path):
    require(path.is_file() and not path.is_symlink(), "regular-evidence-file-required")
    return json.loads(path.read_text())


def cloud(*arguments):
    return invoke(["gcloud", "--project=" + PROJECT, "--account=" + ACCOUNT, *arguments])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=Path.home() / "ms67-evidence")
    args = parser.parse_args(argv)
    os.umask(0o077)
    execution = args.evidence_root.resolve() / ("load-fix-run-" + IMAGE_BUILD)
    refresh = execution / "qualification-refresh" / ("from-" + LOAD_RUN)
    bundle = execution / "regional-load/retry-4f7ccc6c-347d-4d78-a1dc-aede161165eb/bundle"
    print("MS67_SQL_REASSESSMENT=VERIFYING_EXISTING_EVIDENCE", flush=True)
    versions = json.loads(cloud("secrets", "versions", "list", "cloudbank-ms67-evidence-key", "--format=json"))
    enabled = [row["name"] for row in versions if row.get("state") == "ENABLED"]
    require(enabled == ["projects/233419964177/secrets/cloudbank-ms67-evidence-key/versions/1"],
            "evidence-version-1-must-be-sole-enabled-version")
    key = cloud("secrets", "versions", "access", "1", "--secret=cloudbank-ms67-evidence-key").strip()
    require(bool(key), "evidence-key-required")
    state = verified(load(refresh / "refresh-state.json"), key)
    require(state.get("state_type") == "lightyear-ms67-recovery-ms65-refresh"
            and re.fullmatch(r"ms67-refresh-[0-9a-f]{32}", state.get("run_id", ""))
            and state.get("controller_commit") == "22ac6a4c0dcb39fbfdb7eab28cad5eebc4b9ea8e"
            and state.get("passing_load_sha256") == "f23c637611400f8ec9acebc49c3de6ddbcd1ec6d03c9ac3637ce8f837aa34fbf",
            "recorded-refresh-identity-required")
    row = state.get("sql") or {}
    require(row.get("status") == "failed" and type(row.get("attempt")) is int and row["attempt"] == 2,
            "expected-completed-failed-sql-attempt-2")
    source_path = refresh / "sql-attempt-2/database-recovery.json"
    original_bytes = source_path.read_bytes()
    source = verified(load(source_path), key)
    require(source.get("run_id") == row.get("run_id"), "sql-attempt-identity-mismatch")
    prefix = BUCKET + "/qualification-refresh/" + state["run_id"] + "/sql"
    remote = json.loads(cloud("storage", "cat", prefix + "/sql-attempt-2/database-recovery.json"))
    verified(remote, key)
    require(remote == source, "original-signed-evidence-readback-mismatch")
    inputs = argparse.Namespace(
        image_lock=bundle / "image-lock.json", ms64_receipt=bundle / "ms64-receipt.json",
        journeys=bundle / "journeys.json", probe_image=state["inputs"]["probe_image"])
    _, _, journeys, images, binding = load_bound_inputs(inputs, key)
    expected = dict(images=images, environment=binding["environment"], journeys_sha256=journeys["content_sha256"])
    output = refresh / ("sql-reassessment-630-" + source["content_sha256"])
    destination = output / "database-recovery.json"
    if output.exists():
        result = verified(load(destination), key)
        validate_database_recovery(result, key, **expected)
        require(result.get("reassessment", {}).get("source_observation") == source,
                "existing-reassessment-source-mismatch")
    else:
        result = reassess_database_recovery(source, key, ACCOUNT, **expected)
        output.mkdir(mode=0o700)
        write_signed(destination, result, key, ACCOUNT)
        result = verified(load(destination), key)
        validate_database_recovery(result, key, **expected)
    # The uploader reuses the explicit operator account without persisting it.
    previous_account = os.environ.get("CLOUDSDK_CORE_ACCOUNT")
    os.environ["CLOUDSDK_CORE_ACCOUNT"] = ACCOUNT
    try:
        upload(output, prefix, PROJECT, marker="MS67_SQL_REASSESSMENT")
    finally:
        if previous_account is None:
            os.environ.pop("CLOUDSDK_CORE_ACCOUNT", None)
        else:
            os.environ["CLOUDSDK_CORE_ACCOUNT"] = previous_account
    require(source_path.read_bytes() == original_bytes, "original-evidence-was-modified")
    print("MS67_SQL_RECOVERY_ACCEPTANCE=PASSED", flush=True)
    print("MS67_SQL_ACCEPTED_EVIDENCE=" + prefix + "/" + output.name + "/database-recovery.json", flush=True)
    print("MS67_SQL_ACCEPTED_LOCAL=" + str(destination), flush=True)
    print(json.dumps({
        "status": "passed-under-revised-nonproduction-requirement",
        "policy_id": recovery_acceptance_policy()["policy_id"],
        "pitr_rto_seconds": result["pitr"]["database_rto_seconds"],
        "pitr_limit_seconds": 630,
        "backup_restore_rto_seconds": result["backup_restore"]["database_rto_seconds"],
        "rpo_seconds": result["pitr"]["recovery_point_age_seconds"],
        "original_evidence_sha256": source["content_sha256"],
        "original_file_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "original_status": source["status"],
        "measurements_changed": False, "new_recovery_run": False,
        "ms67_complete": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Invocation errors are bounded by the canonical command adapter.
        print("MS67_SQL_REASSESSMENT_ERROR=" + str(error), file=sys.stderr)
        sys.exit(1)
