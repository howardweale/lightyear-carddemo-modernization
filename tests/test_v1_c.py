import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import build_public_abend_context
from tools import v1_mac_integration as v


def pinned_context():
    root = v.ROOT / "spec" / "mainframe"
    metadata = v.ROOT / "tests/fixtures/public-feedback/context-metadata.json"
    context = json.loads(metadata.read_bytes())
    for name in ("CVACT01Y.cpy", "CVACT03Y.cpy", "CVTRA01Y.cpy", "CVTRA02Y.cpy", "CVTRA05Y.cpy"):
        context["copybooks/" + name] = (root / "copybooks" / name).read_text(encoding="utf-8")
    for name in ("CBACT04C.cbl", "INTCALC.jcl"):
        context["source/" + name] = (root / "public-source" / name).read_text(encoding="utf-8")
    raw = build_public_abend_context.materialize(v.c.canonical(context))
    if v.c.sha(raw) != v.launcher.CONTEXT:
        raise AssertionError("pinned stage-1 public context")
    return json.loads(raw)


class IntegrationTests(unittest.TestCase):
    def test_wire_measurement_all_roles_and_maximum_components(self):
        public_suite = v.b.adapter.PUBLIC_SUITE
        context = pinned_context()
        self.assertEqual((len(context), len(v.c.canonical(context))), (13, 70765))
        result = v.bounds(context, public_suite)
        self.assertEqual(len(result["slots"]), 12)
        self.assertEqual((result["holds"], result["ceiling"]), (37664000, 37670000))
        self.assertEqual(tuple(row["role"] for row in result["slots"]), v.p4.SEQUENCE)
        for row in result["slots"]:
            self.assertLessEqual(row["bound"], v.c.CAPS[row["role"]])
            self.assertGreaterEqual(row["bound"], max(row["generation_bytes"], row["count_bytes"]))
            if row["role"] in ("analysis", "repair"):
                self.assertEqual(row["parts"]["feedback"], 8192)
                self.assertEqual(row["feedback_string_bytes"], 10706)
        for role in ("analysis", "repair"):
            role_slots = [row for row in result["slots"] if row["role"] == role]
            self.assertEqual(len(role_slots), 5)
            self.assertTrue(any(row["generation_bytes"] > row["token_upper_bound"] for row in role_slots))

        for role, ceiling in (("analysis", 208896), ("repair", 225280)):
            row = result["maximum_history_by_role"][role]
            self.assertEqual((row["parts"]["public_context"], row["parts"]["source"],
                              row["parts"]["plan"], row["parts"]["feedback"]),
                             (70765, 73728, 16384, 8192))
            if role == "repair":
                self.assertEqual(row["parts"]["analysis"], 16384)
            self.assertLessEqual(max(row["generation_bytes"], row["count_bytes"]), row["bound"])
            self.assertLessEqual(row["token_upper_bound"], ceiling)
            self.assertLessEqual(row["bound"], v.c.CAPS[role])
            self.assertLessEqual(ceiling, v.c.CAPS[role])
            print("full-value-feedback-wire", role, json.dumps(row, sort_keys=True))
        self.assertTrue(result["synthetic_oversize_refused_before_count"])

        feedback = v.full_value_feedback("fixture", public_suite)
        oversized = feedback["samples"][-1]["actual"]
        oversized["text"] += "x"
        oversized["bytes"] += 1
        self.assertEqual(len(v.c.canonical(feedback)), 8193)
        with self.assertRaisesRegex(v.c.Refused, "^feedback-cap$"):
            v.s.values.validate(feedback, v.c.sha(b"fixture"), public_suite, "PUBLIC_DIVERGENCE")
        with self.assertRaisesRegex(v.c.Refused, "^feedback-join$"):
            v.full_value_feedback("fixture", "a" * 64)

    def test_maximum_context_and_escaped_wire_ceiling(self):
        context = {"NOTICE": ""}
        context["NOTICE"] = "x" * (98304 - len(v.c.canonical(context)))
        result = v.bounds(context, v.b.adapter.PUBLIC_SUITE)
        for row in result["slots"]:
            self.assertLessEqual(row["bound"], v.c.CAPS[row["role"]])

    def test_pinned_ceiling_against_independently_serialized_escape_extremes(self):
        # Independently serialize the theoretical extremes in both real bodies.
        # These printable ASCII strings upper-bound every validated nested document.
        original = v.p4.requests
        ceilings = []

        def measured(request):
            counted, generated, token_bound, key = original(request)
            self.assertEqual(token_bound, len(v.c.canonical(request)) + 4096)
            sizes = []
            for body in (counted, generated):
                parsed = json.loads(body)
                parts = parsed["input"][0]["content"]
                for i in range(0, len(parts), 2):
                    name = parts[i]["text"]
                    if name in ("feedback", "score_history"):
                        size = 8192 if name == "feedback" else 1024
                        parts[i + 1]["text"] = (chr(34) + chr(92)) * (size // 2)
                sizes.append(len(v.c.canonical(parsed)))
            ceilings.append(max(sizes))
            return counted, generated, token_bound, key

        with patch.object(v.p4, "requests", measured):
            result = v.bounds(pinned_context(), v.b.adapter.PUBLIC_SUITE)
        rows = result["slots"] + list(result["maximum_history_by_role"].values())
        self.assertEqual(ceilings, [row["bound"] for row in rows])

    def test_provider_refusal_through_public_rehearsal_boundary(self):
        for error, expected in ((v.p4.Refused("provider-wire-bound"), "provider-wire-bound"),
                                (v.p4.Refused("private detail"), "provider-unexpected"),
                                (ValueError("private detail"), "v1-operation-refused")):
            with self.subTest(expected=expected), patch.object(v, "rehearse", side_effect=error):
                pipe = Mock()
                with patch.dict(v.os.environ):
                    v.b.isolated_action(pipe, v.run_c, "public", "pin")
                self.assertEqual(json.loads(pipe.send_bytes.call_args.args[0]), {"refusal": expected})

    def test_both_unicode_limits_are_exact(self):
        for a,b in [(8192,16384),(65536,73728)]:
            text=v.maximal_text(a,b)
            self.assertEqual((len(text.encode()),len(v.c.canonical(text))),(a,b))

    def test_synthetic_binding_cannot_be_a_real_preparation(self):
        cfg={"cli_sha256":"a"*64}
        context={"NOTICE":"public"}
        row=v.bind("public fixture",context,cfg,v.b.adapter.PUBLIC_SUITE)
        v.s.validate_value_binding(row,context)
        for field in ("public_suite_sha256", "public_answer_key_sha256"):
            with self.subTest(field=field), self.assertRaisesRegex(v.c.Refused, "^feedback-join$"):
                v.s.validate_value_binding(dict(row, **{field: "b"*64}), context)
        self.assertEqual(row["authority_sha256"],v.c.sha(b"V1 PUBLIC REHEARSAL public fixture no authority"))
        self.assertEqual(row["heldout_commitment_sha256"],v.c.digest(row["pre_run_commitment"]))

    def test_fake_envelope_consumed_by_real_parser(self):
        raw=v.fake_json({"text":"public rehearsal"})
        row=v.p4.response(raw,{"role":"planner"},1000,"text")
        self.assertEqual(row["artifact"],{"text":"public rehearsal"})

    def test_wrong_gate_bytes_refuse_before_creating_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate=v.PublicGate({"public":True},Path(tmp))
            with self.assertRaisesRegex(ValueError,"synthetic-binding"):
                gate.admit(b"{}",float("inf"))
            self.assertFalse(gate.leaf.exists())

    def test_fake_child_refuses_wrong_route(self):
        pipe=Mock()
        pipe.recv_bytes.return_value=b'{"path":"/other","body":"{}","timeout_ms":200}'
        with patch.dict(v.os.environ,{"SYNTHETIC":"1"}),self.assertRaisesRegex(ValueError,"fake-bound"):
            v.scripted_child(pipe,"early-perfect")
        pipe.send_bytes.assert_called_once_with(b"READY")
        pipe.close.assert_called_once()

    def test_uncertain_send_is_consumed_without_response(self):
        pipe=Mock()
        pipe.recv_bytes.return_value=json.dumps(dict(path=v.p4.COUNT,body="{}",timeout_ms=100)).encode()
        with patch.dict(v.os.environ):
            v.scripted_child(pipe,"uncertain-send")
        self.assertEqual([c.args[0] for c in pipe.send_bytes.call_args_list],[b"READY",b"FAULT"])
        self.assertEqual(pipe.recv_bytes.call_count,1)

    def test_deadline_record_on_error(self):
        meter=v.Meter()
        with self.assertRaises(ValueError):
            meter.call("fixture",Mock(side_effect=ValueError),end=v.time.monotonic()+20)
        self.assertGreaterEqual(meter.rows[0]["slack"],0)
        self.assertEqual(meter.rows[0]["simulated_delay_ticks"],0)

    def test_final_sheet_is_exact_fragment_concatenation(self):
        fragments=[(v.ROOT/("spec/V1-"+k+"-SHA256SUMS")).read_bytes() for k in "ABC"]
        self.assertEqual(b"".join(fragments),(v.ROOT/"spec/MAC-REHEARSAL-SHA256SUMS").read_bytes())
        paths=[row.split(b"  ",1)[1] for row in b"".join(fragments).splitlines()]
        self.assertEqual(len(paths),len(set(paths)))

    def test_all_twelve_ipc_slots_pass_production_provider_parser(self):
        messages=[]
        for _ in v.p4.SEQUENCE:
            for path in (v.p4.COUNT,v.p4.GENERATE):
                messages.append(json.dumps(dict(path=path,body="{}",timeout_ms=100)).encode())
        pipe=Mock()
        pipe.recv_bytes.side_effect=messages
        with patch.dict(v.os.environ):
            v.scripted_child(pipe,"five-repairs")
        responses=[item.args[0] for item in pipe.send_bytes.call_args_list]
        self.assertEqual(responses.pop(0),b"READY")
        self.assertEqual(len(responses),24)
        for i,role in enumerate(v.p4.SEQUENCE):
            count,reply=responses[2*i:2*i+2]
            self.assertEqual(int.from_bytes(count[:2],"big"),200)
            self.assertEqual(json.loads(count[2:])["input_tokens"],50)
            self.assertEqual(int.from_bytes(reply[:2],"big"),200)
            field="source" if role in ("builder","repair") else "text"
            accepted=v.p4.response(reply[2:],{"role":role},1000,field)
            self.assertIn(field,accepted["artifact"])
            if field=="source":
                self.assertEqual("unlisted public input" in accepted["artifact"][field],i==11)
        pipe.close.assert_called_once()

    def test_integration_child_reports_module_map_refusal(self):
        pipe = Mock()
        with patch.dict(v.os.environ), patch.object(v.b, "session", return_value=(None, None)), \
                patch.object(v.b, "host_settings", return_value={}), \
                patch.object(v.b.admission, "checkout", return_value={"modules": {}}):
            v.b.isolated_action(pipe, v.run_c, "fixture", "pin")
        pipe.send_bytes.assert_called_once()
        self.assertEqual(json.loads(pipe.send_bytes.call_args.args[0]), {"refusal": "v1-module-map"})
        pipe.close.assert_called_once()
