#!/usr/bin/env python3
"""Continue MS67 with the canonical regional MS65 rehearsal after SQL acceptance.

Uses existing images, shared journeys and the verified 630-second SQL assessment.
No SQL recovery or sustained load run is started. Resuming adopts the saved build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cloudbank_sql_recovery import load_bound_inputs
from ms67_accept_sql_recovery import ACCOUNT, BUCKET, IMAGE_BUILD, LOAD_RUN, PROJECT, cloud, load
from lightyear_data.cloudbank_journeys import require
from lightyear_data.cloudbank_ms65_rehearsal_gke import validate_database_recovery
from lightyear_data.cloudbank_production_readiness import validate_environment, validate_execution_receipt
from lightyear_data.cloudbank_sql_recovery import invoke, verified, write_signed
from lightyear_data.contracts import content_hash

CONTROLLER = "b482699ffb9f38b2c0afefcd35973b2cd8265ae6"
MS66_BUILD = "65d2e95a-24c7-4ca5-8726-f19f1c231c1b"
PRIOR_MS65 = "d9fb3bf4-6c80-48eb-9b09-1d4181fdb3de"
ORIGINAL_SQL_SHA = "96e8efcffb192bcad2c6d53c9d54b475908d10c67cb4c3a192c2ca12ccf1161d"
REGION, CLUSTER, NAMESPACE = "us-west1", "cloudbank-ms67", "cloudbank-ms67"
SA = "cloudbank-ms67-evidence@" + PROJECT + ".iam.gserviceaccount.com"
SA_RESOURCE = "projects/" + PROJECT + "/serviceAccounts/" + SA
TEMPLATE = "factory/cloudbank/platform-qualification/gke/cloudbuild-ms65-rehearsal.yaml"
UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def builder(build, identifier):
    positions = [i for i, row in enumerate(build["steps"]) if row.get("id") == identifier]
    require(len(positions) == 1, "recorded-builder-missing")
    index = positions[0]
    image = build["steps"][index]["name"].split("@")[0]
    resolved = build["results"]["buildStepImages"][index]
    require(image.startswith("gcr.io/") and re.fullmatch(r"sha256:[0-9a-f]{64}", resolved),
            "recorded-builder-digest-invalid")
    return image + "@" + resolved


def build_config(template, git_image, sdk_image, substitutions, tag):
    # Extract the three literal shell bodies from the reviewed canonical YAML;
    # no optional YAML package is needed on the operator's Mac.
    blocks = re.findall(r"(?m)^  - \|\n((?:    [^\n]*\n|\n)+)", template)
    require(len(blocks) == 3, "canonical-ms65-template-shape-changed")
    scripts = ["".join(line[4:] if line.startswith("    ") else line
                       for line in block.splitlines(keepends=True)) for block in blocks]
    steps = [{"id": identifier, "name": image, "entrypoint": "/bin/bash", "args": ["-ceu", script]}
             for identifier, image, script in zip(
                 ("checkout-pinned-controller", "checkout-pinned-cloudbank", "run-ms65-rehearsal"),
                 (git_image, git_image, sdk_image), scripts, strict=True)]
    steps[-1].update(waitFor=["checkout-pinned-controller", "checkout-pinned-cloudbank"],
                     env=["CLOUDSDK_CORE_PROJECT=$PROJECT_ID", "KUBECONFIG=/workspace/ms65-kubeconfig"],
                     secretEnv=["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"])
    require(set(re.findall(r"\$\{(_[A-Z0-9_]+)\}", "\n".join(scripts))) == set(substitutions),
            "canonical-ms65-substitutions-mismatch")
    return {
        "steps": steps, "substitutions": substitutions,
        "availableSecrets": {"secretManager": [{
            "versionName": "projects/" + PROJECT + "/secrets/cloudbank-ms67-evidence-key/versions/1",
            "env": "LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"}]},
        "options": {"machineType": "E2_HIGHCPU_8", "diskSizeGb": "30", "logging": "CLOUD_LOGGING_ONLY"},
        "tags": ["ms67-ms65-rehearsal", tag], "timeout": "3600s", "queueTtl": "600s",
    }


def expanded(value, substitutions, build_id):
    if isinstance(value, list):
        return [expanded(item, substitutions, build_id) for item in value]
    if not isinstance(value, str):
        return value
    value = value.replace("$$", "\x00")
    variables = {**substitutions, "PROJECT_ID": PROJECT, "BUILD_ID": build_id}
    for name, replacement in variables.items():
        value = value.replace("$" + "{" + name + "}", replacement)
        value = re.sub(r"\$" + re.escape(name) + r"\b", lambda _: replacement, value)
    return value.replace("\x00", "$")


def verify_build(build, config):
    build_id = build.get("id", "")
    require(re.fullmatch(UUID, build_id) and build.get("projectId") == PROJECT
            and build.get("serviceAccount") in (SA_RESOURCE, "projects/233419964177/serviceAccounts/" + SA)
            and set(build.get("tags", [])) == set(config["tags"])
            and all(build.get("substitutions", {}).get(k) == v for k, v in config["substitutions"].items())
            and build.get("availableSecrets") == config["availableSecrets"],
            "ms65-build-identity-or-inputs-mismatch")
    actual = build.get("steps", [])
    require(len(actual) == len(config["steps"]), "ms65-build-steps-mismatch")
    for found, expected in zip(actual, config["steps"], strict=True):
        for name in ("id", "name", "entrypoint", "args", "env", "secretEnv", "waitFor"):
            wanted = expected.get(name, [])
            require(found.get(name, []) in (wanted, expanded(wanted, config["substitutions"], build_id)),
                    "ms65-build-worker-mismatch:" + name)


def choose_build(state, matches):
    require(len(matches) <= 1, "multiple-ms65-builds-for-this-assessment")
    saved = state.get("build_id")
    if saved:
        require(re.fullmatch(UUID, saved) and (not matches or matches[0]["id"] == saved),
                "saved-ms65-build-disagrees")
        return saved
    if matches:
        require(re.fullmatch(UUID, matches[0].get("id", "")), "matched-build-id-invalid")
        return matches[0]["id"]
    require(state.get("phase") == "prepared",
            "submission-outcome-unknown-no-duplicate-build-will-be-started")
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=Path.home() / "ms67-evidence")
    args = parser.parse_args(argv)
    os.umask(0o077)
    print("MS67_MS65_CONTINUATION=1", flush=True)
    execution = args.evidence_root.resolve() / ("load-fix-run-" + IMAGE_BUILD)
    refresh = execution / "qualification-refresh" / ("from-" + LOAD_RUN)
    bundle = execution / "regional-load/retry-4f7ccc6c-347d-4d78-a1dc-aede161165eb/bundle"
    source_dir = refresh / ("sql-reassessment-630-" + ORIGINAL_SQL_SHA)
    output = refresh / "ms65-after-sql-630"
    output.mkdir(exist_ok=True, mode=0o700)
    # This continuation is for the existing macOS operator CLI.
    import fcntl
    lock = (output / "operator.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("MS65 continuation is already running on this Mac") from None

    print("MS67_MS65_PHASE=verify accepted SQL and matching inputs", flush=True)
    versions = json.loads(cloud("secrets", "versions", "list", "cloudbank-ms67-evidence-key", "--format=json"))
    require([row["name"] for row in versions if row.get("state") == "ENABLED"] ==
            ["projects/233419964177/secrets/cloudbank-ms67-evidence-key/versions/1"],
            "evidence-version-1-must-be-sole-enabled-version")
    key = cloud("secrets", "versions", "access", "1", "--secret=cloudbank-ms67-evidence-key").strip()
    require(bool(key), "evidence-key-required")
    old = verified(load(refresh / "refresh-state.json"), key)
    require(old.get("state_type") == "lightyear-ms67-recovery-ms65-refresh"
            and re.fullmatch(r"ms67-refresh-[0-9a-f]{32}", old.get("run_id", ""))
            and old.get("ms65", {}).get("status") == "not-started",
            "original-refresh-ms65-state-mismatch")
    sql = verified(load(source_dir / "database-recovery.json"), key)
    require(sql.get("reassessment", {}).get("source_observation_sha256") == ORIGINAL_SQL_SHA
            and sql.get("run_id") == old["sql"].get("run_id"), "accepted-sql-source-mismatch")
    prefix = BUCKET + "/qualification-refresh/" + old["run_id"]
    sql_uri = prefix + "/sql/" + source_dir.name + "/database-recovery.json"
    require(json.loads(cloud("storage", "cat", sql_uri)) == sql, "accepted-sql-readback-mismatch")
    inputs = argparse.Namespace(image_lock=bundle / "image-lock.json", ms64_receipt=bundle / "ms64-receipt.json",
                                journeys=bundle / "journeys.json", probe_image=old["inputs"]["probe_image"])
    ms64, image_lock, journeys, images, bindings = load_bound_inputs(inputs, key)
    recovery = validate_database_recovery(sql, key, images=images, environment=bindings["environment"],
                                         journeys_sha256=journeys["content_sha256"])
    require(bindings["environment"].get("project") == PROJECT
            and bindings["environment"].get("region") == REGION
            and bindings["environment"].get("cluster") == CLUSTER
            and bindings["environment"].get("namespace") == NAMESPACE, "ms65-environment-mismatch")

    print("MS67_MS65_PHASE=read existing configuration and resolved builders", flush=True)
    prior = json.loads(cloud("builds", "describe", PRIOR_MS65, "--region=" + REGION, "--format=json"))
    ms66 = json.loads(cloud("builds", "describe", MS66_BUILD, "--region=" + REGION, "--format=json"))
    for build, expected_id in ((prior, PRIOR_MS65), (ms66, MS66_BUILD)):
        require(build.get("id") == expected_id and build.get("status") == "SUCCESS"
                and build.get("projectId") == PROJECT, "recorded-successful-build-required")
    reference = prior["substitutions"]
    uri = reference["_MS65_ENVIRONMENT_URI"]
    require(uri.startswith(BUCKET + "/"), "recorded-environment-bucket-mismatch")
    environment_bytes = cloud("storage", "cat", uri).encode()
    require(digest(environment_bytes) == reference["_MS65_ENVIRONMENT_SHA256"],
            "recorded-environment-byte-hash-mismatch")
    environment = json.loads(environment_bytes)
    require(not validate_environment(environment)
            and environment["content_sha256"] == old["inputs"]["ms65_environment_sha256"],
            "recorded-ms65-environment-mismatch")
    files = {name: (bundle / (name + ".json")).read_bytes() for name in ("image-lock", "ms64-receipt", "journeys")}
    files.update({"ms65-environment": environment_bytes,
                  "database-recovery": (source_dir / "database-recovery.json").read_bytes()})
    hashes = {name: digest(raw) for name, raw in files.items()}
    identity = content_hash({"controller": CONTROLLER, "inputs": hashes})
    tag = "ms67-ms65-630-" + identity[:24]
    input_prefix = prefix + "/ms65-630-inputs/" + identity
    evidence_prefix = prefix + "/ms65-630"
    substitutions = {"_SOURCE_COMMIT": CONTROLLER, "_REGION": REGION, "_CLUSTER": CLUSTER,
                     "_NAMESPACE": NAMESPACE, "_SIGNER": SA, "_EVIDENCE_BUCKET_PREFIX": evidence_prefix}
    for name, sha in hashes.items():
        variable = "_" + name.upper().replace("-", "_")
        substitutions[variable + "_URI"] = input_prefix + "/" + name + ".json"
        substitutions[variable + "_SHA256"] = sha
    template = invoke(["git", "-C", str(ROOT), "show", CONTROLLER + ":" + TEMPLATE])
    config = build_config(template, builder(ms66, "checkout-pinned-controller"),
                          builder(ms66, "run-durable-ms66-dual-lane"), substitutions, tag)
    state_path = output / "continuation-state.json"
    expected = {"state_type": "ms67-ms65-after-accepted-sql-630", "controller_commit": CONTROLLER,
                "accepted_sql_sha256": sql["content_sha256"], "config_sha256": content_hash(config),
                "input_hashes": hashes, "tag": tag, "ms67_complete": False}
    if state_path.exists():
        state = verified(load(state_path), key)
        require(all(state.get(k) == v for k, v in expected.items()), "continuation-state-inputs-changed")
    else:
        state = {**expected, "phase": "prepared"}
        write_signed(state_path, state, key, ACCOUNT)
    config_path = output / "cloudbuild.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    matches = json.loads(cloud("builds", "list", "--region=" + REGION, "--filter=tags:" + tag,
                               "--limit=100", "--format=json"))
    build_id = choose_build(state, matches)
    if build_id is None:
        active = json.loads(cloud("builds", "list", "--region=" + REGION, "--ongoing", "--format=json"))
        require(not any("ms67-ms65-rehearsal" in row.get("tags", []) for row in active),
                "another-ms65-rehearsal-is-active")
        print("MS67_MS65_PHASE=stage exact verified inputs", flush=True)
        for name, raw in files.items():
            path = output / (name + ".json")
            path.write_bytes(raw)
            destination = input_prefix + "/" + path.name
            cloud("storage", "cp", str(path), destination)
            require(cloud("storage", "cat", destination).encode() == raw, "ms65-input-readback-mismatch")
        state["phase"] = "submitting"
        write_signed(state_path, state, key, ACCOUNT)
        print("MS67_MS65_PHASE=submit one canonical regional rehearsal", flush=True)
        build_id = cloud("builds", "submit", "--no-source", "--region=" + REGION,
                         "--config=" + str(config_path), "--service-account=" + SA_RESOURCE,
                         "--async", "--format=value(id)").strip()
        require(re.fullmatch(UUID, build_id), "build-id-missing-resume-to-adopt-submission")
    state.update(phase="submitted", build_id=build_id)
    write_signed(state_path, state, key, ACCOUNT)
    print("MS67_MS65_BUILD_ID=" + build_id, flush=True)
    deadline = time.monotonic() + 4500
    while True:
        build = json.loads(cloud("builds", "describe", build_id, "--region=" + REGION, "--format=json"))
        verify_build(build, config)
        status = build.get("status")
        steps = "; ".join(row["id"] + "=" + row.get("status", "PENDING") for row in build.get("steps", []))
        print(time.strftime("%H:%M:%S UTC", time.gmtime()) + " | MS65 " + str(status) + " | " + steps, flush=True)
        if status not in ("QUEUED", "PENDING", "WORKING"):
            break
        require(time.monotonic() < deadline, "monitor-timeout-resume-the-same-build")
        time.sleep(20)
    state["build_status"] = status
    write_signed(state_path, state, key, ACCOUNT)
    receipt_prefix = evidence_prefix + "/ms65-rehearsal-" + build_id
    if status != "SUCCESS":
        print("MS67_MS65_FAILURE_EVIDENCE=" + receipt_prefix + "/ms65-rehearsal.failure.json", flush=True)
        raise RuntimeError("MS65 build failed; preserve its recovery state before another attempt")

    print("MS67_MS65_PHASE=verify signed receipt and exact release bindings", flush=True)
    receipt_uri = receipt_prefix + "/cloudbank-production-readiness.receipt.json"
    raw = cloud("storage", "cat", receipt_uri)
    receipt = verified(json.loads(raw), key)
    require(not validate_execution_receipt(receipt, key, ROOT)
            and receipt["run_id"] == "ms65-" + build_id
            and receipt["signer"] == SA
            and receipt["source_ms64_receipt_sha256"] == ms64["content_sha256"]
            and receipt["image_lock_sha256"] == image_lock["content_sha256"]
            and receipt["environment_sha256"] == environment["content_sha256"]
            and receipt["cluster_identity_sha256"] == environment["cluster_identity_sha256"]
            and receipt["rehearsal"]["backup_restore"] == recovery
            and {row["service"]: row["image"] for row in receipt["rehearsal"]["service_rollouts"]} == images,
            "ms65-receipt-release-or-recovery-bindings-invalid")
    (output / "cloudbank-production-readiness.receipt.json").write_text(raw)
    state.update(phase="verified", receipt_uri=receipt_uri, receipt_sha256=receipt["content_sha256"])
    write_signed(state_path, state, key, ACCOUNT)
    print("MS67_MS65_EVIDENCE_READBACK=VERIFIED", flush=True)
    print("MS67_MS65_RECEIPT=" + receipt_uri, flush=True)
    print("MS67_MS65_REFRESH=VERIFIED", flush=True)
    print("MS67_MS65_LOCAL=" + str(output), flush=True)
    print("SQL and load evidence retained; full MS67 platform admission remains separate.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("MS67_MS65_INTERRUPTED=Resume the same command; the remote build is preserved", file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print("MS67_MS65_CONTINUATION_ERROR=" + str(error), file=sys.stderr)
        sys.exit(1)
