"""Offline tests only. Parser protocol mocks and observations are NOT native evidence."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import io
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

from lightyear_data.contracts import content_hash
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_data.stored_logic import QUALIFICATION_GATES
from lightyear_data.tsql_procedures import VERDICTS
from lightyear_data.tsql_procedures.adapters import (
    Coverage, EngineProfile, NativeExecutionUnavailable, Observation,
    PostgresAdapter, SqlServerAdapter, coverage_gate,
)
from lightyear_data.tsql_procedures.comparison import compare_observations, table_delta
from lightyear_data.tsql_procedures.corpus import artifacts, corpus
from lightyear_data.tsql_procedures.inventory import (
    inventory, parse, public_summary, scan, sha, summary_markdown, tokens,
)
from lightyear_data.tsql_procedures.ledger import build_ledger, validate_ledger

ROOT=Path(__file__).resolve().parents[1]
SQL="CREATE OR ALTER PROCEDURE dbo.private_proc @amount int=3, @out varchar(10) OUTPUT AS BEGIN SELECT @amount; END;"
COVERAGE=Coverage(10,10,5,5,("catch",),("catch",),(),"unit-fixture-not-native")

def parser_reply(source=SQL, **changes):
    body={"schema":"tsql-scriptdom/1","input_sha256":sha(source.encode()),
          "parsed":True,"procedure_count":1,"version":"test-only",
          "errors":[],"ast_nodes":[{"kind":"CreateOrAlterProcedureStatement"}]}
    body.update(changes)
    return subprocess.CompletedProcess(["mock"],0,json.dumps(body),"")

def observation(**changes):
    obj=Observation(
        result_sets=[{"columns":[{"name":"value","canonical_type":"variable-character"}],
                      "rows":[["a"],["b"],["b"]],"ordered":False}],
        output_parameters={}, return_code=0,error=None,raw_error=None,
        side_effects={"all_user_tables_captured":True,"table_inventory":["dbo.t"],
                      "tables":{"dbo.t":{"inserted":[],"deleted":[]}},
                      "identity_sequence_state":{}},
        transaction={"outcome":"committed"},row_count_messages=[],
        informational_messages=[],temp_objects=[],elapsed_seconds=.01,
        engine_version="unit-fixture",session_settings={},coverage=COVERAGE)
    return replace(obj,**changes)

class InventoryTests(unittest.TestCase):
    def test_lexer_removes_nested_comments_and_masks_literals(self):
        s=SQL+" /* xp_cmdshell /* OPENQUERY */ */ SELECT N'xp_cmdshell OPENQUERY'; -- CLR"
        hints=scan(s)
        self.assertEqual([],hints["unsupported_features"])
        self.assertNotIn("xp_cmdshell",json.dumps(hints))
        self.assertEqual(["dbo.private_proc"],hints["procedure_names"])

    def test_parameters_and_output(self):
        p=scan(SQL)["parameters"]
        self.assertEqual(["@amount","@out"],[x["name"] for x in p])
        self.assertTrue(p[0]["has_default"])
        self.assertTrue(p[1]["output"])

    def test_unterminated_tokens_fail(self):
        for suffix in (" /* x"," SELECT 'unterminated"," SELECT [unterminated"):
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):
                tokens(SQL+suffix)

    def test_dynamic_and_unsupported_are_explicit(self):
        h=scan(SQL+" EXEC(@sql); SELECT * FROM OPENQUERY(remote,'x');")
        self.assertTrue(h["dynamic_sql"])
        self.assertIn("linked-server",h["unsupported_features"])
        self.assertEqual("not-assessed",h["dependencies"]["closure"])
        self.assertEqual("not-assessed",h["concurrency"])

    def test_nondeterminism_and_cross_database(self):
        h=scan(SQL+" SELECT GETDATE(),NEWID() FROM db.dbo.t;")
        self.assertEqual(["GETDATE","NEWID"],h["nondeterministic_calls"])
        self.assertIn("cross-database",h["unsupported_features"])

    def test_no_parser_is_unparsed(self):
        self.assertEqual("unparsed",parse(SQL,allow_sqlglot=False)["reason"])

    def test_bridge_protocol_binds_input(self):
        with patch("lightyear_data.tsql_procedures.inventory.subprocess.run",return_value=parser_reply()) as call:
            p=parse(SQL,("trusted-bridge",),allow_sqlglot=False)
        self.assertEqual("parsed",p["status"])
        self.assertFalse(call.call_args.kwargs["shell"])
        self.assertEqual(SQL,call.call_args.kwargs["input"])

    def test_bridge_invalid_binding_shape_or_error_rejected(self):
        variants=[{"input_sha256":"0"*64},{"procedure_count":True},
                  {"procedure_count":0},{"ast_nodes":[]},{"errors":[{"number":1}]},
                  {"version":""},{"parsed":False}]
        for changes in variants:
            with self.subTest(changes=changes),patch(
                "lightyear_data.tsql_procedures.inventory.subprocess.run",
                return_value=parser_reply(**changes)):
                self.assertEqual("unparsed",parse(SQL,("bridge",),allow_sqlglot=False)["reason"])

    def test_bridge_failure_does_not_leak_private_error(self):
        with patch("lightyear_data.tsql_procedures.inventory.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("secret-source",30)):
            p=parse(SQL,("bridge",),allow_sqlglot=False)
        self.assertNotIn("secret-source",json.dumps(p))
        self.assertEqual("unsupported",p["status"])

    def test_sqlglot_fallback_accepts_only_procedure_ast(self):
        class Command: pass
        class Create: pass
        class Node:
            args={"kind":"PROCEDURE"}
            def find_all(self,kind): return [self] if kind is Create else []
        fake=types.ModuleType("sqlglot")
        fake.__version__="unit-mock"
        fake.exp=types.SimpleNamespace(Command=Command,Create=Create)
        fake.parse=lambda *a,**k:[Node()]
        with patch.dict("sys.modules",{"sqlglot":fake}):
            self.assertEqual("sqlglot",parse(SQL)["backend"])

    def test_sqlglot_opaque_command_is_not_parse_success(self):
        class Node:
            def find_all(self,kind): return [object()]
        fake=types.ModuleType("sqlglot")
        fake.exp=types.SimpleNamespace(Command=object)
        fake.parse=lambda *a,**k:[Node()]
        with patch.dict("sys.modules",{"sqlglot":fake}):
            self.assertEqual("unparsed",parse(SQL)["reason"])

    def test_sqlglot_exception_does_not_echo_source(self):
        fake=types.ModuleType("sqlglot")
        fake.exp=types.SimpleNamespace(Command=object)
        def fail(*a,**k): raise RuntimeError("CUSTOMER_SQL_LITERAL")
        fake.parse=fail
        with patch.dict("sys.modules",{"sqlglot":fake}):
            self.assertNotIn("CUSTOMER_SQL_LITERAL",json.dumps(parse(SQL)))

    def test_cli_outputs_and_refuses_overwrite(self):
        from lightyear_data.tsql_procedures.cli import main
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); root=base/"input"; root.mkdir()
            pairs=self._inputs(root)
            manifest=base/"pairs.json"; manifest.write_text(json.dumps(pairs))
            out=base/"out"
            argv=["--root",str(root),"--pairs",str(manifest),"--output",str(out)]
            with patch("lightyear_data.tsql_procedures.inventory.parse",
                       return_value={"status":"unsupported","reason":"unparsed"}),redirect_stdout(io.StringIO()):
                self.assertEqual(0,main(argv))
                original=(out/"inventory.private.json").read_bytes()
                with self.assertRaises(FileExistsError): main(argv)
            self.assertEqual(original,(out/"inventory.private.json").read_bytes())
            self.assertNotIn("CUSTOMER_SECRET",(out/"summary.md").read_text())
            self.assertEqual(1,json.loads((out/"summary.json").read_text())["pair_count"])

    def _inputs(self,root):
        (root/"source.sql").write_text(SQL,encoding="utf-8")
        (root/"twin.sql").write_text("SELECT 'private-literal';",encoding="utf-8")
        return [{"id":"CUSTOMER_SECRET","source":"source.sql","twin":"twin.sql"}]

    def test_every_unparsed_pair_counted_public_summary_redacted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); pairs=self._inputs(root)
            value=inventory(root,pairs,allow_sqlglot=False)
        self.assertEqual(1,value["pair_count"])
        self.assertEqual("unparsed",value["pairs"][0]["reason"])
        public=json.dumps(public_summary(value))+summary_markdown(value)
        for secret in ("CUSTOMER_SECRET","private_proc","private-literal","source.sql"):
            self.assertNotIn(secret,public)
        self.assertEqual({"unsupported":1},public_summary(value)["statuses"])

    def test_invalid_source_counted_as_unparsed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); pairs=self._inputs(root)
            (root/"source.sql").write_bytes(b"\xff")
            value=inventory(root,pairs,allow_sqlglot=False)
        self.assertEqual("unparsed",value["pairs"][0]["reason"])

    def test_missing_unpaired_reused_and_duplicate_inputs_refused(self):
        for mode in ("missing","unpaired","reused","duplicate","escape"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d); pairs=self._inputs(root)
                if mode=="missing": pairs[0]["source"]="absent.sql"
                if mode=="unpaired": (root/"extra.sql").write_text("SELECT 1")
                if mode=="reused": pairs[0]["twin"]="source.sql"
                if mode=="duplicate": pairs.append(dict(pairs[0]))
                if mode=="escape": pairs[0]["source"]="../outside.sql"
                with self.assertRaises(ValueError): inventory(root,pairs,allow_sqlglot=False)

    def test_empty_inventory_refused(self):
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ValueError,"empty-pair"):
            inventory(Path(d),[],allow_sqlglot=False)

    def test_multi_procedure_parser_result_cannot_be_single_pair(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pairs=self._inputs(root)
            with patch("lightyear_data.tsql_procedures.inventory.subprocess.run",
                       return_value=parser_reply(procedure_count=2)):
                value=inventory(root,pairs,("bridge",),allow_sqlglot=False)
        self.assertEqual("requires-explicit-single-procedure-pairing",value["pairs"][0]["reason"])

class CorpusLedgerTests(unittest.TestCase):
    def test_generated_assets_exact_and_hash_bound(self):
        expected=artifacts(ROOT)
        self.assertEqual(260,len(expected))
        for name,raw in expected.items():
            with self.subTest(name=name): self.assertEqual(raw,(ROOT/name).read_bytes())
        manifest=json.loads(expected["data-modernization/tsql-procedures/corpus.json"])
        self.assertEqual(content_hash(manifest),manifest["content_sha256"])
        for row in manifest["procedures"]:
            for asset in row["assets"].values():
                self.assertEqual(hashlib.sha256(expected[asset["path"]]).hexdigest(),asset["sha256"])

    def test_family_closure_and_one_deliberate_mutation_each(self):
        rows=corpus()
        self.assertEqual(42,len(rows))
        self.assertEqual(set(range(1,26)),{r["trap_family"] for r in rows})
        self.assertEqual(42,len({r["id"] for r in rows}))
        for r in rows:
            self.assertTrue(r["mutation"])
            self.assertNotEqual((r["correct_sql"],r["target_setup"]),(r["wrong_sql"],r["wrong_setup"]))
            self.assertEqual(1,len(scan(r["source_sql"])["procedure_names"]))

    def test_expected_labels_are_not_native_results(self):
        m=json.loads((ROOT/"data-modernization/tsql-procedures/corpus.json").read_text())
        for key in ("native_pairs_run","correct_twins_qualified","wrong_twins_killed","signed_native_receipts"):
            self.assertEqual(0,m[key])
        self.assertIsNone(m["coverage_source"])
        self.assertIsNone(m["coverage_target"])
        self.assertTrue(all(r["native_status"]=="not-run" for r in m["procedures"]))

    def test_ambiguous_choices_require_policy(self):
        for r in corpus():
            if r["trap_family"] in (18,25):
                self.assertTrue(r["expected"]["policy_required"])
                self.assertEqual("insufficient-evidence",r["expected"]["correct"])
                self.assertEqual(5,r["cases"][0]["repeated_runs"])

    def test_ledger_retains_107_ase_review_obligations(self):
        value=build_ledger(ROOT)
        self.assertEqual(107,len(value["entries"]))
        self.assertEqual(25,len(value["trap_families"]))
        self.assertFalse(value["inherited_decisions_applied"])
        self.assertFalse(value["sqlserver_native_qualification"])
        self.assertTrue(all(x["decision"] is None for x in value["entries"]))
        self.assertTrue(all(x["classification"]=="policy-decision-required" for x in value["entries"]))
        self.assertEqual(set(COMPATIBILITY_CLASSES),set(value["classifications"]))
        self.assertTrue(validate_ledger(ROOT,value))

    def test_ledger_rejects_unverified_promotion(self):
        value=build_ledger(ROOT);value["entries"][0]["classification"]="exact"
        with self.assertRaisesRegex(ValueError,"unverified-promotion"): validate_ledger(ROOT,value)

class ObservationTests(unittest.TestCase):
    def test_nine_observables_match_is_never_equivalence(self):
        result=compare_observations(observation(),observation(),trap_family=1)
        self.assertTrue(result["observables_match"])
        self.assertEqual("insufficient-evidence",result["procedure_verdict"])
        self.assertFalse(result["native_receipt_verified"])

    def test_unordered_rows_multiset_and_duplicates(self):
        a=observation();b=deepcopy(a);b.result_sets[0]["rows"]=[["b"],["a"],["b"]]
        self.assertTrue(compare_observations(a,b,trap_family=1)["observables_match"])
        b.result_sets[0]["rows"]=[["a"],["b"]]
        self.assertFalse(compare_observations(a,b,trap_family=1)["observables_match"])

    def test_ordered_rows_preserve_order(self):
        a=observation();b=deepcopy(a)
        a.result_sets[0]["ordered"]=b.result_sets[0]["ordered"]=True
        b.result_sets[0]["rows"].reverse()
        self.assertFalse(compare_observations(a,b,trap_family=1)["observables_match"])

    def test_all_other_observables_are_compared(self):
        mutations={"output_parameters":{"out":2},"return_code":2,
            "error":{"category":"runtime"},"side_effects":dict(observation().side_effects,identity_sequence_state={"seq":2}),
            "transaction":{"outcome":"rolled-back"},"row_count_messages":[1],
            "informational_messages":[{"message":"x"}],"temp_objects":["scratch"]}
        for name,value in mutations.items():
            with self.subTest(name=name):
                result=compare_observations(observation(),observation(**{name:value}),trap_family=11)
                self.assertIn(name,[d["observable"] for d in result["differences"]])
                for d in result["differences"]:
                    self.assertIn(d["class"],COMPATIBILITY_CLASSES)
                    self.assertEqual(11,d["trap_family"])

    def test_missing_table_inventory_identity_or_scope_refused(self):
        for effects in ({"all_user_tables_captured":True},
                        {"all_user_tables_captured":True,"table_inventory":[],"tables":{}},
                        dict(observation().side_effects,table_inventory=["dbo.t","trigger.t"])):
            with self.subTest(effects=effects),self.assertRaises(ValueError):
                observation(side_effects=effects).validate()

    def test_bad_observation_and_canonical_type(self):
        with self.assertRaises(ValueError): observation(elapsed_seconds=float("nan")).validate()
        a=observation();a.result_sets[0]["columns"][0]["canonical_type"]="made-up"
        with self.assertRaisesRegex(ValueError,"canonical-result-type"): a.validate()

    def test_policy_even_for_matching_ambiguous_rows(self):
        for family in (18,25):
            r=compare_observations(observation(),observation(),trap_family=family)
            self.assertEqual("policy-decision-required",r["differences"][0]["class"])

    def test_keyed_delta_and_duplicate_key_failure(self):
        r=table_delta([{"id":1,"n":2}],[{"id":1,"n":3},{"id":2,"n":4}],("id",))
        self.assertEqual(1,len(r["changed"]));self.assertEqual(1,len(r["inserted"]))
        with self.assertRaisesRegex(ValueError,"duplicate-primary-key"):
            table_delta([], [{"id":1},{"id":1}],("id",))

    def test_keyless_delta_preserves_duplicate_multiplicity(self):
        r=table_delta([{"v":1}],[{"v":1},{"v":1}])
        self.assertEqual(1,r["inserted"][0][1])
        self.assertEqual([],r["deleted"])

class CoverageAdapterTests(unittest.TestCase):
    def test_both_engine_thresholds_required(self):
        self.assertTrue(coverage_gate(COVERAGE,COVERAGE)["eligible"])
        self.assertFalse(coverage_gate(COVERAGE,replace(COVERAGE,statements_hit=8))["eligible"])
        self.assertFalse(coverage_gate(replace(COVERAGE,branches_hit=3),COVERAGE)["eligible"])
        self.assertFalse(coverage_gate(COVERAGE,None)["eligible"])

    def test_error_paths_not_replaced_by_percentage(self):
        c=replace(COVERAGE,hit_error_paths=())
        self.assertFalse(coverage_gate(c,COVERAGE)["eligible"])
        self.assertEqual(["catch"],coverage_gate(c,COVERAGE)["lanes"]["source"]["missing_error_paths"])

    def test_coverage_boundary_and_invalid_counts(self):
        c=replace(COVERAGE,statements_hit=9,branches_hit=4)
        self.assertTrue(coverage_gate(c,c)["eligible"])
        self.assertFalse(coverage_gate(c,c)["native_provenance_checked"])
        for c in (replace(COVERAGE,statements_hit=11),replace(COVERAGE,statements_total=0),
                  replace(COVERAGE,collector=""),replace(COVERAGE,hit_error_paths=("unknown",))):
            with self.subTest(c=c),self.assertRaises(ValueError): c.validate()

    def test_offline_adapters_never_dispatch_a_process(self):
        profile=EngineProfile("pending","unverified",None,None,"unverified",{})
        with patch("subprocess.run",side_effect=AssertionError("must not dispatch")):
            for adapter in (SqlServerAdapter(profile),PostgresAdapter(profile)):
                for method,args in (("provision",({},{})),("reset",({}, "state")),
                    ("call",({},"p",{},{})),("capture_state",({},[])),("coverage",({},"p"))):
                    with self.subTest(adapter=type(adapter).__name__,method=method),self.assertRaises(NativeExecutionUnavailable):
                        getattr(adapter,method)(*args)

    def test_reused_gates_and_verdict_vocabulary(self):
        self.assertIn("transaction-and-exception-behavior",QUALIFICATION_GATES)
        self.assertEqual({"equivalent","divergent","insufficient-evidence","unsupported"},set(VERDICTS))

if __name__=="__main__": unittest.main()
