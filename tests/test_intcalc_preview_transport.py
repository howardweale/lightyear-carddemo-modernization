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
            status="ADMITTED_ONLY",run_budget_seconds=8100,binding_sha256="1"*64)


class Ledger:
    def __init__(self):self.rows={}
    def record_once(self,name,value):
        if name in self.rows:raise t.TransportRefused("consumed")
        self.rows[name]=copy.deepcopy(value)


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
        self.request=t.ReviewedRequest(self.body,t.sha(t.canonical(self.body)),100,"4"*64,"5"*64)
        self.client=self.make()
    def make(self,**kwargs):
        values=dict(admission=Admission(),spend=self.spend,ledger=self.ledger,api_key="synthetic-not-a-credential",
            validate_artifact=lambda a,s:type(a) is dict and set(a)=={"value"} and type(a["value"]) is str,
            wire=self.wire,clock=lambda:self.now)
        values.update(kwargs);return t.PreviewTransport(**values)
    def fail(self):
        with self.assertRaises(t.TransportRefused):self.client.complete("planner",self.request)
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
        self.assertEqual(evidence["total_reserved_microdollars"],1892000)
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
        self.assertEqual(self.client.public_totals()["reserved_microdollars"],1892000)
        self.fail();self.assertEqual(len(self.wire.calls),1)
    def test_generation_failures_do_not_retry(self):
        for status in (408,429,500,503,302,307):
            self.setUp();self.wire.answers[1]=(status,b"error")
            self.fail();self.assertEqual(len(self.wire.calls),2)
            self.assertTrue(self.client.public_totals()["stopped"])
    def test_uncertain_count_send_stops_generation(self):
        self.wire.answers=[TimeoutError("private diagnostic must not escape")]
        self.fail();self.assertEqual(len(self.wire.calls),1)
        self.assertNotIn("private",json.dumps(self.ledger.rows))
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
        self.request=t.ReviewedRequest(self.body,t.sha(t.canonical(self.body)),100,"","5"*64)
        self.fail();self.assertEqual(self.wire.calls,[])
    def test_presend_projection_changed_zero_sends(self):
        self.body["input"]="changed";self.fail();self.assertEqual(self.wire.calls,[])
    def test_presend_count_bound_exceeded_zero_sends(self):
        self.request=t.ReviewedRequest(self.body,t.sha(t.canonical(self.body)),100001,"4"*64,"5"*64)
        self.fail();self.assertEqual(self.wire.calls,[])
    def test_actual_count_exceeding_proved_bound_refused(self):
        self.request=t.ReviewedRequest(self.body,t.sha(t.canonical(self.body)),9,"4"*64,"5"*64)
        self.fail();self.assertEqual(len(self.wire.calls),1)
    def test_unknown_billing_or_spend_refuses_construction(self):
        for spend in (t.ReviewedSpend("2"*64,"3"*64,False,t.RUN_CAP),t.ReviewedSpend("","3"*64,True,t.RUN_CAP)):
            with self.assertRaises(t.TransportRefused):self.make(spend=spend)
        self.assertEqual(self.wire.calls,[])
    def test_cap_shortage_zero_sends(self):
        self.client=self.make(spend=t.ReviewedSpend("2"*64,"3"*64,True,1891999))
        self.fail();self.assertEqual(self.wire.calls,[])
    def test_five_slots_hold_exact_envelope_never_recycle(self):
        self.wire.answers*=5
        for role in t.ROLES:self.client.complete(role,self.request)
        self.assertEqual(len(self.wire.calls),10)
        self.assertEqual(self.client.public_totals()["reserved_microdollars"],9460000)
        self.fail();self.assertEqual(len(self.wire.calls),10)
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
        self.fail();self.assertEqual(self.client.public_totals()["reserved_microdollars"],1892000)
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
            self.assertEqual(evidence["token_upper_bound"],100)
            self.assertFalse(evidence["count_matches_usage"])
    def test_usage_above_proved_bound_refused(self):
        payload=response();payload["usage"]["input_tokens"]=101
        payload["usage"]["total_tokens"]=106
        self.wire.answers[1]=(200,t.canonical(payload));self.fail()
        self.assertIn("planner-failed.json",self.ledger.rows)
    def test_interrupt_and_exit_record_failure_then_propagate_unchanged(self):
        for error in (KeyboardInterrupt(),SystemExit(7)):
            self.setUp();self.wire.answers=[error]
            with self.assertRaises(type(error)) as caught:
                self.client.complete("planner",self.request)
            self.assertIs(caught.exception,error)
            self.assertEqual(self.ledger.rows["planner-failed.json"]["status"],"FAILED_CONSUMED")
            self.assertEqual(self.client.public_totals()["reserved_microdollars"],t.SLOT_HOLD)
            self.assertTrue(self.client.public_totals()["stopped"])


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
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun == 42 else 1


if __name__ == "__main__":
    raise SystemExit(synthetic_ci_main())
