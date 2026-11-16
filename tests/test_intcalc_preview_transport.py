"""CI-only C2 transport tests. Synthetic public input; no credential or API call."""
import copy
from functools import partial
import json
import multiprocessing
import time
import os
import stat
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from lightyear_factory import intcalc_preview_transport as t


def projection():
    return dict(model=t.MODEL,instructions="Public synthetic instruction",input="Public synthetic input",
        text={"format":{"type":"json_schema","name":"public_fixture","schema":{"type":"object","properties":{"value":{"type":"string"}},"required":["value"],"additionalProperties":False},"strict":True}})


def response():
    return dict(model=t.MODEL,service_tier="flex",status="completed",error=None,incomplete_details=None,
        usage=dict(input_tokens=10,output_tokens=5,total_tokens=15,output_tokens_details={"reasoning_tokens":2}),
        output=[dict(type="message",role="assistant",status="completed",content=[dict(type="output_text",text='{"value":"public"}')])])


class Admission:
    started_monotonic=100.0
    deadline_monotonic=8200.0
    def public_receipt(self):
        return dict(scope="NOT-P5/public-CBACT04C-only",qualified=False,production_controller_receipt=False,
            status="ADMITTED_ONLY",run_budget_seconds=8100,binding_sha256="1"*64,budget_policy_sha256=t.BUDGET_POLICY_SHA256)


class Ledger:
    def __init__(self):self.rows={};self.private={}
    def record_once(self,name,value):
        if name in self.rows:raise t.TransportRefused("consumed")
        self.rows[name]=copy.deepcopy(value)
    def retain_failed_response(self,role,raw):
        if role in self.private:raise t.TransportRefused("private-response-retention-failed")
        self.private[role]=raw


class Wire:
    def __init__(self):
        self.calls=[];self.answers=[(200,t.canonical(dict(object="response.input_tokens",input_tokens=10))),
                                    (200,t.canonical(response()))]
    def post_once(self,path,body,key,end):
        self.calls.append((path,t.strict_json(body),end))
        answer=self.answers.pop(0)
        if isinstance(answer,BaseException):raise answer
        return answer


