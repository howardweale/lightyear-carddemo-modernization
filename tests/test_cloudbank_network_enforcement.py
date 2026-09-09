import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES, hashed
from lightyear_data.cloudbank_network_enforcement import (
    Backend, GATE, INTENT, LABEL, LEASE, NetworkRun, PASS, ROLE, STATE_TYPE,
    compiled_probe, mark, pod_object, route_guard, selected, selector_matches, verify_observation,
)
from lightyear_data.contracts import sign

ROOT = Path(__file__).resolve().parents[1]
APP, MODEL = "cloudbank-test", "cloudbank-model-test"
ENV = {"project": "test-project", "cluster": "test-cluster", "namespace": APP, "region": "us-west1",
       "namespace_uid_sha256": "a" * 64}
IMAGES = {s: "us-west1-docker.pkg.dev/test-project/test/" + s + "@sha256:" + "a" * 64 for s in SERVICES}
PROFILE = {"model_namespace": MODEL, "model_image": "registry.example/ollama@sha256:" + "b" * 64,
           "expected_hostname": "test.example"}
BINDINGS = {k: "c" * 64 for k in ("image_lock_sha256", "ms64_receipt_sha256", "platform_profile_sha256")}
KEY = "unit-test-only-evidence-key"
ARTIFACT = compiled_probe(ROOT)
RUN = "ms67-network-" + "1" * 32


def policy(name, selector, types, namespace):
    return {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {
        "name": name, "namespace": namespace, "uid": namespace + "-" + name, "resourceVersion": "1"},
        "spec": {"podSelector": {"matchLabels": selector}, "policyTypes": types}}


