from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from lightyear_data.cloudbank_journeys import Response, SCENARIOS as JOURNEY_SCENARIOS, hashed, journey_contract
from lightyear_data.cloudbank_ms65_rehearsal_gke import (
    CANARY_NAME,
    CANARY_SERVICE,
    DurableJournal,
    Ms65GkeRehearsal,
    build_observation,
    validate_database_recovery,
    validate_shared_journeys,
)
from lightyear_data.cloudbank_production_readiness import (
    SCENARIO_IDS,
    SERVICES,
    cutover_contract,
    render_deployment_bundle,
    validate_observation,
)
from lightyear_data.contracts import content_hash, sign, verify_signature


KEY = "unit-ms65-live-key"
HEX_A, HEX_B = "a" * 64, "b" * 64


def sealed(value):
    value["content_sha256"] = content_hash(value)
    return value


def image_lock():
    return sealed({
        "schema_version": "1.0", "lock_type": "lightyear-cloudbank-ms65-image-lock",
        "release": "0.65.0", "source_ms64_receipt_sha256": HEX_A,
        "images": [{"service": service,
                    "reference": f"registry.test/{service}@sha256:{index:064x}"}
                   for index, service in enumerate(SERVICES, 1)],
    })


def environment():
    return sealed({
        "schema_version": "1.0", "environment_type": "lightyear-cloudbank-ms65-environment",
        "release": "0.65.0", "cluster_identity_sha256": HEX_B,
        "namespace": "cloudbank-ms67", "ingress_namespace": "ingress-nginx",
        "database_egress_cidr": "10.20.0.2/32", "model_egress_cidr": "192.0.2.1/32",
        "service_secret_names": {service: f"cloudbank-{service}-external" for service in SERVICES},
        "non_production": True,
    })


def live_environment():
    return {"project": "test-project", "region": "us-west1", "cluster": "test-cluster",
            "namespace": "cloudbank-ms67", "namespace_uid_sha256": "c" * 64}


def journey_evidence(lock):
    rows = []
    for identifier, normalized in JOURNEY_SCENARIOS:
        evidence = {"marker": identifier}
        rows.append({"id": identifier, "status": "passed", "normalized_result": normalized,
                     "evidence": evidence, "evidence_sha256": hashed(evidence)})
    return sign({
        "schema_version": "1.0", "observation_type": "lightyear-cloudbank-shared-journey-execution",
        "run_id": "journeys-unit", "bindings": {"ms64_receipt_sha256": HEX_A,
            "image_lock_sha256": lock["content_sha256"], "environment": live_environment(),
            "journey_contract_sha256": journey_contract()["content_sha256"]},
        "status": "passed-shared-journeys", "scenarios": rows, "scenario_count": 18,
        "recovery": {"status": "restored", "errors": [], "remaining_stopped_services": []},
        "synthetic_data_only": True, "raw_output_persisted": False,
        "credentials_persisted": False, "production_environment": False,
        "whole_application_equivalent": False,
        "ms65_complete": False, "ms66_complete": False, "ms67_complete": False,
    }, KEY, "unit-observer")


def recovery_evidence(images, journeys):
    databases = {"account": {"state_sha256": "d" * 64}}
    checkpoint = {"state_sha256": hashed(databases), "databases": databases}
    backup_record = {
        "id": "1", "instance": "cloudbank", "startTime": "2026-01-01T00:00:00Z",
        "endTime": "2026-01-01T00:01:00Z", "status": "SUCCESSFUL", "type": "ON_DEMAND",
    }
    return sign({
        "observation_type": "lightyear-cloudbank-isolated-sql-recovery",
        "status": "passed-isolated-database-recovery",
        "bindings": {"environment": live_environment(), "images_sha256": hashed(images),
                     "journeys_content_sha256": journeys["content_sha256"]},
        "checkpoint": checkpoint,
        "backup": {**backup_record, "metadata_sha256": hashed(backup_record),
                   "retained": True, "managed_backup_bytes_sha256": None},
        "pitr": {"restored_state": checkpoint, "state_matches": True,
                 "recovery_point_age_seconds": 10, "database_rto_seconds": 120,
                 "rpo_within_limit": True, "rto_within_limit": True},
        "backup_restore": {"restored_state": checkpoint, "database_rto_seconds": 100,
                           "state_matches": True, "rto_within_limit": True},
        "recovery": {"status": "restored", "validation_instance_deleted": True,
                     "validation_instance_state": "deleted", "errors": [],
                     "remaining_stopped_services": []},
        "credentials_persisted": False, "raw_database_rows_persisted": False,
        "ms65_complete": False, "ms66_complete": False, "ms67_complete": False,
    }, KEY, "unit-observer")


