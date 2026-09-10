"""Retain passed drill evidence and diagnose database drift without weakening it."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

from test_ms67_finish import (Cloud, KEY, COMMIT, RUN, ENV, IMAGES, CANDIDATES, BINDINGS,
                             SERVICES, engine, finish, drills, images_tool)
from test_cloudbank_image_security import fixture as image_fixture
from lightyear_data.cloudbank_journeys import JourneyFailure, hashed
from lightyear_data.cloudbank_sql_recovery import normalize_snapshot, SNAPSHOT_SQL
from lightyear_data.contracts import sign, seal


def snapshot(row_hash="a"*64, sequence_hash="b"*64):
    raw = "\n".join(json.dumps(r) for r in [{"unsupported": 0},
        {"relation": "public.accounts", "rows": 2, "sha256": row_hash},
        {"sequence": "public.accounts_id_seq", "sha256": sequence_hash}, {"schema_sha256": "c"*64}])
    return drills.detailed_snapshot(raw)


def failed_domain(obj):
    before, after = snapshot(), snapshot(sequence_hash="d"*64)
    # Real state-machine transitions, with only the cloud/database IO simulated.
    with patch.object(obj, "stable_snapshot", side_effect=[before, before, before, after]):
        result = obj.run()
    if result["reason"] != "evacuation-normalized-database-state-changed":
        raise AssertionError(result)
    return result


def candidate_security(run_id):
    shared = image_fixture()
    rows = []
    for service, inherited in zip(SERVICES, shared["services"], strict=True):
        proof = {"baseline_image": IMAGES[service], "candidate_image": CANDIDATES[service],
                 "revision_label": images_tool.REVISION_LABEL, "revision_value": run_id,
                 "rootfs_sha256": "a"*64, "runtime_configuration_sha256": "b"*64,
                 "baseline_config_digest": "sha256:"+"c"*64, "candidate_config_digest": "sha256:"+"d"*64}
        rows.append({"service": service, "packaging": proof, "scan": inherited["scan"],
                     "signature": inherited["signature"], "baseline_signature": inherited["signature"],
                     "provenance": {**inherited["provenance"], "source_commit": finish.DRILL_CONTINUATION_SOURCE},
                     "baseline_provenance": {**inherited["provenance"], "source_commit": images_tool.BASE_SOURCE}})
    lock = seal({"schema_version": "1.0", "lock_type": "lightyear-cloudbank-ms65-image-lock", "release": "0.65.0",
                 "source_ms64_receipt_sha256": BINDINGS["ms64_receipt_sha256"],
                 "images": [{"service": s, "reference": CANDIDATES[s]} for s in SERVICES]})
    return sign({"observation_type": "lightyear-ms67-final-candidate-security", "status": "passed",
                 "credentials_persisted": False, "run_id": run_id, "controller_commit": finish.DRILL_CONTINUATION_SOURCE,
                 "cloud_build_id": "candidate-build", "bindings": BINDINGS, "candidate_lock": lock,
                 "services": rows, "tools": shared["tools"]}, KEY, "original-builder")


class DrillContinuationTests(unittest.TestCase):
    def test_resume_cannot_start_a_new_session(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(finish, "cloud") as cloud:
            with self.assertRaisesRegex(JourneyFailure, "requires-existing-final-session"):
                finish.Session(Path(folder), {}, KEY, COMMIT, resume_drills=True)
            cloud.assert_not_called()

    def test_difference_reports_changed_object_without_altering_shared_hash(self):
        before, after = snapshot(), snapshot(sequence_hash="d"*64)
        raw = "\n".join(json.dumps(r) for r in [{"unsupported": 0}, *before["objects"]])
        self.assertEqual({k:v for k,v in before.items() if k != "objects"}, normalize_snapshot(raw))
        diff = drills.snapshot_difference(before, after)
        self.assertFalse(diff["state_matches"])
        self.assertEqual([r["name"] for r in diff["changed_objects"]], ["public.accounts_id_seq"])
        self.assertTrue(diff["detail_available"])

    def test_failed_comparison_is_durable_and_resume_skips_passed_node(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, cloud = engine(folder)
            result = failed_domain(obj)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["recovery"], {"status": "restored", "errors": []})
            original_node = copy.deepcopy(obj.s["completed"]["resilience"]["node"])
            reference = obj.journal.uri
            saved = json.loads(cloud.objects[reference][1])
            diff = saved["evacuation_comparisons"][-1]["difference"]
            self.assertFalse(diff["state_matches"])
            self.assertEqual(diff["changed_objects"][0]["name"], "public.accounts_id_seq")
            drills.verify_continuation(saved, KEY, obj.bindings, IMAGES, CANDIDATES, ENV)
            # Model replacement pods on A/C after B was drained: uncordoning B
            # leaves it unoccupied, while restored A can accept new pods.
            runtime.evacuated = {"node-1"}
            runtime.actions.clear()
            resumed = drills.FinalDrills(runtime, CANDIDATES, obj.bindings, KEY, "unit-operator", obj.prefix,
                                         state=saved, cloud=cloud, pause=lambda _: None)
            with patch.object(resumed, "stable_snapshot", return_value=snapshot()):
                resumed.preflight(); resumed.claim(); resumed.resilience()
            self.assertEqual(resumed.s["completed"]["resilience"]["node"], original_node)
            self.assertEqual(len([a for a in runtime.actions if a[0] == "drain"]), 1)
            self.assertEqual(set(resumed.s["completed"]["resilience"]), {"node", "failure-domain"})
            self.assertEqual(resumed.cleanup()["status"], "restored")

    def test_re_signed_incomplete_or_false_retained_prefix_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, _, cloud = engine(folder)
            failed_domain(obj)
            saved = json.loads(cloud.objects[obj.journal.uri][1])
            changes = [lambda s: s.update(cleanup_required=True), lambda s: s.update(failure="other-error"),
                       lambda s: s["completed"]["rolling"]["rows"][0].update(maximum_unavailable=1),
                       lambda s: s["completed"]["resilience"]["node"].update(post_state=snapshot("e"*64)),
                       lambda s: s["completed"]["resilience"]["node"].update(nodes_sha256="0"*64)]
            for change in changes:
                value = copy.deepcopy(saved); change(value)
                with self.assertRaises(JourneyFailure):
                    drills.verify_continuation(sign(value, KEY, "unit"), KEY, obj.bindings, IMAGES, CANDIDATES, ENV)

    def test_resume_preflight_rejects_service_or_deployment_drift(self):
        for kind, field in (("service", "uid"), ("deployment", "uid"), ("deployment", "spec")):
            with self.subTest(kind=kind, field=field), tempfile.TemporaryDirectory() as folder:
                obj, runtime, _ = engine(folder)
                obj.preflight()
                if field == "uid": runtime.resources[kind, "account"]["metadata"]["uid"] = "foreign"
                else: runtime.resources[kind, "account"]["spec"]["revisionHistoryLimit"] = 99
                with self.assertRaisesRegex(JourneyFailure, "baseline-identity-or-spec-drift"):
                    obj.preflight()

    def test_remaining_plan_avoids_empty_domain_and_retains_original_node_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            _, runtime, _ = engine(folder)
            nodes = runtime.get("nodes")["items"]
            saved = drills.node_plan(nodes)
            plan = drills.remaining_node_plan(nodes, saved, {"node": {}}, {"node-2"})
            self.assertEqual(plan["node"], saved["node"])
            self.assertEqual(plan["failure-domain"][0]["name"], "node-2")
            with self.assertRaisesRegex(JourneyFailure, "occupied-failure-domain"):
                drills.remaining_node_plan(nodes, saved, {"node": {}}, {"node-0"})

    def test_controller_transition_preserves_source_and_checks_resume_after_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obj, _, cloud = engine(folder)
            failed_domain(obj)
            drill_state = json.loads(cloud.objects[obj.journal.uri][1])
            context = {"images": IMAGES, "bindings": BINDINGS, "environment": ENV}
            with patch.object(finish, "invoke", cloud), patch.object(finish, "cloud", side_effect=lambda *a, **kw: cloud(["gcloud", *a], **kw)), \
                 patch.object(finish, "verify_child", side_effect=lambda phase, value, *a: value):
                session = finish.Session(root, context, KEY, finish.DRILL_CONTINUATION_SOURCE)
                security = candidate_security(session.state["run_id"])
                # Bind the existing drill checkpoint to this parent and candidate lock.
                drill_state["run_id"] = session.state["run_id"]
                drill_state["bindings"]["candidate_image_lock_sha256"] = security["candidate_lock"]["content_sha256"]
                session.state["candidate_build"] = {"phase": "submitted", "build_id": "candidate-build"}
                session.state["completed"]["candidates"] = session.publish("candidate-security.json", security)
                for phase in finish.CHILDREN:
                    session.state["completed"][phase] = session.publish(phase+".json", {"status": "passed", "phase": phase})
                ref = session.publish("restored-drill.json", sign(drill_state, KEY, "unit-operator"))
                session.state["active"] = {"phase": "drills", "recovery": ref}
                session.save()
                old = copy.deepcopy(session.state)
                with self.assertRaisesRegex(JourneyFailure, "inputs-changed"):
                    finish.Session(root, context, KEY, COMMIT)
                before = copy.deepcopy(cloud.objects)
                with patch.object(finish.Session, "publish", side_effect=JourneyFailure("archive-readback-unconfirmed")), \
                     self.assertRaisesRegex(JourneyFailure, "archive-readback-unconfirmed"):
                    finish.Session(root, context, KEY, COMMIT, resume_drills=True)
                self.assertEqual(cloud.objects, before)
                updated = finish.Session(root, context, KEY, COMMIT, resume_drills=True)
                self.assertEqual(updated.read(updated.state["controller_transition"]["previous_parent"]), old)
                self.assertEqual(updated.state["completed"], old["completed"])
                self.assertEqual(updated.state["candidate_build"], old["candidate_build"])
                self.assertEqual(updated.state["candidate_controller_commit"], finish.DRILL_CONTINUATION_SOURCE)
                retained, images = finish.candidates(updated)
                self.assertEqual(retained, security)
                self.assertEqual(images, CANDIDATES)
                resumed = finish.Session(root, context, KEY, COMMIT, resume_drills=True)
                self.assertEqual(resumed.state["controller_transition"], updated.state["controller_transition"])
                changed = {**context, "other_inputs": True}
                with self.assertRaisesRegex(JourneyFailure, "inputs-changed"):
                    finish.Session(root, changed, KEY, COMMIT, resume_drills=True)

    @unittest.skipUnless(os.environ.get("LIGHTYEAR_SQL_RECOVERY_TEST_CONTAINER"), "real PostgreSQL check runs in CI")
    def test_real_postgres_distinguishes_row_mutation_and_sequence_advance(self):
        container = os.environ["LIGHTYEAR_SQL_RECOVERY_TEST_CONTAINER"]
        schema = "ms67_difference_" + uuid.uuid4().hex
        def query(sql):
            return subprocess.run(["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", "postgres",
                                   "-X", "-qAt", "--set=ON_ERROR_STOP=1"], input=sql, capture_output=True,
                                  text=True, check=True, timeout=90).stdout
        try:
            query(f"CREATE SCHEMA {schema}; CREATE TABLE {schema}.accounts (id bigint GENERATED ALWAYS AS IDENTITY, payload text);"
                  f"INSERT INTO {schema}.accounts(payload) VALUES ('private-row-value');")
            before = drills.detailed_snapshot(query(SNAPSHOT_SQL))
            query(f"UPDATE {schema}.accounts SET payload='changed-private-row-value';")
            after = drills.detailed_snapshot(query(SNAPSHOT_SQL))
            self.assertEqual([r["name"] for r in drills.snapshot_difference(before, after)["changed_objects"]], [schema+".accounts"])
            self.assertNotIn("private-row-value", json.dumps(after))
            query(f"SELECT nextval('{schema}.accounts_id_seq');")
            advanced = drills.detailed_snapshot(query(SNAPSHOT_SQL))
            self.assertEqual([r["name"] for r in drills.snapshot_difference(after, advanced)["changed_objects"]], [schema+".accounts_id_seq"])
        finally:
            query(f"DROP SCHEMA IF EXISTS {schema} CASCADE;")


if __name__ == "__main__":
    unittest.main()
