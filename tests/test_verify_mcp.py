"""Zero-model protocol, candidate execution, disclosure and OS isolation acceptance.

Linux integration runs as root ONLY to launch two unprivileged identities. The
judge and MCP server themselves are never root. Windows runs the toolkit tests.
"""

import asyncio
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import zipfile
from datetime import datetime, timezone

from lightyear_toolkit.workspace import Workspace, Refused, sha
from lightyear_control_tower.decisions import canonical, verify_envelope

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/mainframe/fixtures/arrival-rehearsal"
JAR = ROOT / "candidate-java/target/carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"


class PublicToolkitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        cp = ROOT / "spec/mainframe/copybooks/CVACT01Y.cpy"
        (self.root / "account.cpy").write_bytes(cp.read_bytes())
        self.ws = Workspace(
            self.root,
            {"account.cpy": {"purpose": "copybook", "sha256": sha(cp.read_bytes())}},
        )

    def test_paths_sizes_public_binding_and_layout(self):
        self.assertEqual(300, self.ws.describe("account.cpy")["record_length"])
        for name in (
            "../account.cpy",
            str(ROOT / "pyproject.toml"),
            "C:/secret",
            "x\\y",
        ):
            with self.subTest(name=name), self.assertRaises(Refused):
                self.ws.read(name)
        with self.assertRaises(Refused):
            self.ws.read("account.cpy", limit=1)
        with self.assertRaises(Refused):
            self.ws.log("account.cpy")
        (self.root / "account.cpy").write_bytes(b"private changed bytes")
        with self.assertRaises(Refused):
            self.ws.describe("account.cpy")

    @unittest.skipUnless(os.name == "posix", "POSIX special-file assertions")
    def test_symlink_fifo_and_directory_refused(self):
        (self.root / "link").symlink_to(self.root / "account.cpy")
        os.mkfifo(self.root / "pipe")
        for name in ("link", "pipe", "."):
            with self.subTest(name=name), self.assertRaises((ValueError, OSError)):
                self.ws.read(name)

    def test_lane_does_not_invent_qualification(self):
        self.assertEqual("unqualified", self.ws.lane("CBACT04C", "Java")["status"])
        with self.assertRaises(Refused):
            self.ws.lane("other", "Java")


