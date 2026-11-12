"""CI-only synthetic composition tests: no network, compiler, cases or credentials."""
from contextlib import redirect_stdout
from dataclasses import replace
import copy
import io
import json
import tempfile
import zipfile
import stat
import struct
import warnings
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from lightyear_factory import intcalc_preview_composition as c

H = "a" * 64
def make_bundle(members=None):
    members = members if members is not None else [("README.txt", b"synthetic public context"),
                                                  ("source/public.txt", "public UTF-8 caf\u00e9".encode())]
    stream = io.BytesIO()
    files = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, raw in members:
                info = name if isinstance(name, zipfile.ZipInfo) else zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, raw)
                files[info.filename] = {"bytes": len(raw), "sha256": c.digest(raw)}
    allowlist = {"schema": "full-intcalc-model-allowlist/1", "files": files,
                 "model_inputs_only": True, "candidate_and_oracle_execution": False}
    return stream.getvalue(), c.canonical(allowlist)


PUBLIC, ALLOWLIST = make_bundle()


def packet():
    value = {name: H for name in c.HASH_FIELDS}
    value.update(schema="full-intcalc-composition-packet/1", controller_platform="darwin/arm64",
        runtime_platform="linux/arm64", emulation=False, byte_policy_sha256="STRICT",
        run_budget_seconds=8100, cap_microdollars=c.CAP, context_sha256=c.digest(PUBLIC),
        allowlist_sha256=c.digest(ALLOWLIST), feedback_schema_sha256=c.FEEDBACK_HASH,
        named_limit_sha256=c.LIMIT_HASH,
        prerequisites={name: {"status": "PRESENT", "evidence_sha256": H} for name in c.PREREQUISITES})
    return value


