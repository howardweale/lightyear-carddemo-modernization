"""Exercise final-closeout state transitions and evidence rejection without cloud writes."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ms67_finish as finish
import ms67_final_images as images_tool
import ms67_final_controls as controls
from lightyear_data import cloudbank_ms67_drills as drills
from lightyear_data.cloudbank_image_security import ImageJournal, CheckpointFailure
from lightyear_data.cloudbank_secret_rotation_gke import Journal
from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES, SCENARIOS, hashed, journey_contract
from lightyear_data.contracts import seal, sign
from test_cloudbank_runtime_identity import apply, deployment

KEY = "final-runner-unit-key-not-a-cloud-credential"
RUN = "ms67-final-" + "1" * 32
COMMIT = "a" * 40
ENV = {"project": finish.PROJECT, "region": finish.REGION, "cluster": finish.CLUSTER,
       "namespace": finish.NAMESPACE, "namespace_uid_sha256": "c" * 64}
IMAGES = {s: images_tool.REGISTRY + "/" + s + "@sha256:" + f"{i:064x}" for i, s in enumerate(SERVICES, 1)}
CANDIDATES = {s: images_tool.REGISTRY + "/" + s + "@sha256:" + f"{i:064x}" for i, s in enumerate(SERVICES, 101)}
BINDINGS = {k: "b" * 64 for k in ("ms64_receipt_sha256", "image_lock_sha256", "platform_profile_sha256")}


class Cloud:
    def __init__(self):
        self.objects, self.events = {}, []
        self.fail_reads = False

    def __call__(self, argv, **kwargs):
        args = argv[argv.index("storage")+1:]
        if args[0] == "cp":
            path, uri = args[1:3]
            version = self.objects.get(uri, ("0", ""))[0]
            expected = next((a.split("=", 1)[1] for a in args if a.startswith("--if-generation-match=")), version)
            if version != expected:
                raise JourneyFailure("test-generation-conflict")
            self.objects[uri] = str(int(version) + 1), Path(path).read_text()
            self.events.append("upload")
            return ""
        uri = args[2] if args[0] == "objects" else args[1]
        uri, _, generation = uri.partition("#")
        if uri not in self.objects:
            raise JourneyFailure("test-object-not-found")
        version, raw = self.objects[uri]
        if args[0] == "objects":
            return version
        if self.fail_reads:
            raise JourneyFailure("test-readback-unavailable")
        if generation and generation != version:
            raise JourneyFailure("test-generation-mismatch")
        self.events.append("readback")
        return raw


class Runtime:
    project, region, cluster, namespace, run_id = finish.PROJECT, finish.REGION, finish.CLUSTER, finish.NAMESPACE, RUN
    context, probe_image, probe_name = "unit-context", "registry.test/postgres@sha256:" + "f"*64, "unit-probe"

    def __init__(self, output, cloud):
        self.output, self.cloud, self.images = output, cloud, IMAGES.copy()
        self.original, self.resources, self.actions, self.generations = {}, {}, [], {}
        self.progress = lambda _: None
        self.forwards = {}
        for s in SERVICES:
            d = deployment(s)
            d["metadata"].update(namespace=self.namespace, generation=1)
            d["spec"]["template"]["metadata"] = {"labels": {"app.kubernetes.io/name": s}}
            d["spec"]["selector"] = {"matchLabels": {"app.kubernetes.io/name": s}}
            d["spec"]["template"]["spec"]["containers"][0]["image"] = IMAGES[s]
            d["status"] = {"availableReplicas": 2, "readyReplicas": 2, "updatedReplicas": 2, "observedGeneration": 1}
            self.resources["deployment", s] = d
            self.resources["service", s] = {"metadata": {"name": s, "uid": "svc-"+s, "resourceVersion": "1"},
                                             "spec": {"selector": {"app.kubernetes.io/name": s}}}
            self.generations[s] = 1
        for n in range(3):
            self.resources["node", "node-"+str(n)] = {"metadata": {"name": "node-"+str(n), "uid": "node-uid-"+str(n),
                "resourceVersion": "1", "labels": {"topology.kubernetes.io/zone": "us-west1-"+"abc"[n]}},
                "spec": {}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        self.evacuated = set()

    def environment(self):
        return ENV.copy()

    def deployment(self, service):
        value = self.get("deployment", service)
        self.original.setdefault(service, {"uid": value["metadata"]["uid"], "replicas": 2})
        return value

    def all_pods(self, name):
        d = self.resources["deployment", name]
        main = d["spec"]["template"]["spec"]["containers"][0]
        available = [n for (kind, n) in self.resources if kind == "node" and n not in self.evacuated]
        return [{"metadata": {"name": name+"-pod-"+str(i), "uid": f"{name}-{self.generations[name]}-{i}",
                    "labels": {**d["spec"]["template"]["metadata"]["labels"], "pod-template-hash": "hash-"+name+str(self.generations[name])},
                    "ownerReferences": [{"uid": "rs-"+name, "controller": True}]},
                 "spec": {"nodeName": available[i % len(available)]},
                 "status": {"containerStatuses": [{"name": main["name"], "ready": True, "imageID": main["image"]}]}}
                for i in range(d["spec"].get("replicas", 2))]

    def pods(self, service):
        return self.all_pods(service)

    def get(self, kind, name=None, selector=None):
        if kind == "endpoints":
            selected = self.resources["service", name]["spec"]["selector"]
            pods = [p for (k, n) in self.resources if k == "deployment" for p in self.all_pods(n)
                    if all(p["metadata"]["labels"].get(key) == val for key, val in selected.items())]
            return {"subsets": [{"addresses": [{"targetRef": {"uid": p["metadata"]["uid"]}} for p in pods]}]}
        if kind == "replicasets":
            return {"items": [{"metadata": {"uid": "rs-"+n, "ownerReferences": [{"uid": d["metadata"]["uid"], "controller": True}]}}
                              for (k, n), d in self.resources.items() if k == "deployment"]}
        if kind == "pods":
            return {"items": [p for (k, n) in self.resources if k == "deployment" for p in self.all_pods(n)]}
        singular = {"nodes": "node", "deployments": "deployment"}.get(kind)
        if singular:
            return {"items": [copy.deepcopy(d) for (k, _), d in self.resources.items() if k == singular]}
        return copy.deepcopy(self.resources[kind, name])

    def ready(self):
        for s in SERVICES:
            self.deployment(s)

    def wait_ready(self, service):
        self.deployment(service)

    def close_forward(self, service):
        pass

    def close(self):
        return {"status": "restored", "errors": [], "remaining_stopped_services": []}

    def kubectl(self, *args, data=None, **kwargs):
        if args[0] == "auth":
            return "yes"
        if args[0] == "get":
            kind, name = args[1].split("/", 1)
            value = self.resources.get((kind, name))
            return json.dumps(value) if value else ""
        if args[0] == "rollout":
            return "success"
        self.actions.append(args)
        if args[0] in {"patch", "create", "delete", "drain"}:
            if self.cloud.events[-1:] != ["readback"]:
                raise AssertionError("Mutation without durable readback")
        if args[0] == "create":
            value = json.loads(data)
            name, kind = value["metadata"]["name"], value["kind"].lower()
            if (kind, name) in self.resources:
                raise JourneyFailure("test-already-exists")
            value["metadata"].update(uid="created-"+name, resourceVersion="1")
            self.resources[kind, name] = value
            if kind == "deployment":
                self.generations[name] = 1
            return json.dumps(value)
        if args[0] == "patch":
            kind, name = args[1].split("/", 1)
            before = self.resources[kind, name]
            self.resources[kind, name] = apply(before, json.loads(args[-1]))
            if kind == "deployment" and before["spec"]["template"] != self.resources[kind, name]["spec"]["template"]:
                self.generations[name] += 1
        elif args[0] == "delete":
            kind, name = args[1].split("/", 1)
            self.resources.pop((kind, name))
        elif args[0] == "drain":
            self.evacuated.add(args[1])
            for s in SERVICES:
                self.generations[s] += 1
        return ""


def engine(directory):
    cloud = Cloud()
    runtime = Runtime(Path(directory), cloud)
    obj = drills.FinalDrills(runtime, CANDIDATES, {**BINDINGS, "candidate_image_lock_sha256": "d"*64}, KEY,
        "unit-operator", finish.BUCKET + "/final-drills/" + RUN, cloud=cloud, pause=lambda _: None)
    return obj, runtime, cloud


def target_journeys(bindings, run_id=RUN):
    rows = [{"id": identifier, "normalized_result": result, "status": "passed", "evidence": {"observed": identifier},
             "evidence_sha256": hashed({"observed": identifier})} for identifier, result in SCENARIOS]
    return sign({"observation_type": "lightyear-cloudbank-shared-journey-execution", "run_id": run_id,
        "bindings": {**bindings, "journey_contract_sha256": journey_contract()["content_sha256"]},
        "status": "passed-shared-journeys", "scenario_count": 18, "scenarios": rows,
        "recovery": {"status": "restored", "errors": [], "remaining_stopped_services": []},
        "synthetic_data_only": True, "raw_output_persisted": False, "credentials_persisted": False,
        "production_environment": False, "whole_application_equivalent": False,
        "ms65_complete": False, "ms66_complete": False, "ms67_complete": False}, KEY, "unit-operator")


class FinalDrillTests(unittest.TestCase):
    def test_full_drill_evidence_and_resigned_false_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, runtime, _ = engine(directory)
            fake = SimpleNamespace(environment=lambda: ENV, create_probe=lambda: None,
                direct_candidate_health=lambda s, p: {"http_status": 200, "pod_uid_sha256": hashed(p["metadata"]["uid"])})
            snapshot = {"state_sha256": "e"*64, "table_count": 8, "row_count": 100, "sequence_count": 3}
            with patch.object(drills, "CandidateRuntime", return_value=fake), patch.object(obj, "stable_snapshot", return_value=snapshot), \
                 patch.object(drills, "execute_journeys", side_effect=lambda r, b, *a, **kw: target_journeys(b, kw["run_id"])):
                result = obj.run()
            verify = lambda v: drills.verify_observation(v, KEY, obj.bindings, IMAGES, CANDIDATES, ENV)
            verify(result)
            drains = [a for a in runtime.actions if a[0] == "drain"]
            self.assertEqual(len(drains), 2)
            self.assertTrue(all("--force" not in a and "--disable-eviction" not in a for a in drains))
            mutations = [lambda v: v["completed"]["resilience"].pop("failure-domain"),
                lambda v: v["completed"]["resilience"]["node"].update(post_state={**snapshot, "row_count": 101}),
                lambda v: v["completed"]["rolling"]["rows"][0].update(maximum_unavailable=1),
                lambda v: v["completed"]["cutover"]["routes"]["target"].pop("chatbot"),
                lambda v: v["completed"]["cutover"].update(post_rollback_state_sha256="f"*64),
                lambda v: v["target_journeys"]["scenarios"][0].update(status="failed"),
                lambda v: v["recovery"].update(status="failed")]
            for mutate in mutations:
                changed = copy.deepcopy(result); mutate(changed)
                with self.assertRaises(JourneyFailure):
                    verify(sign(changed, KEY, "unit-operator"))

    def test_recovery_does_not_patch_replaced_service_even_with_expected_selector(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, runtime, _ = engine(directory)
            obj.preflight(); obj.claim()
            original = obj.s["baseline"]["account"]
            runtime.resources["service", "account"]["spec"]["selector"] = {
                **original["selector"], "pod-template-hash": original["baseline_pod_hash"]}
            runtime.resources["service", "account"]["metadata"]["uid"] = "foreign"
            result = obj.cleanup()
            self.assertEqual(result["status"], "failed")
            self.assertFalse(any(a[:2] == ("patch", "service/account") for a in runtime.actions))

    def test_all_eight_rollouts_and_return_restore_exact_specs(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, runtime, cloud = engine(directory)
            before = copy.deepcopy({s: runtime.get("deployment", s)["spec"] for s in SERVICES})
            obj.preflight(); obj.claim(); obj.rolling()
            self.assertEqual(len(obj.s["completed"]["rolling"]["rows"]), 8)
            self.assertEqual(before, {s: runtime.get("deployment", s)["spec"] for s in SERVICES})
            self.assertEqual(len([a for a in runtime.actions if a[0] == "patch"]), 16)
            self.assertEqual(obj.cleanup()["status"], "restored")
            self.assertNotIn(("lease", drills.LEASE), runtime.resources)

    def test_checkpoint_failure_blocks_first_live_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, runtime, cloud = engine(directory)
            obj.preflight()
            cloud.fail_reads = True
            with self.assertRaises(CheckpointFailure):
                obj.claim()
            self.assertEqual(runtime.actions, [])

    def test_foreign_spec_and_service_uid_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, runtime, _ = engine(directory)
            obj.preflight(); obj.claim()
            runtime.resources["deployment", "account"]["spec"]["replicas"] = 3
            with self.assertRaisesRegex(JourneyFailure, "changed-by-another"):
                obj.set_image("account", CANDIDATES["account"])
            runtime.resources["service", "account"]["metadata"]["uid"] = "foreign"
            with self.assertRaisesRegex(JourneyFailure, "another-operator"):
                obj.route("account", {drills.LABEL: RUN, "app.kubernetes.io/name": "account"})
            self.assertEqual([a[0] for a in runtime.actions], ["create"])

    def test_availability_fails_on_a_single_bad_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, runtime, _ = engine(directory)
            obj.preflight()
            monitor = drills.Availability(runtime, 2)
            monitor.sample()
            runtime.resources["deployment", "checks"]["status"]["availableReplicas"] = 1
            with self.assertRaisesRegex(JourneyFailure, "availability-below"):
                monitor.sample()

    def test_incomplete_lease_creation_and_release_can_be_recovered(self):
        for phase in ("claim-lease", "release-lease"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                obj, runtime, _ = engine(directory)
                obj.preflight(); obj.intent(phase, {})
                self.assertEqual(obj.cleanup()["status"], "restored")
                self.assertFalse(obj.s["cleanup_required"])
                self.assertEqual(runtime.actions, [])

    def test_canary_routes_only_to_known_candidate_then_restores_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, runtime, _ = engine(directory)
            obj.preflight(); obj.claim()
            fake = SimpleNamespace(environment=lambda: ENV, create_probe=lambda: None,
                direct_candidate_health=lambda s, p: {"http_status": 200, "pod_uid_sha256": hashed(p["metadata"]["uid"])})
            snapshot = {"state_sha256": "e"*64, "table_count": 8, "row_count": 100, "sequence_count": 3}
            with patch.object(drills, "CandidateRuntime", return_value=fake), patch.object(obj, "stable_snapshot", return_value=snapshot), \
                 patch.object(drills, "execute_journeys", side_effect=lambda r, b, *a, **kw: target_journeys(b, kw["run_id"])):
                obj.cutover()
            self.assertEqual(obj.s["completed"]["cutover"]["states"], drills.CUTOVER_STATES)
            for s in SERVICES:
                self.assertEqual(runtime.get("service", s)["spec"]["selector"], {"app.kubernetes.io/name": s})
                self.assertNotIn(("deployment", drills.candidate_name(s, RUN)), runtime.resources)
            self.assertEqual(obj.s["completed"]["cutover"]["pre_state_sha256"], "e"*64)
            self.assertEqual(obj.cleanup()["status"], "restored")

    def test_failed_target_journeys_never_produce_cutover_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, runtime, _ = engine(directory)
            obj.preflight(); obj.claim()
            fake = SimpleNamespace(environment=lambda: ENV, create_probe=lambda: None,
                direct_candidate_health=lambda s, p: {"http_status": 200, "pod_uid_sha256": hashed(p["metadata"]["uid"])})
            with patch.object(drills, "CandidateRuntime", return_value=fake), \
                 patch.object(drills, "execute_journeys", return_value={"status": "failed"}):
                with self.assertRaisesRegex(JourneyFailure, "business-journeys-failed"):
                    obj.cutover()
            self.assertNotIn("cutover", obj.s["completed"])
            self.assertEqual(obj.cleanup()["status"], "restored")

    def test_node_plan_keeps_two_workers_and_refuses_bad_existing_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            _, runtime, _ = engine(directory)
            nodes = runtime.get("nodes")["items"]
            plan = drills.node_plan(nodes)
            self.assertNotEqual(plan["node"][0]["zone"], plan["failure-domain"][0]["zone"])
            nodes[0]["spec"]["unschedulable"] = True
            with self.assertRaisesRegex(JourneyFailure, "preexisting-cordoned"):
                drills.node_plan(nodes)


class EvidenceTests(unittest.TestCase):
    def test_failed_child_summary_cannot_replace_its_recovery_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            cloud = Cloud()
            with patch.object(finish, "invoke", cloud):
                session = finish.Session(Path(directory), {}, KEY, COMMIT)
                session.state["active"] = {"phase": "secret-rotation"}
                uri = finish.BUCKET + "/secret-rotation/unit/recovery-state.json"
                session.checkpoint(sign({"state_type": "secret-recovery", "phase": "before-add"}, KEY, "unit"), uri)
                reference = session.state["active"]["recovery"].copy()
                session.checkpoint(sign({"status": "failed", "recovery": {"status": "recovery-required"}}, KEY, "unit"),
                                   finish.BUCKET + "/secret-rotation/unit/secret-rotation.observation.json")
                self.assertEqual(session.state["active"]["recovery"], reference)
                self.assertIn("result", session.state["active"])

    @unittest.skipUnless(os.environ.get("LIGHTYEAR_MS67_TRIVY_TEST") == "1", "real Trivy contract check runs in CI")
    def test_real_trivy_report_and_privileged_container_rejection(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            images_tool.install_tools(Path(directory))
            manifests = {}
            for s in SERVICES:
                d = deployment(s)
                main = d["spec"]["template"]["spec"]["containers"][0]
                main["securityContext"].update(runAsUser=65532, runAsGroup=65532)
                main["resources"] = {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "1", "memory": "1Gi"}}
                main["livenessProbe"] = {"httpGet": {"path": "/actuator/health/liveness", "port": 8080}}
                main["readinessProbe"] = {"httpGet": {"path": "/actuator/health/readiness", "port": 8080}}
                d["spec"]["selector"] = {"matchLabels": {"app": s}}
                d["spec"]["template"]["metadata"] = {"labels": {"app": s}}
                manifests[s] = d
            result = controls.manifest_scan(manifests)
            self.assertEqual((result["high"], result["critical"]), (0, 0))
            manifests["account"]["spec"]["template"]["spec"]["containers"][0]["securityContext"]["privileged"] = True
            with self.assertRaisesRegex(JourneyFailure, "high-or-critical"):
                controls.manifest_scan(manifests)

    def test_parent_observer_runs_after_readback_and_failure_propagates(self):
        for journal_type in (Journal, ImageJournal):
            with self.subTest(journal=journal_type), tempfile.TemporaryDirectory() as directory:
                cloud = Cloud()
                journal = journal_type(Path(directory)/"state.json", finish.BUCKET+"/unit/state.json", finish.PROJECT,
                                       KEY, "unit", invoke=cloud)
                def callback(value, uri):
                    self.assertEqual(cloud.events[-1], "readback")
                    raise JourneyFailure("parent-checkpoint-unavailable")
                with finish.observer(callback), self.assertRaisesRegex(JourneyFailure, "parent-checkpoint-unavailable"):
                    journal.write({"phase": "before-mutation"})
                self.assertIsNone(finish.checkpoint_module._checkpoint_observer)

    def test_session_resumes_cloud_checkpoint_and_preserves_original_signer(self):
        with tempfile.TemporaryDirectory() as directory:
            cloud = Cloud()
            with patch.object(finish, "invoke", cloud), patch.object(finish, "cloud", side_effect=lambda *a, **kw: cloud(["gcloud", *a], **kw)):
                session = finish.Session(Path(directory), {"retained": "original"}, KEY, COMMIT)
                value = sign({"status": "passed", "measurement": 622}, KEY, "original-cloud-build-signer")
                ref = session.publish("original.json", value)
                self.assertEqual(session.read(ref), value)
                lock = seal({"lock_type": "unit-lock", "images": []})
                retained = session.retain("lock.json", lock)
                self.assertEqual(json.loads(cloud.objects[retained["uri"]][1]), lock)
                session.finish_phase("sql", ref)
                reloaded = finish.Session(Path(directory), {"retained": "original"}, KEY, COMMIT)
                self.assertEqual(reloaded.state["completed"]["sql"], ref)
                with self.assertRaisesRegex(JourneyFailure, "inputs-changed"):
                    finish.Session(Path(directory), {"retained": "other"}, KEY, COMMIT)

    def test_lost_submission_is_adopted_and_unknown_submission_never_duplicates(self):
        identifier = "a4997e85-7244-4cf3-bed3-6756d34391ce"
        self.assertEqual(finish.choose_build({"phase": "submitting"}, [{"id": identifier}]), identifier)
        with self.assertRaisesRegex(JourneyFailure, "no-duplicate"):
            finish.choose_build({"phase": "submitting"}, [])

    def test_oci_revision_rejects_any_filesystem_or_runtime_change(self):
        base = {"RootFS": {"Layers": ["layer1", "layer2"]}, "Os": "linux", "Architecture": "amd64", "Id": "sha256:"+"1"*64,
                "Config": {"Env": ["MODE=synthetic"], "User": "65532", "Labels": {"old": "kept"}}, "RepoDigests": [IMAGES["account"]]}
        candidate = copy.deepcopy(base)
        candidate["Id"], candidate["RepoDigests"] = "sha256:"+"2"*64, [CANDIDATES["account"]]
        candidate["Config"]["Labels"][images_tool.REVISION_LABEL] = RUN
        proof = images_tool.packaging_proof("account", base, candidate, RUN)
        self.assertEqual(proof["baseline_image"], IMAGES["account"])
        for mutation in (lambda c: c["RootFS"]["Layers"].append("changed"), lambda c: c["Config"].update(User="0"),
                         lambda c: c["Config"]["Env"].append("BAD=1"), lambda c: c.update(Architecture="arm64")):
            changed = copy.deepcopy(candidate); mutation(changed)
            with self.assertRaises(JourneyFailure):
                images_tool.packaging_proof("account", base, changed, RUN)

    def test_metrics_reject_other_cluster_and_samples_before_pod_creation(self):
        expected = {"account-abc": {"service": "account", "created_at": "2026-09-10T12:01:00Z", "pod_uid_sha256": "a"*64}}
        series = {"metric": {"type": "kubernetes.io/container/cpu/core_usage_time"},
                  "resource": {"type": "k8s_container", "labels": {"project_id": finish.PROJECT, "cluster_name": finish.CLUSTER,
                    "namespace_name": finish.NAMESPACE, "container_name": "account", "pod_name": "account-abc"}},
                  "points": [{"interval": {"endTime": "2026-09-10T12:02:00Z"}, "value": {"doubleValue": 1.0}}]}
        def read(row):
            return controls.metric_rows({"timeSeries": [row]}, expected, finish.PROJECT, finish.CLUSTER, finish.NAMESPACE,
                datetime(2026, 9, 10, 12, tzinfo=timezone.utc), datetime(2026, 9, 10, 12, 3, tzinfo=timezone.utc))
        self.assertEqual(len(read(series)), 1)
        stale = copy.deepcopy(series); stale["points"][0]["interval"]["endTime"] = "2026-09-10T12:00:30Z"
        self.assertEqual(read(stale), {})
        wrong = copy.deepcopy(series); wrong["resource"]["labels"]["cluster_name"] = "old-cluster"
        with self.assertRaisesRegex(JourneyFailure, "resource-mismatch"):
            read(wrong)

    def test_candidate_worker_config_is_pinned_and_never_grants_iam(self):
        previous = {"serviceAccount": "projects/"+finish.PROJECT+"/serviceAccounts/cloudbank-ms67-evidence@"+finish.PROJECT+".iam.gserviceaccount.com",
            "steps": [{"id": name, "name": "gcr.io/test/"+name} for name in
                      ("checkout-fix", "sign-verify-and-scan-images", "build-and-push-eight-images")],
            "results": {"buildStepImages": ["sha256:"+"a"*64]*3}}
        config = finish.candidate_config({"run_id": RUN, "controller_commit": COMMIT}, previous, finish.BUCKET+"/final-closeout/"+RUN)
        live = {**config, "projectId": finish.PROJECT, "id": "unit-build"}
        finish.verify_build(live, config)
        altered = copy.deepcopy(live); altered["steps"][-1]["args"].append("--skip-verification")
        with self.assertRaisesRegex(JourneyFailure, "worker-mismatch"):
            finish.verify_build(altered, config)
        self.assertNotIn("add-iam-policy-binding", json.dumps(config))


if __name__ == "__main__":
    unittest.main()
