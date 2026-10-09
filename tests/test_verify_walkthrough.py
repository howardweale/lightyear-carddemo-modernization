"""Small offline fake-judge checks; never run a candidate, Docker or a model."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import Mock, patch, AsyncMock
from types import SimpleNamespace

from tools.verify_smoke.walkthrough import Walkthrough, sha


class JudgeDouble:
    def __init__(self):
        self.used = 0
        self.requests = {}
        self.rows = {}
        self.calls = []
        self.polls = {}
        self.now = 0
        self.sleeps = []
        self.owner = None
        self.bad_step = None
        self.timeout = False
        self.no_refusal = False
        self.artifacts = {n:sha(n.encode()) for n in ("good.jar", "rounding.jar", "skipped.jar", "date.jar")}

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def budget(self):
        return dict(submissions_left=5-self.used, attempt_slots_left=5-self.used,
                    inventory_attempts_used=self.used, inventory_attempt_limit=5)

    async def call(self, name, args):
        self.calls.append((self.owner.current["step"], name, copy.deepcopy(args)))
        if self.owner.current["step"] == self.bad_step:
            return {"ok":False, "error":"injected-step-mismatch"}
        if name == "get_task":
            return dict(ok=True, smoke_evidence="public-receipt-bytes-v1", public=dict(source="CBACT04C", target="Java", shapes=["ACCTFILE", "TRANSACT"]))
        if name == "get_budget":
            return dict(ok=True, **self.budget())
        if name == "describe_copybook":
            return dict(record_length=300, fields=[{"name":"ACCT"}])
        if name == "decode_records":
            return dict(ok=False, error="path-refused") if args["path"] == "../private" else dict(records=[{}], sha256="a"*64)
        if name == "read_job_log":
            return dict(steps=[{"step":"STEP15"}])
        if name == "lane_status":
            return dict(status="unqualified")
        if name == "submit_candidate":
            request = args["request_id"]
            assert uuid.UUID(request).version == 4
            if request in self.requests:
                return dict(ok=True, attempt_id=self.requests[request])
            if self.used == 5:
                return dict(ok=True, attempt_id="unexpected") if self.no_refusal else dict(ok=False, error="request-refused", budget=self.budget())
            self.used += 1
            attempt = "attempt-"+str(self.used)
            self.requests[request] = attempt
            ds = {"good.jar":[], "rounding.jar":[dict(field="X.TRAN-AMT")],
                  "skipped.jar":[dict(kind="missing-record", dataset="STEP15/ACCTFILE")],
                  "date.jar":[dict(field="X.TRAN-PROC-TS")]}[args["path"]]
            self.rows[attempt] = dict(attempt_id=attempt, artifact_sha256=self.artifacts[args["path"]],
                verdict="equivalent" if not ds else "divergent", diagnostics=ds, status="completed",
                review="operator review; not independent", signature="fake-test-signature", content_sha256=sha(attempt.encode()))
            return dict(ok=True, attempt_id=attempt, verdict="pending")
        row = self.rows[args["attempt_id"]]
        if name == "get_verdict":
            self.polls[args["attempt_id"]] = self.polls.get(args["attempt_id"], 0)+1
            if self.timeout or self.polls[args["attempt_id"]] == 1:
                return dict(ok=True, verdict="pending")
            return dict(ok=True, verdict=row["verdict"], diagnostics=row["diagnostics"], receipt_sha256=row["content_sha256"])
        if name == "get_receipt":
            # Deliberately noncanonical spacing: byte hash must not reserialize.
            raw = (json.dumps(row, indent=3)+"\n").encode()
            return dict(ok=True, receipt=row, receipt_bytes_base64=base64.b64encode(raw).decode(),
                        journal_head_sha256="b"*64, alerts=["repeated-identical-diagnostics"] if self.used == 5 else [])
        raise AssertionError(name)

    def runner(self):
        self.owner = Walkthrough(self.call, self.artifacts, sleep=self.sleep, clock=lambda:self.now)
        return self.owner


class WalkthroughTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_judge_refuses_before_any_submission(self):
        judge = JudgeDouble();original = judge.call
        async def old(name, args):
            result = await original(name,args)
            result.pop('smoke_evidence', None)
            return result
        judge.call = old
        report = await judge.runner().run()
        self.assertEqual('task-mismatch', report['error'])
        self.assertEqual(0, judge.used)
        self.assertFalse(any(n == 'submit_candidate' for _,n,_ in judge.calls))

    async def test_all_fifteen_steps_exact_bytes_uuid_and_polling(self):
        judge = JudgeDouble()
        report = await judge.runner().run()
        self.assertEqual("passed", report["status"], report)
        self.assertEqual(list(range(1,16)), [r["step"] for r in report["steps"]])
        self.assertTrue(all(r["passed"] for r in report["steps"]))
        self.assertEqual(5, len(report["attempts"]))
        for row in report["attempts"]:
            raw = base64.b64decode(row["receipt_bytes_base64"])
            self.assertEqual(sha(raw), row["receipt_sha256"])
            self.assertNotEqual(sha(json.dumps(json.loads(raw)).encode()), row["receipt_sha256"])
        submissions = [a for _,n,a in judge.calls if n == "submit_candidate"]
        self.assertEqual(7, len(submissions))
        self.assertEqual(submissions[0], submissions[1])
        self.assertEqual(6, len({a["request_id"] for a in submissions}))
        self.assertEqual([2]*5, judge.sleeps)
        self.assertEqual("b"*64, report["final_journal_head_sha256"])
        self.assertEqual(0, report["model_calls"])

    async def test_every_single_step_mismatch_stops_immediately(self):
        for step in range(1,16):
            with self.subTest(step=step):
                judge = JudgeDouble();judge.bad_step = step
                report = await judge.runner().run()
                self.assertEqual("failed", report["status"])
                self.assertEqual(step, len(report["steps"]))
                self.assertFalse(report["steps"][-1]["passed"])
                self.assertEqual(step, max(s for s,_,_ in judge.calls))

    async def test_timeout_never_resubmits_and_keeps_attempt(self):
        judge = JudgeDouble();judge.timeout = True
        report = await judge.runner().run()
        self.assertEqual("attempt-timeout", report["error"])
        self.assertEqual(360, judge.now)
        self.assertTrue(all(s >= 2 for s in judge.sleeps))
        self.assertEqual(1, judge.used)
        self.assertEqual(2, sum(n == "submit_candidate" for _,n,_ in judge.calls))  # intentional step8 only
        self.assertIsNotNone(report["attempts"][0]["attempt_id"])

    async def test_idempotency_and_missing_refusals(self):
        for mode in ("idempotency", "private", "sixth", "alert", "head", "receipt", "date", "class"):
            with self.subTest(mode=mode):
                judge = JudgeDouble();original = judge.call
                async def broken(name, args):
                    result = copy.deepcopy(await original(name,args))
                    step = judge.owner.current["step"]
                    if mode == "idempotency" and step == 8 and name == "submit_candidate":result["attempt_id"] = "different"
                    if mode == "private" and step == 6 and name == "decode_records":result = {"records":[{}]}
                    if mode == "sixth" and step == 15 and name == "submit_candidate":result = {"ok":True,"attempt_id":"sixth"}
                    if mode == "alert" and step == 14 and name == "get_receipt":result["alerts"] = []
                    if mode == "head" and name == "get_receipt":result.pop("journal_head_sha256")
                    if mode == "receipt" and name == "get_receipt":result["receipt_bytes_base64"] = base64.b64encode(b'{}').decode()
                    if mode == "date" and step == 13 and name == "get_verdict" and result.get("diagnostics"):result["diagnostics"] = [{"field":"OTHER-TS"}]
                    if mode == "class" and step == 11 and name == "get_verdict":result["verdict"] = "indeterminate"
                    return result
                judge.call = broken
                report = await judge.runner().run()
                self.assertEqual("failed", report["status"], mode)


class ReceiptEvidenceTests(unittest.TestCase):
    def test_non_fixture_receipt_contract_unchanged(self):
        from lightyear_judge.service import Judge
        judge = object.__new__(Judge)
        judge.lock = threading.RLock();judge.config = {"fixture":False}
        judge.public_receipt = Mock(return_value={"signature":"fake"})
        judge.receipt_evidence = Mock(side_effect=AssertionError("fixture metadata exposed"))
        self.assertEqual({"ok":True,"receipt":{"signature":"fake"}}, judge.invoke("get_receipt", {"attempt_id":"one"}))
        judge.receipt_evidence.assert_not_called()

    def test_service_uses_only_validated_public_bytes_and_observed_head(self):
        from lightyear_judge.service import Judge
        with tempfile.TemporaryDirectory() as folder:
            judge = object.__new__(Judge);judge.root = Path(folder)
            (judge.root/'public-receipts').mkdir()
            rows = {"one":dict(diagnostics=[{"field":"X"}], signature="fake"),
                    "two":dict(diagnostics=[{"field":"X"}], signature="fake")}
            judge.public_receipt = Mock(side_effect=lambda n:rows[n])
            judge.accepted = lambda:[{"attempt_id":n} for n in rows]
            judge.events = [{"content_sha256":"f"*64}]
            for n,r in rows.items():(judge.root/'public-receipts'/f'{n}.json').write_bytes((json.dumps(r,indent=4)+'\n').encode())
            result = judge.receipt_evidence("two")
            raw = (judge.root/'public-receipts/two.json').read_bytes()
            self.assertEqual(raw, base64.b64decode(result["receipt_bytes_base64"]))
            self.assertEqual(["repeated-identical-diagnostics"], result["alerts"])
            self.assertEqual("f"*64, result["journal_head_sha256"])
            (judge.root/'public-receipts/two.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'public-receipt-bytes-changed'):
                judge.receipt_evidence("two")


class ReportTests(unittest.TestCase):
    def test_existing_output_refuses_before_connection(self):
        from tools.verify_smoke import walkthrough as w
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)/'walkthrough-report.json';out.write_bytes(b'preserved')
            with patch.dict('sys.modules', pwd=SimpleNamespace(getpwnam=lambda _:SimpleNamespace(pw_uid=1000))), \
                 patch.object(w.os, 'geteuid', return_value=1000, create=True), \
                 patch.dict(w.os.environ, LIGHTYEAR_VERIFY_TOKEN='test-token'), \
                 patch.object(w, 'Path', return_value=out), patch.object(w, 'protocol', new_callable=AsyncMock) as protocol:
                with self.assertRaises(FileExistsError):w.main()
                protocol.assert_not_called()
            self.assertEqual(b'preserved', out.read_bytes())

    def test_transport_cleanup_failure_preserves_attempt_prefix_without_secret(self):
        from tools.verify_smoke import walkthrough as w
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);out=root/'walkthrough-report.json'
            artifacts = {}
            for name in ('good.jar','rounding.jar','skipped.jar','date.jar'):
                (root/name).write_bytes(name.encode());artifacts[name]=sha(name.encode())
            (root/'candidates.json').write_text(json.dumps({'jars':artifacts}))
            async def broken(artifacts, state):
                state['runner']=SimpleNamespace(report={'steps':[{'step':7,'passed':False}], 'attempts':[{'request_id':'preserved'}], 'model_calls':0})
                raise RuntimeError('test-token must never be printed')
            with patch.dict('sys.modules', pwd=SimpleNamespace(getpwnam=lambda _:SimpleNamespace(pw_uid=1000))), \
                 patch.object(w.os, 'geteuid', return_value=1000, create=True), \
                 patch.dict(w.os.environ, LIGHTYEAR_VERIFY_TOKEN='test-token'), \
                 patch.object(w, 'Path', return_value=out), patch.object(w, 'protocol', side_effect=broken), \
                 patch('builtins.print'):
                self.assertEqual(1,w.main())
            report=json.loads(out.read_bytes())
            self.assertEqual('preserved', report['attempts'][0]['request_id'])
            self.assertEqual('failed',report['status'])
            self.assertNotIn('test-token',out.read_text())