class FakePorts:
    """Trusted synthetic ports, never import transport or call a provider."""
    def __init__(self, outcomes=None):
        self.events = []
        self.records = {}
        self.projections = {}
        self.outcomes = outcomes or [("MATCH",) * 10]
        self.authorized = True
        self.now = 123456.789012345
        self.packet = packet()
        self.fail_role = None
        self.interrupt = None
        self.mutate_build = lambda value: value
        self.mutate_gate = lambda value: value
        self.mutate_evidence = lambda value: value
        self.proof_hash = H
        self.proof_tokens = 100000
        self.drift_projection = False
        self.record_failure = False
    def authenticate(self, value):
        self.events.append("authenticate")
        self.packet = value
        return self.authorized
    def admit(self, value):
        self.events.append("admit")
        return SimpleNamespace(started_monotonic=self.now, deadline_monotonic=self.now + 8100,
            public_receipt=lambda: {"schema": c.SCHEMA, "scope": c.SCOPE, "qualified": False,
                "production_controller_receipt": False, "status": "ADMITTED_ONLY", "binding_sha256": H})
    def transport(self, admission):
        self.events.append("transport")
        return self
    def record_once(self, name, value):
        if self.record_failure:
            raise OSError("synthetic private ledger diagnostic")
        if name in self.records:
            raise AssertionError("duplicate record")
        self.records[name] = copy.deepcopy(value)
    def prove_request(self, role, projection):
        self.projections[role] = copy.deepcopy(projection)
        if self.drift_projection:
            projection["input"] = "unapproved"
        return SimpleNamespace(projection=projection, projection_sha256=c.digest(c.canonical(projection)),
            bound_proof_sha256=self.proof_hash, public_context_approval_sha256=H,
            token_upper_bound=self.proof_tokens)
    def complete(self, role, request):
        self.events.append(role)
        if self.interrupt:
            raise self.interrupt
        if role == self.fail_role:
            raise ValueError("PRIVATE verifier detail must never be returned")
        artifact = {"source": "public class Main {}"} if role.startswith("builder") else {"text": "synthetic public note"}
        evidence = {"role": role, "status": "COMPLETED", "observed_tier": "flex", "model": c.MODEL,
                    "retries": 0, "attempts": 1, "artifact_sha256": c.digest(c.canonical(artifact))}
        return artifact, self.mutate_evidence(evidence)
    def build(self, number, source, window):
        self.events.append("build" + str(number))
        if window.deadline_monotonic > min(self.now + 600, window.original_deadline_monotonic - 15):
            raise AssertionError("phase budget exceeded")
        return self.mutate_build(c.BuildResult(c.digest(source.encode()), H, "linux/arm64", H, H, H, H, H, H, True, True))
    def gate(self, number, built, window):
        self.events.append("gate" + str(number))
        return self.mutate_gate(c.GateResult(H, H, H, H, "linux/arm64", "STRICT",
                                             self.outcomes[number-1], H, True, True))


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.context_patch = patch.object(c, "CONTEXT_HASH", c.digest(PUBLIC))
        self.allowlist_patch = patch.object(c, "ALLOWLIST_HASH", c.digest(ALLOWLIST))
        self.context_patch.start()
        self.allowlist_patch.start()
        self.addCleanup(self.context_patch.stop)
        self.addCleanup(self.allowlist_patch.stop)
        self.ports = FakePorts()
        self.binding = packet()
    def session(self):
        return c.Composition(self.binding, PUBLIC, ALLOWLIST, self.ports, clock=lambda: self.ports.now)
    def stopped(self):
        with self.assertRaises(c.CompositionRefused) as raised:
            self.session().run()
        self.assertEqual(str(raised.exception), "composition-stopped-no-resume")
        result = self.ports.records.get("composition-stopped.json")
        if result:
            self.assertEqual(result["status"], "STOPPED")
            c.verify_result(result)
        return result
    def test_first_success_stops_early(self):
        result = self.session().run()
        self.assertEqual(self.ports.events, ["authenticate", "admit", "transport", "planner", "builder-attempt1", "build1", "gate1"])
        self.assertEqual(result["status"], "MATCH_FIRST_ATTEMPT")
        self.assertEqual(result["reserved_microdollars"], 2 * c.SLOT_HOLD)
        self.assertFalse(c.verify_result(result)["qualified"])
    def test_repair_success_preserves_first_failure(self):
        self.ports.outcomes = [("DIFFERENT",) + ("MATCH",) * 9, ("MATCH",) * 10]
        result = self.session().run()
        self.assertEqual(result["status"], "MATCH_AFTER_REPAIR")
        self.assertEqual(result["attempts"][0]["feedback"]["verdict_counts"]["DIFFERENT"], 1)
        self.assertEqual(result["roles"]["analysis-attempt2"], "NOT_RUN")
        c.verify_result(result)
    def test_two_failures_exact_five_roles(self):
        self.ports.outcomes = [("DIFFERENT",) * 10, ("REFUSAL_NOT_OBSERVED",) * 10]
        result = self.session().run()
        self.assertEqual(result["status"], "CANDIDATE_FAIL")
        self.assertEqual(result["reserved_microdollars"], c.CAP)
        self.assertEqual(result["feedback_observations"], 2)
        self.assertEqual(self.ports.events[-1], "analysis-attempt2")
        c.verify_result(result)
    def test_feedback_reused_without_case_fields(self):
        self.ports.outcomes = [("DIFFERENT",) * 10, ("MATCH",) * 10]
        self.session().run()
        first = json.loads(self.ports.projections["analysis-attempt1"]["input"])
        repair = json.loads(self.ports.projections["builder-repair1"]["input"])
        self.assertEqual(c.canonical(first["feedback"]), c.canonical(repair["feedback"]))
        self.assertEqual(set(first["feedback"]), {"schema", "verdict_counts"})
        self.assertEqual(set(first), {"public_context", "generated_artifacts", "feedback"})
        self.assertNotIn("receipt_sha256", self.ports.projections["analysis-attempt1"]["input"])
    def test_expected_refusals_are_success(self):
        self.ports.outcomes = [("EXPECTED_REFUSAL",) * 10]
        self.assertEqual(self.session().run()["status"], "MATCH_FIRST_ATTEMPT")
    def test_execution_failure_is_candidate_failure(self):
        self.ports.outcomes = [("EXECUTION_FAILED",) * 10, ("MATCH",) * 10]
        self.assertEqual(self.session().run()["status"], "MATCH_AFTER_REPAIR")
    def test_output_contract_violation_is_candidate_failure(self):
        self.ports.outcomes = [("OUTPUT_CONTRACT_VIOLATION",) * 10, ("MATCH",) * 10]
        self.assertEqual(self.session().run()["status"], "MATCH_AFTER_REPAIR")
    def test_timeout_never_repairs(self):
        self.ports.outcomes = [("TIMEOUT",) + ("NOT_RUN",) * 9]
        self.stopped()
        self.assertNotIn("analysis-attempt1", self.ports.events)
    def test_fault_never_repairs(self):
        self.ports.outcomes = [("FAULT",) + ("MATCH",) * 9]
        self.stopped()
        self.assertNotIn("builder-repair1", self.ports.events)
    def test_not_run_never_repairs(self):
        self.ports.outcomes = [("NOT_RUN",) + ("MATCH",) * 9]
        self.stopped()
    def test_incomplete_case_inventory_refused(self):
        self.ports.outcomes = [("MATCH",) * 9]
        self.stopped()
    def test_unknown_verdict_refused(self):
        self.ports.outcomes = [("UNKNOWN",) * 10]
        self.stopped()
    def test_uncertain_gate_cleanup_stops(self):
        self.ports.mutate_gate = lambda value: replace(value, cleanup_confirmed=False)
        self.stopped()
        self.assertNotIn("analysis-attempt1", self.ports.events)
    def test_uncertain_build_cleanup_stops_before_gate(self):
        self.ports.mutate_build = lambda value: replace(value, cleanup_confirmed=False)
        self.stopped()
        self.assertNotIn("gate1", self.ports.events)
    def test_build_source_mismatch_stops(self):
        self.ports.mutate_build = lambda value: replace(value, source_sha256="b" * 64)
        self.stopped()
    def test_build_tool_hash_mismatch_stops(self):
        self.ports.mutate_build = lambda value: replace(value, javac_sha256="b" * 64)
        self.stopped()
    def test_build_platform_mismatch_stops(self):
        self.ports.mutate_build = lambda value: replace(value, runtime_platform="linux/amd64")
        self.stopped()
    def test_gate_artifact_mismatch_stops(self):
        self.ports.mutate_gate = lambda value: replace(value, artifact_sha256="b" * 64)
        self.stopped()
    def test_gate_case_manifest_mismatch_stops(self):
        self.ports.mutate_gate = lambda value: replace(value, case_manifest_sha256="b" * 64)
        self.stopped()
    def test_byte_policy_mismatch_stops(self):
        self.ports.mutate_gate = lambda value: replace(value, byte_policy_sha256="b" * 64)
        self.stopped()
    def test_transport_fault_consumes_slot_and_redacts(self):
        self.ports.fail_role = "planner"
        result = self.stopped()
        self.assertEqual(result["reserved_microdollars"], c.SLOT_HOLD)
        self.assertEqual(result["roles"]["planner"], "FAILED_CONSUMED")
        self.assertNotIn("PRIVATE", c.canonical(result).decode())
    def test_keyboard_interrupt_preserved_and_recorded(self):
        self.ports.interrupt = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.session().run()
        self.assertEqual(self.ports.records["composition-stopped.json"]["reserved_microdollars"], c.SLOT_HOLD)
    def test_system_exit_preserved_and_recorded(self):
        self.ports.interrupt = SystemExit(8)
        with self.assertRaises(SystemExit) as raised:
            self.session().run()
        self.assertEqual(raised.exception.code, 8)
        self.assertIn("composition-stopped.json", self.ports.records)
    def test_mutated_request_refused_before_send(self):
        self.ports.drift_projection = True
        self.stopped()
        self.assertNotIn("planner", self.ports.events)
    def test_missing_token_proof_refused_before_send(self):
        self.ports.proof_hash = "b" * 64
        self.stopped()
        self.assertNotIn("planner", self.ports.events)
    def test_token_bound_boolean_refused(self):
        self.ports.proof_tokens = True
        self.stopped()
    def test_non_flex_evidence_refused(self):
        self.ports.mutate_evidence = lambda value: dict(value, observed_tier="default")
        self.stopped()
    def test_missing_authority_no_admission(self):
        self.ports.authorized = False
        self.stopped()
        self.assertEqual(self.ports.events, ["authenticate"])
    def test_missing_prerequisite_no_authority_or_admission(self):
        self.binding["prerequisites"]["count_billing"] = {"status": "MISSING", "evidence_sha256": None}
        self.stopped()
        self.assertEqual(self.ports.events, [])
    def test_prepare_present_is_not_authority(self):
        result = c.prepare(self.binding)
        self.assertEqual(result["missing"], [])
        self.assertFalse(result["admission_ready"])
        self.assertFalse(result["authority_authenticated"])
    def test_packet_rejects_unknown_or_false_platform(self):
        for value in (None, "linux/amd64", "linux/unknown"):
            binding = copy.deepcopy(self.binding)
            binding["runtime_platform"] = value
            with self.assertRaises(c.CompositionRefused):
                c.validate_packet(binding)
    def test_packet_rejects_emulation(self):
        self.binding["emulation"] = True
        with self.assertRaises(c.CompositionRefused):
            self.session()
    def test_packet_copy_prevents_later_mutation(self):
        session = self.session()
        self.binding["byte_policy_sha256"] = "b" * 64
        self.assertEqual(session.run()["status"], "MATCH_FIRST_ATTEMPT")
    def test_public_bundle_hash_mismatch_refused(self):
        with self.assertRaises(c.CompositionRefused):
            c.Composition(self.binding, b"other", ALLOWLIST, self.ports)
    def test_no_resume_same_instance(self):
        session = self.session()
        session.run()
        with self.assertRaises(c.CompositionRefused) as raised:
            session.run()
        self.assertEqual(str(raised.exception), "session-consumed")
    def test_fractional_monotonic_start_accepted(self):
        self.assertEqual(self.session().run()["status"], "MATCH_FIRST_ATTEMPT")
    def test_phase_timeout_stops_without_repair(self):
        original = self.ports.build
        def late(*args):
            result = original(*args)
            self.ports.now += 601
            return result
        self.ports.build = late
        self.stopped()
        self.assertNotIn("gate1", self.ports.events)
    def test_clock_regression_stops(self):
        original = self.ports.build
        def backwards(*args):
            result = original(*args)
            self.ports.now -= 1
            return result
        self.ports.build = backwards
        self.stopped()
    def test_ledger_failure_never_success(self):
        self.ports.record_failure = True
        self.stopped()
        self.assertNotIn("planner", self.ports.events)
    def test_feedback_rejects_boolean(self):
        value = c.feedback(("MATCH",) * 10)
        value["verdict_counts"]["DIFFERENT"] = False
        with self.assertRaises(c.CompositionRefused):
            c.validate_feedback(value)
    def test_feedback_rejects_extra_case_field(self):
        value = c.feedback(("MATCH",) * 10)
        value["case_name"] = "synthetic"
        with self.assertRaises(c.CompositionRefused):
            c.validate_feedback(value)
    def test_verify_cannot_promote(self):
        result = self.session().run()
        result["qualified"] = True
        with self.assertRaises(c.CompositionRefused):
            c.verify_result(result)
    def test_verify_rejects_cost_mutation(self):
        result = self.session().run()
        result["reserved_microdollars"] = 0
        with self.assertRaises(c.CompositionRefused):
            c.verify_result(result)
    def test_verify_rejects_extra_analysis_after_success(self):
        result = self.session().run()
        result["roles"]["analysis-attempt1"] = "COMPLETED"
        result["reserved_microdollars"] += c.SLOT_HOLD
        with self.assertRaises(c.CompositionRefused):
            c.verify_result(result)
    def test_verify_rejects_third_observation(self):
        result = self.session().run()
        result["attempts"] *= 3
        result["feedback_observations"] = 3
        with self.assertRaises(c.CompositionRefused):
            c.verify_result(result)
    def test_verify_does_not_claim_authentication(self):
        result = c.verify_result(self.session().run())
        self.assertFalse(result["authentication_verified"])
    def test_strict_json_encoding_duplicates_and_floats(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":1e400}', b'{"x":NaN}', '{}'.encode('utf-16')):
            with self.assertRaises(c.CompositionRefused):
                c.strict_json(raw)
    def test_cli_prepare_exact_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public.json"
            raw = c.canonical(self.binding)
            path.write_bytes(raw)
            output = io.StringIO()
            with redirect_stdout(output):
                code = c.main(["prepare", "--input", str(path), "--sha256", c.digest(raw)])
            self.assertEqual(code, 0)
            self.assertFalse(json.loads(output.getvalue())["admission_ready"])
    def test_cli_wrong_hash_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public.json"
            path.write_bytes(c.canonical(self.binding))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(["prepare", "--input", str(path), "--sha256", H]), 2)
    def test_cli_admit_run_and_qualify_refuse_without_reading(self):
        for command in (["admit"], ["run"], ["verify", "--qualify"]):
            with patch.object(Path, "read_bytes", side_effect=AssertionError("must not load any file")):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(c.main(command), 2)