class StaticRuntime:
    def __init__(self, lock, env):
        self.images = {row["service"]: row["reference"] for row in lock["images"]}
        self.namespace, self.context, self.run_id = env["namespace"], "gke_test", "ms65-unit"
        self.forwards = {}
        self.objects = {}
        deployments, services, accounts, budgets, external = [], [], [], [], []
        for service in SERVICES:
            deployments.append({"metadata": {"name": service, "uid": "deploy-" + service}, "spec": {
                "replicas": 2, "strategy": {"type": "RollingUpdate", "rollingUpdate": {
                    "maxUnavailable": 0, "maxSurge": 1}},
                "template": {"metadata": {"annotations": {
                    "lightyear.ai/configuration-sha256": env["content_sha256"]}}, "spec": {
                    "serviceAccountName": service, "automountServiceAccountToken": False,
                    "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [{"name": service, "image": self.images[service],
                        "envFrom": [{"configMapRef": {"name": "cloudbank-runtime"}},
                                    {"secretRef": {"name": f"cloudbank-{service}-external"}}],
                        "securityContext": {"allowPrivilegeEscalation": False,
                            "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                        "resources": {"requests": {"cpu": "100m", "memory": "256Mi"},
                                      "limits": {"cpu": "1", "memory": "1Gi"}},
                        "startupProbe": {"httpGet": {"path": "/live"}},
                        "livenessProbe": {"httpGet": {"path": "/live"}},
                        "readinessProbe": {"httpGet": {"path": "/ready"}}}]}}}})
            services.append({"metadata": {"name": service, "uid": "service-" + service},
                             "spec": {"selector": {"app.kubernetes.io/name": service}}})
            accounts.append({"metadata": {"name": service, "uid": "account-" + service},
                             "automountServiceAccountToken": False})
            budgets.append({"metadata": {"name": service, "uid": "budget-" + service}, "spec": {
                "minAvailable": 1, "selector": {"matchLabels": {"app.kubernetes.io/name": service}}}})
            external.append({"metadata": {"name": "cloudbank-" + service, "uid": "external-" + service},
                "spec": {"secretStoreRef": {"name": "cloudbank-gcp-secret-manager", "kind": "SecretStore"},
                         "target": {"name": f"cloudbank-{service}-external", "creationPolicy": "Owner"},
                         "dataFrom": [{"extract": {"key": f"cloudbank-{service}-external",
                             "conversionStrategy": "Default"}}]},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]}})
        self.objects.update(deployments=deployments, services=services, serviceaccounts=accounts,
                            poddisruptionbudgets=budgets, externalsecrets=external)
        self.objects["networkpolicies"] = [
            {"metadata": {"name": "default-deny", "uid": "deny"},
             "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}},
            {"metadata": {"name": "cloudbank-bounded-traffic", "uid": "bounded"},
             "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/part-of": "cloudbank"}},
                      "policyTypes": ["Ingress", "Egress"],
                      "ingress": [{"from": [
                          {"podSelector": {"matchLabels": {"app.kubernetes.io/part-of": "cloudbank"}}},
                          {"namespaceSelector": {"matchLabels": {
                              "kubernetes.io/metadata.name": env["ingress_namespace"]}}},
                      ]}],
                      "egress": [
                          {"to": [{"podSelector": {"matchLabels": {
                              "app.kubernetes.io/part-of": "cloudbank"}}}]},
                          {"to": [{"namespaceSelector": {"matchLabels": {
                              "kubernetes.io/metadata.name": "kube-system"}}}],
                           "ports": [{"protocol": "UDP", "port": 53},
                                     {"protocol": "TCP", "port": 53}]},
                          {"to": [{"ipBlock": {"cidr": env["database_egress_cidr"]}}],
                           "ports": [{"protocol": "TCP", "port": 5432}]},
                      ]}},
            {"metadata": {"name": "chatbot-model-egress", "uid": "model"},
             "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/name": "chatbot"}},
                      "policyTypes": ["Egress"],
                      "egress": [{"to": [{"ipBlock": {"cidr": env["model_egress_cidr"]}}],
                                  "ports": [{"protocol": "TCP", "port": 443}]}]}},
            {"metadata": {"name": "cloudbank-otel-egress", "uid": "otel"},
             "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/part-of": "cloudbank"}},
                      "policyTypes": ["Egress"],
                      "egress": [{"to": [{
                          "namespaceSelector": {"matchLabels": {
                              "kubernetes.io/metadata.name": "observability"}},
                          "podSelector": {"matchLabels": {"app": "otel-collector"}},
                      }], "ports": [{"protocol": "TCP", "port": 4317}]}]}},
            {"metadata": {"name": "chatbot-in-cluster-model-egress", "uid": "cluster-model"},
             "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/name": "chatbot"}},
                      "policyTypes": ["Egress"],
                      "egress": [{"to": [{
                          "namespaceSelector": {"matchLabels": {
                              "kubernetes.io/metadata.name": "cloudbank-ms67-model"}},
                          "podSelector": {"matchLabels": {"app.kubernetes.io/name": "ollama"}},
                      }], "ports": [{"protocol": "TCP", "port": 11434}]}]}},
            {"metadata": {"name": "cloudbank-acme-http01-ingress", "uid": "acme"},
             "spec": {"podSelector": {"matchLabels": {
                          "acme.cert-manager.io/http01-solver": "true"}},
                      "policyTypes": ["Ingress"],
                      "ingress": [{"from": [{
                          "namespaceSelector": {"matchLabels": {
                              "kubernetes.io/metadata.name": env["ingress_namespace"]}},
                          "podSelector": {"matchLabels": {
                              "app.kubernetes.io/name": "ingress-nginx",
                              "app.kubernetes.io/instance": "ingress-nginx",
                              "app.kubernetes.io/component": "controller",
                          }},
                      }], "ports": [{"protocol": "TCP", "port": 8089}]}]}},
        ]
        self.objects["configmap/cloudbank-runtime"] = {"data": {
            "LIGHTYEAR_RELEASE": "0.65.0", "LIGHTYEAR_CONFIGURATION_SHA256": env["content_sha256"]}}

    def get(self, kind, name=None, selector=None):
        if name:
            return self.objects[f"{kind}/{name}"]
        return {"items": self.objects[kind]}

    def ready(self):
        return {service: {"ready_replicas": 2, "image": self.images[service]} for service in SERVICES}


