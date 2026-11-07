"""CI-only fixtures; no cloud commands, private keys or signing operations."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from lightyear_cloud_runner.signing import verify as real_verify
from lightyear_data import cloudbank_platform_plan as plan
from lightyear_data import cloudbank_platform_receipt as receipt
from lightyear_data import cloudbank_platform_drills as drills

ROOT = Path(__file__).resolve().parents[1]
START, END, NOW = "2030-01-01T10:00:00+00:00", "2030-01-01T10:30:00+00:00", "2030-01-01T11:00:00+00:00"


def fixture():
    policy_raw = (ROOT / "factory/cloudbank/platform-qualification/platform-contract.json").read_bytes()
    policy = plan.decode(policy_raw)
    context = dict(project="offline-project", region="europe-west2", cluster="offline-cluster", namespace="offline-app")
    bundle = {"kind": "List", "items": []}
    resources = []
    def add(address, value):
        resources.append(dict(address=address, mode="managed", values=value))
    cluster = dict(name=context["cluster"], location=context["region"], node_locations=["a", "b", "c"],
                   datapath_provider="ADVANCED_DATAPATH", private_cluster_config=[dict(enable_private_nodes=True)],
                   workload_identity_config=[dict(workload_pool="offline-project.svc.id.goog")],
                   monitoring_config=[dict(managed_prometheus=[dict(enabled=True)])],
                   logging_config=[dict(enable_components=["WORKLOADS", "SYSTEM_COMPONENTS"])])
    backup = dict(enabled=True, start_time="02:00", point_in_time_recovery_enabled=True,
                  transaction_log_retention_days=7, backup_retention_settings=[dict(retained_backups=7, retention_unit="COUNT")])
    sql = dict(name="offline-postgres", region=context["region"], settings=[dict(availability_type="REGIONAL",
               ip_configuration=[dict(ipv4_enabled=False)], backup_configuration=[backup])])
    add("google_container_cluster.estate", cluster)
    add("google_sql_database_instance.postgres", sql)
    secrets = {}
    for name in policy["services"]:
        secrets[name] = "cloudbank-"+name+"-external"
        add('google_secret_manager_secret.service["'+name+'"]', dict(secret_id=secrets[name]))
        add('google_secret_manager_secret_iam_member.reader["'+name+'"]',
            dict(role="roles/secretmanager.secretAccessor", member="principal://offline/reader"))
        bundle["items"].append(dict(kind="Deployment", metadata=dict(name=name, namespace=context["namespace"]),
            spec=dict(replicas=2, template=dict(spec=dict(containers=[dict(name=name, securityContext=dict(
                runAsUser=65532, runAsGroup=65532, runAsNonRoot=True))])))))
        bundle["items"].append(dict(kind="ExternalSecret", metadata=dict(name="cloudbank-"+name, namespace=context["namespace"]),
            spec=dict(refreshInterval="1m", secretStoreRef=dict(kind="SecretStore", name="cloudbank-gcp-secret-manager"),
                      dataFrom=[dict(extract=dict(key=secrets[name]))])))
    bundle["items"].append(dict(kind="NetworkPolicy", metadata=dict(name="default-deny", namespace=context["namespace"]),
                                spec=dict(podSelector={}, policyTypes=["Ingress", "Egress"], ingress=[], egress=[])))
    rollout = plan.canonical(bundle)
    out = dict(schema="cloudbank-iac-infrastructure/1", **context, secrets=secrets,
               sql=dict(instance=sql["name"]), secret_reader="principal://offline/reader",
               telemetry_roles=["roles/cloudtrace.agent", "roles/logging.logWriter", "roles/monitoring.metricWriter"],
               rollout=dict(rendered_sha256=plan.digest(rollout)), qualification_contract=policy,
               qualification_contract_sha256=plan.digest(policy_raw))
    for role in out["telemetry_roles"]:
        add('google_project_iam_member.telemetry["'+role+'"]', dict(role=role, member="principal://offline/otel"))
    value = dict(format_version="1.2", terraform_version="1.13.3", errored=False, complete=True,
                 resource_changes=[], planned_values=dict(root_module=dict(resources=resources),
                 outputs=dict(platform_infrastructure=dict(sensitive=False, value=out))))
    raw = plan.canonical(value)
    arguments = dict(commit="a"*40, plan_sha256=plan.digest(raw), rollout_sha256=plan.digest(rollout), policy_sha256=plan.digest(policy_raw))
    return value, rollout, arguments


def contract_fixture():
    value, rollout, arguments = fixture()
    return plan.compile_plan(plan.canonical(value), rollout, **arguments)


def observed_fixture(contract, drill):
    expected = contract["expectations"][drill]
    configuration = copy.deepcopy({k:v for k,v in expected.items() if k not in {"limits", "fire_and_recovery"}})
    measures = {
        "NETWORK-ENFORCEMENT": {"declared_denials": [dict(namespace="offline-app", direction=d,
            positive_before=True, positive_after=True, negative_checks=[dict(outcome="connect-timeout", elapsed_ms=3000)]*2)
            for d in ("Ingress", "Egress")]},
        "RUNTIME-IDENTITY": {"services": {n:dict(startup_uids=[65532]*2, startup_gids=[65532]*2, ready_replicas=2, http_readiness=200)
            for n in contract["expectations"]["RUNTIME-IDENTITY"]["identities"]}},
        "SECRET-ROTATION": dict(service="creditscore", provider_secret="cloudbank-creditscore-external",
            recovery=dict(temporary_version_disabled=True, original_values_restored=True, preexisting_versions_unchanged=True),
            observations={name:dict(verified_replicas=2, authenticated_contract_matches=True,
                                   pod_uid_sha256=[str(i*2+1)*64, str(i*2+2)*64]) for i,name in enumerate(("baseline", "rotated", "restored"))}),
        "SQL-HA": dict(before=dict(primary_zone="a", standby_zone="b"), after=dict(primary_zone="b", standby_zone="a"),
                       endpoint_unchanged=True, state_matches=True, same_processes=True, recovery_restored=True),
        "SQL-RECOVERY": dict(source_instance="offline-postgres", pitr=dict(state_matches=True, database_rto_seconds=100, recovery_point_age_seconds=10),
                             backup_restore=dict(state_matches=True, database_rto_seconds=100), validation_instance_deleted=True, recovery_restored=True),
        "ALERT-DRILL": dict(states=["OPEN", "CLOSED"], same_alert=True, policy_absent=True, metric_descriptor_absent=True),
        "SUSTAINED-LOAD": dict(requests=1500, duration_seconds=300, concurrency=10, p95_ms=100, errors=0,
                               services=contract["expectations"]["SUSTAINED-LOAD"]["services"]),
    }
    return dict(schema="cloudbank-platform-observation/1", drill=drill, run_id="fixture-run", bindings=receipt.binding(contract),
                context=contract["context"], evidence_class="offline-fixture", started_at=START, finished_at=END,
                legacy_verified=True, legacy_receipt_sha256="b"*64, legacy_verifier_sha256="c"*64,
                configuration=configuration, measurements=measures[drill])


def policy_fixture(contract):
    return dict(schema="cloudbank-platform-trust/1", bindings=receipt.binding(contract), context=contract["context"],
                run_id="fixture-run", not_before=START, expires_at="2030-01-01T12:00:00+00:00", evidence_class="offline-fixture",
                observer_keys={d:"observer-"+d for d in plan.DRILLS}, legacy_verifiers={d:"c"*64 for d in plan.DRILLS},
                code_key="code-key", judge_key="judge-key")


def mock_envelope(body, key):
    return {"body": copy.deepcopy(body), "fixture_key": key}


def mock_verify(envelope, key):
    # Explicit logic seam, not a cryptographic test or a producible live receipt.
    plan.require(envelope["fixture_key"] == key, "wrong-fixture-role")
    return envelope["body"]


class PlatformPlanTests(unittest.TestCase):
    def test_complete_plan_derives_seven_recipes(self):
        contract = contract_fixture()
        self.assertEqual(set(drills.recipes(contract)), set(plan.DRILLS))
        self.assertEqual(drills.recipes(contract)["SQL-HA"]["derived_arguments"]["--source-instance"], "offline-postgres")

    def test_wrong_raw_digest_and_duplicate_json_refused(self):
        value, rollout, args = fixture()
        with self.assertRaisesRegex(ValueError, "digest-mismatch"):
            plan.compile_plan(plan.canonical(value)+b" ", rollout, **args)
        with self.assertRaisesRegex(ValueError, "duplicate-json"):
            plan.decode(b'{"a":1,"a":2}')

    def test_bad_plan_states_fail_closed(self):
        for field, replacement in (("complete", False), ("errored", True), ("terraform_version", "future"),
                                   ("deferred_changes", [dict(reason="unknown")]),
                                   ("resource_changes", [dict(change=dict(actions=["delete", "create"]))])):
            with self.subTest(field=field):
                value, rollout, args = fixture()
                value[field] = replacement
                raw = plan.canonical(value); args["plan_sha256"] = plan.digest(raw)
                with self.assertRaises(ValueError):
                    plan.compile_plan(raw, rollout, **args)

    def test_changed_actual_resource_cannot_hide_behind_output(self):
        value, rollout, args = fixture()
        value["planned_values"]["root_module"]["resources"][1]["values"]["name"] = "other-sql"
        raw = plan.canonical(value); args["plan_sha256"] = plan.digest(raw)
        with self.assertRaisesRegex(ValueError, "sql-output-resource"):
            plan.compile_plan(raw, rollout, **args)

    def test_context_override_refused(self):
        for extra in (["--project", "other"], ["--source-instance=other"], ["recover"]):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                drills.cli_arguments(contract_fixture(), "SQL-HA", extra)

    def test_iam_resource_drift_cannot_hide_in_output(self):
        value, rollout, args = fixture()
        rows = value["planned_values"]["root_module"]["resources"]
        next(r for r in rows if r["address"].startswith("google_secret_manager_secret_iam_member."))["values"]["member"] = "other"
        raw = plan.canonical(value); args["plan_sha256"] = plan.digest(raw)
        with self.assertRaisesRegex(ValueError, "secret-reader-output-resource"):
            plan.compile_plan(raw, rollout, **args)

    def test_every_drill_rejects_configuration_drift(self):
        contract = contract_fixture()
        for drill in plan.DRILLS:
            with self.subTest(drill=drill):
                data = observed_fixture(contract, drill)
                receipt.check_measurements(drill, contract["expectations"][drill], data)
                data["configuration"]["unexpected_resource"] = True
                with self.assertRaisesRegex(ValueError, "configuration-mismatch"):
                    receipt.check_measurements(drill, contract["expectations"][drill], data)

    def test_every_drill_rejects_behaviour_mismatch(self):
        contract = contract_fixture()
        mutations = {
            "NETWORK-ENFORCEMENT": lambda m: m["declared_denials"][0].update(positive_before=False),
            "RUNTIME-IDENTITY": lambda m: next(iter(m["services"].values())).update(startup_gids=[0, 0]),
            "SECRET-ROTATION": lambda m: m["recovery"].update(temporary_version_disabled=False),
            "SQL-HA": lambda m: m.update(same_processes=False),
            "SQL-RECOVERY": lambda m: m["pitr"].update(recovery_point_age_seconds=61),
            "ALERT-DRILL": lambda m: m.update(states=["OPEN", "OPEN"]),
            "SUSTAINED-LOAD": lambda m: m.update(errors=1),
        }
        for drill, mutate in mutations.items():
            with self.subTest(drill=drill):
                data = observed_fixture(contract, drill); mutate(data["measurements"])
                with self.assertRaises(ValueError):
                    receipt.check_measurements(drill, contract["expectations"][drill], data)

    def test_observed_identity_is_not_copied_from_plan(self):
        contract = contract_fixture()
        _, rollout, _ = fixture()
        raw = dict(context=contract["context"], kubernetes=plan.decode(rollout), cluster=dict(name="offline-cluster", location="europe-west2",
                   workloadIdentityConfig=dict(workloadPool="wrong-pool")))
        actual = drills.configuration("RUNTIME-IDENTITY", raw, contract)
        self.assertEqual(actual["workload_pool"], "wrong-pool")
        self.assertNotEqual(actual, contract["expectations"]["RUNTIME-IDENTITY"])


class PlatformReceiptTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract_fixture()
        self.policy = policy_fixture(self.contract)
        self.code = mock_envelope(dict(schema="cloudbank-code-qualification/1", run_id="fixture-run", commit="d"*40,
            rollout_sha256=self.contract["rollout_sha256"], evidence_class="offline-fixture",
            verifier_receipt_sha256="e"*64, verdict="PASS"), "code-key")
        self.observations = {d:mock_envelope(observed_fixture(self.contract,d), self.policy["observer_keys"][d]) for d in plan.DRILLS}

    def evaluate(self):
        with patch.object(receipt, "verify", side_effect=mock_verify):
            return receipt.evaluate(self.contract, self.code, self.observations, self.policy, now=NOW)

    def test_complete_fixture_is_not_live_qualification(self):
        result = self.evaluate()
        self.assertEqual(result["verdict"], "PASS")
        self.assertFalse(result["live_platform_verified"])
        self.assertFalse(result["ms67_closeout"])
        self.assertEqual(result["code"], self.code)

    def test_missing_drill_is_not_run(self):
        del self.observations["SQL-HA"]
        result = self.evaluate()
        self.assertEqual(result["verdict"], "NOT RUN")
        self.assertEqual(result["drills"]["SQL-HA"]["verdict"], "NOT RUN")

    def test_bad_signature_cannot_be_omitted(self):
        self.observations["SQL-HA"]["fixture_key"] = "attacker"
        self.assertEqual(self.evaluate()["verdict"], "FAIL")

    def test_wrong_plan_code_join_refused(self):
        self.code["body"]["rollout_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "code-receipt-binding"):
            self.evaluate()

    def test_expired_policy_and_naive_time_refused(self):
        self.policy["expires_at"] = START
        with self.assertRaises(ValueError):
            self.evaluate()
        with self.assertRaises(ValueError):
            receipt.instant("2030-01-01T12:00:00")

    def test_unknown_drill_refused(self):
        self.observations["EASY-SUBSTITUTE"] = {}
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_changed_measurement_fails_compound_recomputation(self):
        envelope = mock_envelope(self.evaluate(), "judge-key")
        self.observations["SUSTAINED-LOAD"]["body"]["measurements"]["p95_ms"] = 999
        with patch.object(receipt, "verify", side_effect=mock_verify), self.assertRaisesRegex(ValueError, "does-not-recompute"):
            receipt.verify_compound(envelope, self.contract, self.code, self.observations, self.policy, now=NOW)

    def test_hmac_and_wrong_key_fail_real_envelope_verifier(self):
        for algorithm, key in (("HMAC-SHA256", "public"), ("Ed25519", "attacker")):
            envelope = dict(body={}, content_sha256=plan.hashed({}), signature=dict(algorithm=algorithm, key_id="wrong", value=""))
            with self.subTest(algorithm=algorithm), self.assertRaises(ValueError):
                real_verify(envelope, key)

    def test_public_rfc8032_vector_and_tamper(self):
        # RFC8032 section 7.1 test 1: PUBLIC bytes only, no private seed/signing.
        # https://www.rfc-editor.org/rfc/rfc8032#section-7.1
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"))
        signature = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        key.verify(signature, b"")
        with self.assertRaises(InvalidSignature):
            key.verify(signature, b"changed")
