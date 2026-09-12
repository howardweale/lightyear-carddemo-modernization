from __future__ import annotations

import copy
import base64
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from lightyear_data.cloudbank_journeys import JourneyFailure, hashed
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_ms66_dual_lane import build_lane_observation
from lightyear_data.cloudbank_managed_target import (
    ManagedGkeRuntime, PROFILE_TYPE, PROVIDERS, datasource, observe_target, resolve_database, validate_profile,
)
from lightyear_data.cloudbank_ms71 import admit, validate_comparison, verify_receipt, COMPARISON_TYPE
from lightyear_data.cloudbank_whole_application_equivalence import SERVICES
from lightyear_data.contracts import seal, sign
from test_cloudbank_ms66_dual_lane import shared_journey, source_images, KEY, SIGNER

ROOT = Path(__file__).resolve().parents[1]


def profile(provider=PROVIDERS[0]):
    alloy = provider == PROVIDERS[1]
    return seal({"schema_version": "1.0", "profile_type": PROFILE_TYPE, "provider": provider,
        "project": "test-project", "region": "us-west1", "cluster": "test-cluster",
        "namespace": "test-alloydb" if alloy else "test-sql",
        "resource": ("projects/test-project/locations/us-west1/clusters/test-alloydb/instances/primary"
                     if alloy else "projects/test-project/instances/test-sql"),
        "database_version": "POSTGRES_16", "databases": {s: "cloudbank" for s in SERVICES},
        "require_tls": True, "synthetic_data_only": True, "production_environment": False})


def observation(p):
    alloy = p["provider"] == PROVIDERS[1]
    address = "10.1.0.3" if alloy else "10.1.0.2"
    conn = {"address": address, "port": 5432, "database": "cloudbank", "tls": True}
    return seal({"profile_sha256": p["content_sha256"], "database": seal({
        "provider": p["provider"], "resource": p["resource"], "database_version": "POSTGRES_16",
        "created_at": "2026-09-12T01:00:00Z", "address": address}),
        "environment": {**{k: p[k] for k in ("project", "region", "cluster", "namespace")},
                        "namespace_uid_sha256": hashed(p["namespace"])},
        "services": {s: {"connection": conn, "auxiliary_connections": {}, "configuration_refs": []} for s in SERVICES},
        "probe_connection": conn, "images_sha256": hashed(source_images())})


