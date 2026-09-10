#!/usr/bin/env python3
"""Run and independently verify bounded MS67 k6 business traffic on GKE."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import uuid

from cloudbank_journeys import Heartbeat
from cloudbank_ms65_rehearsal import cluster_identity, evidence_key, load
from cloudbank_image_security import live_snapshot
from lightyear_data.cloudbank_edge_ai import validate_execution_receipt as validate_ms64
from lightyear_data.cloudbank_image_security import ImageJournal, CheckpointFailure, save_observation, stamp
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, Journeys, ROLE_SCOPES, SERVICES, hashed, require
from lightyear_data.cloudbank_journeys_gke import GkeRuntime, command
from lightyear_data.cloudbank_ms65_rehearsal_gke import validate_shared_journeys
from lightyear_data.cloudbank_platform_qualification import validate_profile, MINIMUM_LOAD_CONCURRENCY, MINIMUM_LOAD_SECONDS
from lightyear_data.cloudbank_production_readiness import validate_image_lock
from lightyear_data.cloudbank_sustained_load import (
    OBSERVATION_TYPE, OBSERVATION_FILE, PASS, CYCLE_SECONDS, PodForwards, workload, execute_k6,
    validate_summary, verify_observation,
)
from lightyear_data.cloudbank_whole_application_equivalence import validate_execution_receipt as validate_ms66
from lightyear_data.contracts import sign

ROOT = Path(__file__).resolve().parents[1]


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("preflight", "run", "verify"))
    for name in ("project", "region", "cluster", "namespace", "signer", "evidence-bucket"):
        result.add_argument("--" + name, required=True)
    for name in ("image-lock", "ms64-receipt", "platform-profile", "ms66-receipt", "journeys"):
        result.add_argument("--" + name, required=True, type=Path)
    for name in ("output-root", "observation"):
        result.add_argument("--" + name, type=Path)
    result.add_argument("--evidence-key-secret", default="cloudbank-ms67-evidence-key")
    return result


def bound_inputs(args, key):
    lock, ms64, profile, ms66, journeys = map(load, (
        args.image_lock, args.ms64_receipt, args.platform_profile, args.ms66_receipt, args.journeys))
    require(not validate_ms64(ms64, key, ROOT), "load-signed-current-ms64-required")
    require(not validate_image_lock(lock, ms64["content_sha256"]), "load-ms64-bound-image-lock-required")
    require(not validate_profile(profile, key), "load-signed-platform-profile-required")
    require(not validate_ms66(ms66, key, ROOT), "load-signed-ms66-required")
    require(ms66["source_ms64_receipt_sha256"] == ms64["content_sha256"]
            and ms66["postgresql_image_lock_sha256"] == lock["content_sha256"]
            and ms66["postgresql_journey_sha256"] == journeys["content_sha256"], "load-ms66-input-bindings-mismatch")
    environment = journeys.get("bindings", {}).get("environment", {})
    require(all(environment.get(name) == getattr(args, name) for name in ("project", "region", "cluster", "namespace")),
            "load-journeys-context-mismatch")
    validate_shared_journeys(journeys, key, ms64_sha256=ms64["content_sha256"],
                            image_lock_sha256=lock["content_sha256"], environment=environment)
    bindings = {"image_lock_sha256": lock["content_sha256"], "ms64_receipt_sha256": ms64["content_sha256"],
                "platform_profile_sha256": profile["content_sha256"], "ms66_receipt_sha256": ms66["content_sha256"],
                "journeys_sha256": journeys["content_sha256"]}
    return {row["service"]: row["reference"] for row in lock["images"]}, profile, bindings, environment


def final_state(fixtures, summary):
    states = []
    for index, fixture in enumerate(fixtures, 1):
        state = fixture.state()
        require(state["balances"] == [1000, 250, 5], "load-final-balances-invalid")
        count = summary["vu_cycles"][str(index)]
        expected = sorted([(0, "WITHDRAW", 1), (0, "DEPOSIT", 1), (0, "DEPOSIT", 1),
                           (1, "WITHDRAW", 1), (1, "DEPOSIT", 1)] * count)
        require(sorted((r["account"], r["type"], r["amount"]) for r in state["journals"]) == expected,
                "load-final-journal-effects-invalid")
        states.append(state)
    return hashed(states)


def model_snapshot(runtime, profile):
    value = json.loads(command(["kubectl", "--context", runtime.context, "--request-timeout=30s",
        "-n", profile["model_namespace"], "get", "deployment", "ollama", "-o", "json"]))
    spec, status, meta = value["spec"], value.get("status", {}), value["metadata"]
    containers = spec["template"]["spec"].get("containers", [])
    require(len(containers) == 1 and containers[0]["image"] == profile["model_image"]
            and spec.get("replicas") == 2 and status.get("readyReplicas") == 2
            and status.get("updatedReplicas") == 2 and status.get("availableReplicas") == 2
            and status.get("observedGeneration", 0) >= meta["generation"], "load-model-image-or-readiness-invalid")
    return {"image": profile["model_image"], "ready_replicas": 2, "spec_sha256": hashed({"uid": meta["uid"], "spec": spec})}


def main(argv=None):
    args = parser().parse_args(argv)
    heartbeat = Heartbeat()
    heartbeat.thread.start()
    prior_signal = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    runtime, forwards, journal, output, key, phase = None, None, None, None, "", "input-validation"
    result = {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE, "status": "failed",
              "deployment_mutations": 0, "synthetic_data_only": True, "credentials_persisted": False,
              "raw_output_persisted": False, "production_environment": False, "ms67_complete": False,
              "production_ready": False, "local_processes_stopped": False}

    def close_local():
        if forwards:
            forwards.close()
        if runtime:
            for service in list(runtime.forwards):
                runtime.close_forward(service)
            runtime.tokens.clear()
            runtime.credentials.clear()
        result["local_processes_stopped"] = True

    try:
        require(args.evidence_bucket == f"gs://{args.project}-ms67-evidence/sustained-load", "load-private-evidence-prefix-required")
        if args.action == "run":
            require(os.environ.get("LIGHTYEAR_NON_PRODUCTION_ACK") == ACK, "non-production-mutation-ack-required")
        key = evidence_key(args)
        images, profile, bindings, environment = bound_inputs(args, key)
        if args.action == "verify":
            require(args.observation is not None, "load-observation-required")
            verify_observation(load(args.observation), key, bindings=bindings, images=images,
                               environment=environment, profile=profile, root=ROOT)
            print(json.dumps({"status": "passed", "errors": []}))
            return 0

        version = command(["k6", "version"]).strip()
        require(re.fullmatch(r"k6 v2\.2\.0 .+", version), "load-tested-k6-v2-2-0-required")
        run_id = "ms67-load-" + uuid.uuid4().hex
        output = (args.output_root or Path.home() / "ms67-evidence" / run_id).resolve()
        require(not output.exists() and not output.is_relative_to(ROOT), "load-fresh-private-output-required")
        output.mkdir(parents=True, mode=0o700)
        print("MS67_LOAD_ROOT=" + str(output), flush=True)
        result.update(run_id=run_id, started_at=stamp(), bindings=bindings, images=images,
                      environment=environment, workload=workload(ROOT), k6_version=version, live={}, deployment_specs={})
        runtime = GkeRuntime(project=args.project, region=args.region, cluster=args.cluster, namespace=args.namespace,
                             images=images, run_id=run_id, output=output, progress=heartbeat.progress)
        phase = "live-input-validation"
        heartbeat.progress("Checking the signed MS66 evidence, current images and live platform identities")
        cluster = cluster_identity(args.project, args.region, args.cluster)
        namespace = runtime.get("namespace", args.namespace)
        ns_hash = hashlib.sha256(namespace["metadata"]["uid"].encode()).hexdigest()
        require(runtime.environment() == environment and profile["context"] == runtime.context
                and profile["namespace"] == args.namespace and profile["region"] == args.region
                and profile["cluster_uid_sha256"] == cluster and profile["namespace_uid_sha256"] == ns_hash,
                "load-profile-live-environment-mismatch")
        result.update(cluster_identity_sha256=cluster, profile_namespace_uid_sha256=ns_hash)
        result["model"] = {"before": model_snapshot(runtime, profile)}
        result["live"]["before"], result["deployment_specs"]["before"] = live_snapshot(runtime)
        runtime.ready()
        runtime.authorize()
        if args.action == "preflight":
            close_local()
            result.update(status="passed-sustained-load-preflight", finished_at=stamp())
            print(json.dumps({"status": result["status"], "ready_services": len(SERVICES), "ms67_complete": False}))
            return 0

        uri = args.evidence_bucket + "/" + run_id + "/" + OBSERVATION_FILE
        journal = ImageJournal(output / OBSERVATION_FILE, uri, args.project, key, args.signer)
        result.update(status="in-progress", phase="before-synthetic-fixtures", fixtures={"account_count": 0,
                      "final_state_verified": False, "synthetic_records_retained": True})
        journal.write(result)
        phase = "synthetic-fixtures"
        fixtures = []
        for i in range(MINIMUM_LOAD_CONCURRENCY):
            heartbeat.progress(f"Preparing separate synthetic accounts for user {i + 1}/{MINIMUM_LOAD_CONCURRENCY}")
            fixture = Journeys(runtime, run_id + f"-{i + 1}")
            fixture.customer()
            fixture.prepare_accounts()
            fixtures.append(fixture)
            result["fixtures"]["account_count"] = sum(len(f.accounts) for f in fixtures)
        # The recorded field contains only a hash; private IDs/markers/credentials
        # are supplied directly to k6 over stdin and are never written as a script.
        result["fixtures"]["identity_sha256"] = hashed([{"accounts": f.accounts, "marker": f.marker} for f in fixtures])
        for service in list(runtime.forwards):
            runtime.close_forward(service)
        phase = "pod-connections"
        heartbeat.progress("Connecting k6 to both locked pods of each HTTP service")
        forwards = PodForwards(runtime)
        endpoints = forwards.open()
        result["http_pod_identities"] = forwards.identities
        configuration = {"run_id": run_id, "duration_seconds": MINIMUM_LOAD_SECONDS,
                         "vus": MINIMUM_LOAD_CONCURRENCY, "cycle_seconds": CYCLE_SECONDS,
                         "endpoints": endpoints, "credentials": runtime.credentials, "scopes": ROLE_SCOPES,
                         "owner": runtime.owner, "fixtures": [{"accounts": f.accounts, "marker": f.marker} for f in fixtures]}
        result["phase"] = phase = "sustained-traffic"
        result["load_started_at"] = stamp()
        journal.write(result)
        heartbeat.progress("Running k6: 10 users for 300 seconds, followed by completion of in-flight business cycles")
        exit_code, summary = execute_k6(ROOT, configuration)
        result.update(k6_exit_code=exit_code, summary=summary, load_finished_at=stamp())
        # Save even a failing performance measurement before post-run network reads.
        journal.write(result)
        phase = "load-thresholds"
        result["load"] = validate_summary(summary, run_id)
        require(exit_code == 0, "load-k6-exit-nonzero")
        phase = "final-state-verification"
        heartbeat.progress("Verifying balances and journal effects for every virtual user")
        result["fixtures"].update(final_state_sha256=final_state(fixtures, summary), final_state_verified=True)
        phase = "final-live-bindings"
        heartbeat.progress("Rechecking all sixteen service pods and saving the signed load evidence")
        result["live"]["after"], result["deployment_specs"]["after"] = live_snapshot(runtime)
        result["model"]["after"] = model_snapshot(runtime, profile)
        require(result["model"]["before"] == result["model"]["after"] and runtime.environment() == environment
                and cluster_identity(args.project, args.region, args.cluster) == cluster, "load-live-environment-drift")
        close_local()
        result.update(status=PASS, phase="complete", finished_at=stamp())
        verify_observation(sign(result, key, args.signer), key, bindings=bindings, images=images,
                           environment=environment, profile=profile, root=ROOT)
        phase = "final-evidence-upload"
        result = journal.write(result)
        print("MS67_LOAD_EVIDENCE_READBACK=VERIFIED", flush=True)
        print("MS67_LOAD_OBSERVATION=" + uri, flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        reason = str(exc) if isinstance(exc, JourneyFailure) else (
            "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "load-input-or-runtime-error")
        result.update(status="failed", reason=reason, failed_phase=phase, finished_at=stamp())
        try:
            close_local()
        except Exception:
            result["local_processes_stopped"] = False
        if output and key:
            if journal and not isinstance(exc, CheckpointFailure):
                try:
                    result = journal.write(result)
                    print("MS67_LOAD_EVIDENCE_READBACK=VERIFIED", flush=True)
                except Exception:
                    result["evidence_upload"] = "unconfirmed"
            elif isinstance(exc, CheckpointFailure):
                result["evidence_upload"] = "unconfirmed"
            result = save_observation(output / OBSERVATION_FILE, result, key, args.signer)
    finally:
        try:
            close_local()
        finally:
            heartbeat.done.set()
            heartbeat.thread.join(timeout=1)
            signal.signal(signal.SIGTERM, prior_signal)
    report = {k: result[k] for k in ("status", "run_id", "reason", "failed_phase", "load",
                                   "local_processes_stopped", "ms67_complete") if k in result}
    if "summary" in result:
        report["summary"] = {k: result["summary"].get(k) for k in (
            "configured_duration_seconds", "configured_vus", "measured_duration_ms", "requests", "errors",
            "http_failures", "p95_ms", "cycles_started", "cycles_completed", "failure_diagnostics")}
    print(json.dumps(report, indent=2))
    return 0 if result.get("status") == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