class FakeClock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def sleep(self, seconds): self.value += seconds


class CanaryRuntime:
    def __init__(self, lock, journal_path):
        self.images = {row["service"]: row["reference"] for row in lock["images"]}
        self.namespace, self.context, self.run_id = "cloudbank-ms67", "gke_test", "ms65-canary-unit"
        self.forwards, self.canary = {}, None
        self.sticky_canary_endpoints = False
        self.original_pods = [{"metadata": {"uid": "original-1"}}, {"metadata": {"uid": "original-2"}}]
        self.service = {"metadata": {"uid": "service-uid", "resourceVersion": "1"},
                        "spec": {"selector": {"app.kubernetes.io/name": CANARY_SERVICE}}}
        self.journal_path = journal_path

    def deployment(self, service):
        self.assert_service(service)
        return {"metadata": {"uid": "deployment-uid"}, "spec": {"template": {
            "metadata": {"labels": {"app.kubernetes.io/name": service,
                "app.kubernetes.io/part-of": "cloudbank"}, "annotations": {}},
            "spec": {"serviceAccountName": service, "containers": [{"name": service,
                "image": self.images[service]}]}}}}

    def assert_service(self, service):
        if service != CANARY_SERVICE: raise AssertionError(service)

    def get(self, kind, name=None, selector=None):
        if kind == "service": return self.service
        if kind == "pods" and selector and "ms65-canary" in selector:
            return {"items": [] if self.canary is None else [{
                "metadata": {"uid": "canary-pod", "ownerReferences": [
                    {"uid": "canary-rs", "controller": True}]},
                "status": {"containerStatuses": [{"name": CANARY_SERVICE, "ready": True,
                    "state": {"running": {}},
                    "imageID": "registry@sha256:" + self.images[CANARY_SERVICE].split("@sha256:")[1]}]}}]}
        if kind == "replicasets" and selector and "ms65-canary" in selector:
            return {"items": [] if self.canary is None else [{"metadata": {"uid": "canary-rs",
                "ownerReferences": [{"uid": "canary-uid", "controller": True}]}}]}
        if kind == "endpoints":
            switched = self.sticky_canary_endpoints or \
                "lightyear.ai/ms65-canary" in self.service["spec"]["selector"]
            uids = ["canary-pod"] if switched else ["original-1", "original-2"]
            return {"subsets": [{"addresses": [{"targetRef": {"uid": uid}} for uid in uids]}]}
        raise AssertionError((kind, name, selector))

    def kubectl(self, *args, data=None, timeout=45):
        if args[:2] == ("get", "deployment/" + CANARY_NAME):
            return "" if self.canary is None else json.dumps(self.canary)
        if args[:2] == ("create", "-f"):
            saved = json.loads(self.journal_path.read_text())
            if saved["phase"] != "canary-create-intent-saved": raise AssertionError(saved["phase"])
            payload = json.loads(data)
            self.canary = {"metadata": {"uid": "canary-uid", "labels": payload["metadata"]["labels"]},
                           "status": {"readyReplicas": 1}}
            return json.dumps(self.canary)
        if args[:2] == ("rollout", "status"): return "ready"
        if args[0] == "patch":
            patch = json.loads(args[-1])
            self.service["spec"]["selector"] = patch[-1]["value"]
            self.service["metadata"]["resourceVersion"] = str(int(self.service["metadata"]["resourceVersion"]) + 1)
            return "patched"
        if args[0] == "delete":
            self.canary = None
            return "deleted"
        raise AssertionError(args)

    def pods(self, service):
        self.assert_service(service)
        return self.original_pods

    def close_forward(self, service): self.assert_service(service)

    def request(self, service, method, path, role):
        self.assert_service(service)
        return Response(200, b'{"Credit Score":"700"}', {})


