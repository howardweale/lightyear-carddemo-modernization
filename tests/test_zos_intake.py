"""Only disposable copies of the pinned public rehearsal are used here."""

import copy
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lightyear_mainframe.records import (
    DecodeError,
    decode_text_lines,
    load_copybook,
    to_ascii_fixed,
    from_ascii_fixed,
)
from lightyear_mainframe.source import sha
from lightyear_mainframe.zos_bindings import (
    ROOT,
    load_bindings,
    dataset_binding,
    compare_jcl,
)
from lightyear_mainframe.zos_bridge import (
    prepare,
    run_candidate,
    verdict,
    replay,
    approved_paths,
)
from lightyear_mainframe.zos_compare import compare_runs, delta, compare_records
from lightyear_mainframe.zos_evidence import (
    Signer,
    initialize_key,
    read_json,
    verify_arrival,
    load_run,
    confined,
)
from lightyear_mainframe.zos_intake import intake, decode_run
from lightyear_mainframe.zos_logs import observe
from lightyear_mainframe.zos_rehearsal import bridge_self_test, verify_fixtures
from lightyear_mainframe.zos_cli import main
from lightyear_control_tower.decisions import canonical, verify_envelope
from lightyear_control_tower.kinds import default_registry
from lightyear_control_tower.requests import RequestInbox

FIXTURE = ROOT / "tests/mainframe/fixtures/arrival-rehearsal"
JAR = ROOT / "candidate-java/target/carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"


