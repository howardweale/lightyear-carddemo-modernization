import copy
import unittest
from unittest.mock import Mock

from lightyear_data.cloudbank_alloydb_recovery import AlloyRecovery, APPLICATION_SNAPSHOT_SQL
from lightyear_data.cloudbank_journeys import JourneyFailure


class AlloyRecoveryGuards(unittest.TestCase):
    def runner(self):
        runner = object.__new__(AlloyRecovery)
        runner.runtime = Mock(run_id="alloydb-test")
        runner.region_path = "projects/test/locations/us-west1"
        runner.state = {"source": "source", "operations": {}, "targets": {}, "network": "private-network"}
        runner.save = Mock()
        runner.cloud = Mock()
        return runner

    def test_uncertain_mutation_is_never_blindly_retried(self):
        runner = self.runner()
        runner.state["operations"]["pitr"] = {"name": None}
        with self.assertRaisesRegex(JourneyFailure, "already-submitted-or-uncertain"):
            runner.submit("pitr", "target", "clusters", "restore", "target")
        runner.cloud.assert_not_called()

    def test_operation_must_belong_to_requested_resource(self):
        runner = self.runner()
        runner.state["operations"]["pitr"] = {"name": runner.region_path + "/operations/one", "target": "owned"}
        runner.cloud.return_value = {"name": runner.region_path + "/operations/one", "done": True,
                                     "metadata": {"target": "somebody-else"}}
        with self.assertRaisesRegex(JourneyFailure, "target-mismatch"):
            runner.wait("pitr")

    def test_overlapped_primary_with_lost_submission_response_is_not_created_twice(self):
        runner = self.runner()
        runner.state["operations"]["pitr-primary"] = {"name": None}
        runner.provision_primary = Mock()
        with self.assertRaisesRegex(JourneyFailure, "response-uncertain"):
            runner.finish_restore("pitr")
        runner.provision_primary.assert_not_called()

    def test_cleanup_never_adopts_a_recreated_cluster(self):
        runner = self.runner()
        runner.state["targets"]["pitr"] = {"name": "temporary", "resource": "owned", "absent_before": True, "uid": "original"}
        runner.cloud.return_value = {"name": "owned", "uid": "replacement", "networkConfig": {"network": "private-network"}}
        with self.assertRaisesRegex(JourneyFailure, "uid-drift"):
            runner.target_guard("pitr")
        self.assertEqual(runner.cloud.call_args.args, ("clusters", "describe", "temporary"))

    def test_application_hashes_exclude_only_provider_owned_extension_objects(self):
        self.assertEqual(APPLICATION_SNAPSHOT_SQL.count("ed.refclassid='pg_extension'::regclass"), 4)
        self.assertIn("REPEATABLE READ READ ONLY", APPLICATION_SNAPSHOT_SQL)
        self.assertIn("row_security = off", APPLICATION_SNAPSHOT_SQL)
        self.assertIn("ORDER BY h", APPLICATION_SNAPSHOT_SQL)
