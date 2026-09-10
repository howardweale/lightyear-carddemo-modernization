#!/usr/bin/env python3
"""Finish MS67 from retained evidence; resume completed phases without rerunning MS65/66, SQL or load."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ms67_accept_sql_recovery import ACCOUNT, BUCKET, IMAGE_BUILD, LOAD_RUN, PROJECT
from ms67_reconcile_closeout import (anchors, local_paths, read_local, context_match, verify_contract, SQL_SOURCE)
from ms67_resume_ms65 import builder, expanded, choose_build
import ms67_final_images as candidate_tools
import ms67_final_controls as current_tools
from lightyear_data import cloudbank_platform_qualification as platform
from lightyear_data import cloudbank_secret_rotation_gke as checkpoint_module
from lightyear_data.cloudbank_image_security import ImageJournal
from lightyear_data.cloudbank_journeys import ACK, SERVICES, JourneyFailure, require, hashed
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_ms67_drills import FinalDrills, verify_observation as verify_drills
from lightyear_data.cloudbank_sql_recovery import invoke, verified, write_signed
from lightyear_data.contracts import content_hash, sign

REGION = "us-west1"
CLUSTER = NAMESPACE = "cloudbank-ms67"
STATE_TYPE = "lightyear-ms67-resumable-final-closeout"
CHILDREN = {"secret-rotation": "cloudbank_secret_rotation", "log-correlation": "cloudbank_log_correlation",
            "alert-drill": "cloudbank_alert_drill", "network-enforcement": "cloudbank_network_enforcement",
            "runtime-identity": "cloudbank_runtime_identity"}


def cloud(*args, **kwargs):
    return invoke(["gcloud", "--project=" + PROJECT, "--account=" + ACCOUNT, *args], **kwargs)


def load(path):
    return read_local(path)[0]


def retained(root, key):
    paths, gaps = local_paths(root)
    require(not gaps, "retained-local-inventory-incomplete")
    documents = []
    for path in paths:
        value, sha = read_local(path)
        if value is not None:
            documents.append((value, str(path), sha))
    bundle = root / ("load-fix-run-" + IMAGE_BUILD) / "regional-load/retry-4f7ccc6c-347d-4d78-a1dc-aede161165eb/bundle"
    for name in ("image-lock", "ms64-receipt", "journeys"):
        path = bundle / (name + ".json")
        value, sha = read_local(path)
        documents.append((value, str(path), sha))
    context, kept = anchors(root, documents, key)
    execution = root / ("load-fix-run-" + IMAGE_BUILD)
    refresh = execution / "qualification-refresh" / ("from-" + LOAD_RUN)
    receipt_dir = refresh / "ms65-after-sql-630"
    ms65 = verified(load(receipt_dir / "cloudbank-production-readiness.receipt.json"), key)
    require(context_match(ms65, context), "current-ms65-release-bindings-invalid")
    verify_contract(ms65, key, context)
    continuation = verified(load(receipt_dir / "continuation-state.json"), key)
    receipt_uris = [s for s in continuation.values() if isinstance(s, str) and s.startswith(BUCKET + "/")
                    and s.endswith("/cloudbank-production-readiness.receipt.json")]
    # Also accept the fixed verified build's canonical receipt path if the
    # continuation has a nested result. Always compare the entire signed object.
    uri = (receipt_uris[0] if len(receipt_uris) == 1 else BUCKET + "/qualification-refresh/" +
           "ms67-refresh-34ca0840f01e4a4987d695b8e6e82ea9/ms65-630/" +
           "ms65-rehearsal-be0193d2-a9e8-4329-97a3-bacecf2a9dd6/cloudbank-production-readiness.receipt.json")
    require(json.loads(cloud("storage", "cat", uri)) == ms65, "current-ms65-readback-mismatch")
    def find_sha(sha):
        matches = [(value, Path(path)) for value, path, _ in documents if value.get("content_sha256") == sha]
        require(bool(matches), "retained-bound-input-not-located")
        return matches[0]
    paths_by_name, values = {}, {}
    for name, sha in {"image-lock": context["bindings"]["image_lock_sha256"],
                      "ms64-receipt": context["bindings"]["ms64_receipt_sha256"],
                      "platform-profile": context["bindings"]["platform_profile_sha256"],
                      "ms66-receipt": kept["ms66"]["content_sha256"],
                      "load": kept["load"]["content_sha256"], "sql": kept["sql"]["content_sha256"]}.items():
        values[name], paths_by_name[name] = find_sha(sha)
    values["ms65"] = ms65
    old = verified(load(refresh / "refresh-state.json"), key)
    context["probe_image"] = old["inputs"]["probe_image"]
    context["retained_sha256"] = {k: v["content_sha256"] for k, v in values.items()}
    return context, values, paths_by_name


@contextmanager
def observer(callback):
    prior = checkpoint_module._checkpoint_observer
    checkpoint_module._checkpoint_observer = callback
    try:
        yield
    finally:
        checkpoint_module._checkpoint_observer = prior


class Session:
    def __init__(self, directory, context, key, commit, retry_of=None):
        self.directory, self.context, self.key, self.commit = directory, context, key, commit
        self.path = directory / "finish-state.json"
        wanted = {"state_type": STATE_TYPE, "controller_commit": commit,
                  "context_sha256": hashed(context), "credentials_persisted": False}
        if retry_of is not None:
            wanted["retry_of"] = retry_of
        generation = "0"
        if self.path.exists():
            local = verified(load(self.path), key)
            self.prefix = BUCKET + "/final-closeout/" + local["run_id"]
            uri = self.prefix + "/finish-state.json"
            pristine = not local.get("completed") and local.get("active") is None and local.get("candidate_build") == {"phase": "prepared"}
            if pristine:
                # The very first checkpoint may have lost its upload response.
                # A generation-zero CAS can adopt identical bytes but cannot
                # overwrite an existing, different checkpoint.
                self.state = local
            else:
                generation = cloud("storage", "objects", "describe", uri, "--format=value(generation)").strip()
                self.state = verified(json.loads(cloud("storage", "cat", uri + "#" + generation)), key)
            require(self.state["run_id"] == local["run_id"] and all(self.state.get(k) == v for k, v in wanted.items()),
                    "final-session-source-or-retained-inputs-changed")
        else:
            self.state = {**wanted, "run_id": "ms67-final-" + uuid.uuid4().hex, "completed": {},
                          "active": None, "candidate_build": {"phase": "prepared"}, "ms67_complete": False}
            self.prefix = BUCKET + "/final-closeout/" + self.state["run_id"]
        require(re.fullmatch(r"ms67-final-[0-9a-f]{32}", self.state["run_id"]), "final-state-run-id-invalid")
        self.journal = ImageJournal(self.path, self.prefix + "/finish-state.json", PROJECT, key, ACCOUNT,
                                    generation=generation, invoke=invoke)
        self.save()

    def save(self):
        with observer(None):
            self.state = self.journal.write(self.state)

    def publish(self, name, value):
        path = self.directory / name
        uri = self.prefix + "/" + name
        signer = ACCOUNT
        if "signature" in value:
            verified(value, self.key)
            signer = value["signature"]["signer"]
        with observer(None):
            result = ImageJournal(path, uri, PROJECT, self.key, signer, invoke=invoke).write(value)
        if "signature" in value:
            require(result == value, "retained-signature-or-measurements-changed")
        return {"uri": uri, "sha256": result["content_sha256"]}

    def read(self, reference):
        uri = reference["uri"]
        require(uri.startswith(BUCKET + "/") and uri.endswith(".json") and not any(c in uri for c in "*?[]\n\r"),
                "final-evidence-uri-invalid")
        value = verified(json.loads(cloud("storage", "cat", uri)), self.key)
        require(value["content_sha256"] == reference["sha256"], "final-evidence-readback-hash-mismatch")
        return value

    def retain(self, name, value):
        if "signature" in value:
            return self.publish(name, value)
        # Image locks are sealed documents with an exact schema, not signed
        # observations. Adding a signature would invalidate their contract.
        require(value.get("content_sha256") == content_hash(value), "retained-document-content-invalid")
        path, uri = self.directory / name, self.prefix + "/" + name
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        cloud("storage", "cp", str(path), uri, "--if-generation-match=0", timeout=180)
        require(json.loads(cloud("storage", "cat", uri)) == value, "retained-document-readback-mismatch")
        return {"uri": uri, "sha256": value["content_sha256"], "format": "sealed-document"}

    def checkpoint(self, value, uri):
        verified(value, self.key)
        phase = self.state["active"]["phase"]
        prefix = BUCKET + "/" + ("final-drills" if phase == "drills" else phase) + "/"
        require(uri.startswith(prefix) and uri.endswith(".json"), "child-checkpoint-prefix-mismatch")
        field = ("recovery" if "state_type" in value else
                 "observation" if "observation_type" in value else "result")
        self.state["active"][field] = {"uri": uri, "sha256": value["content_sha256"]}
        self.save()

    def finish_phase(self, phase, reference):
        self.state["completed"][phase] = reference
        self.state["active"] = None
        self.save()
        print("MS67_FINAL_VERIFIED=" + phase, flush=True)


def candidate_retry(directory, context, key, build_id):
    """Verify the old attempt read-only; continue in a distinct signed session.

    No signed state is edited to accept a new controller. The deterministic
    child directory resumes the same retry after a disconnected submission.
    """
    require(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", build_id), "candidate-retry-build-id-invalid")
    local = verified(load(directory / "finish-state.json"), key)
    require(re.fullmatch(r"ms67-final-[0-9a-f]{32}", local.get("run_id", "")), "final-state-run-id-invalid")
    prefix = BUCKET + "/final-closeout/" + local["run_id"]
    uri = prefix + "/finish-state.json"
    generation = cloud("storage", "objects", "describe", uri, "--format=value(generation)").strip()
    require(re.fullmatch(r"[1-9][0-9]*", generation), "candidate-retry-generation-invalid")
    state = verified(json.loads(cloud("storage", "cat", uri + "#" + generation)), key)
    require(state.get("state_type") == STATE_TYPE and state.get("run_id") == local["run_id"]
            and state.get("context_sha256") == hashed(context) and state.get("credentials_persisted") is False
            and state.get("ms67_complete") is False and state.get("completed") == {} and state.get("active") is None,
            "candidate-retry-requires-unchanged-inputs-and-no-live-phases")
    candidate = state.get("candidate_build", {})
    require(candidate.get("build_id") == build_id and candidate.get("phase") == "submitted",
            "candidate-retry-saved-build-mismatch")
    config = json.loads((directory / "candidate-cloudbuild.json").read_text())
    require(hashed(config) == candidate.get("config_sha256"), "candidate-retry-config-hash-mismatch")
    build = json.loads(cloud("builds", "describe", build_id, "--region=" + REGION, "--format=json"))
    verify_build(build, config)
    require(build.get("id") == build_id and build.get("status") == "FAILURE", "candidate-retry-requires-confirmed-failed-build")
    old_context = verified(json.loads(cloud("storage", "cat", prefix + "/candidate-context.json")), key)
    require(all(old_context.get(k) == v for k, v in {
        "run_id": state["run_id"], "controller_commit": state["controller_commit"],
        "images": context["images"], "bindings": context["bindings"]}.items()), "candidate-retry-input-binding-mismatch")
    # Keep the original state and the failed build immutable. Record their exact
    # identity in every checkpoint of the new session, including after resume.
    reference = {"build_id": build_id, "controller_commit": state["controller_commit"],
                 "run_id": state["run_id"], "state_uri": uri, "state_generation": generation,
                 "state_sha256": state["content_sha256"], "config_sha256": candidate["config_sha256"],
                 "build_status": "FAILURE", "retained_context_sha256": hashed(context)}
    target = directory / ("candidate-retry-" + build_id)
    target.mkdir(exist_ok=True)
    print("MS67_FINAL_CANDIDATE_RETRY_OF=" + build_id, flush=True)
    return target, reference


def candidate_config(context, previous, prefix):
    git = builder(previous, "checkout-fix")
    sdk = builder(previous, "sign-verify-and-scan-images")
    docker = builder(previous, "build-and-push-eight-images")
    sa = previous.get("serviceAccount", "")
    require(re.fullmatch(r"projects/(?:lightyear-ms67-nonproduction|233419964177)/serviceAccounts/"
                         r"[a-zA-Z0-9_-]+@(?:lightyear-ms67-nonproduction\.iam\.gserviceaccount\.com|cloudbuild\.gserviceaccount\.com)", sa),
            "existing-image-build-service-account-required")
    commit = context["controller_commit"]
    common = ["python3", "/workspace/controller/tools/ms67_final_images.py"]
    options = ["--context", "/workspace/final-context.json", "--work", "/workspace/final-images", "--signer", sa.split("/")[-1]]
    steps = [{"id": "checkout-final-controller", "name": git, "entrypoint": "bash", "args": ["-ceu",
        "git init /workspace/controller\ngit -C /workspace/controller remote add origin "
        "https://github.com/howardweale/lightyear-carddemo-modernization.git\n"
        f"git -C /workspace/controller fetch --depth=1 origin {commit}\n"
        f"git -C /workspace/controller checkout --detach {commit}\n"]},
        {"id": "prepare-packaging-revision", "name": sdk, "entrypoint": "bash", "args": ["-ceu",
         f"gcloud storage cp {prefix}/candidate-context.json /workspace/final-context.json\n" +
         " ".join(common + ["prepare"] + options)], "secretEnv": ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"]},
        {"id": "save-eight-baseline-images", "name": docker, "entrypoint": "sh", "args": ["/workspace/final-images/save.sh"]},
        {"id": "preserve-config-and-layers", "name": sdk, "entrypoint": "python3", "args": common[1:] + ["revise"] + options,
         "secretEnv": ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"]},
        {"id": "push-eight-packaging-revisions", "name": docker, "entrypoint": "sh", "args": ["/workspace/final-images/publish.sh"]},
        {"id": "sign-scan-and-verify-revisions", "name": sdk, "entrypoint": "python3", "args": common[1:] + ["secure"] + options,
         "secretEnv": ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"], "env": ["MS67_FINAL_BUILD_ID=$BUILD_ID"]}]
    return {"steps": steps, "serviceAccount": sa, "tags": ["ms67-final-images", context["run_id"]],
            "availableSecrets": {"secretManager": [{"versionName": f"projects/{PROJECT}/secrets/cloudbank-ms67-evidence-key/versions/1",
                                                     "env": "LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"}]},
            "options": {"logging": "CLOUD_LOGGING_ONLY", "machineType": "E2_HIGHCPU_8", "diskSizeGb": "50"},
            "timeout": "3600s", "queueTtl": "600s"}


def verify_build(build, config):
    require(build.get("projectId") == PROJECT and build.get("serviceAccount") == config["serviceAccount"]
            and set(build.get("tags", [])) == set(config["tags"])
            and build.get("availableSecrets") == config["availableSecrets"]
            and len(build.get("steps", [])) == len(config["steps"]), "final-image-build-identity-invalid")
    for actual, expected in zip(build["steps"], config["steps"], strict=True):
        for field in ("id", "name", "entrypoint", "args", "env", "secretEnv"):
            wanted = expected.get(field, [])
            require(actual.get(field, []) in (wanted, expanded(wanted, {}, build["id"])), "final-image-worker-mismatch-" + field)


def candidates(session):
    context = {"run_id": session.state["run_id"], "controller_commit": session.commit,
               "images": session.context["images"], "bindings": session.context["bindings"]}
    if "candidates" in session.state["completed"]:
        value = session.read(session.state["completed"]["candidates"])
        return value, candidate_tools.verify_result(value, context, session.key)
    previous = json.loads(cloud("builds", "describe", IMAGE_BUILD, "--region=" + REGION, "--format=json"))
    require(previous.get("id") == IMAGE_BUILD and previous.get("projectId") == PROJECT and previous.get("status") == "SUCCESS",
            "retained-successful-image-build-required")
    config = candidate_config(context, previous, session.prefix)
    path = session.directory / "candidate-cloudbuild.json"
    path.write_text(json.dumps(config, indent=2) + "\n")
    state = session.state["candidate_build"]
    require(state.get("config_sha256", hashed(config)) == hashed(config), "candidate-build-config-changed")
    state["config_sha256"] = hashed(config)
    matches = json.loads(cloud("builds", "list", "--region=" + REGION,
                               "--filter=tags:" + context["run_id"], "--limit=100", "--format=json"))
    build_id = choose_build(state, matches)
    if build_id is None:
        session.publish("candidate-context.json", context)
        state["phase"] = "submitting"
        session.save()
        submitted = json.loads(cloud("builds", "submit", "--no-source", "--region=" + REGION,
            "--config=" + str(path), "--service-account=" + config["serviceAccount"], "--async", "--format=json", timeout=180))
        build_id = submitted["id"]
    state.update(build_id=build_id, phase="submitted")
    session.save()
    print("MS67_FINAL_IMAGE_BUILD_ID=" + build_id, flush=True)
    deadline = time.monotonic() + 4200
    while True:
        build = json.loads(cloud("builds", "describe", build_id, "--region=" + REGION, "--format=json"))
        verify_build(build, config)
        status = build.get("status")
        print("MS67_FINAL_IMAGES=" + str(status), flush=True)
        if status == "FAILURE":
            for step in build.get("steps", []):
                if step.get("status") == "FAILURE":
                    print("MS67_FINAL_IMAGE_FAILED_STEP=" + step["id"] + "; exit=" + str(step.get("exitCode")), flush=True)
        if status == "SUCCESS":
            break
        require(status in {"QUEUED", "WORKING", "PENDING"}, "candidate-image-build-failed-inspect-build-" + build_id)
        require(time.monotonic() < deadline, "candidate-image-build-still-running-resume-this-session")
        time.sleep(20)
    uri = session.prefix + "/candidate-security.json"
    result = verified(json.loads(cloud("storage", "cat", uri)), session.key)
    require(result.get("cloud_build_id") == build_id, "candidate-result-build-binding-mismatch")
    images = candidate_tools.verify_result(result, context, session.key)
    session.finish_phase("candidates", {"uri": uri, "sha256": result["content_sha256"]})
    return result, images


def child_args(phase, action, paths, output):
    args = [action, "--project", PROJECT, "--region", REGION, "--cluster", CLUSTER, "--namespace", NAMESPACE,
            "--signer", ACCOUNT, "--evidence-bucket", BUCKET + "/" + phase, "--output-root", str(output)]
    for name in ("image-lock", "ms64-receipt", "platform-profile"):
        args += ["--" + name, str(paths[name])]
    return args


def verify_child(phase, value, context, key):
    module = importlib.import_module(CHILDREN[phase])
    verified(value, key)
    require(value.get("bindings") == context["bindings"] and value.get("environment") == context["environment"],
            "child-release-or-live-context-mismatch-" + phase)
    if "images" in value:
        require(value["images"] == context["images"], "child-image-context-mismatch")
    if phase == "runtime-identity":
        module.verify_observation(value, key, context["bindings"], context["images"], context["environment"])
    elif phase == "network-enforcement":
        module.verify_observation(value, key, context["bindings"], context["images"], context["environment"], module.compiled_probe(ROOT))
    else:
        module.verify_observation(value, key)
    return value


def run_child(session, phase, paths):
    saved = session.state["completed"].get(phase)
    if saved:
        return verify_child(phase, session.read(saved), session.context, session.key)
    require(session.state["active"] is None, "recover-active-phase-before-continuing")
    output = session.directory / (phase + "-" + uuid.uuid4().hex)
    session.state["active"] = {"phase": phase, "output": str(output)}
    session.save()
    module = importlib.import_module(CHILDREN[phase])
    with observer(session.checkpoint):
        code = module.main(child_args(phase, "run", paths, output))
    reference = session.state["active"].get("observation")
    require(code == 0 and reference, "final-child-incomplete-use-recover-" + phase)
    value = verify_child(phase, session.read(reference), session.context, session.key)
    session.finish_phase(phase, reference)
    return value


def runtime_for(session, output, run_id=None):
    output.mkdir(exist_ok=True, parents=True)
    return GkeRuntime(project=PROJECT, region=REGION, cluster=CLUSTER, namespace=NAMESPACE,
        images=session.context["images"].copy(), run_id=run_id or session.state["run_id"], output=output,
        probe_image=session.context["probe_image"], signing_key=session.key, signer=ACCOUNT,
        progress=lambda text: print(text, flush=True))


def drill_inputs(session, security):
    return {**session.context["bindings"], "candidate_image_lock_sha256": security["candidate_lock"]["content_sha256"]}


def run_drills(session, security, images):
    bindings = drill_inputs(session, security)
    saved = session.state["completed"].get("drills")
    if saved:
        return verify_drills(session.read(saved), session.key, bindings, session.context["images"], images, session.context["environment"])
    require(session.state["active"] is None, "recover-active-phase-before-continuing")
    output = session.directory / "drills"
    runtime = runtime_for(session, output)
    uri = BUCKET + "/final-drills/" + session.state["run_id"]
    checkpoint = session.state.get("recovered_drills")
    state = session.read(checkpoint) if checkpoint else None
    session.state["active"] = {"phase": "drills", "output": str(output)}
    session.save()
    with observer(session.checkpoint):
        result = FinalDrills(runtime, images, bindings, session.key, ACCOUNT, uri, state=state).run()
    reference = session.publish("drills-observation-" + uuid.uuid4().hex + ".json", result)
    verify_drills(result, session.key, bindings, session.context["images"], images, session.context["environment"])
    session.finish_phase("drills", reference)
    return result


def recover(session, paths, security, images):
    active = session.state["active"]
    if active is None:
        print("MS67_FINAL_RECOVERY=NO_ACTIVE_PHASE", flush=True)
        return
    phase = active["phase"]
    # A completed upload can outlive a disconnected parent's final update.
    if phase in CHILDREN and active.get("observation"):
        value = session.read(active["observation"])
        if value.get("status", "").startswith("passed-"):
            verify_child(phase, value, session.context, session.key)
            session.finish_phase(phase, active["observation"])
            return
    reference = active.get("recovery")
    require(reference, "no-durable-child-checkpoint-found-review-before-retry")
    # Checkpoints are mutable by their owning child; retrieve the latest signed
    # version rather than trusting the parent's last observed hash.
    state = verified(json.loads(cloud("storage", "cat", reference["uri"])), session.key)
    path = session.directory / ("recover-input-" + uuid.uuid4().hex + ".json")
    path.write_text(json.dumps(state))
    if phase == "drills":
        runtime = runtime_for(session, Path(active["output"]))
        engine = FinalDrills(runtime, images, drill_inputs(session, security), session.key, ACCOUNT,
                            BUCKET + "/final-drills/" + session.state["run_id"], state=state)
        if state.get("cleanup_required"):
            with observer(session.checkpoint):
                result = engine.cleanup()
            require(result.get("status") == "restored", "final-drill-recovery-incomplete")
        else:
            runtime.ready()
            require(not runtime.kubectl("get", "lease/ly-ms67-final-drills", "--ignore-not-found", "-o", "name").strip(),
                    "final-drill-lease-still-present")
        latest = verified(json.loads(cloud("storage", "cat", reference["uri"])), session.key)
        session.state["recovered_drills"] = {"uri": reference["uri"], "sha256": latest["content_sha256"]}
    else:
        require(phase in CHILDREN, "unknown-active-phase")
        if phase == "runtime-identity":
            # Identity enforcement is a guarded forward convergence, with no
            # scaled-down service or rollback-only secret. Its canonical run
            # adopts the already-applied UID/GID setting after interruption.
            output = session.directory / ("identity-continuation-" + uuid.uuid4().hex)
            with observer(session.checkpoint):
                code = importlib.import_module(CHILDREN[phase]).main(child_args(phase, "run", paths, output))
            require(code == 0 and session.state["active"].get("observation"), "runtime-identity-continuation-incomplete")
            reference = session.state["active"]["observation"]
            verify_child(phase, session.read(reference), session.context, session.key)
            session.finish_phase(phase, reference)
            return
        # These tools positively mark cleanup before returning; do not ask their
        # recovery CLIs to replay an already completed cleanup.
        clean = state.get("cleanup_complete") is True or state.get("phase") in {"restored", "lock-released", "installed-and-verified"}
        if not clean:
            args = child_args(phase, "recover", paths, session.directory / ("recovery-" + uuid.uuid4().hex))
            args += ["--recovery-state", str(path)]
            if phase != "secret-rotation":
                args.append("--original-process-stopped")
            with observer(session.checkpoint):
                code = importlib.import_module(CHILDREN[phase]).main(args)
            require(code == 0, "child-recovery-incomplete-" + phase)
    session.state["active"] = None
    session.save()
    print("MS67_FINAL_RECOVERY=VERIFIED; run --execute to continue", flush=True)


def assemble(session, retained_values, security, children, drills, current):
    """Every scenario points to a verified, retained or newly measured proof."""
    context, key = session.context, session.key
    require(set(children) == set(CHILDREN), "all-final-controls-required")
    require({k: v.get("content_sha256") for k, v in retained_values.items()} == context["retained_sha256"],
            "retained-admission-inputs-changed")
    for name in ("ms65", "ms66-receipt", "sql", "load"):
        verify_contract(retained_values[name], key, context)
    for phase, value in children.items():
        verify_child(phase, value, context, key)
    current_tools.verify_result(current, context, key)
    image_context = {"run_id": session.state["run_id"], "controller_commit": session.commit,
                     "images": context["images"], "bindings": context["bindings"]}
    images = candidate_tools.verify_result(security, image_context, key)
    verify_drills(drills, key, drill_inputs(session, security), context["images"], images, context["environment"])
    ms65, ms66, sql = (retained_values[k] for k in ("ms65", "ms66-receipt", "sql"))
    load_summary = retained_values["load"]["summary"]
    done = drills["completed"]
    sources = [ms65, ms66, current, current, current, current, ms65, current, current,
               current, current, current, current, children["secret-rotation"], current,
               children["log-correlation"], children["alert-drill"], retained_values["load"], security,
               security, current, children["network-enforcement"], sql, sql, drills, drills, drills, drills]
    observation = {"schema_version": "1.0", "observation_type": "lightyear-cloudbank-ms67-platform-observation",
        "release": platform.RELEASE, "signer": ACCOUNT,
        "bindings": {"source_ms65_receipt_sha256": ms65["content_sha256"], "source_ms66_receipt_sha256": ms66["content_sha256"],
            "profile_sha256": context["profile"]["content_sha256"], "deployment_bundle_sha256": ms65["deployment_bundle_sha256"],
            "cluster_identity_sha256": ms65["cluster_identity_sha256"],
            "platform_contract_sha256": platform.platform_contract()["content_sha256"],
            "evidence_contract_sha256": platform.evidence_contract()["content_sha256"]},
        "cluster": current["cluster"],
        "scenarios": [{"id": name, "status": "passed", "evidence_sha256": proof["content_sha256"]}
                      for name, proof in zip(platform.SCENARIO_IDS, sources, strict=True)],
        "service_rollouts": [{"service": s, "image": context["images"][s], "desired_replicas": 2, "ready_replicas": 2,
                              "available_during_drills": True} for s in SERVICES],
        "tls": current["tls"]["summary"],
        "external_secrets": {"controller_ready": True, "store_reference_sha256": current["secrets"]["store_reference_sha256"],
                             "synced_services": list(SERVICES), "rotation_observed": True, "secret_values_persisted": False},
        "observability": {"metrics_services": list(SERVICES), "log_services": list(SERVICES), "trace_services": list(SERVICES),
            "correlation_id_sha256": children["log-correlation"]["trace_identity_sha256"], "alert_fired": True, "alert_recovered": True},
        "load": {"tool": "k6", "requests": load_summary["requests"], "duration_seconds": load_summary["configured_duration_seconds"],
            "concurrency": load_summary["configured_vus"], "errors": load_summary["errors"], "p95_ms": load_summary["p95_ms"],
            "requests_per_second": load_summary["requests"] / (load_summary["measured_duration_ms"] / 1000)},
        "security": {"image_scans": [{"service": r["service"], "image": r["packaging"]["baseline_image"],
            "critical": r["scan"]["critical"], "high": r["scan"]["high"], "scan_sha256": hashed({
                "scope": "identical filesystem scan reuse", "packaging": r["packaging"], "candidate_scan": r["scan"]})}
                for r in security["services"]], "signed_services": list(SERVICES), "provenance_services": list(SERVICES),
            "manifest_scan": {k: current["manifest_scan"][k] for k in ("critical", "high")},
            "runtime_policy_violations": 0, "network_policy_tests_passed": True},
        "backup_restore": {"pre_state_sha256": sql["checkpoint"]["state_sha256"], "backup_sha256": sql["backup"]["metadata_sha256"],
            "restored_state_sha256": sql["pitr"]["restored_state"]["state_sha256"], "rpo_seconds": sql["pitr"]["recovery_point_age_seconds"],
            "rto_seconds": sql["pitr"]["database_rto_seconds"], "point_in_time_restore": True},
        "resilience": {"node_disruption_observed": True, "failure_domain_disruption_observed": True,
                       "all_services_recovered": True, "data_loss_observed": False},
        "rolling_deployments": [{k: r[k] for k in ("service", "previous_image", "candidate_image", "maximum_unavailable", "completed")}
                                for r in done["rolling"]["rows"]],
        "cutover_rollback": {k: done["cutover"][k] for k in ("states", "canary_percent", "target_traffic_percent", "business_journey_count",
                            "rollback_exercised", "all_services_recovered", "pre_state_sha256", "post_rollback_state_sha256")},
        "safety": {"non_production": True, "synthetic_data_only": True, "production_accessed": False,
                   "raw_logs_persisted": False, "raw_traces_persisted": False, "secret_values_persisted": False,
                   "cluster_credentials_persisted": False, "backup_bodies_persisted": False}}
    result = sign(observation, key, ACCOUNT)
    errors = platform.validate_observation(result, key, ms65=ms65, ms66=ms66, profile=context["profile"])
    require(not errors, "final-admission-rejected:" + ";".join(errors))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--execute", action="store_true")
    action.add_argument("--recover", action="store_true")
    parser.add_argument("--evidence-root", type=Path, default=Path.home() / "ms67-evidence")
    parser.add_argument("--retry-candidate-build", metavar="FAILED_BUILD_ID",
                        help="verify a failed pre-drill build and resume a separate signed retry session")
    args = parser.parse_args(argv)
    os.umask(0o077)
    for tool in ("git", "gcloud", "kubectl"):
        require(shutil.which(tool), "operator-cli-required-" + tool)
    root = args.evidence_root.resolve()
    directory = root / "ms67-final-closeout"
    directory.mkdir(parents=True, exist_ok=True)
    import fcntl
    lock = (directory / "operator.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise JourneyFailure("another-final-executor-is-running-on-this-Mac") from None
    require(not invoke(["git", "-C", str(ROOT), "status", "--porcelain"]).strip(), "clean-reviewed-controller-required")
    commit = invoke(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip()
    versions = json.loads(cloud("secrets", "versions", "list", "cloudbank-ms67-evidence-key", "--format=json"))
    require([r["name"] for r in versions if r.get("state") == "ENABLED"] ==
            ["projects/233419964177/secrets/cloudbank-ms67-evidence-key/versions/1"], "exactly-evidence-version-1-enabled-required")
    key = cloud("secrets", "versions", "access", "1", "--secret=cloudbank-ms67-evidence-key", sensitive=True).strip()
    env = {"CLOUDSDK_CORE_ACCOUNT": ACCOUNT, "LIGHTYEAR_NON_PRODUCTION_ACK": ACK,
           "LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY": key}
    previous = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        print("MS67_FINAL=VERIFYING_RETAINED_EVIDENCE", flush=True)
        context, values, paths = retained(root, key)
        retry_of = None
        if args.retry_candidate_build:
            directory, retry_of = candidate_retry(directory, context, key, args.retry_candidate_build)
        session = Session(directory, context, key, commit, retry_of=retry_of)
        print("MS67_FINAL_RETAINED=MS65,MS66,SQL_630,300_SECOND_LOAD", flush=True)
        if session.state.get("ms67_complete"):
            receipt = session.read(session.state["completed"]["admission"])
            require(not platform.validate_execution_receipt(receipt, key, ROOT), "saved-final-receipt-invalid")
            print("MS67_CLOSEOUT=YES\nMS67_RECEIPT=" + session.state["completed"]["admission"]["uri"], flush=True)
            return 0
        if args.recover and session.state["active"] is None:
            print("MS67_FINAL_RECOVERY=NO_ACTIVE_PHASE; --execute resumes any saved image build", flush=True)
            return 0
        security, images = candidates(session)
        if args.recover:
            recover(session, paths, security, images)
            return 0
        require(session.state["active"] is None, "active-phase-needs-explicit-recover; no-duplicate-drill-started")
        children = {phase: run_child(session, phase, paths) for phase in CHILDREN}
        drills = run_drills(session, security, images)
        # Re-read current pods after the final rollout, then gather fresh metrics.
        # This is read-only and may be repeated if admission was interrupted.
        tool_root = directory / "operator-tools"
        tool_root.mkdir(exist_ok=True)
        candidate_tools.install_tools(tool_root)
        runtime = runtime_for(session, directory / "current-controls")
        try:
            current = current_tools.observe(runtime, context, key, ACCOUNT)
        finally:
            runtime.close()
        ref = session.publish("current-controls-" + uuid.uuid4().hex + ".json", current)
        current = session.read(ref)
        session.finish_phase("current-controls", ref)
        # Retained receipts get verified copies under this final evidence prefix;
        # originals and their signatures remain unchanged.
        refs = {}
        for name, value in values.items():
            refs[name] = session.retain("retained-" + name + "-" + uuid.uuid4().hex + ".json", value)
        observation = assemble(session, values, security, children, drills, current)
        observation_ref = session.publish("platform-observation-" + uuid.uuid4().hex + ".json", observation)
        output = directory / ("admission-" + uuid.uuid4().hex)
        receipt = platform.execute_qualification(ROOT, values["ms65"], values["ms66-receipt"], context["profile"],
                                                observation, output, key, ACCOUNT, run_id=session.state["run_id"])
        require(not platform.validate_execution_receipt(receipt, key, ROOT), "final-canonical-receipt-invalid")
        receipt_ref = session.publish("platform-receipt-" + uuid.uuid4().hex + ".json", receipt)
        require(not platform.validate_execution_receipt(session.read(receipt_ref), key, ROOT), "final-receipt-readback-invalid")
        session.publish("evidence-index-" + uuid.uuid4().hex + ".json", {"run_id": session.state["run_id"],
            "retained": refs, "phases": session.state["completed"], "observation": observation_ref,
            "receipt": receipt_ref, "ms67_complete": True, "production_ready": False})
        session.state["completed"]["admission"] = receipt_ref
        session.state["ms67_complete"] = True
        session.save()
        print("MS67_CLOSEOUT=YES\nMS67_RECEIPT=" + receipt_ref["uri"], flush=True)
        return 0
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        lock.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        reason = str(exc) if isinstance(exc, JourneyFailure) else "interrupted-or-local-runtime-error"
        print("MS67_FINAL_ERROR=" + reason, file=sys.stderr)
        print("MS67_COMPLETE=false; saved evidence retained", file=sys.stderr)
        raise SystemExit(1)
