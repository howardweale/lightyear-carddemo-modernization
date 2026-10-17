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


class BoundOverlayTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.directory=self.root/'docs/factory';self.directory.mkdir(parents=True)
        self.original=Path(__file__).resolve().parents[1]/'docs/factory/claim-scope-decisions-2026-10-15.json'
        (self.directory/self.original.name).write_bytes(self.original.read_bytes())

    def write(self,value):
        import json
        value={k:v for k,v in value.items() if k!='content_sha256'}
        value['content_sha256']=digest(value)
        (self.directory/'claim-scope-decisions-2026-10-17.json').write_text(json.dumps(value))
        return value

    def readers(self):
        import lightyear_mainframe.claim_scope as engine
        import tools.crosscheck_release_threshold as independent
        return engine,independent

    def test_unlisted_self_sealed_overlay_is_not_authority(self):
        import json
        value=json.loads(self.original.read_bytes());value['reviewed_on']='2026-10-17';self.write(value)
        for reader in self.readers():
            with self.assertRaisesRegex(ValueError,'decision-unbound'):reader.load_decisions(self.root)

    def test_promotion_requires_external_trust_and_bound_signed_review(self):
        import copy
        import json
        from unittest.mock import patch
        from tests.test_decision_console_factory import FactoryTests
        fixture=FactoryTests('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups)
        baseline=json.loads(self.original.read_bytes())
        row=copy.deepcopy(next(r for r in baseline['arguments'] if r['claim_scope']=='host-compiler-scoped'))
        row['claim_scope']='twin-and-zos'
        value=dict(schema=baseline['schema'],reviewed_on='2026-10-17',arguments=[row],acceptances=[])
        value=self.write(value)
        for reader in self.readers():
            with patch.object(reader,'ACCEPTED_OVERLAYS',reader.ACCEPTED_OVERLAYS|{value['content_sha256']}):
                with self.assertRaisesRegex(ValueError,'signed-review-required'):reader.load_decisions(self.root)
        contract=fixture.contract('equivalence-review')
        binding=dict(kind='arguments',**{k:row[k] for k in ('id','record_sha256','source_sha256','claim_scope')})
        contract['details'].update(items=[row['id']],claim_scope='zos-facing',packet_sha256=digest(binding))
        proof,_,_=fixture.decide(contract)
        value['scope_reviews']=[dict(kind='arguments',id=row['id'],proof=proof)];value=self.write(value)
        for reader in self.readers():
            with patch.object(reader,'ACCEPTED_OVERLAYS',reader.ACCEPTED_OVERLAYS|{value['content_sha256']}):
                self.assertEqual(value,reader.load_decisions(self.root,public_key=fixture.service.public_key,
                    trusted_head=proof['journal']['journal_head_sha256']))
                with self.assertRaises(ValueError):reader.load_decisions(self.root,
                    public_key=fixture.service.public_key,trusted_head='f'*64)
        altered=copy.deepcopy(value);altered['arguments'][0]['source_sha256']='0'*64;altered=self.write(altered)
        for reader in self.readers():
            with patch.object(reader,'ACCEPTED_OVERLAYS',reader.ACCEPTED_OVERLAYS|{altered['content_sha256']}):
                with self.assertRaisesRegex(ValueError,'review-binding'):reader.load_decisions(self.root,
                    public_key=fixture.service.public_key,trusted_head=proof['journal']['journal_head_sha256'])

    def test_crosscheck_does_not_call_engine_parser_or_tripwire(self):
        from unittest.mock import patch
        from tools.crosscheck_release_threshold import load_decisions
        with patch('lightyear_mainframe.claim_scope.load_decisions',side_effect=AssertionError('shared parser')):
            self.assertTrue(load_decisions(self.root)['arguments'])
