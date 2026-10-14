import unittest
from tools.ci_changed_paths import cloudbank_required
class ChangedPaths(unittest.TestCase):
    def test_factory_only_omits_cloudbank(self):
        self.assertFalse(cloudbank_required(['src/lightyear_mainframe/targeted_witness.py','docs/factory/review.json','tests/test_scenario_generation.py']))
    def test_shared_workflow_and_unknown_paths_run_cloudbank(self):
        for p in ['.github/workflows/verify.yml','tools/ci_postgres_image.py','src/lightyear_data/anything.py','factory/cloudbank/x','pom.xml','new-unclassified-file','src/lightyear_mainframe_backup/x']:
            self.assertTrue(cloudbank_required(['docs/factory/report.json',p]),p)
    def test_missing_inventory_runs_all(self):self.assertTrue(cloudbank_required([]))
    def test_rename_outside_factory_is_not_suppressed(self):
        self.assertTrue(cloudbank_required(['src/lightyear_data/old.py','src/lightyear_mainframe/new.py']))
