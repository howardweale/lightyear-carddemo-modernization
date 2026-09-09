import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES, hashed
from lightyear_data.cloudbank_log_correlation import (
    ENV, LEASE, MANAGER, MOUNT, VOLUME, OBSERVATION_TYPE, LoggingRollout, Telemetry,
    baseline, configuration, config_name, config_object, controlled, correlate,
    deployment_patch, instrument_bundle, normalized, verify_observation,
)
from lightyear_data.contracts import sign


PROJECT = "example-project"
ENVIRONMENT = {"project": PROJECT, "cluster": "test-cluster", "namespace": "test-namespace", "region": "us-west1"}
TRACE = "1" * 32
SPAN = "fedcba9876543210"
KEY = "unit-test-key-not-a-live-credential"
START, END = "2026-09-09T00:00:00Z", "2026-09-09T00:00:10Z"


def deployment(service="account"):
    return {"apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": service, "namespace": ENVIRONMENT["namespace"], "uid": "uid-" + service, "resourceVersion": "2"},
            "spec": {"replicas": 2, "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}},
                     "template": {"spec": {"containers": [{"name": service, "image": "registry/image@sha256:" + "a" * 64,
                     "env": [{"name": "EXISTING", "value": "unchanged"}], "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}]}],
                     "volumes": [{"name": "tmp", "emptyDir": {}}]}}}}


def apply(value, operations):
    result = copy.deepcopy(value)
    for op in operations:
        parts = [x.replace("~1", "/").replace("~0", "~") for x in op["path"].split("/")[1:]]
        parent = result
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        final = int(parts[-1]) if isinstance(parent, list) and parts[-1] != "-" else parts[-1]
        if op["op"] == "test":
            if parent[final] != op["value"]:
                raise JourneyFailure("test-resource-version-conflict")
        elif op["op"] == "remove":
            del parent[final]
        elif isinstance(parent, list):
            if final == "-":
                parent.append(copy.deepcopy(op["value"]))
            else:
                parent.insert(final, copy.deepcopy(op["value"]))
        else:
            parent[final] = copy.deepcopy(op["value"])
    return result


def provider_fixture():
    trace = {"projectId": PROJECT, "traceId": TRACE, "spans": []}
    logs, pods = [], {}
    for i, service in enumerate(SERVICES):
        span = format(int(SPAN, 16) + i, "016x")
        trace["spans"].append({"spanId": str(int(span, 16)), "labels": {"service.name": service},
                               "startTime": "2026-09-09T00:00:01.123400Z", "endTime": "2026-09-09T00:00:02.123456Z"})
        pods[service] = {service + "-pod": service + "-pod-uid"}
        logs.append({"timestamp": "2026-09-09T00:00:01.223456Z", "insertId": "log-" + service,
                     "trace": "projects/" + PROJECT + "/traces/" + TRACE, "spanId": span,
                     "resource": {"type": "k8s_container", "labels": {"project_id": PROJECT,
                                  "cluster_name": ENVIRONMENT["cluster"], "namespace_name": ENVIRONMENT["namespace"],
                                  "container_name": service, "pod_name": service + "-pod"}}})
    return trace, logs, pods


def matching(trace, logs, pods):
    return correlate(trace, logs, project=PROJECT, environment=ENVIRONMENT, trace_id=TRACE,
                     pods=pods, start=START, end=END)


class ConfigurationTests(unittest.TestCase):
    def test_request_appender_never_formats_messages_or_throwables(self):
        import xml.etree.ElementTree as ET
        xml = ET.fromstring(configuration(PROJECT))
        encoder = xml.find("appender/encoder/pattern").text
        for forbidden in ("%msg", "%message", "%ex", "%exception", "%throwable", "%mdc", "%X{"):
            if forbidden == "%X{":
                self.assertEqual(encoder.count(forbidden), 2)
            else:
                self.assertNotIn(forbidden, encoder)
        self.assertIn("%nopex", encoder)
        logger = xml.find("logger")
        self.assertEqual(logger.attrib, {"name": "org.springframework.web.servlet.DispatcherServlet", "level": "DEBUG", "additivity": "false"})
        self.assertEqual(xml.find("root").get("level"), "INFO")

    def test_project_cannot_inject_xml_or_filter(self):
        for value in ('bad"project', "foo/bar", "foo\nbar", "abc", "../example"):
            with self.subTest(value=value), self.assertRaises(JourneyFailure):
                configuration(value)

    def test_round_trip_preserves_original_spec_and_image(self):
        original = deployment()
        record = baseline(original, "account")
        installed = apply(original, deployment_patch(original, "account", PROJECT, record, install=True))
        self.assertTrue(normalized(installed["spec"], "account", PROJECT, record))
        self.assertEqual(deployment_patch(installed, "account", PROJECT, record, install=True), [])
        restored = apply(installed, deployment_patch(installed, "account", PROJECT, record, install=False))
        self.assertEqual(restored, original)

    def test_absent_lists_round_trip(self):
        original = deployment()
        c = original["spec"]["template"]["spec"]["containers"][0]
        c.pop("env"); c.pop("volumeMounts")
        original["spec"]["template"]["spec"].pop("volumes")
        record = baseline(original, "account")
        installed = apply(original, deployment_patch(original, "account", PROJECT, record, install=True))
        restored = apply(installed, deployment_patch(installed, "account", PROJECT, record, install=False))
        self.assertEqual(restored, original)

    def test_existing_exact_configuration_can_be_verified_and_is_preserved_by_recovery(self):
        obj = deployment()
        installed = apply(obj, deployment_patch(obj, "account", PROJECT, baseline(obj, "account"), install=True))
        record = baseline(installed, "account", PROJECT)
        self.assertTrue(record["logging_preexisting"])
        self.assertEqual(deployment_patch(installed, "account", PROJECT, record, install=True), [])
        self.assertEqual(deployment_patch(installed, "account", PROJECT, record, install=False), [])
        self.assertTrue(normalized(installed["spec"], "account", PROJECT, record))
        installed["spec"]["replicas"] = 1
        with self.assertRaises(JourneyFailure):
            normalized(installed["spec"], "account", PROJECT, record)

    def test_existing_logging_is_not_overwritten(self):
        for collection, value in (("env", ENV), ("volumeMounts", {"name": "other", "mountPath": MOUNT + "/nested"})):
            obj = deployment()
            obj["spec"]["template"]["spec"]["containers"][0][collection].append(value)
            with self.assertRaisesRegex(JourneyFailure, "conflict"):
                baseline(obj, "account")

    def test_drift_fails_before_mutation(self):
        original = deployment()
        record = baseline(original, "account")
        installed = apply(original, deployment_patch(original, "account", PROJECT, record, install=True))
        for mutate in (
            lambda d: d["spec"].update(replicas=1),
            lambda d: d["metadata"].update(uid="replacement"),
            lambda d: d["spec"]["template"]["spec"]["containers"][0].update(image="another-image"),
            lambda d: d["spec"]["template"]["spec"]["containers"][0]["env"][1].update(value="/other.xml"),
            lambda d: d["spec"]["template"]["spec"]["containers"][0]["env"].append({"name": "ANOTHER_OPERATOR", "value": "yes"}),
        ):
            changed = copy.deepcopy(installed)
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(JourneyFailure):
                deployment_patch(changed, "account", PROJECT, record, install=False)

    def test_atomic_patch_rejects_change_after_read(self):
        original = deployment()
        operations = deployment_patch(original, "account", PROJECT, baseline(original, "account"), install=True)
        original["metadata"]["resourceVersion"] = "3"
        with self.assertRaisesRegex(JourneyFailure, "resource-version"):
            apply(original, operations)

    def test_partial_configuration_does_not_look_restored(self):
        obj = deployment()
        record = baseline(obj, "account")
        obj["spec"]["template"]["spec"]["containers"][0]["env"].append(ENV)
        with self.assertRaisesRegex(JourneyFailure, "partial"):
            normalized(obj["spec"], "account", PROJECT, record)

    def test_unsafe_rollout_strategy_rejected(self):
        obj = deployment()
        obj["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] = 1
        with self.assertRaises(JourneyFailure):
            baseline(obj, "account")

    def test_fresh_deploy_uses_identical_immutable_configuration(self):
        bundle = {"kind": "List", "items": [deployment(s) for s in SERVICES]}
        original = copy.deepcopy(bundle)
        rendered = instrument_bundle(bundle, PROJECT, ENVIRONMENT["namespace"])
        self.assertEqual(bundle, original)
        self.assertEqual(rendered["items"][0], config_object(PROJECT, ENVIRONMENT["namespace"]))
        for obj in rendered["items"][1:]:
            service = obj["metadata"]["name"]
            self.assertTrue(normalized(obj["spec"], service, PROJECT, baseline(deployment(service), service)))
        self.assertTrue(rendered["items"][0]["immutable"])

    def test_incomplete_or_wrong_namespace_bundle_rejected(self):
        for items in ([deployment()], [deployment(s) for s in SERVICES]):
            with self.assertRaises(JourneyFailure):
                instrument_bundle({"kind": "List", "items": items}, PROJECT, "other-namespace")

    def test_fresh_manifests_do_not_require_live_metadata_but_rollout_does(self):
        bundle = {"kind": "List", "items": [deployment(s) for s in SERVICES]}
        for item in bundle["items"]:
            item["metadata"].pop("uid")
            item["metadata"].pop("resourceVersion")
        rendered = instrument_bundle(bundle, PROJECT, ENVIRONMENT["namespace"])
        self.assertTrue(all("uid" not in row["metadata"] for row in rendered["items"]))
        with self.assertRaisesRegex(JourneyFailure, "live-deployment-uid-required"):
            baseline(bundle["items"][0], SERVICES[0])


class CorrelationTests(unittest.TestCase):
    def test_exact_server_span_matches_for_all_eight_services(self):
        trace, logs, pods = provider_fixture()
        result = matching(trace, logs, pods)
        self.assertEqual(set(result), set(SERVICES))
        self.assertEqual(result[SERVICES[0]]["span_identity_sha256"], hashed(SPAN))
        self.assertNotIn("pod-uid", json.dumps(result))
        self.assertNotIn(TRACE, json.dumps(result))

    def test_matching_service_name_alone_is_not_correlation(self):
        trace, logs, pods = provider_fixture()
        logs[0]["spanId"] = "0" * 16
        self.assertNotIn(SERVICES[0], matching(trace, logs, pods))

    def test_other_pod_namespace_cluster_project_trace_or_time_rejected(self):
        for key in ("pod_name", "namespace_name", "cluster_name", "project_id"):
            trace, logs, pods = provider_fixture()
            logs[0]["resource"]["labels"][key] = "other"
            self.assertNotIn(SERVICES[0], matching(trace, logs, pods), key)
        for field, value in (("trace", "projects/other/traces/" + TRACE), ("timestamp", "2026-09-10T00:00:00Z"), ("timestamp", "bad")):
            trace, logs, pods = provider_fixture()
            logs[0][field] = value
            self.assertNotIn(SERVICES[0], matching(trace, logs, pods), field)

    def test_wrong_trace_response_fails_closed(self):
        trace, logs, pods = provider_fixture()
        for key in ("projectId", "traceId"):
            invalid = {**trace, key: "other"}
            with self.assertRaises(JourneyFailure):
                matching(invalid, logs, pods)

    def test_span_wrong_service_zero_overflow_or_nondecimal_rejected(self):
        for value in ("0", str(2 ** 64), "fedcba98", "-1"):
            trace, logs, pods = provider_fixture()
            trace["spans"][0]["spanId"] = value
            self.assertNotIn(SERVICES[0], matching(trace, logs, pods))
        trace, logs, pods = provider_fixture()
        trace["spans"][0]["labels"]["service.name"] = "other"
        self.assertNotIn(SERVICES[0], matching(trace, logs, pods))

    def test_query_follows_empty_pages_and_reports_exhaustion(self):
        api = Telemetry(PROJECT)
        api.request = Mock(side_effect=[{"nextPageToken": "a"}, {"entries": [{"spanId": "x"}]}])
        rows, complete = api.logs(ENVIRONMENT, TRACE, START, END)
        self.assertTrue(complete)
        self.assertEqual(rows, [{"spanId": "x"}])
        self.assertEqual(api.request.call_count, 2)
        api.request = Mock(return_value={"nextPageToken": "more"})
        self.assertEqual(api.logs(ENVIRONMENT, TRACE, START, END), ([], False))
        self.assertEqual(api.request.call_count, 5)

    def test_query_only_requests_metadata_in_exact_environment(self):
        api = Telemetry(PROJECT)
        api.request = Mock(return_value={})
        api.logs(ENVIRONMENT, TRACE, START, END)
        url = api.request.call_args.args[0]
        body = api.request.call_args.kwargs["body"]
        self.assertNotIn("textPayload", url)
        self.assertNotIn("jsonPayload", url)
        for expected in (PROJECT, ENVIRONMENT["cluster"], ENVIRONMENT["namespace"], TRACE, START, END, 'jsonPayload.event="cloudbank-request-context"'):
            self.assertIn(expected, body["filter"])


def observation():
    trace, logs, pods = provider_fixture()
    return {"observation_type": OBSERVATION_TYPE, "status": "passed-service-log-trace-correlation",
            "environment": ENVIRONMENT, "services": matching(trace, logs, pods), "images": {s: "registry/image@sha256:" + "a" * 64 for s in SERVICES},
            "bindings": {k: "a" * 64 for k in ("image_lock_sha256", "ms64_receipt_sha256", "platform_profile_sha256")},
            "ready_replicas": {s: 2 for s in SERVICES}, "configuration_sha256": hashlib.sha256(configuration(PROJECT).encode()).hexdigest(),
            "trace_identity_sha256": hashed(TRACE), "query_window": {"start": START, "end": END},
            "scope": "eight-service-readiness-probes-with-common-client-trace-context", "configuration_retained": True,
            "service_correlation_qualified": True, "business_journey_qualified": False, "ms67_complete": False,
            "production_ready": False, "production_environment": False, "credentials_persisted": False, "raw_output_persisted": False,
            "recovery": {"status": "not-required", "errors": []}}


class EvidenceTests(unittest.TestCase):
    def test_independent_verification_and_tamper_rejection(self):
        signed = sign(observation(), KEY, "unit-tests")
        verify_observation(signed, KEY)
        signed["images"][SERVICES[0]] = "another"
        with self.assertRaisesRegex(JourneyFailure, "signature"):
            verify_observation(signed, KEY)

    def test_resigned_overclaim_missing_service_or_unready_replica_rejected(self):
        for mutation in (
            lambda v: v.update(ms67_complete=True), lambda v: v.update(production_ready=True),
            lambda v: v.update(business_journey_qualified=True), lambda v: v.update(configuration_retained=False),
            lambda v: v["services"].pop(SERVICES[0]), lambda v: v["ready_replicas"].update({SERVICES[0]: 1}),
            lambda v: v["services"][SERVICES[0]].update(trace_identity_sha256="c" * 64),
            lambda v: v.update(status="preflight"), lambda v: v.update(recovery={"status": "recovery-required", "errors": []}),
            lambda v: v["services"][SERVICES[0]].update(log_timestamp="2026-09-10T00:00:00Z"),
            lambda v: v.update(configuration_sha256="f" * 64),
        ):
            value = observation(); mutation(value)
            with self.subTest(value=value), self.assertRaises(JourneyFailure):
                verify_observation(sign(value, KEY, "unit-tests"), KEY)


class RolloutTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.runtime = Mock(project=PROJECT, namespace=ENVIRONMENT["namespace"], output=Path(self.directory.name))
        self.runtime.deployment.return_value = deployment()
        self.state = {"run_id": "ms67-logs-test", "executor_id": "executor", "recovery_uri": "gs://example/recovery.json", "lease_uid": "lease-uid",
                      "baseline": {s: baseline(deployment(s), s) for s in SERVICES}, "config_preexisting": True}
        self.journal = Mock()
        self.engine = LoggingRollout(self.runtime, self.journal, self.state)
        self.lease = {"metadata": {"uid": "lease-uid", "name": LEASE, "resourceVersion": "3",
                                  "labels": {"app.kubernetes.io/managed-by": MANAGER},
                                  "annotations": {"lightyear.ai/executor": "executor", "lightyear.ai/recovery-state": self.state["recovery_uri"]}},
                      "spec": {"holderIdentity": self.state["run_id"]}}

    def test_lock_fences_other_executor_and_replaced_lease(self):
        self.engine.optional = Mock(return_value=self.lease)
        self.engine.owned()
        self.lease["metadata"]["annotations"]["lightyear.ai/executor"] = "another"
        with self.assertRaises(JourneyFailure):
            self.engine.owned()
        self.lease["metadata"]["annotations"]["lightyear.ai/executor"] = "executor"
        self.lease["metadata"]["uid"] = "replacement"
        with self.assertRaises(JourneyFailure):
            self.engine.owned()

    def test_failed_durable_checkpoint_prevents_patch(self):
        self.engine.owned = Mock(return_value=self.lease)
        self.journal.write.side_effect = JourneyFailure("checkpoint-write-failed")
        with self.assertRaisesRegex(JourneyFailure, "checkpoint-write"):
            self.engine.update("account", True)
        self.runtime.kubectl.assert_not_called()

    def test_recovery_handles_lost_patch_response(self):
        obj = deployment()
        installed = apply(obj, deployment_patch(obj, "account", PROJECT, self.state["baseline"]["account"], install=True))
        # The signed state still says 'before-install', but the server applied it.
        self.runtime.deployment.return_value = installed
        self.engine.owned = Mock(return_value=self.lease)
        def kubectl(*args, **kwargs):
            if args[0] == "patch":
                ops = json.loads(Path(args[-1]).read_text())
                self.runtime.deployment.return_value = apply(self.runtime.deployment.return_value, ops)
            return ""
        self.runtime.kubectl.side_effect = kubectl
        self.engine.update("account", False)
        self.assertEqual(self.runtime.deployment.return_value, obj)
        self.assertFalse((self.runtime.output / "logging-patch.json").exists())

    def test_recovery_attempts_other_services_but_keeps_lock_on_drift(self):
        self.engine.owned = Mock(return_value=self.lease)
        self.engine.update = Mock(side_effect=[JourneyFailure("logging-deployment-spec-drift")] + [None] * 7)
        self.engine.release = Mock()
        recovery = self.engine.recover()
        self.assertEqual(self.engine.update.call_count, 8)
        self.assertEqual(recovery["status"], "recovery-required")
        self.engine.release.assert_not_called()

    def test_configmap_content_or_uid_drift_is_not_adopted(self):
        value = config_object(PROJECT, ENVIRONMENT["namespace"])
        value["metadata"]["uid"] = "config-uid"
        self.engine.optional = Mock(return_value=value)
        self.assertEqual(self.engine.check_config(), value)
        value["data"]["logback-spring.xml"] += "changed"
        with self.assertRaises(JourneyFailure):
            self.engine.check_config()

    def test_each_lost_mutation_response_recovers_original_eight_deployments(self):
        # Exercise the actual install/recover state machine after a server-side
        # write succeeds but its response is lost. This includes ConfigMap
        # creation and each of the eight independent deployment patches.
        for lost_at in range(1, 10):
            with self.subTest(lost_at=lost_at):
                objects = {("deployment", s): deployment(s) for s in SERVICES}
                original = copy.deepcopy(objects)
                counter = [0]
                state = copy.deepcopy(self.state)
                state.update(lease_uid=None, config_uid=None, config_preexisting=False)
                def changed():
                    counter[0] += 1
                    if counter[0] == lost_at:
                        raise JourneyFailure("provider-response-lost")
                def invoke(*args, **kwargs):
                    if args[0] == "get":
                        obj = objects.get((args[1], args[2]))
                        return json.dumps(obj) if obj else ""
                    if args[0] == "create":
                        obj = json.loads(kwargs["data"])
                        obj["metadata"].update(uid="uid-" + obj["metadata"]["name"], resourceVersion="1")
                        objects[(obj["kind"].lower(), obj["metadata"]["name"])] = obj
                        if obj["kind"] == "ConfigMap":
                            changed()
                    elif args[0] == "patch":
                        key = (args[1], args[2])
                        operations = json.loads(Path(args[-1]).read_text())
                        objects[key] = apply(objects[key], operations)
                        objects[key]["metadata"]["resourceVersion"] = str(int(objects[key]["metadata"]["resourceVersion"]) + 1)
                        if args[1] == "deployment":
                            changed()
                    elif args[0] == "delete":
                        self.assertEqual(args[1], "--raw")
                        self.assertEqual(args[2], "/api/v1/namespaces/" + ENVIRONMENT["namespace"] + "/configmaps/" + config_name(PROJECT))
                        body = json.loads(Path(args[-1]).read_text())
                        obj = objects[("configmap", config_name(PROJECT))]
                        self.assertEqual(body["preconditions"], {k: obj["metadata"][k] for k in ("uid", "resourceVersion")})
                        objects.pop(("configmap", config_name(PROJECT)))
                    return ""
                runtime = Mock(project=PROJECT, namespace=ENVIRONMENT["namespace"], output=Path(self.directory.name))
                runtime.kubectl.side_effect = invoke
                runtime.deployment.side_effect = lambda s: copy.deepcopy(objects[("deployment", s)])
                runtime.get.side_effect = lambda kind: {"items": [] if kind == "pods" else [objects[("deployment", s)] for s in SERVICES]}
                engine = LoggingRollout(runtime, Mock(), state)
                with self.assertRaisesRegex(JourneyFailure, "response-lost"):
                    engine.install()
                self.assertEqual(engine.recover(), {"status": "restored", "errors": []})
                self.assertTrue(state["cleanup_complete"])
                for key, value in original.items():
                    self.assertEqual(objects[key]["spec"], value["spec"])
                self.assertNotIn(("configmap", config_name(PROJECT)), objects)
                self.assertEqual(objects[("lease", LEASE)]["spec"]["holderIdentity"], "")


if __name__ == "__main__":
    unittest.main()
