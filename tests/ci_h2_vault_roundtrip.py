"""Linux CI integration using only public rows and a Docker transport double."""
import ast
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import unittest

from lightyear_factory import public_repair_durable as durable
from tools import intcalc_h3_custody as h3
from tools import intcalc_h3_usb_channel as channel
from tools import intcalc_hidden_answer_receiver as receiver
from tools import intcalc_private_answer_session as session


stream = session.stream
# RFC 7748 section 6.1 Alice PUBLIC value, encoded as a native age recipient.
RECIPIENT = "age1s5s0qzvfxzn4gayt0hwtg0hhtgxm7wsdycup4a8t5j5ca25mfe4qt4hs7q"
AGE_SHA256 = "eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c"
IMAGE = "sha256:" + "1" * 64


def public_stream(count):
    cases = []
    rows = []
    for index in range(count):
        inputs = {dd: "41" for dd in stream.FIELDS}
        clock = dict(processing_date="2026111600", timestamp="2026-11-16-12.00.00.000000")
        cases.append(dict(id=f"HC-{index+1:03d}", inputs=inputs, **clock))
        rows.append(dict(sequence=index, inputs=inputs, outputs={dd: "42" for dd in stream.CHANNELS},
                         exit=0, compare_output_files=True, **clock))
    payload = dict(schema="fresh-heldout-inputs/1", qualified=False, expected_outputs_present=False,
                   named_limit="open-source reference, not mainframe-proven; inputs only, unqualified",
                   source_manifest={"generator_sha256": "1"*64}, cases=cases)
    first = dict(schema="heldout-input-commitment/1", count=count,
                 sha256=stream.sha(stream.canonical(payload)))
    end = dict(schema="heldout-answer-end/1", count=count, complete=True)
    frames = [stream.canonical(row) for row in (first, *rows, end)]
    return b"".join(len(raw).to_bytes(8, "big") + raw for raw in frames), first["sha256"]


class DockerFixture:
    """Supply public Docker replies; use real Git and a real stdin/stdout child for attach."""
    def __init__(self, parent, frames):
        self.commands = self
        self.created = self.removed = self.observed = False
        self.name = None
        self.executable = parent / "public-docker"
        self.executable.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "assert sys.argv[5:8] == ['start', '--attach', '--interactive']\n"
            "assert sys.stdin.buffer.read(33) == bytes(32)\n"
            f"sys.stdout.buffer.write({frames!r})\n", encoding="ascii")
        self.executable.chmod(0o700)

    def out(self, args, **limits):
        if args[0] == "git":
            return subprocess.check_output(args, timeout=15)
        assert args[0] == "docker" and "build" in args
        Path(args[args.index("--iidfile") + 1]).write_text(IMAGE, encoding="ascii")
        return b""

    def docker(self, action, *args, **limits):
        if action == "image":
            assert args == ("inspect", IMAGE)
            return stream.canonical([dict(Id=IMAGE, Architecture="amd64", Os="linux")])
        if action == "create":
            assert not self.created
            self.name = args[args.index("--name") + 1]
            self.uid = args[args.index("--user") + 1]
            self.mounts = []
            for i, arg in enumerate(args):
                if arg == "--mount":
                    spec = args[i+1].split(",")
                    values = dict(item.split("=", 1) for item in spec if "=" in item)
                    self.mounts.append(dict(Type=values["type"], Source=values["src"],
                                            Destination=values["dst"], RW="readonly" not in spec))
            self.created = True
            return b""
        if action == "inspect":
            assert self.created and args == (self.name,)
            config = dict(Image=IMAGE, User=self.uid, OpenStdin=True, Tty=False)
            host = dict(NetworkMode="none", ReadonlyRootfs=True, CapDrop=["ALL"], Memory=2**31,
                        PidsLimit=128, NanoCpus=2000000000, CgroupnsMode="private",
                        LogConfig={"Type": "none"}, SecurityOpt=["no-new-privileges"],
                        Tmpfs={"/work": "", "/tmp": ""})
            return stream.canonical([dict(Config=config, HostConfig=host, Mounts=self.mounts)])
        if action == "rm":
            assert self.created and args == ("-f", self.name)
            self.removed = True
            return b""
        assert action == "ps" and self.removed
        return b""

    def observe(self):
        # The CI fixture observes Docker cleanup; real WSL custody is operator-only.
        assert self.removed
        self.observed = True


