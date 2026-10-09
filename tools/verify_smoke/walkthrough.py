"""One no-model MCP walkthrough as lyagent; consumes five fresh task attempts."""
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

TOOLS = {"get_task", "get_budget", "describe_copybook", "decode_records", "read_job_log",
         "lane_status", "submit_candidate", "get_verdict", "get_receipt", "propose_normalization"}


class Mismatch(Exception):
    pass


def require(condition, code):
    if not condition:
        raise Mismatch(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Walkthrough:
    def __init__(self, call, artifacts, *, sleep=asyncio.sleep, clock=time.monotonic):
        self.call, self.artifacts, self.sleep, self.clock = call, artifacts, sleep, clock
        self.report = dict(schema="verify-smoke-walkthrough/1", status="running", steps=[],
                           attempts=[], final_journal_head_sha256=None, model_calls=0,
                           claim="Operator protocol review; not independent attestation")
        self.current = None
        self.ids = set()

    async def tool(self, name, **arguments):
        self.current["tools"].append(name)
        result = await asyncio.wait_for(self.call(name, arguments), timeout=30)
        require(isinstance(result, dict), "tool-response-shape")
        return result

    async def budget(self, left):
        result = await self.tool("get_budget")
        require(result.get("ok") is True and result.get("submissions_left") == left
                and result.get("attempt_slots_left") == left
                and result.get("inventory_attempts_used") == 5-left
                and result.get("inventory_attempt_limit") == 5, "budget-mismatch")
        return result

    async def submit(self, name):
        request = str(uuid.uuid4())
        require(request not in self.ids, "request-id-collision")
        self.ids.add(request)
        # Preserve identity even when a response times out; never resubmit.
        row = dict(request_id=request, artifact=name, artifact_sha256=self.artifacts[name],
                   attempt_id=None, verdict=None, receipt_sha256=None, deadline=self.clock()+360)
        self.report["attempts"].append(row)
        result = await self.tool("submit_candidate", path=name, request_id=request)
        require(result.get("ok") is True and result.get("verdict") == "pending"
                and isinstance(result.get("attempt_id"), str) and result["attempt_id"], "submission-mismatch")
        row["attempt_id"] = result["attempt_id"]
        require(len({a["attempt_id"] for a in self.report["attempts"]}) == len(self.report["attempts"]), "attempt-id-reused")
        await self.budget(5-len(self.report["attempts"]))
        return row

    async def verdict(self, row):
        while True:
            # Includes time spent on transport, idempotency and budget checks.
            remaining = row["deadline"]-self.clock()
            require(remaining > 0, "attempt-timeout")
            try:
                result = await asyncio.wait_for(self.tool("get_verdict", attempt_id=row["attempt_id"]), remaining)
            except asyncio.TimeoutError:
                raise Mismatch("attempt-timeout") from None
            require(self.clock() <= row["deadline"], "attempt-timeout")
            require(result.get("ok") is True, "verdict-refused")
            if result.get("verdict") != "pending":
                break
            require(row["deadline"]-self.clock() >= 2, "attempt-timeout")
            await self.sleep(2)
        expected = "equivalent" if row["artifact"] == "good.jar" else "divergent"
        require(result.get("verdict") == expected, "verdict-mismatch")
        ds = result.get("diagnostics")
        require(isinstance(ds, list) and all(isinstance(d, dict) for d in ds), "diagnostic-shape")
        name = row["artifact"]
        if name == "good.jar":
            require(ds == [], "equivalent-diagnostics")
        elif name == "skipped.jar":
            require(any(d.get("kind") == "missing-record" and d.get("dataset") == "STEP15/ACCTFILE" for d in ds), "missing-record-diagnostic")
        else:
            field = "TRAN-AMT" if name == "rounding.jar" else "TRAN-PROC-TS"
            require(any(str(d.get("field", "")).endswith(field) for d in ds), "field-diagnostic")
        row.update(verdict=expected, diagnostics=ds, receipt_content_sha256=result.get("receipt_sha256"))

    async def receipt(self, row):
        result = await self.tool("get_receipt", attempt_id=row["attempt_id"])
        require(result.get("ok") is True, "receipt-refused")
        raw = base64.b64decode(result.get("receipt_bytes_base64", ""), validate=True)
        receipt = json.loads(raw)
        require(receipt == result.get("receipt") and receipt.get("attempt_id") == row["attempt_id"]
                and receipt.get("artifact_sha256") == row["artifact_sha256"]
                and receipt.get("verdict") == row["verdict"]
                and receipt.get("diagnostics") == row["diagnostics"]
                and receipt.get("content_sha256") == row["receipt_content_sha256"]
                and receipt.get("status") == "completed"
                and receipt.get("review") == "operator review; not independent"
                and receipt.get("signature"), "receipt-mismatch")
        if row["receipt_sha256"] is not None:
            require(row["receipt_sha256"] == sha(raw), "receipt-bytes-changed")
        row.update(receipt_sha256=sha(raw), receipt_bytes_base64=result["receipt_bytes_base64"])
        head = result.get("journal_head_sha256", "")
        require(isinstance(head, str) and re.fullmatch(r"[0-9a-f]{64}", head), "journal-head-missing")
        self.report["final_journal_head_sha256"] = head
        return result

    async def run(self):
        row = None
        try:
            for step in range(1, 16):
                self.current = dict(step=step, tools=[], outcome="started", passed=False)
                self.report["steps"].append(self.current)
                if step == 1:
                    task = await self.tool("get_task")
                    public = task.get("public", {})
                    require(task.get("ok") is True and public.get("source") == "CBACT04C"
                            and task.get("smoke_evidence") == "public-receipt-bytes-v1"
                            and public.get("target") == "Java" and public.get("shapes") == ["ACCTFILE", "TRANSACT"], "task-mismatch")
                    self.before = await self.budget(5)
                elif step == 2:
                    r = await self.tool("describe_copybook", path="account.cpy")
                    require(r.get("record_length") == 300 and r.get("fields"), "copybook-mismatch")
                elif step == 3:
                    r = await self.tool("decode_records", path="accounts.bin", copybook="account.cpy", codec="cp037", framing="fixed")
                    require(isinstance(r.get("records"), list) and r["records"] and r.get("sha256"), "records-mismatch")
                elif step == 4:
                    r = await self.tool("read_job_log", path="job.txt")
                    require(r and not r.get("error") and r.get("ok") is not False and r.get("steps"), "log-mismatch")
                elif step == 5:
                    r = await self.tool("lane_status")
                    require(r.get("status") == "unqualified", "lane-mismatch")
                elif step == 6:
                    before = await self.budget(5)
                    r = await self.tool("decode_records", path="../private", copybook="account.cpy")
                    require(r.get("ok") is False and r.get("error") == "path-refused", "private-path-not-refused")
                    require(await self.budget(5) == before, "private-path-budget-changed")
                elif step == 7:
                    row = await self.submit("good.jar")
                elif step == 8:
                    before = await self.budget(4)
                    r = await self.tool("submit_candidate", path="good.jar", request_id=row["request_id"])
                    require(r.get("ok") is True and r.get("attempt_id") == row["attempt_id"], "idempotency-mismatch")
                    require(await self.budget(4) == before, "idempotency-budget-changed")
                elif step == 9:
                    await self.verdict(row)
                elif step == 10:
                    await self.receipt(row)
                elif step in (11, 12, 13, 14):
                    row = await self.submit({11:"rounding.jar", 12:"skipped.jar", 13:"date.jar", 14:"date.jar"}[step])
                    await self.verdict(row)
                    result = await self.receipt(row)
                    if step == 14:
                        require(row["diagnostics"] == self.report["attempts"][-2]["diagnostics"], "repeated-diagnostic-mismatch")
                        require("repeated-identical-diagnostics" in result.get("alerts", []), "repeated-alert-missing")
                else:
                    before = await self.budget(0)
                    request = str(uuid.uuid4())
                    require(request not in self.ids, "request-id-collision")
                    self.report["refused_request_id"] = request
                    r = await self.tool("submit_candidate", path="good.jar", request_id=request)
                    require(r.get("ok") is False and r.get("error") == "request-refused"
                            and not r.get("attempt_id") and r.get("budget") == {k:v for k,v in before.items() if k != "ok"}, "sixth-not-refused")
                    require(await self.budget(0) == before, "sixth-budget-changed")
                    await self.receipt(row)  # observe the head after the refusal
                self.current.update(outcome="matched", passed=True)
            self.report["status"] = "passed"
        except Exception as exc:
            code = str(exc) if isinstance(exc, Mismatch) else "transport-or-response-failure"
            self.report.update(status="failed", error=code)
            if self.current is not None:
                self.current.update(outcome=code, passed=False)
        finally:
            for attempt in self.report["attempts"]:
                attempt.pop("deadline", None)
            self.report["at_utc"] = datetime.now(timezone.utc).isoformat()
        return self.report


async def protocol(artifacts, state):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    # Same stdio command and RAM-only token environment as inspector.py.
    params = StdioServerParameters(command="/opt/lightyear-verify-venv/bin/lightyear-verify-mcp",
        args=["--workspace", "/srv/dev", "--public-manifest", "/srv/dev/public.json", "--judge-url", "http://127.0.0.1:8770"],
        env={"PATH":os.environ["PATH"], "LIGHTYEAR_VERIFY_TOKEN":os.environ["LIGHTYEAR_VERIFY_TOKEN"]})
    with open(os.devnull, "w") as errors:
        async with stdio_client(params, errlog=errors) as (reader, writer), ClientSession(reader, writer) as session:
            await asyncio.wait_for(session.initialize(), 30)
            names = {t.name for t in (await asyncio.wait_for(session.list_tools(), 30)).tools}
            require(names == TOOLS, "baseline-tool-set-mismatch")
            async def call(name, arguments):
                reply = await session.call_tool(name, arguments)
                require(not reply.is_error, "mcp-tool-error")
                return reply.structured_content
            runner = Walkthrough(call, artifacts)
            state["runner"] = runner
            return await runner.run()


def main():
    import pwd
    if os.geteuid() != pwd.getpwnam("lyagent").pw_uid or not os.environ.get("LIGHTYEAR_VERIFY_TOKEN"):
        raise SystemExit("Run through agent.py as lyagent with its existing token environment")
    path = Path("/srv/dev/walkthrough-report.json")
    # Claim output before any connection/submission; an existing report always refuses.
    with path.open("x", encoding="utf-8") as output:
        state = {}
        try:
            workspace = path.parent
            artifacts = json.loads((workspace/"candidates.json").read_bytes())["jars"]
            for name in ("good.jar", "rounding.jar", "skipped.jar", "date.jar"):
                require(sha((workspace/name).read_bytes()) == artifacts[name], "candidate-hash-mismatch")
            report = asyncio.run(protocol(artifacts, state))
        except (Exception, KeyboardInterrupt):
            report = (state["runner"].report if "runner" in state else
                      dict(schema="verify-smoke-walkthrough/1", steps=[], attempts=[], final_journal_head_sha256=None, model_calls=0))
            report.update(status="failed", error="walkthrough-preflight-or-transport-failure")
        json.dump(report, output, indent=2);output.write("\n");output.flush();os.fsync(output.fileno())
    print(json.dumps({"status":report["status"], "report":str(path), "model_calls":0}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