class ArchiveAndRoleTests(unittest.TestCase):
    def construct(self, archive, allowlist):
        # Patch only the synthetic pair's approved hashes, never extraction,
        # decoding, ZipFile, per-member validation or the context constructor.
        with patch.object(c, "CONTEXT_HASH", c.digest(archive)), patch.object(c, "ALLOWLIST_HASH", c.digest(allowlist)):
            bound = packet()
            bound["context_sha256"] = c.digest(archive)
            bound["allowlist_sha256"] = c.digest(allowlist)
            return c.Composition(bound, archive, allowlist, FakePorts())
    def refused(self, archive, allowlist, code=None):
        with self.assertRaises(c.CompositionRefused) as caught:
            self.construct(archive, allowlist)
        if code:
            self.assertEqual(str(caught.exception), code)
    def test_real_zip_decodes_to_name_text_mapping(self):
        session = self.construct(PUBLIC, ALLOWLIST)
        self.assertEqual(session._context, {"README.txt": "synthetic public context", "source/public.txt": "public UTF-8 caf\u00e9"})
    def test_payload_uses_mapping_and_fixed_role_instructions(self):
        with patch.object(c, "CONTEXT_HASH", c.digest(PUBLIC)), patch.object(c, "ALLOWLIST_HASH", c.digest(ALLOWLIST)):
            ports = FakePorts([( "DIFFERENT",) * 10, ("DIFFERENT",) * 10])
            c.Composition(packet(), PUBLIC, ALLOWLIST, ports, clock=lambda: ports.now).run()
        for role, projection in ports.projections.items():
            self.assertEqual(projection["instructions"], c.ROLE_INSTRUCTIONS[role])
            self.assertEqual(json.loads(projection["input"])["public_context"],
                             {"README.txt": "synthetic public context", "source/public.txt": "public UTF-8 caf\u00e9"})
    def test_role_table_bound_and_builder_contract_explicit(self):
        self.assertEqual(c.digest(c.canonical(c.ROLE_INSTRUCTIONS)), c.ROLE_INSTRUCTIONS_SHA256)
        self.assertEqual(set(c.ROLE_INSTRUCTIONS), set(c.ROLES))
        for role in ("builder-attempt1", "builder-repair1"):
            for phrase in ('"source"', "complete text", "Java 21", "Main.java", "default-package public class Main", "only the JDK", "not a patch or diff"):
                self.assertIn(phrase, c.ROLE_INSTRUCTIONS[role])
        for role in ("planner", "analysis-attempt1", "analysis-attempt2"):
            self.assertIn('"text"', c.ROLE_INSTRUCTIONS[role])
            self.assertTrue("plain text" in c.ROLE_INSTRUCTIONS[role] or "plain-text" in c.ROLE_INSTRUCTIONS[role])
    def test_role_table_drift_refuses_before_send(self):
        with patch.object(c, "CONTEXT_HASH", c.digest(PUBLIC)), patch.object(c, "ALLOWLIST_HASH", c.digest(ALLOWLIST)):
            ports = FakePorts()
            with patch.dict(c.ROLE_INSTRUCTIONS, {"planner": "unreviewed"}):
                with self.assertRaises(c.CompositionRefused):
                    c.Composition(packet(), PUBLIC, ALLOWLIST, ports, clock=lambda: ports.now).run()
            self.assertNotIn("planner", ports.events)
    def test_missing_member_refused(self):
        archive, _ = make_bundle([("README.txt", b"synthetic public context")])
        self.refused(archive, ALLOWLIST, "context-exact-member-set")
    def test_extra_member_refused(self):
        archive, _ = make_bundle([("README.txt", b"synthetic public context"), ("source/public.txt", "public UTF-8 caf\u00e9".encode()), ("extra.txt", b"extra")])
        self.refused(archive, ALLOWLIST, "context-exact-member-set")
    def test_member_size_mismatch_refused(self):
        allowlist = json.loads(ALLOWLIST)
        allowlist["files"]["README.txt"]["bytes"] += 1
        self.refused(PUBLIC, c.canonical(allowlist), "context-member-size")
    def test_member_hash_mismatch_refused(self):
        allowlist = json.loads(ALLOWLIST)
        allowlist["files"]["README.txt"]["sha256"] = "0" * 64
        self.refused(PUBLIC, c.canonical(allowlist), "context-member-hash")
    def test_duplicate_member_refused(self):
        self.refused(*make_bundle([("README.txt", b"a"), ("README.txt", b"a")]), code="context-duplicate-member")
    def test_directory_entry_refused(self):
        self.refused(*make_bundle([("folder/", b"")]), code="context-member-name")
    def test_directory_mode_refused(self):
        info = zipfile.ZipInfo("README.txt")
        info.create_system = 3
        info.external_attr = (stat.S_IFDIR | 0o700) << 16
        self.refused(*make_bundle([(info, b"public")]), code="context-nonregular-member")
    def test_symlink_mode_refused(self):
        info = zipfile.ZipInfo("README.txt")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o700) << 16
        self.refused(*make_bundle([(info, b"public")]), code="context-nonregular-member")
    def test_encrypted_flag_refused(self):
        archive, allowlist = make_bundle([("README.txt", b"public")])
        raw = bytearray(archive)
        for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            position = raw.index(signature) + offset
            struct.pack_into("<H", raw, position, struct.unpack_from("<H", raw, position)[0] | 1)
        self.refused(bytes(raw), allowlist, "context-encrypted-member")
    def test_traversal_refused(self):
        for name in ("../public.txt", "a/../public.txt", "./public.txt", "a//public.txt"):
            with self.subTest(name=name):
                self.refused(*make_bundle([(name, b"public")]), code="context-member-name")
    def test_absolute_name_refused(self):
        for name in ("/public.txt", "C:/public.txt", "\\host\\public.txt"):
            with self.subTest(name=name):
                self.refused(*make_bundle([(name, b"public")]), code="context-member-name")
    def test_non_utf8_member_refused(self):
        self.refused(*make_bundle([("README.txt", b"\xff")]), code="invalid-public-context-archive")
    def test_total_uncompressed_bound_refused(self):
        self.refused(*make_bundle([("a.txt", b"a" * 70000), ("b.txt", b"b" * 70000)]), code="context-total-size")
    def test_individual_member_bound_refused(self):
        self.refused(*make_bundle([("a.txt", b"a" * (c.MAX_CONTEXT_TOTAL + 1))]), code="context-member-metadata")
    def test_archive_input_bound_refused(self):
        self.refused(b"x" * (c.MAX_CONTEXT_ARCHIVE + 1), ALLOWLIST, "context-archive-size")
    def test_member_count_bound_refused(self):
        self.refused(*make_bundle([(str(i)+".txt", b"public") for i in range(c.MAX_CONTEXT_MEMBERS + 1)]), code="context-member-count")
    def test_boolean_member_size_refused(self):
        value = json.loads(ALLOWLIST)
        value["files"]["README.txt"]["bytes"] = True
        self.refused(PUBLIC, c.canonical(value), "context-member-metadata")
    def test_malformed_zip_refused(self):
        self.refused(b"not a zip", ALLOWLIST, "invalid-public-context-archive")
    def test_non_utf8_allowlist_refused(self):
        self.refused(PUBLIC, b"\xff", "invalid-json")
    def test_allowlist_context_scope_refused(self):
        value = json.loads(ALLOWLIST)
        value["candidate_and_oracle_execution"] = True
        self.refused(PUBLIC, c.canonical(value), "context-allowlist-schema")


if __name__ == "__main__":
    unittest.main()