class PreviewTransportTests(unittest.TestCase):
    def setUp(self):
        self.now=100.0;self.ledger=Ledger();self.wire=Wire()
        self.spend=t.ReviewedSpend("2"*64,"3"*64,True,t.RUN_CAP)
        self.body=projection()
        self.request=t.ReviewedRequest(self.body,t.sha(t.canonical(self.body)),len(t.canonical(self.body))+4096,"4"*64,"5"*64)
        self.client=self.make()
    def make(self,**kwargs):
        values=dict(admission=Admission(),spend=self.spend,ledger=self.ledger,api_key="synthetic-not-a-credential",
            validate_artifact=lambda a,s:type(a) is dict and set(a)=={"value"} and type(a["value"]) is str,
            wire=self.wire,clock=lambda:self.now)
        values.update(kwargs);return t.PreviewTransport(**values)
    def fail(self):
        with self.assertRaises(t.TransportRefused):self.client.complete("planner",self.request)
    def test_post_response_fixed_code_and_private_bytes_without_public_content(self):
        raw = t.canonical(dict(response(), status="incomplete", private_sentinel="NEVER-PUBLIC"))
        self.wire.answers[1] = (200, raw)
        with self.assertRaisesRegex(t.TransportRefused, "slot-failed-consumed-no-retry") as stopped:
            self.client.complete("planner", self.request)
        record = self.ledger.rows["planner-failed.json"]
        self.assertEqual(record["refusal_code"], "incomplete-or-failed-response")
        self.assertEqual(t.public_failure_code(stopped.exception), record["refusal_code"])
        self.assertEqual(record["private_response"], "RETAINED_PRIVATE")
        self.assertEqual(self.ledger.private["planner"], raw)
        self.assertNotIn("NEVER-PUBLIC", json.dumps(self.ledger.rows))
        self.assertIsNone(self.client._generation_raw)
        self.fail()
        self.assertEqual(len(self.wire.calls), 2)

    def test_invalid_response_json_retained_before_parse(self):
        self.wire.answers[1]=(200,b"not-json-private")
        self.fail()
        self.assertEqual(self.ledger.rows["planner-failed.json"]["refusal_code"], "invalid-response-json")
        self.assertEqual(self.ledger.private["planner"],b"not-json-private")

    def test_unknown_exception_text_never_public(self):
        self.client=self.make(validate_artifact=lambda *_: (_ for _ in ()).throw(ValueError("PRIVATE-CONTENT")))
        self.fail()
        self.assertEqual(self.ledger.rows["planner-failed.json"]["refusal_code"],"unexpected-controller-fault")
        self.assertNotIn("PRIVATE-CONTENT",json.dumps(self.ledger.rows))

    def test_retention_failure_keeps_original_code_and_consumption(self):
        self.ledger.retain_failed_response=Mock(side_effect=OSError("PRIVATE-PATH"))
        self.wire.answers[1]=(200,t.canonical(dict(response(),status="incomplete")))
        self.fail()
        row=self.ledger.rows["planner-failed.json"]
        self.assertEqual(row["refusal_code"],"incomplete-or-failed-response")
        self.assertEqual(row["private_response"],"RETENTION_FAILED")
        self.assertEqual(self.client.public_totals()["reserved_microdollars"],1736636)
        self.assertNotIn("PRIVATE-PATH",json.dumps(self.ledger.rows))

    def test_count_failure_and_success_do_not_retain_generation(self):
        self.client.complete("planner",self.request)
        self.assertEqual(self.ledger.private,{})
        self.setUp()
        self.wire.answers[0]=(500,b"PRIVATE-COUNT")
        self.fail()
        self.assertEqual(self.ledger.private,{})
        self.assertEqual(self.ledger.rows["planner-failed.json"]["private_response"],"NOT_AVAILABLE")

    def test_fixed_code_allowlist_rejects_untrusted_attribute(self):
        error=t.TransportRefused("PRIVATE")
        error.public_code="PRIVATE-PATH"
        self.assertEqual(t.public_failure_code(error),"unexpected-controller-fault")
        self.assertEqual(t.public_failure_code(KeyboardInterrupt()),"operator-interrupted")
        self.assertEqual(t.public_failure_code(SystemExit()),"controller-exit")

    def test_exact_projection_route_and_success_receipt(self):
        artifact,evidence=self.client.complete("planner",self.request)
        self.assertEqual(artifact,{"value":"public"})
        self.assertEqual(self.wire.calls[0][0],t.COUNT_PATH)
        self.assertEqual(self.wire.calls[0][1],self.body)
        generation=self.wire.calls[1][1]
        self.assertEqual({k:generation[k] for k in self.body},self.body)
        self.assertEqual(generation["service_tier"],"flex")
        self.assertEqual(generation["max_output_tokens"],32000)
        self.assertEqual(generation["reasoning"],{"effort":"medium"})
        self.assertFalse(generation["stream"] or generation["background"] or generation["store"])
        self.assertEqual(generation["tools"],[])
        self.assertEqual(generation["truncation"],"disabled")
        self.assertTrue(evidence["count_matches_usage"])
        self.assertEqual(self.wire.calls[0][2],220)
        self.assertEqual(self.wire.calls[1][2],1000)
        self.assertEqual(evidence["total_reserved_microdollars"],1736636)
        self.assertFalse(evidence["billing_final"] or evidence["holds_released"])
    def test_reservation_and_latches_precede_sends(self):
        original=self.wire.post_once
        def observe(path,body,key,end):
            phase="count" if path==t.COUNT_PATH else "generation"
            self.assertIn("planner-reservation.json",self.ledger.rows)
            self.assertIn("planner-"+phase+"-send.json",self.ledger.rows)
            return original(path,body,key,end)
        self.wire.post_once=observe
        self.client.complete("planner",self.request)
    def test_count_408_one_send_and_consumed(self):
        self.wire.answers=[(408,b"error")];self.fail()
        self.assertEqual(len(self.wire.calls),1)
        self.assertEqual(self.client.public_totals()["reserved_microdollars"],1736636)
        self.fail();self.assertEqual(len(self.wire.calls),1)
    def test_generation_failures_do_not_retry(self):
        for status in (408,429,500,503,302,307):
            self.setUp();self.wire.answers[1]=(status,b"error")
            self.fail();self.assertEqual(len(self.wire.calls),2)
            self.assertTrue(self.client.public_totals()["stopped"])
    def test_uncertain_count_send_stops_generation(self):
        self.wire.answers=[TimeoutError("private diagnostic must not escape")]
        self.fail();self.assertEqual(len(self.wire.calls),1)
        self.assertNotIn("private diagnostic must not escape",json.dumps(self.ledger.rows))
    def test_incomplete_or_truncated_consumes_slot(self):
        for payload in (dict(response(),status="incomplete"),dict(response(),incomplete_details={"reason":"max_output_tokens"})):
            self.setUp();self.wire.answers[1]=(200,t.canonical(payload));self.fail()
            self.assertEqual(len(self.wire.calls),2)
            self.assertIn("planner-failed.json",self.ledger.rows)
    def test_missing_flex_or_wrong_snapshot_refused(self):
        for key,value in (("service_tier","default"),("service_tier",None),("model","gpt-5.4")):
            self.setUp();payload=response();payload[key]=value
            self.wire.answers[1]=(200,t.canonical(payload));self.fail()
    def test_count_integer_and_cap(self):
        for value in (True,-1,100001,None):
            self.setUp();self.wire.answers[0]=(200,t.canonical(dict(object="response.input_tokens",input_tokens=value)))
            self.fail();self.assertEqual(len(self.wire.calls),1)
    def test_usage_malformed_or_over_cap(self):
        for key,value in (("input_tokens",True),("input_tokens",100001),("output_tokens",32001),("total_tokens",16)):
            self.setUp();payload=response();payload["usage"][key]=value
            self.wire.answers[1]=(200,t.canonical(payload));self.fail()
    def test_reasoning_included_in_output_cap(self):
        payload=response();payload["usage"]["output_tokens_details"]["reasoning_tokens"]=6
        self.wire.answers[1]=(200,t.canonical(payload));self.fail()
    def test_presend_proof_missing_zero_sends(self):
        self.request=t.ReviewedRequest(self.body,t.sha(t.canonical(self.body)),len(t.canonical(self.body))+4096,"","5"*64)
        self.fail();self.assertEqual(self.wire.calls,[])
    def test_presend_projection_changed_zero_sends(self):
        self.body["input"]="changed";self.fail();self.assertEqual(self.wire.calls,[])
    def test_presend_count_bound_exceeded_zero_sends(self):
        self.request=t.ReviewedRequest(self.body,t.sha(t.canonical(self.body)),100001,"4"*64,"5"*64)
        self.fail();self.assertEqual(self.wire.calls,[])
    def test_actual_count_exceeding_proved_bound_refused(self):
        self.wire.answers[0]=(200,t.canonical(dict(object="response.input_tokens",input_tokens=self.request.token_upper_bound+1)))
        self.fail();self.assertEqual(len(self.wire.calls),1)
    def test_unknown_billing_or_spend_refuses_construction(self):
        for spend in (t.ReviewedSpend("2"*64,"3"*64,False,t.RUN_CAP),t.ReviewedSpend("","3"*64,True,t.RUN_CAP)):
            with self.assertRaises(t.TransportRefused):self.make(spend=spend)
        self.assertEqual(self.wire.calls,[])
    def test_cap_shortage_zero_sends(self):
        self.client=self.make(spend=t.ReviewedSpend("2"*64,"3"*64,True,1736635))
        self.fail();self.assertEqual(self.wire.calls,[])
    def test_four_slots_hold_e2_total_never_recycle(self):
        self.wire.answers*=4
        for role in t.ROLES:self.client.complete(role,self.request)
        self.assertEqual(len(self.wire.calls),8)
        self.assertEqual(self.client.public_totals()["reserved_microdollars"],9458636)
        self.fail();self.assertEqual(len(self.wire.calls),8)
    def test_concurrent_duplicate_has_one_pair_of_sends(self):
        outcomes=[]
        def attempt():
            try:self.client.complete("planner",self.request);outcomes.append("success")
            except t.TransportRefused:outcomes.append("refused")
        threads=[threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertCountEqual(outcomes,["success","refused"])
        self.assertEqual(len(self.wire.calls),2)
    def test_run_deadline_and_process_identity(self):
        self.now=8185;self.fail();self.assertEqual(self.wire.calls,[])
        self.now=100
        with patch.object(t.os,"getpid",return_value=-1):self.fail()
        self.assertEqual(self.wire.calls,[])
    def test_phase_deadline_not_extended(self):
        original=self.wire.post_once
        def late(path,body,key,end):
            result=original(path,body,key,end);self.now=end;return result
        self.wire.post_once=late;self.fail();self.assertEqual(len(self.wire.calls),1)
    def test_full_hold_when_artifact_invalid(self):
        self.client=self.make(validate_artifact=lambda a,s:False)
        self.fail();self.assertEqual(self.client.public_totals()["reserved_microdollars"],1736636)
    def test_late_artifact_validation_cannot_succeed(self):
        def late(artifact,schema):self.now=1001;return True
        self.client=self.make(validate_artifact=late)
        self.fail();self.assertTrue(self.client.public_totals()["stopped"])
    def test_output_tools_or_partial_message_refused(self):
        for item in (dict(type="function_call"),dict(type="message",role="assistant",status="incomplete",content=[])):
            self.setUp();payload=response();payload["output"]=[item]
            self.wire.answers[1]=(200,t.canonical(payload));self.fail()
    def test_failed_ledger_no_send(self):
        self.ledger.record_once=Mock(side_effect=t.TransportRefused("fullfsync-failed"))
        self.fail();self.assertEqual(self.wire.calls,[])
    def test_wrong_admission_scope_refused(self):
        admission=Admission();admission.public_receipt=lambda:dict(scope="P5",qualified=True)
        with self.assertRaises(t.TransportRefused):self.make(admission=admission)


    def test_fractional_monotonic_start_uses_admission_addition(self):
        admission=Admission()
        admission.started_monotonic=123456.789012345
        admission.deadline_monotonic=admission.started_monotonic+8100
        self.now=admission.started_monotonic
        self.client=self.make(admission=admission)
        self.client.complete("planner",self.request)
        self.assertEqual(len(self.wire.calls),2)
    def test_usage_count_difference_within_bound_is_recorded(self):
        for actual in (9,11):
            self.setUp();payload=response()
            payload["usage"]["input_tokens"]=actual
            payload["usage"]["total_tokens"]=actual+5
            self.wire.answers[1]=(200,t.canonical(payload))
            _,evidence=self.client.complete("planner",self.request)
            self.assertEqual(evidence["count_tokens"],10)
            self.assertEqual(evidence["usage"]["input_tokens"],actual)
            self.assertEqual(evidence["token_upper_bound"],len(t.canonical(self.body))+4096)
            self.assertFalse(evidence["count_matches_usage"])
    def test_usage_above_proved_bound_refused(self):
        payload=response();payload["usage"]["input_tokens"]=self.request.token_upper_bound+1
        payload["usage"]["total_tokens"]=self.request.token_upper_bound+6
        self.wire.answers[1]=(200,t.canonical(payload));self.fail()
        self.assertIn("planner-failed.json",self.ledger.rows)
    def test_interrupt_and_exit_record_failure_then_propagate_unchanged(self):
        for error in (KeyboardInterrupt(),SystemExit(7)):
            self.setUp();self.wire.answers=[error]
            with self.assertRaises(type(error)) as caught:
                self.client.complete("planner",self.request)
            self.assertIs(caught.exception,error)
            self.assertEqual(self.ledger.rows["planner-failed.json"]["status"],"FAILED_CONSUMED")
            self.assertEqual(self.client.public_totals()["reserved_microdollars"],t.ROLE_HOLDS["planner"])
            self.assertTrue(self.client.public_totals()["stopped"])


    def test_e2_fixed_role_caps_holds_and_policy(self):
        self.assertEqual(tuple(t.ROLE_INPUT_CAPS.values()),(85876,100000,188000,198000))
        self.assertEqual(sum(t.ROLE_HOLDS.values()),9458636)
        self.assertEqual(t.RUN_CAP-sum(t.ROLE_HOLDS.values()),1364)
        self.assertEqual(self.client.budget_policy_sha256,t.BUDGET_POLICY_SHA256)
    def test_e2_exact_bound_and_one_byte_over_each_role(self):
        for role,cap in t.ROLE_INPUT_CAPS.items():
            for excess in (0,1):
                self.setUp()
                body=projection()
                fixed=len(t.canonical(body))
                body["input"] += "a"*(cap-4096-fixed+excess)
                raw=t.canonical(body)
                request=t.ReviewedRequest(body,t.sha(raw),len(raw)+4096,"4"*64,"5"*64)
                if excess:
                    with self.assertRaises(t.TransportRefused):self.client.complete(role,request)
                    self.assertEqual(self.wire.calls,[])
                    self.assertEqual(self.ledger.rows,{})
                    self.assertEqual(self.client.public_totals()["reserved_microdollars"],0)
                    self.assertTrue(self.client.public_totals()["stopped"])
                else:
                    _,evidence=self.client.complete(role,request)
                    self.assertEqual(evidence["total_reserved_microdollars"],t.ROLE_HOLDS[role])
                    self.assertEqual(evidence["budget_policy_sha256"],t.BUDGET_POLICY_SHA256)
    def test_e2_old_admission_policy_refused(self):
        old=Admission(); original=old.public_receipt
        old.public_receipt=lambda:dict(original(),budget_policy_sha256="f"*64)
        with self.assertRaises(t.TransportRefused):self.make(admission=old)
        self.assertEqual(self.wire.calls,[])
    def test_e2_removed_role_cannot_send(self):
        with self.assertRaises(t.TransportRefused):self.client.complete("analysis-attempt2",self.request)
        self.assertEqual(self.wire.calls,[])
        self.assertEqual(self.client.public_totals()["reserved_microdollars"],0)
    def test_e2_cap_bypass_understated_proof_refused(self):
        self.body["input"]="a"*100000
        self.request=t.ReviewedRequest(self.body,t.sha(t.canonical(self.body)),1,"4"*64,"5"*64)
        self.fail()
        self.assertEqual(self.wire.calls,[])
        self.assertEqual(self.client.public_totals()["reserved_microdollars"],0)
    def test_e2_usage_exact_cap_and_next_token(self):
        for role,cap in t.ROLE_INPUT_CAPS.items():
            payload=response()
            payload["usage"].update(input_tokens=cap,output_tokens=32000,total_tokens=cap+32000)
            cost,_=t.usage_cost(payload,cap,role)
            self.assertEqual(cost,(cap*11+1)//2+792000)
            payload["usage"].update(input_tokens=cap+1,total_tokens=cap+32001)
            with self.assertRaises(t.TransportRefused):t.usage_cost(payload,cap,role)

    def test_e2_policy_file_hash_and_arithmetic(self):
        import hashlib
        raw=(Path(__file__).resolve().parents[1] / "spec/intcalc-preview/2026-11-13/TRANSPORT-E2-BUDGET.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),t.BUDGET_POLICY_SHA256)
        policy=json.loads(raw)
        holds={role:2*((cap*11+1)//2)+792000 for role,cap in policy["role_input_caps"].items()}
        self.assertEqual(holds,policy["role_holds_microdollars"])
        self.assertEqual(sum(holds.values()),9458636)
        self.assertEqual(policy["envelope_microdollars"]-sum(holds.values()),1364)

class WireAndLedgerTests(unittest.TestCase):
    def test_http_single_request_no_redirect(self):
        connection=Mock();connection.getresponse.return_value.status=307
        connection.getresponse.return_value.read.return_value=b"redirect"
        with patch.object(t.http.client,"HTTPSConnection",return_value=connection) as ctor:
            status,raw=t.https_once(t.COUNT_PATH,b"{}","synthetic",5)
        self.assertEqual(status,307);connection.request.assert_called_once();ctor.assert_called_once_with("api.openai.com",timeout=5)
        connection.close.assert_called_once()
    def test_http_exception_not_retried(self):
        connection=Mock();connection.request.side_effect=TimeoutError()
        with patch.object(t.http.client,"HTTPSConnection",return_value=connection):
            with self.assertRaises(TimeoutError):t.https_once(t.COUNT_PATH,b"{}","synthetic",5)
        connection.request.assert_called_once();connection.close.assert_called_once()
    def test_response_size_bound(self):
        connection=Mock();connection.getresponse.return_value.read.return_value=b"x"*(t.MAX_RESPONSE+1)
        with patch.object(t.http.client,"HTTPSConnection",return_value=connection):
            with self.assertRaises(t.TransportRefused):t.https_once(t.COUNT_PATH,b"{}","synthetic",5)
    def test_json_rejects_non_utf8_float_duplicate_nonfinite(self):
        for raw in ('{"a":1}'.encode("utf-16"),b'{"a":1e400}',b'{"a":NaN}',b'{"a":1,"a":2}',b'{'):
            with self.subTest(raw=raw),self.assertRaises(t.TransportRefused):t.strict_json(raw)
    def test_private_response_owner_mode_exact_bytes_and_exclusive_name(self):
        if os.name != "posix":
            with self.assertRaisesRegex(t.TransportRefused,"posix-required"):
                t.ExclusiveRunLedger.__new__(t.ExclusiveRunLedger).retain_failed_response("planner",b"private")
            return
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve(strict=True)
            os.chmod(root,0o700)
            ledger=t.ExclusiveRunLedger(root,"7"*64)
            try:
                raw=b"private raw response\x00\xff"
                ledger.retain_failed_response("planner",raw)
                file=root/("7"*64)/"planner-generation-response.private"
                self.assertEqual(file.read_bytes(),raw)
                self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o600)
                with self.assertRaises(t.TransportRefused):ledger.retain_failed_response("planner",b"replace")
                with self.assertRaises(t.TransportRefused):ledger.retain_failed_response("../escape",raw)
                self.assertEqual(file.read_bytes(),raw)
            finally:ledger.close()

    def test_exclusive_ledger_no_reopen_or_duplicate(self):
        if os.name != "posix":
            with self.assertRaisesRegex(t.TransportRefused,"posix-required"):
                t.ExclusiveRunLedger("unused", "1"*64)
            return
        with tempfile.TemporaryDirectory() as directory:
            # This is a trusted test fixture, not a change to runtime path policy.
            # macOS may spell its temporary root through a symlink alias.
            directory = Path(directory).resolve(strict=True)
            os.chmod(directory,0o700)
            sync_events = []
            real_persist = t.persist
            def observe_real_persist(fd):
                kind = "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
                try:
                    real_persist(fd)
                except OSError as error:
                    sync_events.append({"kind": kind, "errno": error.errno})
                    raise
                sync_events.append({"kind": kind, "ok": True})
            with patch.object(t,"persist",side_effect=observe_real_persist):
                try:
                    ledger=t.ExclusiveRunLedger(directory,"1"*64)
                    try:
                        ledger.record_once("planner-count-send.json",{"consumed":True})
                        with self.assertRaises(t.TransportRefused):ledger.record_once("planner-count-send.json",{})
                        with self.assertRaises(t.TransportRefused):t.ExclusiveRunLedger(directory,"1"*64)
                    finally:ledger.close()
                except t.TransportRefused as error:
                    self.fail("canonical fixture ledger refused; real synchronization events=" + repr(sync_events))

    def test_ledger_symlink_ancestor_refused_without_creation(self):
        if os.name != "posix":
            with self.assertRaisesRegex(t.TransportRefused,"posix-required"):
                t.ExclusiveRunLedger("unused", "2"*64)
            return
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            real = root / "real"
            real.mkdir(mode=0o700)
            parent = real / "parent"
            parent.mkdir(mode=0o700)
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises(t.TransportRefused):
                t.ExclusiveRunLedger(alias / "parent", "2"*64)
            self.assertFalse((parent / ("2"*64)).exists())
    def test_fullfsync_selected_on_mac_and_errors_not_downgraded(self):
        if os.name != "posix":
            with self.assertRaisesRegex(t.TransportRefused,"posix-required"):
                t.persist(123)
            return
        import fcntl
        with patch.object(t.sys,"platform","darwin"),patch.object(fcntl,"F_FULLFSYNC",51,create=True),patch.object(fcntl,"fcntl") as full,patch.object(t.os,"fsync") as fallback:
            t.persist(123);full.assert_called_once_with(123,51);fallback.assert_not_called()
            full.side_effect=OSError()
            with self.assertRaises(OSError):t.persist(123)
            fallback.assert_not_called()
    def test_deadline_wire_does_not_start_without_cleanup_budget(self):
        context=Mock();wire=t.DeadlineWire(clock=lambda:100,context=context)
        with self.assertRaises(t.TransportRefused):wire.post_once(t.COUNT_PATH,b"{}","synthetic",105)
        context.Process.assert_not_called()
    def test_timed_out_worker_reaped_no_second_process(self):
        context=Mock();parent,child=Mock(),Mock();context.Pipe.return_value=(parent,child)
        parent.poll.return_value=False;worker=context.Process.return_value
        worker.is_alive.side_effect=[True,False,False]
        with patch.object(t.threading,"Timer"):
            wire=t.DeadlineWire(clock=lambda:100,context=context)
            with self.assertRaises(t.TransportRefused):wire.post_once(t.COUNT_PATH,b"{}","synthetic",220)
        context.Process.assert_called_once();worker.start.assert_called_once();worker.terminate.assert_called_once()
        worker.join.assert_called_once();worker.close.assert_called_once()



# Module-level picklable workers: no HTTP helper, socket, credential or model call.
def synthetic_frame_worker(marker,pipe,path,body,key,timeout):
    try:
        Path(marker).write_bytes(b"worker-started\n")
        pipe.send_bytes((200).to_bytes(2,"big")+b"public synthetic frame")
    finally:pipe.close()

def synthetic_stalled_worker(marker,pipe,path,body,key,timeout):
    try:
        Path(marker).write_bytes(b"worker-started\n")
        time.sleep(60)
    finally:pipe.close()

def synthetic_empty_worker(marker,pipe,path,body,key,timeout):
    try:Path(marker).write_bytes(b"worker-started\n")
    finally:pipe.close()

def synthetic_missing_start_worker(marker,pipe,path,body,key,timeout):
    # Negative control: EOF without the startup witness must not pass the helper.
    pipe.close()

class RecordedProcess:
    def __init__(self,process):self.process=process;self.closed=None
    @property
    def daemon(self):return self.process.daemon
    @daemon.setter
    def daemon(self,value):self.process.daemon=value
    def __getattr__(self,name):return getattr(self.process,name)
    def close(self):
        self.closed=(self.process.pid,self.process.exitcode,self.process.is_alive())
        self.process.close()

class RecordedSpawnContext:
    def __init__(self):self.context=multiprocessing.get_context("spawn");self.created=[]
    def Pipe(self,**kwargs):return self.context.Pipe(**kwargs)
    def Process(self,**kwargs):
        process=RecordedProcess(self.context.Process(**kwargs));self.created.append(process);return process

class RealSpawnWireTests(unittest.TestCase):
    def run_worker(self,target,refusal=False):
        context=RecordedSpawnContext()
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory).resolve(strict=True) / "worker-started.txt"
            wire=t.DeadlineWire(context=context,worker_target=partial(target,str(marker)))
            started=time.monotonic()
            stalled = target is synthetic_stalled_worker
            # Keep the exact reviewed TR-8 timing margins.
            end = started + (7 if stalled else 25)
            if refusal:
                with self.assertRaises(t.TransportRefused):
                    wire.post_once(t.COUNT_PATH,b"{}","synthetic-not-a-credential",end)
                result=None
            else:result=wire.post_once(t.COUNT_PATH,b"{}","synthetic-not-a-credential",end)
            self.assertLess(time.monotonic()-started,6 if stalled else 15)
            self.assertEqual(len(context.created),1)
            closed=context.created[0].closed
            self.assertIsNotNone(closed)
            self.assertIsNotNone(closed[1])
            self.assertFalse(closed[2])
            self.assertTrue(marker.is_file(), "worker-start-not-observed")
            self.assertEqual(marker.read_bytes(), b"worker-started\n")
            return result,closed[1]
    def test_spawn_normal_frame(self):
        result,_=self.run_worker(synthetic_frame_worker)
        self.assertEqual(result,(200,b"public synthetic frame"))
    def test_spawn_stall_killed_and_reaped(self):
        _,exitcode=self.run_worker(synthetic_stalled_worker,refusal=True)
        self.assertNotEqual(exitcode,0)
    def test_spawn_exit_without_frame_refused_and_reaped(self):
        self.run_worker(synthetic_empty_worker,refusal=True)
    def test_spawn_missing_start_witness_cannot_pass_as_empty_exit(self):
        with self.assertRaisesRegex(AssertionError,"worker-start-not-observed"):
            self.run_worker(synthetic_missing_start_worker,refusal=True)


class ProviderEnvelopeTests(unittest.TestCase):
    """Provider metadata may contain floats; artifact/accounting records may not."""
    def fixture(self):
        path = Path(__file__).parent / "fixtures" / "intcalc-preview" / "provider-envelope.json"
        return json.loads(path.read_bytes())

    def client(self, count_raw=None, generation_raw=None):
        body = projection()
        body["input"] = "synthetic public padding " * 1000
        request = t.ReviewedRequest(body, t.sha(t.canonical(body)), len(t.canonical(body))+4096, "4"*64, "5"*64)
        envelope = self.fixture()
        envelope["output"][1]["content"][0]["text"] = '{"value":"public"}'
        wire, ledger = Wire(), Ledger()
        wire.answers = [(200, count_raw if count_raw is not None else t.canonical(
            dict(object="response.input_tokens", input_tokens=13975, metadata={"finite":0.25}))),
            (200, generation_raw if generation_raw is not None else t.canonical(envelope))]
        client = t.PreviewTransport(admission=Admission(),
            spend=t.ReviewedSpend("2"*64,"3"*64,True,t.RUN_CAP), ledger=ledger,
            api_key="synthetic-not-a-credential", wire=wire, clock=lambda:100.0,
            validate_artifact=lambda a,s:type(a) is dict and set(a)=={"value"} and type(a["value"]) is str)
        return client, request, ledger, wire

    def test_fixture_matches_reported_structure_not_private_content(self):
        envelope = self.fixture()
        keys = "access_programs background billing completed_at created_at error frequency_penalty id image incomplete_details input_transformations instructions max_output_tokens max_tool_calls metadata model moderation object output parallel_tool_calls presence_penalty previous_response_id prompt_cache_key prompt_cache_retention reasoning safety_identifier service_tier status store temperature text tool_choice tool_usage tools top_logprobs top_p truncation usage user".split()
        self.assertEqual(len(keys), 39)
        self.assertEqual(set(envelope), set(keys))
        for key,value in {"frequency_penalty":0.0,"presence_penalty":0.0,"temperature":1.0,"top_p":0.98}.items():
            self.assertIs(type(envelope[key]), float)
            self.assertEqual(envelope[key], value)
        reasoning, message = envelope["output"]
        self.assertNotIn("status", reasoning)
        self.assertEqual(reasoning["content"], [])
        self.assertEqual(message["status"], "completed")
        self.assertEqual(len(message["content"]), 1)
        self.assertIsInstance(envelope["usage"]["input_tokens_details"]["cache_details"], dict)

    def test_finite_envelopes_complete_and_records_have_no_floats(self):
        client, request, ledger, wire = self.client()
        artifact, evidence = client.complete("planner", request)
        self.assertEqual(artifact, {"value":"public"})
        self.assertEqual(evidence["usage"], {"input_tokens":13975,"output_tokens":4328,"total_tokens":18303})
        self.assertEqual(len(wire.calls), 2)
        self.assertEqual(ledger.private, {})
        # The unchanged integer-only parser admits every record, recursively.
        self.assertEqual(t.strict_json(t.canonical(ledger.rows)), ledger.rows)
        self.assertNotIn('"temperature"', json.dumps(ledger.rows))

    def test_provider_parser_allows_nested_finite_values(self):
        raw = b'{"metadata":{"values":[0.0,-1.5,2e2]},"top_p":0.98}'
        self.assertEqual(t.provider_envelope_json(raw)["metadata"]["values"], [0.0,-1.5,200.0])
        with self.assertRaisesRegex(t.TransportRefused, "float-or-nonfinite-json"):
            t.strict_json(raw)

    def test_nonfinite_and_overflow_refuse_both_endpoints_with_fixed_code(self):
        for literal in (b'NaN',b'Infinity',b'-Infinity',b'1e400',b'-1e400'):
            for phase in ("count", "generation"):
                with self.subTest(literal=literal, phase=phase):
                    raw = b'{"metadata":{"nested":['+literal+b']}}'
                    kwargs = {phase+"_raw":raw}
                    client, request, ledger, wire = self.client(**kwargs)
                    with self.assertRaisesRegex(t.TransportRefused, "slot-failed-consumed-no-retry"):
                        client.complete("planner", request)
                    self.assertEqual(ledger.rows["planner-failed.json"]["refusal_code"], "float-or-nonfinite-json")
                    self.assertEqual(len(wire.calls), 1 if phase=="count" else 2)
                    self.assertEqual(t.strict_json(t.canonical(ledger.rows)), ledger.rows)

    def test_duplicate_keys_refuse_at_root_and_nested_in_both_endpoints(self):
        for raw in (b'{"x":1,"x":2}', b'{"metadata":{"x":0.0,"x":1.0}}'):
            for phase in ("count", "generation"):
                with self.subTest(raw=raw, phase=phase):
                    client, request, ledger, wire = self.client(**{phase+"_raw":raw})
                    with self.assertRaises(t.TransportRefused):
                        client.complete("planner", request)
                    self.assertEqual(ledger.rows["planner-failed.json"]["refusal_code"], "duplicate-json-key")
                    self.assertEqual(t.strict_json(t.canonical(ledger.rows)), ledger.rows)

    def test_provider_parser_keeps_utf8_size_and_syntax_refusals(self):
        for raw,code in ((b'{"x":"\xff"}',"invalid-response-json"),
                         ('{"x":1}'.encode('utf-16'),"invalid-response-json"),
                         (b'{',"invalid-response-json"),
                         (b' '* (t.MAX_RESPONSE+1),"response-size")):
            with self.subTest(code=code):
                with self.assertRaises(t.TransportRefused) as caught:
                    t.provider_envelope_json(raw)
                self.assertEqual(str(caught.exception),code)

    def test_finite_float_accounting_still_refuses_before_recording_values(self):
        for key in ("input_tokens","output_tokens","total_tokens"):
            envelope=self.fixture()
            envelope["usage"][key]=float(envelope["usage"][key])
            client,request,ledger,wire=self.client(generation_raw=t.canonical(envelope))
            with self.subTest(key=key), self.assertRaises(t.TransportRefused):
                client.complete("planner",request)
            self.assertNotIn("planner-complete.json",ledger.rows)
            self.assertEqual(t.strict_json(t.canonical(ledger.rows)),ledger.rows)
        client,request,ledger,wire=self.client(count_raw=b'{"object":"response.input_tokens","input_tokens":13975.0}')
        with self.assertRaises(t.TransportRefused): client.complete("planner",request)
        self.assertEqual(ledger.rows["planner-failed.json"]["refusal_code"],"count-response")
        self.assertEqual(len(wire.calls),1)

    def test_artifact_float_remains_refused_after_finite_envelope_parses(self):
        envelope=self.fixture()
        envelope["output"][1]["content"][0]["text"]='{"value":1.0}'
        client,request,ledger,wire=self.client(generation_raw=t.canonical(envelope))
        with self.assertRaises(t.TransportRefused): client.complete("planner",request)
        self.assertEqual(ledger.rows["planner-failed.json"]["refusal_code"],"float-or-nonfinite-json")
        self.assertEqual(ledger.rows["planner-failed.json"]["private_response"],"RETAINED_PRIVATE")
        self.assertEqual(t.strict_json(t.canonical(ledger.rows)),ledger.rows)


def synthetic_ci_main():
    # A real file and a main guard let spawn import this module without rerunning
    # the suite in each child. Children use only the synthetic workers above.
    import platform
    import socket
    import sys
    if platform.system() == "Darwin":
        assert platform.machine() == "arm64"
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    with patch.object(socket.socket,"connect",side_effect=AssertionError("Provider networking forbidden in CI")):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun == 64 else 1




# Historical synthetic semantics remain tested without granting live admission.
# test_intcalc_retirement exercises every real boundary with this mock absent.
from unittest.mock import patch as _retirement_unit_patch


def setUpModule():
    global _retirement_unit_scope
    _retirement_unit_scope = _retirement_unit_patch(
        "lightyear_mainframe.intcalc_retirement.require_current", return_value=None)
    _retirement_unit_scope.start()


def tearDownModule():
    _retirement_unit_scope.stop()


if __name__ == "__main__":
    raise SystemExit(synthetic_ci_main())