class IntakeCase(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work/zos-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.tmp.name)
        self.addCleanup(self.cleanup)
        self.key = self.root / "authority.pem"
        self.pub = initialize_key(self.key)
        self.signer = Signer(self.key)
        self.delivery = self.root / "delivery"
        shutil.copytree(FIXTURE, self.delivery)
        self.arrivals = self.root / "arrivals"
        self.patcher = patch("lightyear_mainframe.zos_evidence.ARRIVALS", self.arrivals)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def cleanup(self):
        # Only the test's verified temporary subtree; originals were made read-only.
        self.assertTrue(
            self.root.resolve().is_relative_to((ROOT / "work/zos-tests").resolve())
        )
        for p in self.root.rglob("*"):
            if p.is_file() and not p.is_symlink():
                p.chmod(stat.S_IREAD | stat.S_IWRITE)
        self.tmp.cleanup()

    def first(self):
        return self.delivery / "INTCALC-run1-2026-10-05"

    def freeze(self):
        arrival, result = intake(self.delivery, "public test fixture", self.signer)
        return arrival, sorted((arrival / "runs").iterdir()), result

    def codes(self):
        arrival, runs, result = self.freeze()
        return {x["code"] for x in read_json(arrival / "intake.json")["findings"]}

    def edit_meta(self, callback):
        path = self.first() / "run.json"
        m = read_json(path)
        callback(m)
        path.write_bytes(canonical(m))

    def test_complete_arrival_is_signed_readonly_and_preserves_every_byte(self):
        arrival, runs, result = self.freeze()
        self.assertEqual(0, result["findings"])
        manifest = verify_arrival(arrival, self.signer.public)
        self.assertEqual(50, len(manifest["files"]))
        for item in manifest["files"]:
            self.assertEqual(
                (self.delivery / item["path"]).read_bytes(),
                (arrival / "original" / item["path"]).read_bytes(),
            )
        self.assertTrue(
            verify_envelope(read_json(arrival / "intake.json"), self.signer.public)
        )
        self.assertEqual(3, len(runs))
        from lightyear_control_tower.carddemo_policy import (
            Inbox,
            registry,
            write_request,
        )

        request_id = write_request(ROOT, "intake-acceptance", {"intake": result})["id"]
        request = Inbox(ROOT, "carddemo-zos", registry()).item(request_id)
        self.assertEqual("intake-acceptance", request["kind"])

    def test_crlf_is_plain_words_finding(self):
        p = self.first() / "before/ACCTFILE.bin"
        p.write_bytes(p.read_bytes() + b"\r\n")
        self.assertIn("text-conversion-crlf", self.codes())

    def test_ascii_conversion_is_detected(self):
        p = self.first() / "before/ACCTFILE.bin"
        p.write_bytes(p.read_bytes().decode("cp037").encode("ascii"))
        self.assertIn("text-conversion-ascii", self.codes())

    def test_missing_job_output(self):
        (self.first() / "job-output.txt").unlink()
        self.assertIn("missing-job-output", self.codes())

    def test_truncated_record(self):
        p = self.first() / "before/ACCTFILE.bin"
        p.write_bytes(p.read_bytes()[:-1])
        self.assertIn("decode-refused", self.codes())

    def test_unknown_file_retained(self):
        (self.first() / "unexpected.dat").write_bytes(b"unknown")
        self.assertIn("unknown-file", self.codes())

    def test_changed_submitted_jcl(self):
        p = self.first() / "submitted.jcl"
        p.write_bytes(
            p.read_bytes().replace(
                b"AWS.M2.CARDDEMO.TCATBALF", b"BAD.M2.CARDDEMO.TCATBALF"
            )
        )
        self.assertIn("jcl-difference", self.codes())

    def test_nonzero_rc_is_finding_not_tool_crash(self):
        (self.first() / "return-codes.txt").write_text(
            "STEP STEP15 PGM=CBACT04C RC=0008\n"
        )
        self.assertIn("step-nonzero", self.codes())

    def test_vb_refusal_includes_resend_instruction(self):
        self.edit_meta(lambda m: m["datasets"][0].update(recfm="VB"))
        arrival, _, _ = self.freeze()
        text = (arrival / "gaps.md").read_text()
        self.assertIn("resend unblocked binary RDW", text)

    def test_missing_image_is_detected(self):
        p = self.first() / "before/TRANSACT.bin"
        p.unlink()
        self.assertIn("missing-image", self.codes())

    def test_missing_input_is_detected(self):
        (self.first() / "before/DISCGRP.bin").unlink()
        self.assertIn("missing-input", self.codes())

    def test_declared_dcb_disagreement_and_length(self):
        self.edit_meta(
            lambda m: next(d for d in m["datasets"] if d["dd"] == "TRANSACT").update(
                lrecl=351
            )
        )
        codes = self.codes()
        self.assertIn("dcb-disagreement", codes)
        self.assertIn("record-length", codes)

    def test_jcl_dcb_fallback_is_marked_derived(self):
        def edit(m):
            for d in m["datasets"]:
                if d["dd"] == "TRANSACT":
                    for key in ("recfm", "lrecl", "blksize"):
                        d.pop(key)

        self.edit_meta(edit)
        _, runs, safe = self.freeze()
        self.assertEqual(0, safe["findings"])
        _, run = load_run(runs[0], self.signer.public)
        origins = next(
            d["format_origins"] for d in run["datasets"] if d["dd"] == "TRANSACT"
        )
        self.assertEqual({"derived-from-submitted-JCL"}, set(origins.values()))

    def test_assumed_code_page_recorded_per_dataset(self):
        self.edit_meta(lambda m: [d.pop("codec") for d in m["datasets"]])
        _, runs, _ = self.freeze()
        _, decoded = decode_run(runs[0], self.signer.public)
        self.assertEqual(
            {"assumed cp037"},
            {
                d["descriptor"]["code_page_observation"]
                for d in decoded["datasets"].values()
            },
        )

    def test_unknown_codepage_refused(self):
        self.edit_meta(lambda m: m["datasets"][0].update(codec="utf-8"))
        self.assertIn("unbound-dataset", self.codes())

    def test_unbound_dataset_and_path_traversal(self):
        self.edit_meta(lambda m: m["datasets"][0].update(file="../other.bin"))
        self.assertIn("unbound-dataset", self.codes())
        with self.assertRaises(ValueError):
            confined(self.root, "../other")

    def test_original_tamper_blocks_all_downstream(self):
        arrival, runs, _ = self.freeze()
        p = arrival / "original/INTCALC-run1-2026-10-05/before/ACCTFILE.bin"
        p.chmod(stat.S_IREAD | stat.S_IWRITE)
        p.write_bytes(p.read_bytes()[:-1])
        with self.assertRaises(ValueError):
            decode_run(runs[0], self.signer.public)

    def test_wrong_trusted_key_is_refused(self):
        _, runs, _ = self.freeze()
        other = self.root / "other.pem"
        initialize_key(other)
        with self.assertRaises(ValueError):
            decode_run(runs[0], Signer(other).public)

    def test_intake_index_tamper_refused(self):
        arrival, runs, _ = self.freeze()
        p = arrival / "intake.json"
        data = read_json(p)
        data["status"] = "accepted"
        p.write_bytes(canonical(data))
        with self.assertRaises(ValueError):
            load_run(runs[0], self.signer.public)

    def test_run_binding_tamper_refused(self):
        _, runs, _ = self.freeze()
        p = runs[0] / "run.json"
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            load_run(runs[0], self.signer.public)

    def test_reject_record_decodes_both_parts(self):
        _, runs, _ = self.freeze()
        _, decoded = decode_run(runs[2], self.signer.public)
        record = decoded["datasets"]["STEP15/DALYREJS/after"]["records"][0]
        self.assertEqual(430, len(bytes.fromhex(record["raw_hex"])))
        names = {f["path"] for f in record["fields"]}
        self.assertIn("REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-ID", names)
        self.assertIn(
            "REJECT-RECORD.WS-VALIDATION-TRAILER.WS-VALIDATION-FAIL-REASON", names
        )
        self.assertIn(
            "REJECT-RECORD.WS-VALIDATION-TRAILER.WS-VALIDATION-FAIL-REASON-DESC", names
        )

    def test_determinism_drafts_but_does_not_apply_rule(self):
        _, runs, _ = self.freeze()
        r = compare_runs(runs[0], runs[1], self.signer.public)
        self.assertEqual([], r["findings"])
        self.assertEqual([], r["normalizations_applied"])
        self.assertEqual(1, len(r["proposals"]))
        self.assertTrue(r["proposals"][0]["still_caught"]["detected"])
        self.assertEqual("draft", r["proposals"][0]["status"])
        field = r["datasets"]["STEP15/TRANSACT"]["fields"][0]
        self.assertEqual("declared-timestamp-pattern", field["kind"])
        self.assertNotIn("2022-07-18", json.dumps(r))
        self.assertNotIn("raw_hex", json.dumps(r))

    def test_other_difference_prevents_any_rule_draft(self):
        p = self.delivery / "INTCALC-run2-2026-10-05/after/ACCTFILE.bin"
        raw = bytearray(p.read_bytes())
        raw[11] = "X".encode("cp037")[0]
        p.write_bytes(raw)
        _, runs, _ = self.freeze()
        r = compare_runs(runs[0], runs[1], self.signer.public)
        self.assertTrue(r["findings"])
        self.assertEqual([], r["proposals"])

    def test_missing_after_record_prevents_timestamp_rule_draft(self):
        path = self.delivery / "INTCALC-run2-2026-10-05/after/ACCTFILE.bin"
        binding = dataset_binding(load_bindings(), "INTCALC", "STEP15", "ACCTFILE")
        path.write_bytes(path.read_bytes()[binding["record_length"] :])
        _, runs, _ = self.freeze()
        result = compare_runs(runs[0], runs[1], self.signer.public)
        self.assertEqual(1, result["datasets"]["STEP15/ACCTFILE"]["deleted"])
        self.assertTrue(result["findings"])
        self.assertEqual([], result["proposals"])

    def test_changed_starting_state_is_not_determinism(self):
        p = self.delivery / "INTCALC-run2-2026-10-05/before/ACCTFILE.bin"
        raw = bytearray(p.read_bytes())
        raw[11] = "X".encode("cp037")[0]
        p.write_bytes(raw)
        _, runs, _ = self.freeze()
        r = compare_runs(runs[0], runs[1], self.signer.public)
        self.assertIn(
            "Before-images differ; same restored starting state is not established.",
            r["findings"],
        )

    def test_delta_additions_and_changed_fields_have_no_values(self):
        p = self.first() / "after/ACCTFILE.bin"
        raw = bytearray(p.read_bytes())
        raw[11] = "X".encode("cp037")[0]
        p.write_bytes(raw)
        _, runs, _ = self.freeze()
        r = delta(runs[0], self.signer.public)
        self.assertGreater(r["datasets"]["STEP15/TRANSACT"]["added"], 0)
        self.assertGreater(r["datasets"]["STEP15/ACCTFILE"]["changed"], 0)
        self.assertNotIn("raw_hex", json.dumps(r))
        self.assertNotIn("2022-07-18", json.dumps(r))

    def test_bridge_binds_before_images_and_explicit_parameters(self):
        _, runs, _ = self.freeze()
        r = prepare(runs[0], self.signer.public, self.signer)
        self.assertEqual("2022071800", r["processing_date"])
        self.assertEqual(4, len(r["files"]))
        self.assertTrue(verify_envelope(r, self.signer.public))
        before = read_json(runs[0] / "run.json")["datasets"]
        hashes = {d["sha256"] for d in before if d["phase"] == "before"}
        self.assertTrue(all(d["source_sha256"] in hashes for d in r["files"].values()))

    def test_missing_timestamp_is_never_inferred_from_after_answers(self):
        self.edit_meta(lambda m: m.pop("candidate_timestamp"))
        _, runs, _ = self.freeze()
        with self.assertRaisesRegex(ValueError, "Explicit candidate timestamp"):
            prepare(runs[0], self.signer.public, self.signer)

    def test_processing_parameter_conflict(self):
        self.edit_meta(lambda m: m.update(processing_date="2022100500"))
        self.assertIn("processing-date-unbound", self.codes())

    def test_invalid_clock_metadata_is_a_finding(self):
        self.edit_meta(lambda m: m.update(processing_date={"unexpected": 1}))
        self.assertIn("parameter-invalid", self.codes())

    def test_system_time_requires_timezone(self):
        self.edit_meta(lambda m: m.update(system_datetime="2026-10-05T10:00:00"))
        self.assertIn("system-time-invalid", self.codes())

    def test_duplicate_dataset_identity_is_refused(self):
        def duplicate(m):
            extra = dict(m["datasets"][0], file="before/duplicate.bin")
            shutil.copyfile(
                self.first() / m["datasets"][0]["file"], self.first() / extra["file"]
            )
            m["datasets"].append(extra)

        self.edit_meta(duplicate)
        self.assertIn("unbound-dataset", self.codes())

    def test_explicit_note_parameters_are_bound_without_after_inference(self):
        self.edit_meta(
            lambda m: [
                m.pop(k)
                for k in ("processing_date", "candidate_timestamp", "system_datetime")
            ]
        )
        p = self.first() / "note.txt"
        p.write_text(
            "PROCESSING_DATE=2022071800\nCANDIDATE_TIMESTAMP=2022-07-18-00.00.00.000000\nSYSTEM_DATETIME=2026-10-05T10:00:00Z\n"
        )
        _, runs, safe = self.freeze()
        self.assertEqual(0, safe["findings"])
        _, run = load_run(runs[0], self.signer.public)
        self.assertEqual(
            "explicit-run-note", run["parameter_sources"]["processing_date"]
        )
        prepare(runs[0], self.signer.public, self.signer)

    def test_tower_normalization_requires_exact_signed_operator_approval(self):
        from datetime import datetime, timezone, timedelta
        from uuid import uuid4
        from lightyear_control_tower.console import provision, ConsoleService

        _, runs, _ = self.freeze()
        compared = compare_runs(runs[0], runs[1], self.signer.public)
        from lightyear_control_tower.carddemo_policy import from_draft, write_request

        rule = from_draft(compared["proposals"][0])
        request_id = write_request(ROOT, "normalization", {"rule": rule})["id"]
        original_request = (
            ROOT / "work/control-tower/requests/carddemo-zos" / (request_id + ".json")
        )
        request = read_json(original_request)
        data = self.root / "console-data"
        data.mkdir()
        for rel in request["evidence"].values():
            target = data / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / rel).read_bytes())
        target = (
            data / "work/control-tower/requests/carddemo-zos" / (request_id + ".json")
        )
        target.parent.mkdir(parents=True)
        target.write_bytes(original_request.read_bytes())
        authority = self.root / "console-authority/authority.json"
        credential = (
            provision(authority, "carddemo-zos", "howard-weale", "Howard Weale")
            .read_text()
            .strip()
        )
        service = ConsoleService(data, authority)
        self.addCleanup(service.close)
        service.grant_roles(
            "howard-weale",
            ["operator", "normalization-approver"],
            reason="Disposable unit test only",
        )
        agent = service.add_identity(
            "zos-intake", "Intake agent", identity_kind="agent"
        )
        service.grant_roles("zos-intake", ["agent"], reason="Disposable fixture")
        agent_token = service.login(agent)["token"]
        token = service.login(credential)["token"]
        initial = service.item(agent_token, request_id)
        service.propose(
            agent_token,
            "rule-proposal",
            dict(
                item_id=request_id,
                bound=initial["bound"],
                request_id=str(uuid4()),
                text="Public fixture proposal",
                rule=rule,
            ),
        )
        item = service.review(token, request_id)
        event = service.decide(
            token,
            dict(
                item_id=request_id,
                bound=item["bound"],
                outcome="approved",
                reason="Disposable test decision",
                named_owner="howard-weale",
                review_after=(
                    datetime.now(timezone.utc).date() + timedelta(days=2)
                ).isoformat(),
                previous_decision_sha256=None,
                request_id=str(uuid4()),
            ),
        )
        proof = service.proof(token, event["content_sha256"])
        bundle = dict(
            schema="zos-approved-rules/1", rules=[dict(rule=rule, proof=proof)]
        )
        head = proof["journal"]["journal_head_sha256"]
        valid = approved_paths(
            bundle,
            service.public_key,
            head,
            compared["runs"][0],
            at=datetime.now(timezone.utc),
        )
        self.assertEqual({rule["dataset"]: [rule["field"]]}, valid)
        with self.assertRaises(ValueError):
            approved_paths(
                bundle,
                service.public_key,
                "0" * 64,
                compared["runs"][0],
                at=datetime.now(timezone.utc),
            )
        broken = copy.deepcopy(bundle)
        broken["rules"][0]["rule"]["field"] = "ACCOUNT-RECORD.ACCT-CURR-BAL"
        with self.assertRaises(ValueError):
            approved_paths(
                broken,
                service.public_key,
                head,
                compared["runs"][0],
                at=datetime.now(timezone.utc),
            )
        with self.assertRaises(ValueError):
            approved_paths(
                bundle, None, None, compared["runs"][0], at=datetime.now(timezone.utc)
            )
        if JAR.is_file():
            from lightyear_mainframe.zos_bridge import compute_verdict

            # The second public run has a planted timestamp delta. Actual Java
            # output differs under exact comparison and matches only after the
            # authenticated Tower rule is supplied. Nothing is overwritten.
            prepare(runs[1], self.signer.public, self.signer)
            run_candidate(runs[1], JAR, self.signer.public, self.signer)
            self.assertEqual(
                "divergent", compute_verdict(runs[1], self.signer.public)["verdict"]
            )
            register = service.register(token)
            result = verdict(
                runs[1],
                self.signer.public,
                self.signer,
                normalizations=register,
                tower_key=service.public_key,
                tower_head=register["journal_head_sha256"],
            )
            self.assertEqual("equivalent", result["verdict"])
            self.assertEqual([], result["base_rules"])
            self.assertEqual(
                "verified",
                replay(runs[1], self.signer.public, tower_key=service.public_key)[
                    "status"
                ],
            )

    @unittest.skipUnless(
        JAR.is_file(), "Build the Java candidate for the public divergence rehearsal"
    )
    def test_divergent_java_verdict_emits_closed_tower_request(self):
        from lightyear_control_tower.carddemo_policy import Inbox, registry

        _, runs, _ = self.freeze()
        prepare(runs[1], self.signer.public, self.signer)
        run_candidate(runs[1], JAR, self.signer.public, self.signer)
        result = verdict(runs[1], self.signer.public, self.signer)
        self.assertEqual("divergent", result["verdict"])
        found = []
        for item in Inbox(ROOT, "carddemo-zos", registry()).queue():
            if item.get("kind") == "difference-disposition":
                summary = read_json(ROOT / item["evidence"]["diagnostic"])
                if summary["diagnostic_sha256"] == result["content_sha256"]:
                    found.append(summary)
        self.assertEqual(1, len(found))
        self.assertGreater(found[0]["changed"], 0)
        self.assertEqual(result["run_sha256"], found[0]["source_sha256"])

    def test_cli_never_echoes_unknown_file_contents(self):
        marker = "PRIVATE_RECORD_VALUE_NEVER_PRINT"
        (self.first() / "unknown.txt").write_text(marker)
        output = io.StringIO()
        with patch("sys.stdout", output):
            rc = main(["intake", str(self.delivery), "--key", str(self.key)])
        self.assertEqual(0, rc)
        self.assertNotIn(marker, output.getvalue())

    def test_arrival_ignore_rule(self):
        p = ROOT / "work/mainframe/arrivals/example/original/secret.bin"
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", str(p)], cwd=ROOT, check=False
        )
        self.assertEqual(0, result.returncode)

    @unittest.skipUnless(
        JAR.is_file(),
        "Build the Java candidate to exercise the public-only subprocess rehearsal",
    )
    def test_java_execution_signed_verdict_offline_replay_and_output_tamper(self):
        _, runs, _ = self.freeze()
        prepare(runs[0], self.signer.public, self.signer)
        r = run_candidate(runs[0], JAR, self.signer.public, self.signer)
        self.assertEqual(0, r["return_code"])
        v = verdict(runs[0], self.signer.public, self.signer)
        self.assertEqual("equivalent", v["verdict"])
        with patch(
            "subprocess.run", side_effect=AssertionError("replay must not execute Java")
        ):
            self.assertEqual("verified", replay(runs[0], self.signer.public)["status"])
        with self.assertRaisesRegex(ValueError, "already attempted"):
            run_candidate(runs[0], JAR, self.signer.public, self.signer)
        p = runs[0] / "candidate/outputs/acctdata.txt"
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "output bytes changed"):
            replay(runs[0], self.signer.public)


