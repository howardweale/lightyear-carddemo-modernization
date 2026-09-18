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
from tests.agent_support import ROOT, fixture


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install .[agent]; mandatory in local-agent CI")
class MCPWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root, self.project = fixture(self)
        self.environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}

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
        request_id = str(uuid.uuid4())
        async with self.client() as session:
            tools = (await session.list_tools()).tools
            self.assertEqual({"capabilities", "plan", "start", "status", "events", "verify", "export", "resume"}, {t.name for t in tools})
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


if __name__ == "__main__":
    unittest.main()
