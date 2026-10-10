import unittest
from lightyear_evidence.completeness import Completeness, cleanup_error, partial_equipment_summary

class CompletenessTests(unittest.TestCase):
    def test_missing_clock_and_execution_are_not_synthesized(self):
        c=Completeness(("clock.json","sql-execution.json","result.json"),frozenset({"result.json"}))
        self.assertEqual(["clock.json","sql-execution.json"],c.missing)
        self.assertFalse(c.complete)
    def test_signed_available_prefix_stays_partial(self):
        # Adapter already authenticated this non-B06 SQL collector's signature.
        prefix=[dict(lane="sql",event_count=3,prefix_authenticated=True,census_sha256="a"*64)]
        result=partial_equipment_summary(prefix,("clock","execution"),())
        self.assertEqual(prefix,result["collector_prefixes"])
        self.assertTrue(result["partial_evidence"])
        self.assertEqual(["clock","execution"],result["missing_artifacts"])
        self.assertNotIn("complete_gate_replayed",result)
    def test_presence_does_not_upgrade_failed_audit(self):
        self.assertTrue(Completeness(("clock",),frozenset({"clock"})).complete)
        self.assertTrue(partial_equipment_summary([],(),())["partial_evidence"])
    def test_cleanup_success_preserves_equipment_failure(self):
        error={"kind":"equipment-failure","exception_type":"LostConnection"}
        self.assertIs(error,cleanup_error(error,True))
        self.assertIsNone(cleanup_error(None,True))
    def test_cleanup_failure_overrides_success_and_candidate_fault(self):
        expected={"kind":"equipment-failure","exception_type":"CleanupIncomplete"}
        self.assertEqual(expected,cleanup_error(None,False))
        self.assertEqual(expected,cleanup_error({"kind":"execution-failure"},False))
