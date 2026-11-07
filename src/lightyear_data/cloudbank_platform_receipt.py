"""Recompute seven plan-bound platform verdicts; public Ed25519 verification only."""
from __future__ import annotations

import math
import re
from datetime import datetime

from lightyear_cloud_runner.signing import verify
from .cloudbank_platform_plan import DRILLS, HEX, canonical, digest, hashed, require


def number(value):
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.utcoffset() is not None, "timestamp-offset-required")
    return parsed


def binding(contract):
    return {key: contract[key] for key in ("iac_commit", "plan_sha256", "rollout_sha256", "policy_sha256")}


def check_measurements(drill, expected, data):
    """Existing producer gates remain mandatory; these comparisons add IaC joins."""
    require(data.get("legacy_verified") is True, "legacy-verifier-not-passed")
    require(re.fullmatch(HEX, data.get("legacy_receipt_sha256", ""))
            and re.fullmatch(HEX, data.get("legacy_verifier_sha256", "")), "legacy-evidence-binding-required")
    actual, measure = data["configuration"], data["measurements"]
    configuration = {k:v for k,v in expected.items() if k not in {"limits", "fire_and_recovery"}}
    require(canonical(actual) == canonical(configuration), "declared-observed-configuration-mismatch")
    if drill == "NETWORK-ENFORCEMENT":
        # A default-deny declaration requires actual repeated negatives, bracketed
        # by successful controls, in addition to the unchanged legacy verifier.
        deny = set()
        for name, spec in expected["policies"].items():
            if spec.get("podSelector") == {}:
                for direction in ("Ingress", "Egress"):
                    if direction in spec.get("policyTypes", []) and not spec.get(direction.lower(), []):
                        deny.add((name.split('/')[0], direction))
        rows = measure["declared_denials"]
        require(len(rows) == len(deny) and {(r["namespace"], r["direction"]) for r in rows} == deny,
                "declared-deny-probe-coverage-incomplete")
        for row in rows:
            require(row["positive_before"] is True and row["positive_after"] is True
                    and len(row["negative_checks"]) == 2
                    and all(c["outcome"] == "connect-timeout" and type(c["elapsed_ms"]) is int
                            and 2500 <= c["elapsed_ms"] <= 30000 for c in row["negative_checks"]),
                    "declared-denial-not-observed")
    elif drill == "RUNTIME-IDENTITY":
        rows = measure["services"]
        require(set(rows) == set(expected["identities"]), "runtime-service-coverage")
        for name, identity in expected["identities"].items():
            row = rows[name]
            require(row["startup_uids"] == [identity["runAsUser"]] * 2
                    and row["startup_gids"] == [identity["runAsGroup"]] * 2
                    and row["ready_replicas"] == 2 and row["http_readiness"] == 200,
                    "declared-runtime-identity-mismatch")
    elif drill == "SECRET-ROTATION":
        service = measure["service"]
        require(service in expected["external_secrets"], "rotation-service-not-declared")
        require(measure["provider_secret"] == expected["external_secrets"][service]["secret_id"],
                "rotation-provider-not-declared")
        require(measure["recovery"] == {"temporary_version_disabled": True, "original_values_restored": True,
                                       "preexisting_versions_unchanged": True}, "rotation-not-restored")
        phases = measure["observations"]
        require(set(phases) == {"baseline", "rotated", "restored"}, "rotation-observations-incomplete")
        prior = set()
        for phase in ("baseline", "rotated", "restored"):
            row = phases[phase]
            ids = row["pod_uid_sha256"]
            require(row["verified_replicas"] == 2 and row["authenticated_contract_matches"] is True
                    and len(ids) == len(set(ids)) == 2 and all(re.fullmatch(HEX, x) for x in ids)
                    and not prior.intersection(ids), "rotation-not-observed-on-fresh-replicas")
            prior = set(ids)
    elif drill == "SQL-HA":
        before, after = measure["before"], measure["after"]
        require(before["primary_zone"] != before["standby_zone"]
                and after["primary_zone"] == before["standby_zone"]
                and after["standby_zone"] == before["primary_zone"], "standby-promotion-not-observed")
        require(measure["endpoint_unchanged"] is True and measure["state_matches"] is True
                and measure["same_processes"] is True and measure["recovery_restored"] is True,
                "ha-behaviour-or-recovery-incomplete")
    elif drill == "SQL-RECOVERY":
        limits = expected["limits"]
        require(measure["source_instance"] == expected["instance"], "recovery-source-mismatch")
        for name, limit in (("pitr", "maximum_rto_seconds"), ("backup_restore", "maximum_backup_restore_rto_seconds")):
            row = measure[name]
            require(row["state_matches"] is True and number(row["database_rto_seconds"])
                    and row["database_rto_seconds"] <= limits[limit], "declared-recovery-limit-exceeded")
        age = measure["pitr"]["recovery_point_age_seconds"]
        require(number(age) and age <= limits["maximum_rpo_seconds"] and measure["validation_instance_deleted"] is True
                and measure["recovery_restored"] is True, "recovery-rpo-or-cleanup-failed")
    elif drill == "ALERT-DRILL":
        require(expected["fire_and_recovery"] is True and measure["states"] == ["OPEN", "CLOSED"]
                and measure["same_alert"] is True and measure["policy_absent"] is True
                and measure["metric_descriptor_absent"] is True, "declared-alert-not-observed-or-cleaned")
    elif drill == "SUSTAINED-LOAD":
        limits = expected["limits"]
        for key in ("requests", "duration_seconds", "concurrency", "p95_ms", "errors"):
            require(number(measure[key]), "invalid-load-measurement")
        require(measure["requests"] >= limits["minimum_requests"]
                and measure["duration_seconds"] >= limits["minimum_duration_seconds"]
                and measure["concurrency"] >= limits["minimum_concurrency"]
                and measure["p95_ms"] <= limits["maximum_p95_ms"]
                and measure["errors"] <= limits["maximum_errors"]
                and set(measure["services"]) == set(expected["services"])
                and len(measure["services"]) == len(expected["services"]), "declared-load-limit-or-coverage-failed")
    else:
        raise ValueError("unknown-drill")


