import copy
import unittest

from lightyear_data.cloudbank_alloydb_ha import TYPE, verify_ha
from lightyear_data.cloudbank_journeys import JourneyFailure
from lightyear_data.contracts import sign
from test_cloudbank_ms71 import profile, observation, PROVIDERS, source_images, KEY, SIGNER


class AlloyHaReceiptTests(unittest.TestCase):
    def fixture(self):
        p = profile(PROVIDERS[1])
        managed = observation(p)
        ready = {s: {"ready_replicas": 2, "http_readiness": 200} for s in source_images()}
        processes = {s: "a" * 64 for s in source_images()}
        before = {"resource": p["resource"], "private_ip": managed["database"]["address"],
                  "availability_type": "REGIONAL", "active_zone": "us-west1-a"}
        operation = p["resource"].split("/clusters/", 1)[0] + "/operations/test"
        value = {"observation_type": TYPE, "status": "passed-alloydb-primary-failover", "profile": p,
            "images": source_images(), "environment": managed["environment"],
            "preflight": {"source_profile": before, "managed_target": managed,
                          "processes": processes, "services": ready},
            "promoted_profile": {**before, "active_zone": "us-west1-b"},
            "after": {"processes": processes, "services": ready, "acknowledged_state_matches": True,
                "transfer_replay_no_extra_effects": True, "new_transfer": {"http_status": 200},
                "new_deposit": {"queue": {"state": "PROCESSED"}},
                "new_clearance": {"queue": {"state": "PROCESSED"}, "replay_unchanged": True},
                "credit": {"score_in_declared_range": True}, "chat": {"bounded_response": True}},
            "recovery_seconds": 60, "recovery_within_limit": True,
            "recovery": {"status": "restored", "errors": [], "operation_completion_observed": True, "services": ready},
            "operation": {"name": operation, "target": p["resource"],
                          "result": {"name": operation, "done": True, "metadata": {"target": p["resource"]}}},
            **{k: False for k in ("production_ready", "alloydb_platform_qualified", "credentials_persisted", "raw_database_rows_persisted")}}
        return p, managed["environment"], value

    def test_re_signed_incomplete_or_unrelated_failover_proofs_are_rejected(self):
        p, env, good = self.fixture()
        verify_ha(sign(good, KEY, SIGNER), KEY, p, source_images(), env)
        for name in ("wrong-provider-target", "missing-processes", "missing-new-writes", "failed-provider-operation"):
            bad = copy.deepcopy(good)
            if name == "wrong-provider-target":
                bad["operation"]["result"]["metadata"]["target"] = "some-other-database"
            elif name == "missing-processes":
                bad["preflight"]["processes"] = bad["after"]["processes"] = {}
            elif name == "missing-new-writes":
                bad["after"].pop("new_deposit")
            else:
                bad["operation"]["result"]["error"] = {"code": 13}
            with self.subTest(name=name), self.assertRaises(JourneyFailure):
                verify_ha(sign(bad, KEY, SIGNER), KEY, p, source_images(), env)