class VaultContract(unittest.TestCase):
    def setUp(self):
        self.opid = secrets.token_hex(32)
        self.assertRegex(self.opid, r"^[0-9a-f]{64}$")
        parent = self.enterContext(tempfile.TemporaryDirectory(dir=os.environ["H2_SYNTHETIC_PARENT"]))
        self.parent = Path(parent)
        self.frames, self.input_hash = public_stream(64)
        self.host = DockerFixture(self.parent, self.frames)
        self.config = self.parent / "client-config"
        self.config.mkdir(mode=0o700)
        self.session_dir = self.parent / ("answers-" + self.opid)
        self.vault = self.session_dir / "encrypted"

    def produce(self):
        root = session.ref.ROOT
        cmd = ["git", "-C", str(root), "rev-parse"]
        commit, tree = subprocess.check_output([*cmd, "HEAD", "HEAD^{tree}"], text=True).split()
        docker = self.host.executable
        profile = dict(private_root=str(self.parent), client_config=str(self.config),
                       source_commit=commit, source_tree=tree,
                       binaries={"docker": dict(path=str(docker), sha256=stream.sha(docker.read_bytes()))})
        age = dict(path=os.environ["SYNTHETIC_AGE"], sha256=AGE_SHA256, version="v1.3.2")
        policy = dict(age=age, count=64, recipient=RECIPIENT,
                      recipient_sha256=stream.sha(RECIPIENT.encode("ascii")),
                      generator_sources={"generator_sha256": "1"*64}, reference_binding={"sha256": "2"*64})
        auth = dict(operation_id=self.opid, policy_sha256=stream.sha(stream.canonical(policy)),
                    profile_sha256=stream.sha(stream.canonical(profile)), qualification_sha256="3"*64)

        def postflight():
            self.assertTrue(self.host.observed)
            self.assertTrue((self.vault / "answers.age").is_file())
            self.assertFalse((self.vault / "completion.json").exists())
            return "4"*64

        return session.operation(self.host, profile, policy, auth, "5"*64, time.monotonic()+180,
                                 time.time()+180, lambda: "00"*32, postflight)

    def test_roundtrip(self):
        result = self.produce()
        raw = (self.vault / "completion.json").read_bytes()
        self.assertEqual(result, dict(schema="heldout-public-commitment/1", commitment_sha256=stream.sha(raw)))
        row = json.loads(raw)
        self.assertTrue(row["cleanup"])
        self.assertEqual(row["postflight_sha256"], "4"*64)
        self.assertEqual(row["bindings"]["input_commitment_sha256"], self.input_hash)
        projection = dict(operation_id="a"*64, count=64, completion_sha256=result["commitment_sha256"],
                          bindings_sha256=stream.checked_binding(row["bindings"]),
                          input_sha256=self.input_hash, age_sha256=AGE_SHA256)
        broker = h3.CustodyBroker(self.session_dir, "encrypted", None, None, None,
                                  projection, "3"*64, lambda: "6"*64, None, None)
        end = time.monotonic()+10
        claim = broker.claim(projection, end)
        self.assertEqual(broker.read_completion(claim, end), raw)
        with h3.opened(broker.root / broker.vault / "answers.age") as fd:
            receiver.verify_cipher(fd, row["ciphertext"], end)

    def test_generated_names(self):
        self.produce()
        self.assertEqual(self.host.name, "ha-answer-" + self.opid[:32])
        self.assertRegex(self.host.name, r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
        self.assertEqual(len(self.host.name), 42)
        self.assertTrue(self.session_dir.is_dir())
        self.assertEqual(len(self.session_dir.name), 72)
        self.assertLessEqual(len(os.fsencode(self.session_dir.name)), os.pathconf(self.parent, "PC_NAME_MAX"))
        self.assertIsNotNone(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", self.vault.name))
        self.assertEqual({p.name for p in self.vault.iterdir()}, {"answers.age", "completion.json"})
        replay = durable.DurablePorts(self.parent, self.opid, time.monotonic()+15)
        try:
            replay_dir = self.parent / ("public-repair-" + self.opid)
            self.assertTrue(replay_dir.is_dir())
            self.assertEqual(len(replay_dir.name), 78)
        finally:
            replay.close()
        self.assertLessEqual(len(channel.address(self.opid, 4194304).encode("ascii")), 108)
        # Also check the actual H1/canary ID-derived literals without invoking their host operations.
        for filename, prefix, width, docker in (
            ("intcalc_private_reference_host.py", "public-qualification-", 64, False),
            ("intcalc_private_reference_host.py", "ha-public-", 32, True),
            ("public_age_canary.py", "age-canary-", 64, False),
            ("public_age_canary.py", "canary-controls-", 64, False),
        ):
            source = (session.ref.ROOT / "tools" / filename).read_text(encoding="utf-8")
            names = []
            for expr in ast.walk(ast.parse(source)):
                if not isinstance(expr, ast.BinOp) or not isinstance(expr.op, ast.Add):
                    continue
                if not isinstance(expr.left, ast.Constant) or expr.left.value != prefix:
                    continue
                key = expr.right
                length = 64
                if isinstance(key, ast.Subscript) and isinstance(key.slice, ast.Slice):
                    self.assertIsNone(key.slice.lower)
                    self.assertIsNone(key.slice.step)
                    length = ast.literal_eval(key.slice.upper)
                    key = key.value
                self.assertIsInstance(key, ast.Subscript)
                self.assertEqual(ast.literal_eval(key.slice), "operation_id")
                self.assertEqual(length, width)
                names.append(prefix + self.opid[:length])
            with self.subTest(prefix=prefix):
                self.assertEqual(len(names), 1)
                if docker:
                    self.assertRegex(names[0], r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
                else:
                    self.assertLessEqual(len(names[0]), os.pathconf(self.parent, "PC_NAME_MAX"))


if __name__ == "__main__":
    unittest.main()