def validate_policy(policy, contract):
    require(set(policy) == {"schema", "bindings", "context", "run_id", "not_before", "expires_at",
                           "evidence_class", "observer_keys", "legacy_verifiers", "code_key", "judge_key"},
            "trust-policy-fields")
    require(policy["schema"] == "cloudbank-platform-trust/1" and policy["bindings"] == binding(contract)
            and policy["context"] == contract["context"], "trust-policy-plan-binding")
    require(policy["evidence_class"] in {"offline-fixture", "live-nonproduction"}, "evidence-class-required")
    require(set(policy["observer_keys"]) == set(DRILLS) and set(policy["legacy_verifiers"]) == set(DRILLS),
            "all-seven-observer-policies-required")
    require(instant(policy["not_before"]) < instant(policy["expires_at"]), "invalid-policy-window")
    require(isinstance(policy["run_id"], str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", policy["run_id"]),
            "run-id-required")


def evaluate(contract, code_envelope, observations, policy, *, now):
    """Signature-free verdict preparation. Sign this complete body externally.

    Trust policy is supplied out of band, never selected from any receipt. Missing
    observations are NOT RUN; present but invalid evidence is FAIL, never omitted.
    """
    validate_policy(policy, contract)
    require(instant(policy["not_before"]) <= instant(now) <= instant(policy["expires_at"]), "trust-policy-expired")
    code = verify(code_envelope, policy["code_key"])
    require(code.get("schema") == "cloudbank-code-qualification/1" and code.get("run_id") == policy["run_id"]
            and code.get("evidence_class") == policy["evidence_class"]
            and code.get("rollout_sha256") == contract["rollout_sha256"]
            and re.fullmatch(r"[0-9a-f]{40}", code.get("commit", ""))
            and re.fullmatch(HEX, code.get("verifier_receipt_sha256", ""))
            and code.get("verdict") in {"PASS", "FAIL", "NOT RUN"}, "code-receipt-binding-invalid")
    require(set(observations) <= set(DRILLS), "unexpected-drill-evidence")
    results = {}
    for drill in DRILLS:
        envelope = observations.get(drill)
        if envelope is None:
            results[drill] = {"verdict": "NOT RUN", "evidence_sha256": None, "reason": "observation-absent"}
            continue
        sha = hashed(envelope)
        try:
            data = verify(envelope, policy["observer_keys"][drill])
            require(set(data) == {"schema", "drill", "run_id", "bindings", "context", "evidence_class",
                                  "started_at", "finished_at", "legacy_verified", "legacy_receipt_sha256",
                                  "legacy_verifier_sha256", "configuration", "measurements"}, "observation-fields")
            require(data["schema"] == "cloudbank-platform-observation/1" and data["drill"] == drill
                    and data["run_id"] == policy["run_id"] and data["bindings"] == binding(contract)
                    and data["context"] == contract["context"] and data["evidence_class"] == policy["evidence_class"]
                    and data["legacy_verifier_sha256"] == policy["legacy_verifiers"][drill], "observation-binding-mismatch")
            require(instant(policy["not_before"]) <= instant(data["started_at"]) <= instant(data["finished_at"])
                    <= instant(now) <= instant(policy["expires_at"]), "observation-outside-window")
            check_measurements(drill, contract["expectations"][drill], data)
            results[drill] = {"verdict": "PASS", "evidence_sha256": sha, "reason": None}
        except Exception:
            results[drill] = {"verdict": "FAIL", "evidence_sha256": sha, "reason": "invalid-or-mismatched-evidence"}
    verdicts = [row["verdict"] for row in results.values()] + [code["verdict"]]
    verdict = "FAIL" if "FAIL" in verdicts else "NOT RUN" if "NOT RUN" in verdicts else "PASS"
    return {"schema": "cloudbank-code-and-platform-receipt/1", "run_id": policy["run_id"],
            "bindings": binding(contract), "context": contract["context"], "policy_sha256": hashed(policy),
            "evaluated_at": now, "evidence_class": policy["evidence_class"], "code": code_envelope,
            "code_receipt_sha256": hashed(code_envelope), "drills": results, "verdict": verdict,
            "live_platform_verified": verdict == "PASS" and policy["evidence_class"] == "live-nonproduction",
            "ms67_closeout": False, "native_p5_qualification": False}


def verify_compound(envelope, contract, code_envelope, observations, policy, *, now):
    body = verify(envelope, policy["judge_key"])
    require(body == evaluate(contract, code_envelope, observations, policy, now=body["evaluated_at"]),
            "compound-verdict-does-not-recompute")
    require(instant(body["evaluated_at"]) <= instant(now) <= instant(policy["expires_at"]), "compound-receipt-expired")
    return body
