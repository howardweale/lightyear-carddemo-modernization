import unittest
from lightyear_mainframe.claim_scope import digest, check_consistency
from lightyear_mainframe.equivalence_evidence import mutation_threshold_report
from tools.crosscheck_release_threshold import recompute


class ClaimScopeTests(unittest.TestCase):
    def assess(self, text, declared):
        row = dict(id="fixture", argument={"argument": text}, mutant={"source_sha256":"a"*64}, class_covered=True)
        fresh = [dict(id="fixture", status="survived")]
        records = dict(arguments=[] if declared is None else [dict(id="fixture", record_sha256=digest(row["argument"]),
            source_sha256="a"*64, claim_scope=declared)], acceptances=[])
        engine = mutation_threshold_report(fresh, [row], [], "zos-facing", {"defects":[]}, scope_decisions=records)
        independent = recompute(fresh, [row], [], "zos-facing", scope_decisions=records)
        self.assertEqual(engine["eligible"], independent["eligible"])
        return engine

    def test_wording_never_selects_scope(self):
        for text in ("Portable arithmetic", "This is not z/OS-specific arithmetic"):
            self.assertEqual(0, self.assess(text, "twin-and-zos")["eligible"])
            self.assertEqual(1, self.assess(text, "host-compiler-scoped")["eligible"])

    def test_missing_scope_fails_closed(self):
        result = self.assess("Portable claim without a dated scope decision", None)
        self.assertEqual(1, len(result["unresolved_survivors"]))

    def test_host_wording_is_only_a_tripwire(self):
        for argument in ({"argument":"not native z/OS"}, {"compiler_storage_semantics":{"length":4}}):
            check_consistency(argument, "host-compiler-scoped")
            for scope in (None, "twin-and-zos"):
                with self.assertRaisesRegex(ValueError, "host-semantics-unclassified"):
                    check_consistency(argument, scope)