def comparison(provider):
    # Exercise the real current receipt validator using the published receipt's shape.
    # All synthetic changes are re-signed with the test-only key; never execution evidence.
    receipt_path = next((ROOT / "docs/receipts").rglob("retained-ms66-receipt.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    p = profile(provider)
    before = observation(p)
    run_id = "ms66-test-" + ("alloydb" if provider == PROVIDERS[1] else "sql")
    oracle = shared_journey("oracle", source_images(), receipt["oracle_source_image_lock_sha256"])
    target = shared_journey("postgresql", source_images(), receipt["postgresql_image_lock_sha256"])
    probe = {"database": "cloudbank", "server_version_num": 160003, "tls": True}
    oracle["run_id"] = run_id + "-oracle"
    target["run_id"] = run_id + "-postgresql"
    target["bindings"].update({"ms71_campaign_id": "ms71-test", "managed_target_sha256": before["content_sha256"],
                               "managed_probe_sql": probe, "environment": before["environment"]})
    oracle, target = sign(oracle, KEY, SIGNER), sign(target, KEY, SIGNER)
    receipt.update({"comparison_run_id": run_id, "run_id": run_id,
                    "oracle_journey_sha256": oracle["content_sha256"],
                    "postgresql_journey_sha256": target["content_sha256"], "signer": SIGNER})
    for lane, journey in (("oracle", oracle), ("postgresql", target)):
        obs = build_lane_observation(journey, KEY, SIGNER, lane,
            ms61_sha256=receipt["source_ms61_receipt_sha256"], ms64_sha256=receipt["source_ms64_receipt_sha256"],
            oracle_image_id_sha256=receipt["oracle_image_id_sha256"],
            postgresql_image_id_sha256=receipt["postgresql_image_id_sha256"], comparison_run_id=run_id,
            oracle_source_image_lock_sha256=receipt["oracle_source_image_lock_sha256"],
            postgresql_image_lock_sha256=receipt["postgresql_image_lock_sha256"],
            oracle_journey_sha256=oracle["content_sha256"], postgresql_journey_sha256=target["content_sha256"],
            expected_images=source_images(), recovery={"status": "restored", "errors": []})
        receipt[lane + "_observation_sha256"] = obs["content_sha256"]
    receipt = sign(receipt, KEY, SIGNER)
    return sign({"schema_version": "1.0", "receipt_type": COMPARISON_TYPE,
        "campaign_id": "ms71-test", "controller_commit": "a" * 40,
        "profile": p, "before": before, "after": before, "probe_sql": probe,
        "comparison": receipt, "oracle_journey": oracle, "target_journey": target,
        "source_images": source_images(), "target_images": source_images(),
        "recovery": {"oracle": {"status": "restored", "errors": []},
                     "target": {"status": "restored", "errors": []}},
        "production_ready": False, "ms71_complete": False}, KEY, SIGNER)


class AcceptanceTests(unittest.TestCase):
    def test_both_targets_pass_one_gate_and_receipt_revalidates(self):
        rows = [comparison(provider) for provider in PROVIDERS]
        receipt = admit(rows, KEY, SIGNER, ROOT)
        verify_receipt(receipt, KEY, ROOT)
        self.assertTrue(receipt["ms71_complete"])
        self.assertFalse(receipt["production_ready"])
        self.assertFalse(receipt["alloydb_platform_qualified"])

    def test_missing_or_duplicate_target_never_admits(self):
        sql = comparison(PROVIDERS[0])
        for rows in ([], [sql], [sql, sql]):
            with self.subTest(count=len(rows)), self.assertRaises(JourneyFailure):
                admit(rows, KEY, SIGNER, ROOT)

    def test_mutations_cannot_turn_partial_or_wrong_evidence_into_acceptance(self):
        def change_scenario(v):
            v["target_journey"]["scenarios"][3]["normalized_result"] = "wrong"
            v["target_journey"] = sign(v["target_journey"], KEY, SIGNER)
        mutations = [
            lambda v: v["target_images"].pop("chatbot"),
            lambda v: v["recovery"]["target"].update(status="failed"),
            lambda v: v["before"]["database"].update(provider=PROVIDERS[0]),
            lambda v: v["probe_sql"].update(tls=False),
            lambda v: v["probe_sql"].update(database="wrong"),
            lambda v: v["probe_sql"].update(server_version_num=150000),
            lambda v: v["target_journey"]["scenarios"].pop(),
            change_scenario,
            lambda v: v["target_journey"]["scenarios"][0]["evidence"].update(tampered=True),
            lambda v: v.update(production_ready=True),
            lambda v: v["target_journey"]["bindings"].update(ms71_campaign_id="ms71-other"),
        ]
        for index, mutate in enumerate(mutations):
            value = copy.deepcopy(comparison(PROVIDERS[1]))
            mutate(value)
            with self.subTest(mutation=index), self.assertRaises((JourneyFailure, ValueError)):
                validate_comparison(sign(value, KEY, SIGNER), KEY, ROOT)

    def test_two_individually_valid_runs_with_different_common_inputs_are_rejected(self):
        sql, alloy = [comparison(p) for p in PROVIDERS]
        alloy["controller_commit"] = "b" * 40
        alloy = sign(alloy, KEY, SIGNER)
        validate_comparison(alloy, KEY, ROOT)
        with self.assertRaisesRegex(JourneyFailure, "common-inputs"):
            admit([sql, alloy], KEY, SIGNER, ROOT)

    def test_receipt_tampering_and_wrong_key_are_rejected(self):
        receipt = admit([comparison(p) for p in PROVIDERS], KEY, SIGNER, ROOT)
        with self.assertRaises(JourneyFailure):
            verify_receipt(receipt, "wrong-key", ROOT)
        receipt["ms71_complete"] = False
        with self.assertRaises(JourneyFailure):
            verify_receipt(receipt, KEY, ROOT)
        receipt = sign(receipt, KEY, SIGNER)
        with self.assertRaises(JourneyFailure):
            verify_receipt(receipt, KEY, ROOT)


class TargetTests(unittest.TestCase):
    def test_private_datasource_only_with_bounded_tls_options(self):
        self.assertTrue(datasource("jdbc:postgresql://10.1.0.3/cloudbank?sslmode=require")["tls"])
        for url in ("jdbc:postgresql://127.0.0.1/db", "jdbc:postgresql://8.8.8.8/db",
                    "jdbc:postgresql://user:secret@10.1.0.3/db", "jdbc:postgresql://10.1.0.3/db?sslmode=disable",
                    "jdbc:postgresql://10.1.0.3/db?sslmode=require&sslmode=disable"):
            with self.subTest(url=url), self.assertRaises((JourneyFailure, ValueError)):
                datasource(url)

    def test_alloydb_profile_rejects_cloud_sql_resource_and_plaintext(self):
        for change in ({"resource": profile()["resource"]}, {"require_tls": False}, {"password": "secret"}):
            with self.subTest(change=change), self.assertRaises(JourneyFailure):
                validate_profile(seal({**profile(PROVIDERS[1]), **change}))

    def test_resolves_real_provider_and_requires_writable_primary(self):
        p = profile(PROVIDERS[1])
        cluster = {"name": p["resource"].split("/instances/")[0], "state": "READY", "databaseVersion": "POSTGRES_16"}
        instance = {"name": p["resource"], "state": "READY", "instanceType": "PRIMARY",
                    "ipAddress": "10.1.0.3", "createTime": "2026-09-12T01:00:00Z"}
        call = Mock(side_effect=[json.dumps(cluster), json.dumps(instance)])
        resolved = resolve_database(p, call)
        self.assertEqual(resolved["address"], "10.1.0.3")
        self.assertIn("--quiet", call.call_args.args[0])
        instance["instanceType"] = "READ_POOL"
        with self.assertRaises(JourneyFailure):
            resolve_database(p, Mock(side_effect=[json.dumps(cluster), json.dumps(instance)]))

    def test_cloud_sql_address_and_version_are_verified(self):
        p = profile()
        raw = {"name": "test-sql", "region": "us-west1", "state": "RUNNABLE",
               "databaseVersion": "POSTGRES_16", "createTime": "2026-09-12T01:00:00Z",
               "ipAddresses": [{"type": "PRIVATE", "ipAddress": "10.1.0.2"}]}
        self.assertEqual(resolve_database(p, Mock(return_value=json.dumps(raw)))["provider"], PROVIDERS[0])
        raw["databaseVersion"] = "POSTGRES_15"
        with self.assertRaises(JourneyFailure):
            resolve_database(p, Mock(return_value=json.dumps(raw)))

    def test_target_observation_rejects_datasource_for_other_instance(self):
        p = profile(PROVIDERS[1])
        r = Mock(**{k: p[k] for k in ("project", "region", "cluster", "namespace")})
        r.images = source_images()
        r.environment.return_value = observation(p)["environment"]
        r.deployment.side_effect = lambda service: {"spec": {"template": {"spec": {"containers": [
            {"name": service, "envFrom": [{"secretRef": {"name": "cloudbank-" + service + "-external"}}]}]}}}}
        r.secret_json.return_value = {"SPRING_DATASOURCE_URL": "jdbc:postgresql://10.1.0.3/cloudbank?sslmode=require",
                                      "SPRING_DATASOURCE_PASSWORD": "never-in-evidence"}
        r.get.side_effect = lambda *args: {"metadata": {"uid": "uid", "resourceVersion": "1"},
            "data": {k: base64.b64encode(v.encode()).decode() for k, v in r.secret_json.return_value.items()}}
        with patch("lightyear_data.cloudbank_managed_target.resolve_database", return_value=observation(p)["database"]):
            result = observe_target(r, p, Mock())
            self.assertNotIn("never-in-evidence", json.dumps(result))
            r.secret_json.return_value["LIQUIBASE_DATASOURCE_URL"] = "jdbc:postgresql://10.1.0.2/cloudbank"
            with self.assertRaisesRegex(JourneyFailure, "auxiliary-database-mismatch"):
                observe_target(r, p, Mock())
            del r.secret_json.return_value["LIQUIBASE_DATASOURCE_URL"]
            r.secret_json.return_value["SPRING_DATASOURCE_URL"] = "jdbc:postgresql://10.1.0.2/cloudbank?sslmode=require"
            with self.assertRaises(JourneyFailure):
                observe_target(r, p, Mock())

    def test_managed_probe_uses_namespace_secret_instead_of_original_cloud_sql_secret(self):
        p = profile(PROVIDERS[1])
        runtime = ManagedGkeRuntime(**{k: p[k] for k in ("project", "region", "cluster", "namespace")},
            images=source_images(), run_id="ms71-probe", output=Path("."), probe_image="test/probe@sha256:" + "a" * 64)
        jdbc = "jdbc:postgresql://10.1.0.3/cloudbank?sslmode=require"
        obj = {"data": {"SPRING_DATASOURCE_URL": base64.b64encode(jdbc.encode()).decode()}}
        manifests = []
        def call(*args, **kwargs):
            if args[0] == "create":
                manifests.append(json.loads(kwargs["data"]))
                return '{"metadata":{"uid":"probe"}}'
            return ""
        with patch.object(runtime, "get", return_value=obj) as get, \
                patch.object(runtime, "kubectl", side_effect=call), patch.object(runtime, "recovery_checkpoint"), \
                patch.object(runtime, "sql", return_value={"postgresql": True, "queue_present": True}), \
                patch("lightyear_data.cloudbank_journeys_gke.command") as cloud:
            runtime.create_probe()
            get.assert_called_once_with("secret", "cloudbank-checks-external")
            cloud.assert_not_called()
        env = {v["name"]: v for v in manifests[0]["spec"]["containers"][0]["env"]}
        self.assertEqual(env["PGHOST"]["value"], "10.1.0.3")
        self.assertEqual(env["PGSSLMODE"]["value"], "require")

    def test_tls_probe_keeps_credentials_as_references(self):
        r = GkeRuntime(project="test-project", region="us-west1", cluster="test-cluster", namespace="test-alloydb",
                       images=source_images(), run_id="ms71-test", output=Path("."),
                       probe_image="test/probe@sha256:" + "a" * 64)
        manifests = []
        def call(*args, **kw):
            if args[0] == "create":
                manifests.append(json.loads(kw["data"]))
                return '{"metadata":{"uid":"probe"}}'
            return ""
        with patch.object(r, "kubectl", side_effect=call), patch.object(r, "recovery_checkpoint"), \
                patch.object(r, "sql", return_value={"postgresql": True, "queue_present": True}):
            r.create_probe(jdbc_url="jdbc:postgresql://10.1.0.3/cloudbank?sslmode=require")
        env = {row["name"]: row for row in manifests[0]["spec"]["containers"][0]["env"]}
        self.assertEqual(env["PGSSLMODE"]["value"], "require")
        self.assertIn("secretKeyRef", env["PGPASSWORD"]["valueFrom"])


class CliTests(unittest.TestCase):
    def test_preflight_rejects_source_byte_drift_before_cloud_access(self):
        spec = importlib.util.spec_from_file_location("ms71_cli", ROOT / "tools/cloudbank_ms71.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        source = ROOT / "source-checkout"
        with patch.object(cli, "validate_edge_source", return_value=["source-drift"]) as validate, \
                patch.object(cli, "command") as command, patch.object(cli, "ManagedGkeRuntime") as runtime:
            with self.assertRaisesRegex(JourneyFailure, "pinned-source-bytes-invalid"):
                cli.preflight({}, {}, [], source)
            validate.assert_called_once_with(source)
            command.assert_not_called()
            runtime.assert_not_called()

    def test_new_attempt_refuses_unfinished_signed_target_recovery(self):
        spec = importlib.util.spec_from_file_location("ms71_cli", ROOT / "tools/cloudbank_ms71.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "alloydb-attempt" / "postgres-runtime" / "recovery-state.json"
            path.parent.mkdir(parents=True)
            state = {"state_type": "lightyear-cloudbank-journey-recovery", "stopped_services": [],
                     "probe_uid": None, "checks_delivery": None}
            path.write_text(json.dumps(sign(state, KEY, SIGNER)))
            cli.require_recovered_attempts(root, KEY)
            for change in ({"stopped_services": ["account"]}, {"probe_uid": "active"},
                           {"checks_delivery": {"restore": True}}):
                path.write_text(json.dumps(sign({**state, **change}, KEY, SIGNER)))
                with self.subTest(change=change), self.assertRaisesRegex(JourneyFailure, "recovery-required"):
                    cli.require_recovered_attempts(root, KEY)

    def test_invalid_input_reports_failure_without_traceback_or_cloud_calls(self):
        spec = importlib.util.spec_from_file_location("ms71_cli", ROOT / "tools/cloudbank_ms71.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text('{}', encoding="utf-8")
            with patch.object(cli, "command") as call, redirect_stdout(io.StringIO()) as output:
                code = cli.main(["seal-profile", str(path), str(Path(directory) / "out.json")])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output.getvalue())["MS71_COMPLETE"])
            call.assert_not_called()


class ProvisionTests(unittest.TestCase):
    def test_provision_requires_nonproduction_before_creating_anything(self):
        from lightyear_data.cloudbank_alloydb_provision import provision
        call = Mock(return_value="production")
        with self.assertRaises(JourneyFailure):
            provision(profile(PROVIDERS[1]), network="test-network", admin_secret="test-admin",
                      cpu_count=2, command=call)
        self.assertEqual(call.call_count, 1)

    def test_admin_password_never_enters_command_arguments(self):
        from lightyear_data.cloudbank_alloydb_provision import provision
        p = profile(PROVIDERS[1])
        calls, files = [], []
        password = "x" * 48
        def call(argv, **kwargs):
            calls.append(argv)
            self.assertNotIn(password, " ".join(argv))
            if "projects" in argv:
                return "non-production"
            if "clusters" in argv and "list" in argv:
                return "[]"
            if "secrets" in argv and "list" in argv:
                return "test-admin"
            if "access" in argv:
                return json.dumps({"username": "postgres", "password": password,
                                   "resource": p["resource"].split("/instances/")[0]})
            flags = next(a for a in argv if a.startswith("--flags-file="))
            path = Path(flags.split("=", 1)[1])
            self.assertEqual(json.loads(path.read_text())["--password"], password)
            files.append(path)
            return "operation"
        result = provision(p, network="test-network", admin_secret="test-admin", cpu_count=2, command=call)
        self.assertEqual(result["status"], "cluster-provisioning")
        self.assertFalse(result["MS71_COMPLETE"])
        self.assertTrue(all(not p.exists() for p in files))

    def test_existing_cluster_in_another_network_is_rejected(self):
        from lightyear_data.cloudbank_alloydb_provision import provision
        p = profile(PROVIDERS[1])
        call = Mock(side_effect=["non-production", json.dumps([{
            "name": p["resource"].split("/instances/")[0], "state": "READY",
            "databaseVersion": "POSTGRES_16", "networkConfig": {"network": "projects/test-project/global/networks/wrong"}
        }]), "123456789"])
        with self.assertRaisesRegex(JourneyFailure, "configuration-drift"):
            provision(p, network="test-network", admin_secret="test-admin", cpu_count=2, command=call)
        self.assertEqual(call.call_count, 3)


class DeploymentTests(unittest.TestCase):
    def test_telemetry_is_scoped_and_attributed_to_the_new_target(self):
        from lightyear_data.cloudbank_alloydb_deploy import telemetry_attributes, telemetry_policy
        value = telemetry_attributes("deployment.environment=non-production,lightyear.milestone=ms67", "alloydb")
        self.assertNotIn("ms67", value)
        self.assertIn("k8s.namespace.name=alloydb", value)
        policy = telemetry_policy("alloydb")["spec"]
        self.assertEqual(policy["ingress"][0]["ports"], [{"protocol": "TCP", "port": 4317}])
        peer = policy["ingress"][0]["from"][0]
        self.assertEqual(peer["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"], "alloydb")
        self.assertIn("podSelector", peer)

    def test_migration_and_runtime_connections_both_use_alloydb_credentials(self):
        from lightyear_data.cloudbank_alloydb_deploy import application_secret
        values = {"LIQUIBASE_DATASOURCE_URL": "jdbc:postgresql://10.1.0.2/cloudbank",
                  "LIQUIBASE_DATASOURCE_PASSWORD": "old", "OAUTH_CLIENT": "retained"}
        result = application_secret(values, "10.1.0.3", "cloudbank", "ms71", "new")
        self.assertEqual(result["LIQUIBASE_DATASOURCE_URL"], result["SPRING_DATASOURCE_URL"])
        self.assertEqual(result["LIQUIBASE_DATASOURCE_PASSWORD"], "new")
        self.assertEqual(result["OAUTH_CLIENT"], "retained")
        self.assertEqual(values["LIQUIBASE_DATASOURCE_PASSWORD"], "old")

    def test_secret_grants_are_scoped_to_new_secrets_and_namespace_identity(self):
        from lightyear_data.cloudbank_alloydb_deploy import grant_secret_access
        call = Mock(return_value="123456789")
        grant_secret_access("test-project", "test-alloydb", None, call)
        grants = [c.args[0] for c in call.call_args_list if "add-iam-policy-binding" in c.args[0]]
        self.assertEqual(len(grants), 8)
        for argv in grants:
            self.assertIn("--role=roles/secretmanager.secretAccessor", argv)
            member = next(v for v in argv if v.startswith("--member="))
            self.assertTrue(member.endswith("/subject/ns/test-alloydb/sa/cloudbank-secret-reader"))
            self.assertIn("cloudbank-ms71-alloydb-", " ".join(argv))
        with self.assertRaises(JourneyFailure):
            grant_secret_access("test-project", "test-alloydb", "wrong@other.iam.gserviceaccount.com", call)

    def test_clone_retains_images_but_does_not_start_consumers_before_seed(self):
        from lightyear_data.cloudbank_alloydb_deploy import copy_resource
        item = {"kind": "Deployment", "metadata": {"name": "account", "uid": "old", "namespace": "source",
            "resourceVersion": "2", "ownerReferences": [{"uid": "old"}]}, "status": {"readyReplicas": 2},
            "spec": {"replicas": 2, "template": {"spec": {"containers": [{"name": "account", "image": "bound-image"}]}}}}
        result = copy_resource(item, "alloydb", "10.1.0.2", "10.1.0.3")
        self.assertEqual(result["metadata"], {"name": "account", "namespace": "alloydb"})
        self.assertEqual(result["spec"]["replicas"], 0)
        self.assertEqual(result["spec"]["template"], item["spec"]["template"])
        self.assertNotIn("status", result)
        self.assertEqual(item["spec"]["replicas"], 2)

    def test_database_egress_is_replaced_not_added(self):
        from lightyear_data.cloudbank_alloydb_deploy import copy_resource
        item = {"kind": "NetworkPolicy", "metadata": {"name": "db"},
                "spec": {"egress": [{"to": [{"ipBlock": {"cidr": "10.1.0.2/32"}}]}]}}
        result = copy_resource(item, "alloydb", "10.1.0.2", "10.1.0.3")
        self.assertNotIn("10.1.0.2", json.dumps(result))
        self.assertIn("10.1.0.3/32", json.dumps(result))

    def test_seed_job_credentials_are_references_and_have_bounded_lifetime(self):
        from lightyear_data.cloudbank_alloydb_deploy import seed_pod
        pod = seed_pod("target", "10.1.0.2", "10.1.0.3", "cloudbank", "pinned-image")
        env = {row["name"]: row for row in pod["spec"]["containers"][0]["env"]}
        for name in ("SOURCE_PASSWORD", "ADMIN_PASSWORD", "APP_PASSWORD"):
            self.assertIn("secretKeyRef", env[name]["valueFrom"])
        self.assertEqual(pod["spec"]["activeDeadlineSeconds"], 1800)
        self.assertFalse(pod["spec"]["automountServiceAccountToken"])


if __name__ == "__main__":
    unittest.main()