@unittest.skipUnless(
    sys.platform.startswith("linux") and os.geteuid() == 0 and JAR.is_file(),
    "Requires Linux two-user acceptance runner and built candidate JAR",
)
class VerifyAcceptance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lightyear-verify-")
        self.base = Path(self.tmp.name)
        self.base.chmod(0o755)
        self.addCleanup(self.tmp.cleanup)
        self.agent, self.judge_uid = 65534, 1000
        self.public = self.base / "public"
        self.public.mkdir(mode=0o755)
        self.tower = self.base / "tower"
        self.tower.mkdir()
        os.chown(self.tower, self.judge_uid, self.judge_uid)
        self.private = self.base / "operator"
        self.private.mkdir(mode=0o700)
        os.chown(self.private, self.judge_uid, self.judge_uid)
        self.eval = self.private / "evaluation"
        self.eval.mkdir()
        for source in FIXTURE.glob("INTCALC-run1-*"):
            shutil.copytree(source, self.eval / source.name)
        self.eval.chmod(0o700)
        # A canary absent from all public files; identical before/after address change
        # does not change business semantics. Only synthetic rehearsal copies change.
        self.canary = "Q" + uuid.uuid4().hex[:8].upper()
        from lightyear_mainframe.records import load_copybook

        layout = load_copybook(ROOT / "spec/mainframe/copybooks/CVACT01Y.cpy")
        address = next(f for f in layout.fields if f.path.endswith("ACCT-ADDR-ZIP"))
        for path in self.eval.rglob("ACCTFILE.bin"):
            raw = bytearray(path.read_bytes())
            raw[address.offset : address.offset + address.length] = self.canary.ljust(
                address.length
            ).encode("cp037")
            path.write_bytes(raw)
        for path in (self.eval, *self.eval.rglob("*")):
            os.chown(path, self.judge_uid, self.judge_uid)
        public_files = {}

        def add(source, name, purpose, **extra):
            raw = source.read_bytes()
            (self.public / name).write_bytes(raw)
            public_files[name] = {"purpose": purpose, "sha256": sha(raw), **extra}

        add(ROOT / "spec/mainframe/copybooks/CVACT01Y.cpy", "account.cpy", "copybook")
        first = next(FIXTURE.iterdir())
        add(
            first / "before/ACCTFILE.bin",
            "accounts.bin",
            "development-records",
            copybook="account.cpy",
        )
        add(first / "job-output.txt", "job.txt", "development-log")
        # Document every public overlap by exact fixture-file hash, never by a
        # blanket exemption for numbers, keys or particular value patterns.
        from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding
        from lightyear_mainframe.records import decode_fixed

        bindings = load_bindings()

        def values(folder):
            result = set()
            for meta_path in folder.glob("*/run.json"):
                meta = json.loads(meta_path.read_bytes())
                for d in meta["datasets"]:
                    binding = dataset_binding(bindings, meta["job"], d["step"], d["dd"])
                    if not binding.get("copybook"):
                        continue
                    for record in decode_fixed(
                        load_copybook(ROOT / binding["copybook"]),
                        (meta_path.parent / d["file"]).read_bytes(),
                        codec=d["codec"],
                    ):
                        for field in record["fields"]:
                            value = str(field["value"]).strip()
                            if len(value) >= 4:
                                result.add(value)
            return result

        # Only INTCALC development files are declared; Maintec is never an overlap source.
        development = self.base / "development"
        development.mkdir()
        shutil.copytree(next(FIXTURE.glob("INTCALC-run1-*")), development / "run1")
        self.public_values = values(development)
        self.evaluation_values = values(self.eval)
        self.protected_values = self.evaluation_values - self.public_values
        self.assertIn(self.canary, self.protected_values)
        overlaps = {
            p.relative_to(development).as_posix(): sha(p.read_bytes())
            for p in development.rglob("*")
            if p.is_file()
        }
        self.manifest = self.public / "public.json"
        self.manifest.write_bytes(
            canonical(
                {"files": public_files, "documented_public_overlap_files": overlaps}
            )
        )
        shutil.copyfile(JAR, self.public / "good.jar")
        self.build_mutants()
        self.root = self.private / "session"
        config = {
            "task_id": "verify-intcalc",
            "agent_uid": self.agent,
            "evaluation": str(self.eval),
            "exports": str(self.tower / "exports"),
            "tower_workspace": str(self.tower),
            "submissions": 5,
            "attempt_slots": 5,
            "fixture": self._testMethodName != "test_confidential_receipts_and_replay",
            "public_task": {
                "development_manifest_sha256": sha(self.manifest.read_bytes()),
                "shapes": ["ACCTFILE", "TRANSACT"],
                "source": "CBACT04C",
                "target": "Java",
            },
        }
        config_path = self.private / "config.json"
        config_path.write_bytes(canonical(config))
        self.env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
        init = subprocess.run(
            self.as_user(self.judge_uid)
            + [
                sys.executable,
                "-m",
                "lightyear_judge.cli",
                "init",
                "--data-root",
                str(self.root),
                "--config",
                str(config_path),
            ],
            env=self.env,
            capture_output=True,
        )
        self.assertEqual(0, init.returncode, init.stderr.decode())
        self.log = (self.private / "service.log").open("wb")
        self.process = subprocess.Popen(
            self.as_user(self.judge_uid)
            + [
                sys.executable,
                "-m",
                "lightyear_judge.cli",
                "serve",
                "--data-root",
                str(self.root),
                "--task",
                "verify-intcalc",
                "--port",
                "0",
            ],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=self.log,
        )
        self.addCleanup(self.stop)
        startup = await asyncio.wait_for(
            asyncio.to_thread(self.process.stdout.readline), 30
        )
        self.assertTrue(startup, (self.private / "service.log").read_text())
        self.url = "http://127.0.0.1:" + str(json.loads(startup)["port"])
        self.env["LIGHTYEAR_VERIFY_TOKEN"] = (self.root / "token").read_text().strip()
        self.responses = []

    def as_user(self, uid):
        return ["setpriv", "--reuid", str(uid), "--regid", str(uid), "--clear-groups"]

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=15)
        self.process.stdout.close()
        self.log.close()

    def build_mutants(self):
        original = (
            ROOT
            / "candidate-java/src/main/java/ai/lightyear/carddemo/service/InterestCalculationService.java"
        )
        changes = {
            "rounding": (
                ".divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)",
                '.divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN).add(new BigDecimal("0.01"))',
            ),
            "skipped": (
                "new ArrayList<>(accountById.values()), generated",
                "new ArrayList<>(accountById.values()).subList(1, accountById.size()), generated",
            ),
            "date": (
                "                    timestamp,",
                '                    "2022-07-19-00.00.00.000000",',
            ),
        }
        for name, (old, new) in changes.items():
            scratch = self.base / ("compile-" + name)
            scratch.mkdir()
            source = scratch / original.name
            self.assertIn(old, original.read_text())
            source.write_text(original.read_text().replace(old, new))
            annotation = scratch / "Service.java"
            annotation.write_text(
                "package org.springframework.stereotype; @java.lang.annotation.Retention(java.lang.annotation.RetentionPolicy.RUNTIME) public @interface Service {}"
            )
            subprocess.run(
                [
                    "javac",
                    "--release",
                    "17",
                    "-cp",
                    str(ROOT / "candidate-java/target/classes"),
                    "-d",
                    str(scratch),
                    str(annotation),
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            compiled = (
                scratch
                / "ai/lightyear/carddemo/service/InterestCalculationService.class"
            )
            with (
                zipfile.ZipFile(JAR) as z,
                zipfile.ZipFile(self.public / (name + ".jar"), "w") as out,
            ):
                for info in z.infolist():
                    data = (
                        compiled.read_bytes()
                        if info.filename
                        == "BOOT-INF/classes/ai/lightyear/carddemo/service/InterestCalculationService.class"
                        else z.read(info)
                    )
                    out.writestr(info, data)

    async def test_hostile_candidate_and_timestamp_negative_control(self):
        scratch = self.private / "hostile"
        scratch.mkdir()
        source = scratch / "Probe.java"
        source.write_text(
            """
import java.nio.file.*;
import java.net.*;
public class Probe {
  public static void main(String[] args) throws Exception {
    if (args.length == 1) {
      Thread.sleep(1500);
      Files.writeString(Path.of("/outputs/acctdata.txt"), "ORPHAN");
      return;
    }
    boolean read = false, net = false;
    try { Files.readAllBytes(Path.of(args[0])); read = true; } catch (Exception expected) {}
    try (Socket s = new Socket()) { s.connect(new InetSocketAddress("127.0.0.1", Integer.parseInt(args[1])), 1000); net = true; } catch (Exception expected) {}
    System.out.println("host_read=" + read + ";network=" + net);
    new ProcessBuilder("/runtime/bin/java", "-jar", "/candidate.jar", "child").inheritIO().start();
  }
}
"""
        )
        subprocess.run(["javac", str(source)], check=True, capture_output=True)
        jar = scratch / "probe.jar"
        subprocess.run(
            [
                "jar",
                "--create",
                "--file",
                str(jar),
                "--main-class",
                "Probe",
                "-C",
                str(scratch),
                "Probe.class",
            ],
            check=True,
            capture_output=True,
        )
        (scratch / "inputs").mkdir()
        for p in (scratch, *scratch.rglob("*")):
            os.chown(p, self.judge_uid, self.judge_uid)
        script = "from pathlib import Path; import sys; from lightyear_judge.sandbox import run; p=Path(sys.argv[1]); print(run(p/'probe.jar',p/'inputs',p/'outputs',[sys.argv[2],sys.argv[3]],p/'log',timeout=10))"
        result = subprocess.run(
            self.as_user(self.judge_uid)
            + [
                sys.executable,
                "-c",
                script,
                str(scratch),
                str(self.root / "authority.pem"),
                self.url.rsplit(":", 1)[1],
            ],
            env=self.env,
            capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode())
        self.assertIn("host_read=false;network=false", (scratch / "log").read_text())
        time.sleep(2)
        self.assertEqual(
            b"",
            (scratch / "outputs/acctdata.txt").read_bytes(),
            "Candidate descendant survived",
        )
        negative = self.private / "negative"
        negative.mkdir()
        delivery = negative / "delivery"
        delivery.mkdir()
        shutil.copytree(next(FIXTURE.glob("INTCALC-run2-*")), delivery / "run2")
        for p in (negative, *negative.rglob("*")):
            os.chown(p, self.judge_uid, self.judge_uid)
        script = "from pathlib import Path; import sys,json; from lightyear_judge.evaluation import evaluate; from lightyear_mainframe.zos_evidence import Signer; p=Path(sys.argv[1]); result=evaluate(p,p/'delivery',Path(sys.argv[2]),Signer(Path(sys.argv[3])),review_root=sys.argv[4]); print(json.dumps(result[:2]))"
        result = subprocess.run(
            self.as_user(self.judge_uid)
            + [
                sys.executable,
                "-c",
                script,
                str(negative),
                str(JAR),
                str(self.root / "authority.pem"),
                str(self.tower),
            ],
            env=self.env,
            capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode())
        verdict, ds = json.loads(result.stdout)
        self.assertEqual("divergent", verdict)
        self.assertTrue(any(d["field"].endswith("TRAN-PROC-TS") for d in ds))

    async def test_confidential_receipts_and_replay(self):
        from lightyear_toolkit.client import JudgeClient
        from lightyear_judge.service import replay, journal

        client = JudgeClient(self.url, self.env["LIGHTYEAR_VERIFY_TOKEN"])
        replies = []
        for name in ("good", "rounding", "skipped", "date", "date"):
            submitted = await asyncio.to_thread(
                client.call,
                "submit_candidate",
                request_id=str(uuid.uuid4()),
                artifact=base64.b64encode(
                    (self.public / (name + ".jar")).read_bytes()
                ).decode(),
            )
            self.assertTrue(submitted["ok"], submitted)
            self.assertEqual("pending", submitted["verdict"])
            attempt = submitted["attempt_id"]
            deadline = time.monotonic() + 340
            while True:
                result = await asyncio.to_thread(
                    client.call, "get_verdict", attempt_id=attempt
                )
                self.assertTrue(result["ok"], result)
                if result["verdict"] != "pending" or time.monotonic() >= deadline:
                    break
                await asyncio.sleep(2)
            self.assertEqual(
                "equivalent" if name == "good" else "divergent", result["verdict"]
            )
            for d in result["diagnostics"]:
                self.assertEqual({"dataset", "kind"}, set(d))
                self.assertEqual("differs", d["kind"])
            receipt = (
                await asyncio.to_thread(client.call, "get_receipt", attempt_id=attempt)
            )["receipt"]
            self.assertNotIn("evidence_sha256", receipt)
            replies.extend([submitted, result, receipt])
        key = (self.root / "authority.public.pem").read_bytes()
        events = journal(self.root, key)
        self.assertEqual(
            5,
            replay(self.root, key, events[-1]["content_sha256"])[
                "native_verdicts_replayed"
            ],
        )
        exposed = json.dumps(replies) + "".join(
            p.read_text() for p in (self.tower / "exports").glob("*.json")
        )
        self.assertEqual(
            [], [sha(v.encode()) for v in self.protected_values if v in exposed]
        )
        self.assertNotIn("count_band", exposed)
        self.assertNotIn("TRAN-AMT", exposed)
        print(
            "VERIFY_CONFIDENTIAL: five real sandbox submissions and offline replays; zero protected-value matches"
        )

    async def test_full_sdk_session_and_security(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from lightyear_judge.service import replay, journal
        from lightyear_control_tower.verify_status import project
        from lightyear_control_tower.requests import RequestInbox
        from lightyear_control_tower.kinds import default_registry

        parameters = StdioServerParameters(
            command="setpriv",
            args=self.as_user(self.agent)[1:]
            + [
                sys.executable,
                "-m",
                "lightyear_toolkit.mcp",
                "--workspace",
                str(self.public),
                "--public-manifest",
                str(self.manifest),
                "--judge-url",
                self.url,
            ],
            env=self.env,
            cwd=str(self.public),
        )
        denied = parameters.model_copy(
            update={"env": {**self.env, "LIGHTYEAR_VERIFY_TOKEN": "wrong-token"}}
        )
        async with (
            stdio_client(denied) as (reader, writer),
            ClientSession(reader, writer) as client,
        ):
            await client.initialize()
            for method in ("get_task", "get_budget"):
                response = (await client.call_tool(method, {})).structured_content
                self.responses.append(response)
                self.assertFalse(response["ok"])
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as client,
        ):
            await client.initialize()
            names = {t.name for t in (await client.list_tools()).tools}
            self.assertEqual(
                {
                    "describe_copybook",
                    "decode_records",
                    "read_job_log",
                    "lane_status",
                    "get_task",
                    "submit_candidate",
                    "get_verdict",
                    "get_budget",
                    "get_receipt",
                    "propose_normalization",
                },
                names,
            )

            async def call(name, **args):
                result = await client.call_tool(name, args)
                self.assertFalse(result.is_error, result)
                value = result.structured_content
                self.responses.append(value)
                return value

            self.assertEqual(
                300,
                (await call("describe_copybook", path="account.cpy"))["record_length"],
            )
            self.assertTrue(
                (
                    await call(
                        "decode_records", path="accounts.bin", copybook="account.cpy"
                    )
                )["records"]
            )
            self.assertEqual(
                "zos-run-observation/1",
                (await call("read_job_log", path="job.txt"))["schema"],
            )
            self.assertEqual("unqualified", (await call("lane_status"))["status"])
            self.assertTrue((await call("get_task"))["ok"])
            self.assertEqual(5, (await call("get_budget"))["submissions_left"])
            for method, args in (
                ("describe_copybook", {"path": "missing"}),
                ("read_job_log", {"path": "missing"}),
                ("lane_status", {"source": "unknown"}),
                (
                    "decode_records",
                    {
                        "path": "accounts.bin",
                        "copybook": "account.cpy",
                        "codec": "utf8",
                    },
                ),
            ):
                self.assertFalse((await call(method, **args))["ok"])
            for name in (
                "../operator/session/token",
                str(self.root / "token"),
                "missing",
            ):
                self.assertFalse(
                    (await call("decode_records", path=name, copybook="account.cpy"))[
                        "ok"
                    ]
                )
            (self.public / "secret-link").symlink_to(self.root / "token")
            self.assertFalse(
                (
                    await call(
                        "decode_records", path="secret-link", copybook="account.cpy"
                    )
                )["ok"]
            )
            self.assertFalse(
                (await call("get_verdict", attempt_id="../../token"))["ok"]
            )
            self.assertFalse((await call("get_receipt", attempt_id="unknown"))["ok"])
            self.assertFalse(
                (
                    await call(
                        "propose_normalization",
                        attempt_id="unknown",
                        dataset="x",
                        field="x",
                    )
                )["ok"]
            )
            self.assertFalse(
                (
                    await call(
                        "submit_candidate",
                        path="accounts.bin",
                        request_id=str(uuid.uuid4()),
                    )
                )["ok"]
            )
            receipts = []
            for index, name in enumerate(
                ("good", "rounding", "skipped", "date", "date")
            ):
                request = str(uuid.uuid4())
                submitted = await call(
                    "submit_candidate", path=name + ".jar", request_id=request
                )
                self.assertTrue(submitted["ok"], submitted)
                attempt = submitted["attempt_id"]
                self.assertEqual(
                    attempt,
                    (
                        await call(
                            "submit_candidate", path=name + ".jar", request_id=request
                        )
                    )["attempt_id"],
                )
                verdict = await call("get_verdict", attempt_id=attempt)
                deadline = time.monotonic() + 340
                while (
                    verdict.get("verdict") == "pending" and time.monotonic() < deadline
                ):
                    await asyncio.sleep(2)
                    verdict = await call("get_verdict", attempt_id=attempt)
                self.assertEqual(
                    "equivalent" if name == "good" else "divergent",
                    verdict["verdict"],
                    verdict,
                )
                if name == "rounding":
                    self.assertTrue(
                        any(
                            d["field"].endswith("TRAN-AMT")
                            for d in verdict["diagnostics"]
                        ),
                        verdict,
                    )
                if name == "skipped":
                    self.assertTrue(
                        any(
                            d["kind"] == "missing-record"
                            and d["dataset"] == "STEP15/ACCTFILE"
                            for d in verdict["diagnostics"]
                        ),
                        verdict,
                    )
                if name == "date":
                    self.assertTrue(
                        any("TS" in d["field"] for d in verdict["diagnostics"]), verdict
                    )
                    diagnostic = next(
                        d
                        for d in verdict["diagnostics"]
                        if d["field"].endswith("TRAN-PROC-TS")
                    )
                    proposal = await call(
                        "propose_normalization",
                        attempt_id=attempt,
                        dataset=diagnostic["dataset"],
                        field=diagnostic["field"],
                    )
                    self.assertTrue(proposal["ok"], proposal)
                receipts.append(
                    (await call("get_receipt", attempt_id=attempt))["receipt"]
                )
            self.assertFalse(
                (
                    await call(
                        "submit_candidate",
                        path="good.jar",
                        request_id=str(uuid.uuid4()),
                    )
                )["ok"]
            )
            self.assertEqual(0, (await call("get_budget"))["submissions_left"])
        key = (self.root / "authority.public.pem").read_bytes()
        events = journal(self.root, key)
        self.assertTrue(
            all(
                verify_envelope({k: v for k, v in r.items() if k != "ok"}, key)
                for r in receipts
            )
        )
        self.assertEqual(
            5,
            replay(self.root, key, events[-1]["content_sha256"])[
                "native_verdicts_replayed"
            ],
        )
        task = json.loads((self.root / "task.json").read_bytes())
        view = project(
            self.tower / "exports",
            key,
            "verify-intcalc",
            {"task": task["content_sha256"]},
            datetime.now(timezone.utc),
            scope="verify-intcalc",
        )
        self.assertEqual(5, view["submissions"])
        self.assertTrue(
            {"budget-exhausted", "repeated-identical-diagnostics"}
            <= {a["code"] for a in view["alerts"]}
        )
        queue = RequestInbox(self.tower, "verify-intcalc", default_registry()).queue()
        self.assertTrue(queue)
        self.assertTrue(all(x["status"] == "pending" for x in queue), queue)
        from lightyear_control_tower.console import ConsoleService, provision
        from lightyear_control_tower.server import ConsoleAPI

        authority = self.base / "console-authority/authority.json"
        token = (
            provision(authority, "verify-intcalc", "reviewer", "Test operator")
            .read_text()
            .strip()
        )
        console = ConsoleService(self.tower, authority)
        self.addCleanup(console.close)
        console.grant_roles(
            "reviewer",
            ["operator", "normalization-approver"],
            reason="Synthetic acceptance only",
        )
        token = console.login(token)["token"]
        (self.tower / "producer.public.pem").write_bytes(key)
        (self.tower / "control-tower").mkdir(exist_ok=True)
        (self.tower / "control-tower/campaigns.json").write_bytes(
            canonical(
                {
                    "campaigns": [
                        {
                            "id": "verify-intcalc",
                            "scope": "verify-intcalc",
                            "adapter": "tower-status-export",
                            "read_mode": "write-once-status",
                            "producer_profile": "lightyear-verify",
                            "export_directory": str(self.tower / "exports"),
                            "trusted_public_key": str(
                                self.tower / "producer.public.pem"
                            ),
                            "bindings": {"task": task["content_sha256"]},
                        }
                    ]
                }
            )
        )
        api = ConsoleAPI(console)
        self.assertEqual(
            5,
            api.campaigns.view("verify-intcalc", now=datetime.now(timezone.utc))[
                "submissions"
            ],
        )
        self.assertTrue(console.queue(token))
        agent_credential = console.add_identity(
            "test-agent", "Test agent", identity_kind="agent"
        )
        console.grant_roles("test-agent", ["agent"], reason="Synthetic acceptance only")
        agent_queue = console.queue(console.login(agent_credential)["token"])
        self.assertFalse(
            any(item.get("decidable") for item in agent_queue.get("items", []))
        )
        self.responses.extend(
            [
                api.read("campaign", token, {"id": "verify-intcalc"}),
                api.read("queue", token, {}),
            ]
        )
        # Actual OS reads as the same identity that hosted MCP, not simulated ACLs.
        check = subprocess.run(
            self.as_user(self.agent)
            + [
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).read_bytes()",
                str(self.root / "token"),
            ],
            capture_output=True,
        )
        self.assertNotEqual(0, check.returncode)
        joined = json.dumps(self.responses + [view, queue])
        joined += "".join(
            p.read_text() for p in (self.tower / "exports").glob("*.json")
        )
        matches = [sha(v.encode()) for v in self.protected_values if v in joined]
        self.assertEqual([], matches, "Protected-value matches (hashes only)")
        self.assertNotIn(self.env["LIGHTYEAR_VERIFY_TOKEN"], joined)
        self.assertNotIn("PRIVATE KEY", joined)
        # Tamper each independently, retain the original signed bytes afterward.
        path = self.root / "receipts" / (receipts[0]["attempt_id"] + ".json")
        original = path.read_bytes()
        corrupt = json.loads(original)
        corrupt["verdict"] = "divergent"
        path.write_bytes(canonical(corrupt))
        with self.assertRaises(ValueError):
            replay(self.root, key, events[-1]["content_sha256"])
        path.write_bytes(original)
        event = self.root / "journal/000001.json"
        original = event.read_bytes()
        changed = json.loads(original)
        changed["kind"] = "tampered"
        event.write_bytes(canonical(changed))
        with self.assertRaises(ValueError):
            replay(self.root, key, events[-1]["content_sha256"])
        event.write_bytes(original)
        # Process restart reuses the journal; it cannot buy five more submissions.
        self.stop()
        script = "from lightyear_judge.service import Judge; import sys,json; j=Judge(sys.argv[1],task='verify-intcalc'); print(json.dumps(j.budget())); j.close()"
        restarted = subprocess.run(
            self.as_user(self.judge_uid)
            + [sys.executable, "-c", script, str(self.root)],
            env=self.env,
            capture_output=True,
        )
        self.assertEqual(0, restarted.returncode, restarted.stderr.decode())
        self.assertEqual(0, json.loads(restarted.stdout)["submissions_left"])
        print(
            "VERIFY_ACCEPTANCE: five real sandbox submissions; five existing offline verdict replays; two OS identities; zero model calls"
        )
