"""Real stdio client/server, detached workers, reconnect and CI exit semantics."""
import asyncio
from contextlib import asynccontextmanager
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
import uuid

from lightyear_agent.service import Workflow
from lightyear_workflow.run_store import RunStore
from tests.agent_support import ROOT, fixture


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install .[agent]; mandatory in local-agent CI")
class MCPWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root, self.project = fixture(self)
        self.environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}

    async def start_worker(self):
        if os.name != "nt":
            return
        # Deliberately outside the MCP client's kill-on-close Windows Job.
        process = subprocess.Popen([sys.executable, "-m", "lightyear_agent.cli", "worker", "--project", str(self.project)],
                                   env=self.environment, cwd=self.project.parent, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        def cleanup():
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            process.wait(timeout=15)
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 30
        observer = Workflow(self.project)
        while not observer._broker_running():
            self.assertIsNone(process.poll(), "Separate local worker exited during startup")
            self.assertLess(time.monotonic(), deadline, "Separate local worker did not become ready")
            await asyncio.sleep(0.1)

    @asynccontextmanager
    async def client(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        parameters = StdioServerParameters(command=sys.executable,
            args=["-m", "lightyear_agent.mcp", "--project", str(self.project)],
            env=self.environment, cwd=str(self.project.parent))
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                yield session

    async def call(self, session, name, arguments=None):
        result = await session.call_tool(name, arguments or {})
        self.assertFalse(result.is_error, result)
        self.assertIsInstance(result.structured_content, dict)
        return result.structured_content

    async def test_complete_external_workflow_survives_mcp_disconnect(self):
        asyncio.get_running_loop().slow_callback_duration = 2
        await self.start_worker()
        request_id = str(uuid.uuid4())
        async with self.client() as session:
            tools = (await session.list_tools()).tools
            self.assertEqual({"capabilities", "plan", "start", "status", "events", "verify", "export", "resume", "cancel"}, {t.name for t in tools})
            self.assertTrue(all(t.input_schema["type"] == "object" for t in tools))
            capabilities = await self.call(session, "capabilities")
            self.assertFalse(capabilities["creates_human_approval"])
            plan = await self.call(session, "plan")
            self.assertTrue(plan["ok"], plan)
            full = await session.read_resource("lightyear://plan/current")
            self.assertEqual(plan["plan_sha256"], json.loads(full.contents[0].text)["content_sha256"])
            started = await self.call(session, "start", {"plan_sha256": plan["plan_sha256"], "request_id": request_id})
            self.assertTrue(started["ok"], started)
            run_id = started["run_id"]
            duplicate = await self.call(session, "start", {"plan_sha256": plan["plan_sha256"], "request_id": request_id})
            self.assertEqual(run_id, duplicate["run_id"])
            self.assertFalse(duplicate["new_dispatch"])
        # The real MCP server is gone. No mocked dispatcher or worker: observe
        # completion through a fresh service while the detached engine runs.
        observer = Workflow(self.project)
        deadline = time.monotonic() + 240
        while True:
            status = await asyncio.to_thread(observer.invoke, "status", run_id=run_id)
            if not status["ok"] or status.get("terminal") or status["status"] == "execution-failed":
                break
            self.assertLess(time.monotonic(), deadline, status)
            await asyncio.sleep(0.5)
        self.assertTrue(status["ok"], status)
        self.assertEqual("human-decision-required", status["status"], status)
        self.assertEqual(19, status["summary"]["actions_executed"])
        async with self.client() as session:
            verified = await self.call(session, "verify", {"run_id": run_id})
            self.assertTrue(verified["verified"])
            self.assertFalse(verified["workflow_completed"])
            page = await self.call(session, "events", {"run_id": run_id, "limit": 3})
            self.assertEqual(3, len(page["events"]))
            self.assertTrue(page["has_more"])
            exported = await self.call(session, "export", {"run_id": run_id})
            self.assertTrue(exported["ok"], exported)
            resource = await session.read_resource(exported["resource_uri"])
            self.assertEqual("human-decision-required", json.loads(resource.contents[0].text)["halt_reason"])
            denied = await self.call(session, "status", {"run_id": "../../private"})
            self.assertFalse(denied["ok"])
            self.assertEqual("invalid-run-id", denied["error"]["code"])
        command = [sys.executable, "-m", "lightyear_agent.cli", "verify", "--project", str(self.project), "--run-id", run_id]
        cli = await asyncio.to_thread(subprocess.run, command, cwd=self.project.parent, env=self.environment,
                                      capture_output=True, text=True, timeout=60)
        self.assertEqual(3, cli.returncode, cli.stderr)
        self.assertEqual(verified["journal_head_sha256"], json.loads(cli.stdout)["journal_head_sha256"])

    async def test_current_plan_resource_rejects_changed_project_configuration(self):
        from mcp.shared.exceptions import MCPError
        async with self.client() as session:
            await session.read_resource("lightyear://plan/current")
            original = self.project.read_text()
            config = json.loads(original)
            config["project_id"] = "changed-after-server-start"
            self.project.write_text(json.dumps(config))
            try:
                with self.assertRaises(MCPError):
                    await session.read_resource("lightyear://plan/current")
                response = await self.call(session, "plan")
                self.assertEqual("configuration-changed", response["error"]["code"])
            finally:
                self.project.write_text(original)

    async def test_cancel_survives_disconnect_and_resume_only_settles_the_stop(self):
        await self.start_worker()
        observer = Workflow(self.project)
        request_id = str(uuid.uuid4())
        _, run_id = observer._run_id(request_id)
        # Hold the worker lease to make the queued/in-flight race deterministic
        # without changing the production runner or its bound implementation.
        lease = RunStore(observer._run_directory(run_id) / "lease")
        try:
            async with self.client() as session:
                plan = await self.call(session, "plan")
                started = await self.call(session, "start", {"plan_sha256": plan["plan_sha256"], "request_id": request_id})
                self.assertTrue(started["ok"], started)
                request = await self.call(session, "cancel", {"run_id": run_id})
                self.assertEqual("cancel-requested", request["status"], request)
                self.assertFalse(request["terminal"])
            self.assertEqual(request["cancellation_requested_at"], observer.invoke("status", run_id=run_id)["cancellation_requested_at"])
        finally:
            lease.close()
        async with self.client() as session:
            resumed = await self.call(session, "resume", {"run_id": run_id})
            # The independent Windows worker can acknowledge cancellation before
            # it finishes publishing the terminal archive. Reconnect may observe
            # that publication window, or the worker may still own the run lease.
            if resumed["status"] == "resume-requested":
                self.assertEqual("Repair terminal archive publication only; no actions will repeat.", resumed["note"])
            else:
                self.assertIn(resumed["status"], {"cancel-requested", "cancelled"}, resumed)
                self.assertFalse(resumed["new_dispatch"])
            deadline = time.monotonic() + 60
            while True:
                status = await self.call(session, "status", {"run_id": run_id})
                self.assertIn(status["status"], {"cancel-requested", "cancelled"}, status)
                if status["status"] == "cancelled" and status["dispatch_state"] == "finished":
                    break
                self.assertLess(time.monotonic(), deadline, status)
                await asyncio.sleep(0.1)
            resumed = await self.call(session, "resume", {"run_id": run_id})
            self.assertEqual("cancelled", resumed["status"], resumed)
            self.assertFalse(resumed["new_dispatch"])
            verified = await self.call(session, "verify", {"run_id": run_id})
            self.assertTrue(verified["verified"])
            self.assertFalse(verified["workflow_completed"])
            self.assertEqual(0, verified["summary"]["actions_executed"])
            exported = await self.call(session, "export", {"run_id": run_id})
            resource = await session.read_resource(exported["resource_uri"])
            self.assertEqual("cancelled", json.loads(resource.contents[0].text)["halt_reason"])
        cli = await asyncio.to_thread(subprocess.run,
            [sys.executable, "-m", "lightyear_agent.cli", "cancel", "--project", str(self.project), "--run-id", run_id],
            cwd=self.project.parent, env=self.environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(5, cli.returncode, cli.stderr)
        self.assertEqual("cancelled", json.loads(cli.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
