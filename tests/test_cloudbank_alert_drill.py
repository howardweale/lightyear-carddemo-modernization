"""Exercise provider observations, bounded ownership, interrupted writes, and the CLI."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from lightyear_data.cloudbank_alert_drill import (
    AlertDrill, ApiFailure, LABEL, Monitoring, STATE_FILE, STATE_TYPE, descriptor_spec,
    instant, metric_type, policy_spec, stamp, validate_state, verify_observation,
)
from lightyear_data.cloudbank_journeys import ACK, JourneyFailure
from lightyear_data.cloudbank_secret_rotation_gke import hashed
from lightyear_data.contracts import sign


PROJECT, NUMBER = "lightyear-ms67-test", "233419964177"
RUN = "ms67-alert-" + "a" * 32
KEY = "unit-test-evidence-key-only"
BUCKET = "gs://" + PROJECT + "-ms67-evidence/alert-drill"
ENVIRONMENT = {"project": PROJECT, "region": "us-west1", "cluster": "cloudbank-ms67",
               "namespace": "cloudbank-ms67", "namespace_uid_sha256": "1" * 64}
BINDINGS = {"image_lock_sha256": "2" * 64, "ms64_receipt_sha256": "3" * 64, "platform_profile_sha256": "4" * 64}


def state():
    return {"state_type": STATE_TYPE, "schema_version": "1.0", "run_id": RUN,
            "environment": dict(ENVIRONMENT), "bindings": dict(BINDINGS), "project_number": NUMBER,
            "context": f"gke_{PROJECT}_us-west1_cloudbank-ms67", "recovery_uri": BUCKET + "/" + RUN + "/" + STATE_FILE,
            "descriptor_phase": "not-started", "policy_phase": "not-started", "policy_name": None,
            "observations": {}, "cleanup_complete": False, "phase": "validated", "updated_at": "2026-09-09T15:00:00Z",
            "credentials_persisted": False, "raw_output_persisted": False, "production_environment": False}


class Crash(BaseException):
    pass


class Clock:
    def __init__(self):
        self.seconds = 0

    def now(self):
        return datetime(2026, 9, 9, 15, tzinfo=timezone.utc) + timedelta(seconds=self.seconds)

    def sleep(self, seconds):
        self.seconds += seconds


class MemoryJournal:
    def __init__(self):
        self.records = []
        self.fail_at = None

    def write(self, value):
        if len(self.records) + 1 == self.fail_at:
            raise JourneyFailure("checkpoint-readback-failed")
        self.records.append(copy.deepcopy(value))
        return sign(value, KEY, "unit-test-operator")


class Provider(Monitoring):
    """Transport fixture; all ownership, query, and qualification code stays real."""
    def __init__(self, clock):
        super().__init__(PROJECT, NUMBER)
        self.clock = clock
        self.descriptor_value = None
        self.policies, self.incidents, self.points, self.mutations = [], [], [], []
        self.high_since = self.low_since = None
        self.disable_incidents = self.hide_points = False
        self.crash_after = self.lose_response = None
        self.hide_descriptor_reads = 0
        self.delete_noop = False

    def changed(self, operation):
        self.mutations.append(operation)
        if len(self.mutations) == self.crash_after:
            raise Crash(operation)
        if self.lose_response == operation:
            self.lose_response = None
            raise JourneyFailure("alert-api-unavailable-or-timed-out")

    def evaluate(self, point):
        value, at = int(point["value"]["int64Value"]), instant(point["interval"]["endTime"])
        if self.disable_incidents or not self.policies:
            return
        if value == 1:
            self.high_since = self.high_since or at
            if not self.incidents and (at - self.high_since).total_seconds() >= 60:
                self.incidents = [{"name": self.prefix + "/alerts/incident1", "state": "OPEN", "openTime": stamp(at),
                    "policy": {"name": self.policies[0]["name"], "userLabels": {LABEL: RUN}},
                    "metric": {"type": metric_type(RUN), "labels": {"run_id": RUN}},
                    "resource": {"type": "global", "labels": {"project_id": PROJECT}}}]
        elif self.incidents:
            self.low_since = self.low_since or at
            if (at - self.low_since).total_seconds() >= 60:
                self.incidents[0].update(state="CLOSED", closeTime=stamp(at))

    def request(self, method, path, *, query=None, body=None, absent=False):
        if method == "GET":
            if path == self.descriptor_path(RUN):
                if self.hide_descriptor_reads:
                    self.hide_descriptor_reads -= 1
                    return None
                return copy.deepcopy(self.descriptor_value)
            if path == self.prefix + "/alertPolicies":
                return {"alertPolicies": copy.deepcopy(self.policies)}
            if path == self.prefix + "/alerts":
                return {"alerts": copy.deepcopy(self.incidents)}
            if path == self.prefix + "/timeSeries":
                if self.hide_points:
                    return {}
                points = [p for p in self.points if
                    instant(query["interval.startTime"]) < instant(p["interval"]["endTime"]) <= instant(query["interval.endTime"])]
                return {"timeSeries": [{"metric": {"type": metric_type(RUN), "labels": {"run_id": RUN}},
                    "resource": {"type": "global", "labels": {"project_id": PROJECT}}, "points": list(reversed(points))}]} if points else {}
            return next((copy.deepcopy(p) for p in self.policies if p["name"] == path), None)
        if method == "POST" and path == self.prefix + "/metricDescriptors":
            self.descriptor_value = copy.deepcopy(body)
            self.changed("create-descriptor")
            return copy.deepcopy(self.descriptor_value)
        if method == "POST" and path == self.prefix + "/alertPolicies":
            value = copy.deepcopy(body)
            value["name"] = self.prefix + "/alertPolicies/policy1"
            value["conditions"][0]["name"] = value["name"] + "/conditions/condition1"
            value["mutationRecord"] = {"mutateTime": stamp(self.clock.now()), "mutatedBy": "unit-test-operator"}
            self.policies.append(value)
            self.changed("create-policy")
            return copy.deepcopy(value)
        if method == "POST" and path == self.prefix + "/timeSeries":
            point = copy.deepcopy(body["timeSeries"][0]["points"][0])
            self.points.append(point)
            self.evaluate(point)
            self.changed("point-" + point["value"]["int64Value"])
            return {}
        if method == "DELETE":
            kind = "descriptor" if path == self.descriptor_path(RUN) else "policy"
            if not self.delete_noop:
                if kind == "descriptor":
                    self.descriptor_value = None
                else:
                    self.policies = [p for p in self.policies if p["name"] != path]
            self.changed("delete-" + kind)
            return {}
        raise AssertionError((method, path))


def make():
    clock, journal = Clock(), MemoryJournal()
    api = Provider(clock)
    engine = AlertDrill(api, journal, state(), now=clock.now, sleep=clock.sleep,
                        monotonic=lambda: clock.seconds, phase_seconds=240)
    return api, journal, engine


class AlertTests(unittest.TestCase):
    def test_observes_provider_open_and_close_before_deleting(self):
        api, journal, engine = make()
        result = engine.run()
        verify_observation(sign(result, KEY, "unit-test-operator"), KEY)
        self.assertEqual(api.mutations[-2:], ["delete-policy", "delete-descriptor"])
        closed = next(i for i, row in enumerate(journal.records) if row["phase"] == "closed-observed")
        removed = next(i for i, row in enumerate(journal.records) if row["phase"] == "before-policy-deletion")
        self.assertLess(closed, removed)
        self.assertIsNone(api.descriptor_value)
        self.assertEqual(api.policies, [])
        self.assertFalse(result["service_correlation_qualified"])
        self.assertFalse(result["ms67_complete"])
        self.assertEqual(result["notification_recipients"], 0)
        self.assertNotIn("unit-test-operator", json.dumps(result))

    def test_crash_after_every_provider_mutation_recovers_without_passing(self):
        complete, _, completed = make()
        completed.run()
        for index, operation in enumerate(complete.mutations, 1):
            with self.subTest(index=index, operation=operation):
                api, journal, engine = make()
                api.crash_after = index
                with self.assertRaises(Crash):
                    engine.run()
                api.crash_after = None
                engine.state = copy.deepcopy(journal.records[-1])
                validate_state(sign(engine.state, KEY, "unit-test"), KEY, **{
                    **{k: ENVIRONMENT[k] for k in ("project", "region", "cluster", "namespace")},
                    "project_number": NUMBER, "evidence_bucket": BUCKET})
                result = engine.observation("recovered-alert-drill", engine.cleanup())
                self.assertFalse(result["alert_recovered"])
                self.assertIsNone(api.descriptor_value)
                self.assertEqual(api.policies, [])
                with self.assertRaises(JourneyFailure):
                    verify_observation(sign(result, KEY, "unit-test"), KEY)

    def test_lost_creation_response_is_adopted_without_second_post(self):
        for operation in ("create-descriptor", "create-policy"):
            api, journal, engine = make()
            api.lose_response = operation
            with self.assertRaises(JourneyFailure):
                engine.run()
            engine.state = copy.deepcopy(journal.records[-1])
            engine.cleanup()
            self.assertEqual(api.mutations.count(operation), 1)
            self.assertIsNone(api.descriptor_value)
            self.assertEqual(api.policies, [])

    def test_pending_creation_without_positive_identity_preserves_resources(self):
        for kind in ("descriptor", "policy"):
            api, _, engine = make()
            engine.state[kind + "_phase"] = "creating"
            with self.assertRaisesRegex(JourneyFailure, "creation-ambiguous"):
                engine.cleanup()
            self.assertEqual(api.mutations, [])

    def test_duplicate_owned_policy_is_not_guessed(self):
        api, _, engine = make()
        engine.create("descriptor")
        engine.create("policy")
        engine.state["policy_phase"] = "creating"
        api.policies.append(copy.deepcopy(api.policies[0]))
        before = list(api.mutations)
        with self.assertRaisesRegex(JourneyFailure, "creation-ambiguous"):
            engine.cleanup()
        self.assertEqual(api.mutations, before)

    def test_acknowledged_policy_version_cannot_be_replaced_during_reconciliation(self):
        api, _, engine = make()
        engine.create("descriptor")
        engine.create("policy")
        engine.state["policy_phase"] = "creating"
        api.policies[0]["mutationRecord"]["mutateTime"] = "2026-09-09T16:00:00Z"
        before = list(api.mutations)
        with self.assertRaisesRegex(JourneyFailure, "changed-after-creation"):
            engine.cleanup()
        self.assertEqual(api.mutations, before)

    def test_changed_resources_are_never_deleted(self):
        changes = (lambda a: a.policies[0].update(notificationChannels=["projects/other/notificationChannels/1"]),
                   lambda a: a.policies[0]["mutationRecord"].update(mutateTime="2026-09-09T15:01:00Z"),
                   lambda a: a.policies[0].update(enabled=False),
                   lambda a: a.descriptor_value["labels"].append({"key": "unowned", "valueType": "STRING"}))
        for change in changes:
            api, _, engine = make()
            engine.create("descriptor")
            engine.create("policy")
            change(api)
            with self.assertRaises(JourneyFailure):
                engine.guard()
            with self.assertRaises(JourneyFailure):
                engine.cleanup()
            # Descriptor drift may permit deleting our unchanged policy, never the changed descriptor.
            self.assertNotIn("delete-descriptor", api.mutations)

    def test_missing_incident_or_metric_never_passes_and_cleanup_is_separate(self):
        for missing in ("disable_incidents", "hide_points"):
            api, _, engine = make()
            setattr(api, missing, True)
            with self.assertRaisesRegex(JourneyFailure, "timeout"):
                engine.run()
            result = engine.observation("failed", engine.cleanup())
            self.assertFalse(result["alert_fired"])
            self.assertFalse(result["alert_recovered"])
            self.assertTrue(result["recovery"]["policy_absent"])

    def test_delete_response_without_confirmed_absence_is_not_cleanup(self):
        api, _, engine = make()
        engine.create("descriptor")
        engine.create("policy")
        api.delete_noop = True
        with self.assertRaisesRegex(JourneyFailure, "removal-unconfirmed"):
            engine.cleanup()
        self.assertFalse(engine.state["cleanup_complete"])
        self.assertNotIn("delete-descriptor", api.mutations)

    def test_checkpoint_failure_fences_further_mutation_including_cleanup(self):
        api, journal, engine = make()
        engine.create("descriptor")
        before = list(api.mutations)
        journal.fail_at = len(journal.records) + 1
        with self.assertRaisesRegex(JourneyFailure, "checkpoint-not-confirmed"):
            engine.create("policy")
        with self.assertRaisesRegex(JourneyFailure, "checkpoint-not-confirmed"):
            engine.cleanup()
        self.assertEqual(api.mutations, before)

    def test_descriptor_asynchronous_readback_waits_without_duplicate_create(self):
        api, _, engine = make()
        api.hide_descriptor_reads = 2
        engine.create("descriptor")
        self.assertEqual(api.mutations, ["create-descriptor"])
        self.assertEqual(engine.state["descriptor_phase"], "created")

    def test_definite_create_rejection_is_not_pending(self):
        api, _, engine = make()
        with patch.object(api, "request", side_effect=ApiFailure(403)):
            with self.assertRaises(ApiFailure):
                engine.create("descriptor")
        self.assertEqual(engine.state["descriptor_phase"], "rejected")
        engine.cleanup()
        self.assertEqual(api.mutations, [])

    def test_repeated_cleanup_is_idempotent_and_never_recreates(self):
        api, _, engine = make()
        engine.run()
        before = list(api.mutations)
        engine.cleanup()
        self.assertEqual(api.mutations, before)


class ObservationTests(unittest.TestCase):
    def test_signed_wrong_or_incomplete_evidence_is_rejected(self):
        _, _, engine = make()
        result = engine.run()
        changes = (
            lambda v: v.update(ms67_complete=True),
            lambda v: v.update(notification_recipients=False),
            lambda v: v["bindings"].update(image_lock_sha256="not-a-hash"),
            lambda v: v["environment"].update(project="another-project"),
            lambda v: v["observations"]["closed"].update(alert_identity_sha256="b" * 64),
            lambda v: v["observations"]["closed"].update(close_time="2026-09-09T16:00:00Z"),
            lambda v: v["observations"]["closed"].update(close_time="2026-09-09T15:00:00Z"),
            lambda v: v["observations"].pop("closed"),
            lambda v: v["observations"]["closed"]["point"].update(value=1),
            lambda v: v["recovery"].update(policy_absent=False),
        )
        for change in changes:
            candidate = copy.deepcopy(result)
            change(candidate)
            with self.assertRaises(JourneyFailure):
                verify_observation(sign(candidate, KEY, "unit-test"), KEY)
        with self.assertRaisesRegex(JourneyFailure, "signature-invalid"):
            verify_observation(sign(result, "wrong-key", "unit-test"), KEY)

    def test_recovery_validation_rejects_foreign_project_uri_and_owner(self):
        context = {k: ENVIRONMENT[k] for k in ("project", "region", "cluster", "namespace")}
        context.update(project_number=NUMBER, evidence_bucket=BUCKET)
        validate_state(sign(state(), KEY, "unit-test"), KEY, **context)
        for change in (lambda v: v.update(project_number="99"),
                       lambda v: v.update(recovery_uri="gs://foreign-bucket/state.json"),
                       lambda v: v.update(policy_name="projects/99/alertPolicies/1"),
                       lambda v: v.update(policy_phase="created"),
                       lambda v: v.update(cleanup_complete=True)):
            candidate = state()
            change(candidate)
            with self.assertRaises(JourneyFailure):
                validate_state(sign(candidate, KEY, "unit-test"), KEY, **context)


class TransportTests(unittest.TestCase):
    def test_unrelated_incidents_are_ignored_and_same_policy_wrong_metric_rejected(self):
        api, _, engine = make()
        engine.run()
        name = engine.state["policy_name"]
        api.incidents[0]["policy"]["name"] = api.prefix + "/alertPolicies/other"
        self.assertEqual(api.matching_alerts(RUN, name), [])
        api.incidents[0]["policy"]["name"] = name
        api.incidents[0]["metric"]["labels"]["run_id"] = "other"
        with self.assertRaisesRegex(JourneyFailure, "identity-mismatch"):
            api.matching_alerts(RUN, name)

    def test_point_query_retains_earliest_point_including_phase_start(self):
        api, _, engine = make()
        result = engine.run()
        first_high = next(p for p in api.points if p["value"]["int64Value"] == "1")
        self.assertEqual(result["observations"]["opened"]["point"]["timestamp"], first_high["interval"]["endTime"])

    def test_pagination_and_partial_query_errors_fail_closed(self):
        api = Monitoring(PROJECT, NUMBER)
        with patch.object(api, "request", side_effect=[{"alerts": [{"name": "one"}], "nextPageToken": "two"},
                                                       {"alerts": [{"name": "two"}]}]) as call:
            self.assertEqual(len(api.listing("alerts")), 2)
            self.assertEqual(call.call_args.kwargs["query"]["pageToken"], "two")
        for response in ({"nextPageToken": "again"}, {"executionErrors": [{"code": 13}]}):
            with patch.object(api, "request", return_value=response), self.assertRaises(JourneyFailure):
                api.listing("timeSeries")

    def test_rest_token_is_memory_only_and_http_body_not_disclosed(self):
        token = "token-never-in-evidence"
        invoke = lambda argv: token
        api = Monitoring(PROJECT, NUMBER, invoke=invoke)
        raw = io.BytesIO(b"{\"alerts\": []}")
        with patch.object(api.opener, "open", return_value=raw) as call:
            self.assertEqual(api.listing("alerts"), [])
            request = call.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer " + token)
            self.assertTrue(request.full_url.startswith("https://monitoring.googleapis.com/v3/projects/" + NUMBER))
        error = HTTPError("https://monitoring.googleapis.com/", 403, "forbidden", {}, io.BytesIO(b"secret-body"))
        with patch.object(api.opener, "open", side_effect=error), self.assertRaisesRegex(JourneyFailure, "^alert-api-http-403$"):
            api.listing("alerts")
        for path in ("projects/99/alerts", api.prefix + "/../alerts", api.prefix + "/alerts?redirect=evil"):
            with self.assertRaisesRegex(JourneyFailure, "boundary-invalid"):
                api.request("GET", path)

    def test_omitted_protobuf_defaults_are_supported_but_drift_is_not(self):
        api = Monitoring(PROJECT, NUMBER)
        descriptor = descriptor_spec(RUN)
        descriptor["labels"][0].pop("valueType")
        api.check_descriptor(RUN, descriptor)
        policy = policy_spec(PROJECT, RUN)
        policy["name"] = api.prefix + "/alertPolicies/1"
        threshold = policy["conditions"][0]["conditionThreshold"]
        threshold.update(denominatorFilter="", denominatorAggregations=[])
        threshold["aggregations"][0].update(crossSeriesReducer="REDUCE_NONE", groupByFields=[])
        api.check_policy(RUN, policy)
        threshold["evaluationMissingData"] = "EVALUATION_MISSING_DATA_INACTIVE"
        with self.assertRaises(JourneyFailure):
            api.check_policy(RUN, policy)


def load_cli():
    root = Path(__file__).resolve().parents[1]
    # Executing a tools script adds tools to sys.path on both Unix and Windows.
    spec = importlib.util.spec_from_file_location("alert_drill_cli_under_test", root / "tools/cloudbank_alert_drill.py")
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", [str(root / "tools"), *sys.path]):
        spec.loader.exec_module(module)
    return module


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = load_cli()

    def args(self, action):
        return [action, "--project", PROJECT, "--region", "us-west1", "--cluster", "cloudbank-ms67",
                "--namespace", "cloudbank-ms67", "--signer", "unit-test", "--evidence-bucket", BUCKET]

    def test_missing_mutation_ack_stops_before_any_gcloud_or_key_access(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(self.cli, "command") as command_call, \
                patch.object(self.cli, "evidence_key") as key_call, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.cli.main(self.args("run")), 1)
            command_call.assert_not_called()
            key_call.assert_not_called()

    def test_cli_verify_uses_bound_environment_without_gcp_mutations(self):
        _, _, engine = make()
        evidence = sign(engine.run(), KEY, "unit-test")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "observation.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            with patch.object(self.cli, "evidence_key", return_value=KEY), patch.object(self.cli, "command") as invoke, \
                    patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(self.cli.main(self.args("verify") + ["--observation", str(path)]), 0)
                invoke.assert_not_called()

    def test_recovery_reads_latest_generation_and_requires_stopped_process(self):
        supplied, latest = sign(state(), KEY, "unit-test"), state()
        latest.update(phase="restored", descriptor_phase="deleted", policy_phase="deleted", cleanup_complete=True)
        latest = sign(latest, KEY, "unit-test")
        args = self.cli.parser().parse_args(self.args("recover") + ["--recovery-state", "old.json", "--original-process-stopped"])
        with patch.object(self.cli, "load", return_value=supplied), \
                patch.object(self.cli, "command", side_effect=["123", json.dumps(latest)]) as invoke:
            recovered, generation = self.cli.current_recovery(args, KEY, NUMBER)
            self.assertEqual(generation, "123")
            self.assertTrue(recovered["cleanup_complete"])
            self.assertIn(supplied["recovery_uri"] + "#123", invoke.call_args.args[0])
        args.original_process_stopped = False
        with patch.object(self.cli, "command") as invoke, self.assertRaises(JourneyFailure):
            self.cli.current_recovery(args, KEY, NUMBER)
        invoke.assert_not_called()

    def test_run_uploads_verified_observation_and_cleans_resources(self):
        api, _, clocked_engine = make()
        journals = []

        def journal(*args, **kwargs):
            value = MemoryJournal()
            journals.append(value)
            return value

        def engine(provider, sink, payload, **kwargs):
            return AlertDrill(provider, sink, payload, now=clocked_engine.now, sleep=clocked_engine.sleep,
                              monotonic=clocked_engine.monotonic, phase_seconds=240)

        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"LIGHTYEAR_NON_PRODUCTION_ACK": ACK}), \
                patch.object(self.cli, "evidence_key", return_value=KEY), patch.object(self.cli, "command", return_value=NUMBER), \
                patch.object(self.cli, "Monitoring", return_value=api), patch.object(self.cli, "initial_state", return_value=state()), \
                patch.object(self.cli, "Journal", side_effect=journal), patch.object(self.cli, "AlertDrill", side_effect=engine), \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(self.cli.main(self.args("run") + ["--output-root", str(Path(folder) / "new-run")]), 0)
            self.assertIn("MS67_ALERT_EVIDENCE_READBACK=VERIFIED", output.getvalue())
        self.assertEqual(len(journals), 2)
        verify_observation(sign(journals[-1].records[-1], KEY, "unit-test"), KEY)
        self.assertEqual(api.policies, [])
        self.assertIsNone(api.descriptor_value)

    def test_existing_output_directory_is_never_written_even_for_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"LIGHTYEAR_NON_PRODUCTION_ACK": ACK}), \
                patch.object(self.cli, "evidence_key", return_value=KEY), patch.object(self.cli, "command", return_value=NUMBER), \
                patch.object(self.cli, "Journal") as journal, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.cli.main(self.args("run") + ["--output-root", folder]), 1)
            journal.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