class Ms65LiveTests(unittest.TestCase):
    def test_durable_journal_seals_locally_before_remote_checkpoint(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"

            def upload(argv, *, timeout):
                saved = json.loads(path.read_text())
                self.assertTrue(verify_signature(saved, KEY))
                self.assertEqual("traffic-switch-intent-saved", saved["phase"])
                calls.append((argv, timeout))
                return ""

            journal = DurableJournal(path, KEY, "observer", "gs://private/state.json", upload,
                                     project="test-project")
            sealed_state = journal.write({"phase": "traffic-switch-intent-saved"})

        self.assertTrue(verify_signature(sealed_state, KEY))
        self.assertEqual(
            (["gcloud", "storage", "cp", str(path), "gs://private/state.json",
              "--project", "test-project"], 180),
            calls[0],
        )

    def test_signed_prerequisites_are_bound_to_same_live_target(self):
        lock = image_lock()
        images = {row["service"]: row["reference"] for row in lock["images"]}
        journeys = journey_evidence(lock)
        recovery = recovery_evidence(images, journeys)
        self.assertEqual(18, validate_shared_journeys(journeys, KEY, ms64_sha256=HEX_A,
            image_lock_sha256=lock["content_sha256"], environment=live_environment())["scenario_count"])
        mapped = validate_database_recovery(
            recovery, KEY, images=images, environment=live_environment(),
            journeys_sha256=journeys["content_sha256"],
        )
        self.assertEqual(mapped["pre_cutover_state_sha256"], mapped["restored_state_sha256"])
        with self.assertRaisesRegex(Exception, "passed-bound-database-recovery-required"):
            validate_database_recovery(
                recovery, KEY, images=images, environment=live_environment(),
                journeys_sha256="f" * 64,
            )
        recovery["backup_restore"]["state_matches"] = False
        recovery = sign(recovery, KEY, "unit-observer")
        with self.assertRaisesRegex(Exception, "passed-bound-database-recovery-required"):
            validate_database_recovery(
                recovery, KEY, images=images, environment=live_environment(),
                journeys_sha256=journeys["content_sha256"],
            )

    def test_live_static_controls_cover_all_eight_services(self):
        lock, env = image_lock(), environment()
        manifest, bundle = render_deployment_bundle(lock, env, HEX_A)
        runtime = StaticRuntime(lock, env)
        with tempfile.TemporaryDirectory() as directory:
            journal = DurableJournal(Path(directory) / "state.json", KEY, "observer")
            runner = Ms65GkeRehearsal(runtime, env, bundle, manifest, KEY, "observer", journal)
            details, rollouts = runner.inspect_controls(HEX_A, lock["content_sha256"])
        self.assertEqual(list(SERVICES), [row["service"] for row in rollouts])
        self.assertEqual(8, len(details["security"]))
        self.assertEqual(8, len(details["secrets"]))

    def test_live_controls_reject_extra_egress_and_inline_secret_templates(self):
        lock, env = image_lock(), environment()
        manifest, bundle = render_deployment_bundle(lock, env, HEX_A)
        for mutation, reason in (
            (lambda runtime: runtime.objects["networkpolicies"][1]["spec"]["egress"].append(
                {"to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]}),
             "ms65-bounded-network-policy-invalid"),
            (lambda runtime: runtime.objects["externalsecrets"][0]["spec"]["target"].update(
                template={"data": {"PASSWORD": "inline"}}),
             "ms65-external-secret-binding-invalid"),
        ):
            runtime = StaticRuntime(lock, env)
            mutation(runtime)
            with tempfile.TemporaryDirectory() as directory:
                runner = Ms65GkeRehearsal(
                    runtime, env, bundle, manifest, KEY, "observer",
                    DurableJournal(Path(directory) / "state.json", KEY, "observer"),
                )
                with self.assertRaisesRegex(Exception, reason):
                    runner.inspect_controls(HEX_A, lock["content_sha256"])

    def test_canary_switch_slo_and_rollback_restore_original_service(self):
        lock, env = image_lock(), environment()
        manifest, bundle = render_deployment_bundle(lock, env, HEX_A)
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            runtime = CanaryRuntime(lock, path)
            runner = Ms65GkeRehearsal(runtime, env, bundle, manifest, KEY, "observer",
                                      DurableJournal(path, KEY, "observer"), clock=clock, pause=clock.sleep)
            runner.save("admitted")
            runner.save("backup-verified")
            runner.create_canary()
            runner.save("smoke-passed")
            runner.switch_to_canary()
            runner.save("business-checks-passed")
            slo = runner.measure_slo()
            runner.rollback()
            cleanup = runner.cleanup()
        self.assertEqual(100, slo["requests"])
        self.assertEqual(60, slo["duration_seconds"])
        self.assertEqual({"app.kubernetes.io/name": CANARY_SERVICE}, runtime.service["spec"]["selector"])
        self.assertIsNone(runtime.canary)
        self.assertEqual("restored", cleanup["status"])
        self.assertFalse(cleanup["canary_preserved"])

    def test_fixed_canary_name_serializes_competing_rehearsals(self):
        lock, env = image_lock(), environment()
        manifest, bundle = render_deployment_bundle(lock, env, HEX_A)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "first.json"
            runtime = CanaryRuntime(lock, path)
            first = Ms65GkeRehearsal(runtime, env, bundle, manifest, KEY, "observer",
                                     DurableJournal(path, KEY, "observer"))
            first.save("admitted")
            first.save("backup-verified")
            first.create_canary()
            runtime.run_id = "ms65-competing-unit"
            second = Ms65GkeRehearsal(
                runtime, env, bundle, manifest, KEY, "observer",
                DurableJournal(Path(directory) / "second.json", KEY, "observer"),
            )
            self.assertEqual(CANARY_NAME, first.canary_name)
            self.assertEqual(CANARY_NAME, second.canary_name)
            with self.assertRaisesRegex(Exception, "ms65-canary-name-already-exists"):
                second.create_canary()
            cleanup = second.cleanup()
        self.assertEqual("failed", cleanup["status"])
        self.assertTrue(cleanup["canary_preserved"])
        self.assertIsNotNone(runtime.canary)

    def test_cleanup_preserves_canary_when_service_identity_drift_blocks_rollback(self):
        lock, env = image_lock(), environment()
        manifest, bundle = render_deployment_bundle(lock, env, HEX_A)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            runtime = CanaryRuntime(lock, path)
            runner = Ms65GkeRehearsal(runtime, env, bundle, manifest, KEY, "observer",
                                      DurableJournal(path, KEY, "observer"))
            runner.save("admitted")
            runner.save("backup-verified")
            runner.create_canary()
            runner.save("smoke-passed")
            runner.switch_to_canary()
            runtime.service["metadata"]["uid"] = "replacement-service-uid"
            cleanup = runner.cleanup()
        self.assertEqual("failed", cleanup["status"])
        self.assertTrue(cleanup["canary_preserved"])
        self.assertIsNotNone(runtime.canary)
        self.assertEqual({"lightyear.ai/ms65-canary": runner.canary_label},
                         runtime.service["spec"]["selector"])

    def test_cleanup_waits_for_original_endpoints_before_deleting_canary(self):
        lock, env = image_lock(), environment()
        manifest, bundle = render_deployment_bundle(lock, env, HEX_A)
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            runtime = CanaryRuntime(lock, path)
            runner = Ms65GkeRehearsal(runtime, env, bundle, manifest, KEY, "observer",
                                      DurableJournal(path, KEY, "observer"),
                                      clock=clock, pause=clock.sleep)
            runner.save("admitted")
            runner.save("backup-verified")
            runner.create_canary()
            runner.save("smoke-passed")
            runner.switch_to_canary()
            runtime.sticky_canary_endpoints = True
            cleanup = runner.cleanup()
        self.assertEqual("failed", cleanup["status"])
        self.assertTrue(cleanup["canary_preserved"])
        self.assertIsNotNone(runtime.canary)
        self.assertEqual({"app.kubernetes.io/name": CANARY_SERVICE},
                         runtime.service["spec"]["selector"])

    def test_generated_observation_is_accepted_by_existing_ms65_controller(self):
        lock, env = image_lock(), environment()
        manifest, bundle = render_deployment_bundle(lock, env, HEX_A)
        controls, rollouts = Ms65GkeRehearsal(
            StaticRuntime(lock, env), env, bundle, manifest, KEY, "observer",
            DurableJournal(Path(tempfile.mkdtemp()) / "state.json", KEY, "observer"),
        ).inspect_controls(HEX_A, lock["content_sha256"])
        backup = {"pre_cutover_state_sha256": "d" * 64, "backup_sha256": "e" * 64,
                  "restored_state_sha256": "d" * 64}
        observation, details = build_observation(
            ms64_sha256=HEX_A, image_lock_sha256=lock["content_sha256"], environment=env,
            bundle=bundle, control_details=controls, rollouts=rollouts,
            journeys={"content_sha256": "f" * 64, "scenario_count": 18, "recovery_status": "restored"},
            backup_restore=backup, canary={"status": "ready"}, traffic={"status": "switched"},
            business={"http_status": 200}, rollback={"status": "restored"},
            slo={"requests": 100, "errors": 0, "p95_ms": 10, "duration_seconds": 60},
            cutover_states=cutover_contract()["required_state_sequence"],
            key=KEY, signer="observer")
        self.assertEqual([], validate_observation(observation, KEY, ms64_sha256=HEX_A,
            image_lock=lock, environment=env, bundle=bundle))
        self.assertEqual(SCENARIO_IDS, [row["id"] for row in observation["scenarios"]])
        self.assertTrue(verify_signature(details, KEY))

    def test_observation_rejects_uncheckpointed_cutover_sequence(self):
        lock, env = image_lock(), environment()
        _, bundle = render_deployment_bundle(lock, env, HEX_A)
        with self.assertRaisesRegex(Exception, "ms65-cutover-state-sequence-invalid"):
            build_observation(
                ms64_sha256=HEX_A, image_lock_sha256=lock["content_sha256"], environment=env,
                bundle=bundle, control_details={}, rollouts=[], journeys={}, backup_restore={},
                canary={}, traffic={}, business={}, rollback={},
                slo={"requests": 100, "errors": 0, "p95_ms": 10, "duration_seconds": 60},
                cutover_states=["admitted"], key=KEY, signer="observer",
            )


if __name__ == "__main__":
    unittest.main()