class FakeBackend:
    """Independent transport model: routes depend on source labels and IP/port,
    never on the runner's requested expected outcome.
    """
    def __init__(self):
        self.objects = {}
        self.next_id = 1
        self.commands, self.deleted = [], []
        self.create_lost_kind = None
        self.bad_outcomes = {}
        self.before_connection = None
        for namespace in (APP, MODEL):
            self.put({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace,
                "labels": {"environment": "non-production", "kubernetes.io/metadata.name": namespace}}})
            self.put(policy("default-deny", {}, ["Ingress", "Egress"], namespace))
        self.put(policy("bounded", {"app.kubernetes.io/part-of": "cloudbank"}, ["Ingress", "Egress"], APP))
        self.put(policy("chatbot-model", {"app.kubernetes.io/name": "chatbot"}, ["Egress"], APP))
        self.put(policy("model-ingress", {"app.kubernetes.io/name": "ollama"}, ["Ingress"], MODEL))
        for index, service in enumerate([*SERVICES, "ollama"]):
            namespace = MODEL if service == "ollama" else APP
            image = PROFILE["model_image"] if service == "ollama" else IMAGES[service]
            labels = {"app.kubernetes.io/name": service, "pod-template-hash": "template-" + service}
            if namespace == APP:
                labels["app.kubernetes.io/part-of"] = "cloudbank"
            container = {"name": service, "image": image, "securityContext": {"allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}}}
            spec = {"containers": [container], "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}}}
            dep = self.put({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": service, "namespace": namespace},
                "spec": {"replicas": 2, "template": {"metadata": {"labels": labels}, "spec": spec}},
                "status": {"observedGeneration": 1, "readyReplicas": 2, "updatedReplicas": 2, "availableReplicas": 2}})
            rs = self.put({"apiVersion": "apps/v1", "kind": "ReplicaSet", "metadata": {"name": service, "namespace": namespace,
                "ownerReferences": [{"controller": True, "uid": dep["metadata"]["uid"]}]}, "spec": {}})
            for i in range(2):
                self.put({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": service + "-" + str(i), "namespace": namespace,
                    "labels": labels, "ownerReferences": [{"controller": True, "uid": rs["metadata"]["uid"]}]},
                    "spec": spec, "status": {"phase": "Running", "podIP": f"10.30.{index}.{i + 1}",
                    "containerStatuses": [{"name": service, "imageID": image, "ready": True, "state": {"running": {}},
                                           "user": {"linux": {"uid": 65532, "gid": 65532}}}]}})
            self.put({"apiVersion": "v1", "kind": "Service", "metadata": {"name": service, "namespace": namespace},
                      "spec": {"selector": {"app.kubernetes.io/name": service}, "publishNotReadyAddresses": False}})
        self.put({"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": "public", "namespace": APP},
            "spec": {"rules": [{"host": PROFILE["expected_hostname"]}]},
            "status": {"loadBalancer": {"ingress": [{"ip": "8.8.4.4"}]}}})

    def put(self, obj):
        obj = copy.deepcopy(obj)
        meta = obj["metadata"]
        meta.setdefault("uid", "uid-" + str(self.next_id))
        meta.setdefault("resourceVersion", "1")
        meta.setdefault("generation", 1)
        self.next_id += 1
        self.objects[(meta.get("namespace"), obj["kind"].lower(), meta["name"])] = obj
        return copy.deepcopy(obj)

    def get(self, namespace, kind, name=None):
        normal = {"networkpolicies": "networkpolicy"}.get(kind.lower(), kind.lower())
        if name is None:
            return {"items": [copy.deepcopy(v) for (ns, k, _), v in self.objects.items() if ns == namespace and k == normal]}
        return copy.deepcopy(self.objects.get((namespace, normal, name)))

    def create(self, obj):
        self.commands.append(("create", copy.deepcopy(obj)))
        if self.get(obj["metadata"].get("namespace"), obj["kind"], obj["metadata"]["name"]):
            raise JourneyFailure("test-create-conflict")
        if obj["kind"] == "Pod":
            obj = copy.deepcopy(obj)
            obj["status"] = {"phase": "Running", "podIP": "10.40.0." + str(self.next_id),
                "conditions": [{"type": "Ready", "status": "False"}],
                "containerStatuses": [{"name": "probe", "imageID": IMAGES["testrunner"], "state": {"running": {}}, "ready": True}]}
        value = self.put(obj)
        if obj["kind"] == self.create_lost_kind:
            self.create_lost_kind = None
            raise JourneyFailure("test-create-response-lost")
        return value

    def delete(self, obj):
        self.deleted.append(copy.deepcopy(obj))
        self.objects.pop((obj["metadata"].get("namespace"), obj["kind"].lower(), obj["metadata"]["name"]))

    def namespace_snapshot(self, namespace):
        return [copy.deepcopy(v) for (ns, _, _), v in self.objects.items() if ns == namespace]

    def sql_instance(self, name):
        return {"name": name, "region": "us-west1", "databaseVersion": "POSTGRES_16", "state": "RUNNABLE",
                "connectionName": "test-project:us-west1:" + name, "ipAddresses": [{"type": "PRIVATE", "ipAddress": "10.151.0.2"}]}

    def connections(self, namespace, pod_name, cases):
        if self.before_connection:
            self.before_connection(self)
            self.before_connection = None
        source = self.get(namespace, "Pod", pod_name)
        labels = source["metadata"]["labels"]
        role = labels[ROLE]
        service = labels.get("app.kubernetes.io/name")
        result = []
        for row in cases:
            ip, port = row["ip"], row["port"]
            target = next((obj for obj in self.objects.values() if obj["kind"] == "Pod" and obj["status"]["podIP"] == ip), None)
            if ip == "127.0.0.1":
                permitted = True
            else:
                target_ns = target["metadata"].get("namespace") if target else None
                target_labels = target["metadata"].get("labels", {}) if target else {}
                target_model = target_ns == MODEL and target_labels.get("app.kubernetes.io/name") == "ollama"
                egress = (role == "sink" or role == "wrong-service" and target_model and port == 11434
                    or namespace == APP and service in SERVICES and (
                        target_ns == APP and target_labels.get("app.kubernetes.io/part-of") == "cloudbank"
                        or ip == "10.151.0.2" and port == 5432 or service == "chatbot" and target_model and port == 11434))
                ingress = (target is None or target_labels.get(ROLE) == "sink"
                    or target_ns == APP and target_labels.get("app.kubernetes.io/part-of") == "cloudbank"
                       and namespace == APP and labels.get("app.kubernetes.io/part-of") == "cloudbank"
                    or target_model and namespace == APP and service == "chatbot" and port == 11434)
                permitted = bool(egress and ingress)
            outcome = ("nonce-matched" if row.get("nonce") else "connected") if permitted else "connect-timeout"
            outcome = self.bad_outcomes.get(row["id"], outcome)
            result.append({"id": row["id"], "outcome": outcome, "elapsed_ms": 3001 if outcome == "connect-timeout" else 2})
        return result


class MemoryJournal:
    def __init__(self):
        self.writes = []
        self.fail = None

    def write(self, state):
        if state["phase"] == self.fail:
            raise JourneyFailure("test-checkpoint-unavailable")
        self.writes.append(copy.deepcopy(state))


def engine():
    backend, journal = FakeBackend(), MemoryJournal()
    state = {"schema_version": "1.0", "state_type": STATE_TYPE, "run_id": RUN, "environment": ENV,
             "bindings": BINDINGS, "images": IMAGES, "source_instance": "cloudbank-test-postgres", "resources": [],
             "lease_uid": None, "cleanup_complete": False, "phase": "validating", "credentials_persisted": False,
             "production_environment": False, "recovery_uri": "gs://test-project-ms67-evidence/network-enforcement/" + RUN + "/state.json"}
    return NetworkRun(backend, journal, state, PROFILE, ARTIFACT), backend, journal


def cli_module():
    import sys
    tools = ROOT / "tools"
    sys.path.insert(0, str(tools))
    try:
        spec = importlib.util.spec_from_file_location("network_cli", tools / "cloudbank_network_enforcement.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(tools))


class SelectorAndRoutingTests(unittest.TestCase):
    def test_selector_expressions_and_union(self):
        self.assertTrue(selector_matches({"matchExpressions": [{"key": "a", "operator": "NotIn", "values": ["x"]}]}, {}))
        for op, labels, expected in [("In", {"a": "x"}, True), ("NotIn", {"a": "x"}, False),
                                     ("Exists", {}, False), ("DoesNotExist", {}, True)]:
            self.assertEqual(selector_matches({"matchExpressions": [{"key": "a", "operator": op, "values": ["x"]}]}, labels), expected)
        policies = [policy("deny", {}, ["Ingress", "Egress"], APP), policy("allow", {"a": "x"}, ["Egress"], APP)]
        self.assertEqual(len(selected(policies, {"a": "x"}, "Egress")), 2)
        self.assertEqual(len(selected(policies, {"a": "x"}, "Ingress")), 1)
        with self.assertRaisesRegex(JourneyFailure, "unsupported"):
            selector_matches({"matchExpressions": [{"key": "a", "operator": "Unsupported"}]}, {})

    def test_service_readiness_and_endpoint_guards(self):
        pod = {"metadata": {"uid": "probe", "labels": {"name": "account"}}}
        route_guard([pod], [{"spec": {"selector": {"name": "account"}}}], [])
        with self.assertRaisesRegex(JourneyFailure, "publishes-unready"):
            route_guard([pod], [{"spec": {"selector": {"name": "account"}, "publishNotReadyAddresses": True}}], [])
        for conditions in ({}, {"ready": True}, {"ready": False, "serving": True}):
            with self.assertRaisesRegex(JourneyFailure, "serving-endpoint"):
                route_guard([pod], [], [{"endpoints": [{"targetRef": {"uid": "probe"}, "conditions": conditions}]}])
        pod["status"] = {"conditions": [{"type": "Ready", "status": "True"}]}
        with self.assertRaisesRegex(JourneyFailure, "became-ready"):
            route_guard([pod], [], [])

    def test_probe_has_controller_owner_and_no_credentials_or_application_port(self):
        obj = pod_object(APP, "probe", {"app.kubernetes.io/name": "account"}, IMAGES["testrunner"],
                         {"metadata": {"uid": "config-uid", "name": "probe-config"}}, "1" * 32, RUN, "account")
        self.assertTrue(obj["metadata"]["ownerReferences"][0]["controller"])
        self.assertEqual(obj["spec"]["readinessGates"], [{"conditionType": GATE}])
        self.assertFalse(obj["spec"]["automountServiceAccountToken"])
        self.assertNotIn("envFrom", obj["spec"]["containers"][0])
        self.assertNotIn("8080", json.dumps(obj["spec"]))


class RunnerTests(unittest.TestCase):
    def test_full_matrix_signed_verification_and_cleanup(self):
        run, backend, journal = engine()
        original = copy.deepcopy(backend.objects)
        value = run.run()
        self.assertEqual(value["status"], PASS)
        self.assertEqual(len(value["cases"]), 65)
        self.assertEqual(len(value["checks"]), 130)
        verify_observation(sign(value, KEY, "operator"), KEY, BINDINGS, IMAGES, ENV, ARTIFACT)
        self.assertEqual(backend.objects, original)
        self.assertTrue(run.s["cleanup_complete"])
        self.assertGreater(len(journal.writes), 20)
        self.assertFalse(any(obj["kind"] in {"Deployment", "Secret", "Service"} for _, obj in backend.commands))

    def test_refused_and_read_timeout_cannot_count_as_denied(self):
        for outcome in ("connected", "connection-refused", "read-timeout", "transport-error"):
            run, backend, _ = engine()
            original = copy.deepcopy(backend.objects)
            backend.bad_outcomes["default-egress-denied"] = outcome
            with self.assertRaisesRegex(JourneyFailure, "connection-expectation-failed"):
                run.run()
            self.assertEqual(run.recover()["status"], "restored")
            self.assertEqual(original, backend.objects)

    def test_failed_positive_control_prevents_all_denial_evidence(self):
        run, backend, _ = engine()
        backend.bad_outcomes["control-database"] = "connection-refused"
        with self.assertRaisesRegex(JourneyFailure, "connection-expectation-failed"):
            run.run()
        self.assertTrue(all(row["phase"] == "positive-before" for row in run.s["checks"]))
        run.recover()

    def test_lost_create_reply_is_recovered_from_durable_intent(self):
        for kind in ("Namespace", "ServiceAccount", "ConfigMap", "NetworkPolicy", "Pod"):
            run, backend, journal = engine()
            original = copy.deepcopy(backend.objects)
            backend.create_lost_kind = kind
            with self.assertRaisesRegex(JourneyFailure, "create-response-lost"):
                run.run()
            durable = copy.deepcopy(journal.writes[-1])
            self.assertIsNone(durable["resources"][-1]["uid"])
            recovered = NetworkRun(backend, journal, durable, PROFILE, ARTIFACT)
            self.assertEqual(recovered.recover()["status"], "restored")
            self.assertEqual(backend.objects, original)

    def test_checkpoint_failure_prevents_next_create(self):
        run, backend, journal = engine()
        journal.fail = "before-create-namespace"
        with self.assertRaisesRegex(JourneyFailure, "checkpoint-unavailable"):
            run.run()
        self.assertEqual([o["kind"] for _, o in backend.commands], ["Lease"])
        journal.fail = None
        run.recover()

    def test_foreign_replacement_and_its_parents_are_preserved(self):
        run, backend, _ = engine()
        run.preflight()
        run.setup()
        record = next(r for r in run.s["resources"] if r["object"]["kind"] == "Pod")
        meta = record["object"]["metadata"]
        foreign = backend.objects[(meta["namespace"], "pod", meta["name"])]
        foreign["metadata"]["uid"] = "replacement-uid"
        result = run.recover()
        self.assertEqual(result["status"], "recovery-required")
        self.assertIsNotNone(backend.get(meta["namespace"], "Pod", meta["name"]))
        self.assertIsNotNone(backend.get(meta["namespace"], "ConfigMap", run.prefix))
        self.assertIsNotNone(backend.get(APP, "Lease", LEASE))

    def test_lost_final_checkpoint_after_lease_deletion_is_idempotent(self):
        run, backend, journal = engine()
        original = copy.deepcopy(backend.objects)
        journal.fail = "restored"
        with self.assertRaisesRegex(JourneyFailure, "checkpoint-unavailable"):
            run.run()
        self.assertEqual(backend.objects, original)
        durable = copy.deepcopy(journal.writes[-1])
        journal.fail = None
        other = NetworkRun(backend, journal, durable, PROFILE, ARTIFACT)
        self.assertEqual(other.recover()["status"], "restored")

    def test_existing_lock_prevents_mutation(self):
        run, backend, _ = engine()
        backend.put({"kind": "Lease", "metadata": {"name": LEASE, "namespace": APP}, "spec": {"holderIdentity": "another"}})
        with self.assertRaisesRegex(JourneyFailure, "lock-held"):
            run.run()
        self.assertEqual(backend.commands, [])

    def test_lost_lock_prevents_each_resource_create(self):
        for kind in ("Namespace", "ServiceAccount", "ConfigMap", "NetworkPolicy", "Pod"):
            with self.subTest(kind=kind):
                run, backend, journal = engine()
                run.acquire()
                backend.objects[(APP, "lease", LEASE)]["spec"]["holderIdentity"] = "another-run"
                commands, checkpoints = len(backend.commands), len(journal.writes)
                obj = mark({"apiVersion": "v1", "kind": kind, "metadata": {"name": "unused"}}, RUN)
                with self.assertRaisesRegex(JourneyFailure, "lock-ownership-mismatch"):
                    run.create(obj)
                self.assertEqual(len(backend.commands), commands)
                self.assertEqual(len(journal.writes), checkpoints)
                self.assertEqual(run.s["resources"], [])

    def test_service_routing_conflict_prevents_mutation(self):
        run, backend, _ = engine()
        backend.objects[(APP, "service", "account")]["spec"]["publishNotReadyAddresses"] = True
        with self.assertRaisesRegex(JourneyFailure, "publishes-unready"):
            run.run()
        self.assertEqual(backend.commands, [])

    def test_added_policy_and_deployment_drift_fail(self):
        for kind in ("policy", "deployment"):
            run, backend, _ = engine()
            run.preflight()
            run.setup()
            if kind == "policy":
                backend.put(policy("unexpected", {}, ["Egress"], APP))
            else:
                backend.objects[(APP, "deployment", "account")]["spec"]["template"]["spec"]["extra"] = True
            with self.assertRaisesRegex(JourneyFailure, "baseline-drift"):
                run.unchanged()
            run.recover()

    def test_new_policy_that_only_selects_probes_is_rejected(self):
        run, backend, _ = engine()
        run.preflight()
        run.setup()
        # Pretend the policy existed in the baseline but matches only probes.
        added = backend.put(policy("probe-only", {LABEL: RUN}, ["Egress"], APP))
        run.s["baseline"][APP]["policies"].append({"uid": added["metadata"]["uid"], "spec_sha256": hashed(added["spec"])})
        run.s["baseline"][APP]["policies"].sort(key=lambda row: row["uid"])
        with self.assertRaisesRegex(JourneyFailure, "policy-selection-drift"):
            run.unchanged()
        run.recover()

    def test_verifier_rejects_signed_missing_and_false_evidence(self):
        run, _, _ = engine()
        good = run.run()
        mutations = [lambda v: v["checks"].pop(), lambda v: v["cases"].pop(),
            lambda v: v["checks"][0].update(outcome="connection-refused"),
            lambda v: v.update(ms67_complete=True), lambda v: v["recovery"].update(status="recovery-required"),
            lambda v: v["final"][APP]["workloads"]["account"].update(spec_sha256="f" * 64),
            lambda v: v.update(probe_image="unapproved"), lambda v: v["checks"].__setitem__(0, v["checks"][1])]
        for mutate in mutations:
            value = copy.deepcopy(good)
            mutate(value)
            with self.assertRaises(JourneyFailure):
                verify_observation(sign(value, KEY, "operator"), KEY, BINDINGS, IMAGES, ENV, ARTIFACT)


@unittest.skipUnless(shutil.which("java"), "Java runtime needed for actual socket probe integration")
class JavaProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="network-java-test-")
        cls.work = Path(cls.directory.name)
        (cls.work / "NetworkProbe.class").write_bytes(base64.b64decode(ARTIFACT["class_base64"]))
        cls.base = ["java", "-Xmx24m", "-cp", str(cls.work), "NetworkProbe"]

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def invoke(self, payload):
        return subprocess.run([*self.base, "connect"], input=payload, capture_output=True, text=True, timeout=15)

    def test_real_connect_nonce_refused_and_read_timeout(self):
        from threading import Thread
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            nonce = "a" * 32
            def serve():
                for data in (nonce + "\n", "b" * 32 + "\n", None):
                    client, _ = listener.accept()
                    with client:
                        if data is None:
                            time.sleep(0.4)
                        else:
                            client.sendall(data.encode())
            thread = Thread(target=serve, daemon=True)
            thread.start()
            raw = self.invoke("".join(f"test-{i} 127.0.0.1 {port} 200 {nonce}\n" for i in range(3)))
            self.assertEqual(raw.returncode, 0, raw.stderr)
            self.assertEqual([r["outcome"] for r in map(json.loads, raw.stdout.splitlines())], ["nonce-matched", "nonce-mismatch", "read-timeout"])
            thread.join(timeout=2)
        raw = self.invoke(f"refused 127.0.0.1 {port} 200 -\n")
        self.assertEqual(json.loads(raw.stdout)["outcome"], "connection-refused")

    def test_no_dns_or_shell_input_and_bounded_ports(self):
        for payload in ("x localhost 5432 100 -\n", "x 999.2.3.4 5432 100 -\n", "x 127.0.0.1 0 100 -\n",
                        "x 127.0.0.1 5432 999999 -\n", "x 127.0.0.1 5432 100 private-secret\n", "x;exit 127.0.0.1 5432 100 -\n"):
            raw = self.invoke(payload)
            self.assertEqual(raw.returncode, 2)
            self.assertEqual(raw.stdout, "")
            self.assertNotIn("private-secret", raw.stderr)

    def test_real_listener_uses_run_nonce(self):
        proc = subprocess.Popen([*self.base, "serve", "a" * 32], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while True:
                self.assertIsNone(proc.poll(), "probe listener exited")
                try:
                    with socket.create_connection(("127.0.0.1", 19067), timeout=0.3) as client:
                        self.assertEqual(client.recv(100), ("a" * 32 + "\n").encode())
                    break
                except (ConnectionRefusedError, TimeoutError):
                    # Windows may time out instead of refusing the first SYN
                    # while the Java process is starting. This is a bounded
                    # listener startup wait, not a policy-denial observation.
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.1)
        finally:
            proc.terminate()
            proc.communicate(timeout=5)


class BackendGuards(unittest.TestCase):
    def test_full_matrix_through_real_backend_commands(self):
        # Mock only the subprocess boundary. The real Backend must create the
        # lease, serialize all resources and probes, and perform UID deletes.
        run, model, _ = engine()
        original = copy.deepcopy(model.objects)
        calls = []

        def invoke(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[0] == "gcloud":
                self.assertEqual(argv[1:4], ["sql", "instances", "describe"])
                self.assertEqual(argv[-3:], ["--project", ENV["project"], "--format=json"])
                return json.dumps(model.sql_instance(argv[4]))
            self.assertEqual(argv[:3], ["kubectl", "--context", "explicit-context"])
            self.assertRegex(argv[3], r"^--request-timeout=[0-9]+s$")
            args, namespace = argv[4:], None
            if args[0] == "--namespace":
                namespace, args = args[1], args[2:]
            if args[0] == "get":
                kind = args[1]
                if "," in kind:
                    return json.dumps({"items": model.namespace_snapshot(namespace)})
                name = args[2] if args[2] != "-o" else None
                value = model.get(namespace, kind, name)
                return json.dumps(value) if value is not None else ""
            if args[0] == "create":
                self.assertEqual(args, ["create", "-f", "-", "-o", "json"])
                obj = json.loads(kwargs["data"])
                self.assertEqual(namespace, obj["metadata"].get("namespace"))
                return json.dumps(model.create(obj))
            if args[0] == "exec":
                self.assertEqual(args[1], "-i")
                self.assertEqual(args[-1], "connect")
                cases = []
                for line in kwargs["data"].splitlines():
                    case_id, ip, port, timeout, nonce = line.split()
                    self.assertEqual(timeout, "3000")
                    cases.append({"id": case_id, "ip": ip, "port": int(port),
                                  **({"nonce": nonce} if nonce != "-" else {})})
                return "\n".join(json.dumps(row) for row in model.connections(namespace, args[2], cases))
            if args[0] == "delete":
                self.assertEqual(args[1], "--raw")
                options = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
                uid = options["preconditions"]["uid"]
                obj = next(o for o in model.objects.values() if o["metadata"]["uid"] == uid)
                self.assertTrue(args[2].endswith("/" + obj["metadata"]["name"]))
                model.delete(obj)
                return "{}"
            self.fail("Unexpected backend operation: " + args[0])

        with tempfile.TemporaryDirectory() as work:
            run.b = Backend(SimpleNamespace(context="explicit-context", project=ENV["project"], output=Path(work)))
            with patch("lightyear_data.cloudbank_network_enforcement.command", invoke):
                result = run.run()
        verify_observation(sign(result, KEY, "operator"), KEY, BINDINGS, IMAGES, ENV, ARTIFACT)
        self.assertEqual(len(result["checks"]), 130)
        self.assertEqual(model.objects, original)
        self.assertEqual(model.commands[0][1]["kind"], "Lease")
        self.assertEqual(sum(obj["kind"] == "Pod" for _, obj in model.commands), 12)
        self.assertTrue(any("exec" in argv for argv, _ in calls))

    def test_delete_uses_raw_uid_precondition_and_explicit_context(self):
        with tempfile.TemporaryDirectory() as work:
            class Runtime:
                context, output = "explicit-context", Path(work)
            calls = []
            def invoke(argv, **kwargs):
                calls.append((argv, json.loads(Path(argv[-1]).read_text())))
                return "{}"
            with patch("lightyear_data.cloudbank_network_enforcement.command", invoke):
                Backend(Runtime()).delete({"kind": "Pod", "metadata": {"namespace": APP, "name": "owned", "uid": "owned-uid", "resourceVersion": "22"}})
            argv, body = calls[0]
            self.assertIn("explicit-context", argv)
            self.assertIn("/api/v1/namespaces/" + APP + "/pods/owned", argv)
            self.assertEqual(body["preconditions"], {"uid": "owned-uid"})
            self.assertFalse((Path(work) / "network-delete-options.json").exists())

    def test_cli_help_and_recovery_state_scope(self):
        module = cli_module()
        run, _, _ = engine()
        run.preflight()
        run.setup()
        module.verified_state(sign(run.s, KEY, "operator"), KEY, BINDINGS, IMAGES, ENV, PROFILE)
        value = copy.deepcopy(run.s)
        value["resources"][0]["object"]["metadata"]["name"] = "unrelated-namespace"
        with self.assertRaisesRegex(JourneyFailure, "namespace-invalid"):
            module.verified_state(sign(value, KEY, "operator"), KEY, BINDINGS, IMAGES, ENV, PROFILE)

    def test_failure_preserves_original_phase_without_exception_payload(self):
        module = cli_module()
        for cleanup_failure in (False, True):
            with self.subTest(cleanup_failure=cleanup_failure):
                run, backend, journal = engine()
                original = copy.deepcopy(backend.objects)
                with patch.object(backend, "create", side_effect=AttributeError("private-payload-must-not-be-saved")):
                    try:
                        run.run()
                    except AttributeError as exc:
                        if cleanup_failure:
                            journal.fail = "restoring"
                        result = module.failure_result(exc, run, "run")
                    else:
                        self.fail("Expected setup failure")
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["reason"], "network-input-or-runtime-error")
                self.assertEqual(result["error_type"], "AttributeError")
                self.assertEqual(result["failed_phase"], "before-lock")
                self.assertEqual(result["phase"], "restoring" if cleanup_failure else "restored")
                self.assertEqual(result["recovery"]["status"], "recovery-required" if cleanup_failure else "restored")
                self.assertEqual(backend.objects, original)
                self.assertFalse(result["ms67_complete"])
                self.assertNotIn("private-payload", json.dumps(result))
                self.assertNotIn("traceback", json.dumps(result))

        arbitrary = type("private_exception_subclass_name", (Exception,), {})
        result = module.failure_result(arbitrary("private-value"), None, "run")
        self.assertEqual(result["error_type"], "Exception")
        self.assertEqual(result["failed_phase"], "before-run")
        self.assertNotIn("private", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
