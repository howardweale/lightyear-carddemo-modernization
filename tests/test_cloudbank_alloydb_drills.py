"""Paced maintenance must retain eviction guards and stop on failed recovery."""
import copy
import json
import tempfile
import unittest
from unittest.mock import Mock

from lightyear_data.cloudbank_alloydb_drills import AlloyDrills
from lightyear_data.cloudbank_journeys import SERVICES, JourneyFailure
from lightyear_data.contracts import sign
from test_ms67_drill_continuation import failed_domain
from test_ms67_finish import engine, KEY, IMAGES, CANDIDATES, ENV, drills


class AlloyDbDrillTests(unittest.TestCase):
    def paced(self):
        obj = object.__new__(AlloyDrills)
        obj.s = {}
        obj.r = Mock()
        obj.r.get.return_value = {"metadata": {"uid": "node-uid"}, "spec": {"unschedulable": True}}
        obj.assert_lease = Mock()
        obj.intent = Mock()
        obj.save = Mock()
        return obj

    def test_next_service_waits_for_recovery_and_final_drain_has_no_selector(self):
        obj = self.paced()
        obj.drain_node({"name": "node", "uid": "node-uid"})
        calls = [c for c in obj.r.mock_calls if c[0] in {"kubectl", "wait_ready"}]
        for index, service in enumerate(SERVICES):
            self.assertEqual(calls[2 * index][0], "kubectl")
            self.assertIn("--pod-selector=app.kubernetes.io/name=" + service, calls[2 * index].args)
            self.assertEqual(calls[2 * index + 1].args, (service,))
        self.assertEqual(len(calls), len(SERVICES) * 2 + 1)
        self.assertFalse(any(a.startswith("--pod-selector") for a in calls[-1].args))
        for call in obj.r.kubectl.call_args_list:
            self.assertFalse({"--force", "--disable-eviction"} & set(call.args))
            self.assertIn("--timeout=600s", call.args)
        self.assertTrue(obj.s["evacuation_procedures"][0]["final_drain_completed"])

    def test_failed_recovery_stops_before_the_next_service(self):
        obj = self.paced()
        obj.r.wait_ready.side_effect = JourneyFailure("service-recovery-timeout")
        with self.assertRaisesRegex(JourneyFailure, "service-recovery-timeout"):
            obj.drain_node({"name": "node", "uid": "node-uid"})
        self.assertEqual(obj.r.kubectl.call_count, 1)
        self.assertFalse(obj.s["evacuation_procedures"][0]["final_drain_completed"])

    def test_changed_or_uncordoned_node_blocks_eviction(self):
        for current in ({"metadata": {"uid": "other"}, "spec": {"unschedulable": True}},
                        {"metadata": {"uid": "node-uid"}, "spec": {"unschedulable": False}}):
            obj = self.paced()
            obj.r.get.return_value = current
            with self.assertRaisesRegex(JourneyFailure, "owned-cordoned-node"):
                obj.drain_node({"name": "node", "uid": "node-uid"})
            obj.r.kubectl.assert_not_called()

    def test_incomplete_pacing_proof_cannot_be_admitted_even_when_resigned(self):
        procedure = {"mode": "service-paced-controlled-evacuation", "node_uid_sha256": "a" * 64,
                     "final_drain_completed": True, "steps": [{"service": service,
                     "selector": "app.kubernetes.io/name=" + service,
                     "alloydb_replicas_recovered": True, "pdb_enforced": True} for service in SERVICES]}
        for mutate in (lambda p: p.update(final_drain_completed=False), lambda p: p["steps"].pop(),
                       lambda p: p["steps"][0].update(pdb_enforced=False),
                       lambda p: p["steps"][0].update(alloydb_replicas_recovered=False)):
            bad = copy.deepcopy(procedure)
            mutate(bad)
            value = sign({"observation_type": drills.OBSERVATION_TYPE, "status": drills.PASS, "bindings": {},
                          "baseline_images": IMAGES, "candidate_images": CANDIDATES, "environment": ENV,
                          "recovery": {"status": "restored", "errors": []}, "credentials_persisted": False,
                          "evacuation_procedures": [bad]}, KEY, "unit-operator")
            with self.assertRaisesRegex(JourneyFailure, "paced-evacuation-proof-incomplete"):
                drills.verify_observation(value, KEY, {}, IMAGES, CANDIDATES, ENV)

    def test_timeout_continuation_requires_exact_restored_failure_and_measured_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, _, cloud = engine(folder)
            failed_domain(obj)
            saved = json.loads(cloud.objects[obj.journal.uri][1])
            saved.update(failure="service-recovery-timeout", failure_context={"phase": "drained-failure-domain"})
            saved = sign(saved, KEY, "unit-operator")
            drills.verify_continuation(saved, KEY, obj.bindings, IMAGES, CANDIDATES, ENV, readiness_timeout=True)
            with self.assertRaisesRegex(JourneyFailure, "restored-failure-domain"):
                drills.verify_continuation(saved, KEY, obj.bindings, IMAGES, CANDIDATES, ENV)
            for mutate in (lambda s: s["failure_context"].update(phase="drained-node"),
                           lambda s: s.update(cleanup_required=True),
                           lambda s: s["completed"]["rolling"]["rows"][0].update(maximum_unavailable=1)):
                bad = copy.deepcopy(saved)
                mutate(bad)
                with self.assertRaises(JourneyFailure):
                    drills.verify_continuation(sign(bad, KEY, "unit-operator"), KEY, obj.bindings,
                                               IMAGES, CANDIDATES, ENV, readiness_timeout=True)