class DecoderAndLogTests(unittest.TestCase):
    def test_public_fixture_provenance_and_bridge_exceptions(self):
        verify_fixtures()
        r = bridge_self_test()
        self.assertFalse(r["values_rewritten"])
        self.assertTrue(
            all(d["ebcdic_roundtrip_exact"] for d in r["datasets"].values())
        )

    def test_text_keeps_asa_and_trailing_blanks_all_code_pages(self):
        for codec in ("cp037", "cp500", "cp1140"):
            raw = "1HELLO   ".encode(codec)
            line = decode_text_lines(raw, record_length=9, codec=codec, asa=True)[0]
            self.assertEqual("1", line["fields"][0]["value"])
            self.assertEqual("HELLO   ", line["fields"][1]["value"])
            self.assertEqual(raw.hex(), line["raw_hex"])
        with self.assertRaises(DecodeError):
            decode_text_lines(b"bad", record_length=9)

    def test_html_is_text_not_dom(self):
        line = decode_text_lines("<b>X</b>  ".encode("cp037"), record_length=10)[0]
        self.assertEqual("<b>X</b>  ", line["fields"][0]["value"])

    def test_ascii_bridge_requires_exact_width(self):
        layout = load_copybook(ROOT / "spec/mainframe/copybooks/CVACT03Y.cpy")
        with self.assertRaises(DecodeError):
            from_ascii_fixed(layout, b"123\n")

    def test_all_job_bindings_derive_lengths_and_reject_layout(self):
        b = load_bindings()
        self.assertEqual(
            {"INTCALC", "POSTTRAN", "CREASTMT", "TRANREPT"}, set(b["jobs"])
        )
        self.assertEqual(430, b["datasets"]["reject"]["record_length"])
        for name in (
            "card",
            "account",
            "customer",
            "xref",
            "transaction",
            "daily",
            "balance",
            "disclosure",
            "type",
            "category",
            "statement",
            "html",
            "report",
        ):
            self.assertIn(name, b["datasets"])

    def test_real_ief_formats_and_abend(self):
        r = observe(
            "JOB00321 IEF403I INTCALC - STARTED\nIEF142I INTCALC STEP15 - STEP WAS EXECUTED - COND CODE 0008\nIEF450I INTCALC STEP16 - ABEND=S0C7\n"
        )
        self.assertEqual("INTCALC", r["job_name"])
        self.assertEqual("JOB00321", r["job_id"])
        self.assertEqual(2, len(r["findings"]))
        self.assertIn("start", r["missing"])
        self.assertIsNone(r["steps"][0]["program"])

    def test_fingerprint_binds_compiler_options(self):
        a = observe("", "NUMPROC(PFD) TRUNC(STD) ARITH(COMPAT)")
        b = observe("", "NUMPROC(NOPFD) TRUNC(STD) ARITH(COMPAT)")
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])

    def test_keyed_diff_does_not_confuse_reorder_with_changes(self):
        b = dict(keys=["ID"], timestamp_fields=[])
        r = lambda i, v: dict(
            fields=[
                dict(path="ID", value=i, filler=False),
                dict(path="TEXT", value=v, filler=False),
            ]
        )
        one, two = r("1", "a"), r("2", "b")
        self.assertTrue(compare_records([one, two], [two, one], b)["identical"])
        d = compare_records([one, two], [r("1", "c"), r("3", "x")], b)
        self.assertEqual((1, 1, 1), (d["added"], d["deleted"], d["changed"]))
        with self.assertRaises(ValueError):
            compare_records([one, one], [one], b)


if __name__ == "__main__":
    unittest.main()
