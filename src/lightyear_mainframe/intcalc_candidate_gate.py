"""Credential-free, public INTCALC black-box gate. NOT-P5; no provider calls.

The caller supplies an independently approved binding hash. Expected answers
are frozen before this invocation, never regenerated from candidate behavior.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile
import tempfile
import threading
import contextvars
import selectors
import signal
import time
import uuid

from carddemo_oracle.compare import compare_directories, validate_normalization_ledger
from .public_dataset_diff import compare_dataset

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
INPUTS = {"ACCTFILE": 300, "TCATBALF": 50, "DISCGRP": 50, "XREFFILE": 50}
OUTPUTS = {"ACCTFILE": 300, "TRANSACT": 350}
REQUIRED = {"NZ-POSTTRAN", "TRUNCATION", "DEFAULT", "ZERO-RATE", "ACCOUNT-BREAK",
            "FINAL-ACCOUNT", "EMPTY-INPUT", "ERR-NO-RATE", "ERR-NO-ACCOUNT", "ERR-NO-XREF"}
SPEC_SHA256 = "dbd33179d7eb5e79054e0048cb4cb38fd392adc2f3de5048c5c5eea7905ac143"
BYTE_POLICY = {"TRANSACT_56_131": "verdict-bearing exact bytes; report-only recommendation pending",
               "TRANSACT_330_349": "verdict-bearing exact bytes; report-only recommendation pending"}
MAX_DATA = 8 * 1024 * 1024
MAX_CAPTURE = 128 * 1024
COMMAND = ["/opt/java/openjdk/bin/java", "-jar", "/candidate.jar", "--input-dir", "/input",
           "--output-dir", "/output", "--processing-date", "{processing_date}",
           "--timestamp", "{timestamp}", "--codec", "{codec}"]
SOURCE_PATHS = ("src/carddemo_oracle/oracle.py", "src/carddemo_oracle/records.py",
                "src/carddemo_oracle/compare.py", "spec/comparison-normalizations.json",
                "spec/mainframe/carddemo-bindings.json",
                "src/lightyear_mainframe/public_dataset_diff.py",
                "src/lightyear_mainframe/records.py", "src/lightyear_mainframe/zos_bindings.py",
                "src/lightyear_mainframe/intcalc_candidate_gate.py",
                "spec/mainframe/copybooks/CVACT01Y.cpy", "spec/mainframe/copybooks/CVACT03Y.cpy",
                "spec/mainframe/copybooks/CVTRA01Y.cpy", "spec/mainframe/copybooks/CVTRA02Y.cpy",
                "spec/mainframe/copybooks/CVTRA05Y.cpy")


class Refused(ValueError):
    pass


class CandidateTimeout(Refused):
    """The original deadline expired during a started candidate exec."""


class OutputProblem(ValueError):
    def __init__(self, message, verdict="OUTPUT_CONTRACT_VIOLATION"):
        super().__init__(message)
        self.verdict = verdict


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path, limit=MAX_DATA):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise Refused("linked-path")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise Refused("bounded-regular-file-required")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > limit or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise Refused("file-changed")
    return raw


def bound_file(root, row, limit=MAX_DATA):
    name = row["path"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", name):
        raise Refused("relative-public-path-required")
    if any(p in ("", ".", "..") for p in name.split("/")) or name.startswith("/"):
        raise Refused("relative-public-path-required")
    raw = regular(Path(root) / name, limit)
    if digest(raw) != row["sha256"]:
        raise Refused("bound-file-hash")
    return raw


def selected_runtime_platform(binding):
    value = binding.get("runtime_platform")
    if type(value) is not str or value not in {"linux/amd64", "linux/arm64"}:
        raise Refused("explicit-supported-runtime-platform-required")
    return value


def daemon_runtime_platform(raw):
    try:
        info = json.loads(raw)
        if type(info) is not dict or info.get("os") != "linux":
            raise ValueError("not Linux")
        arch = info.get("architecture")
        if type(arch) is not str:
            raise ValueError("unknown architecture")
        return {"amd64": "linux/amd64", "x86_64": "linux/amd64",
                "arm64": "linux/arm64", "aarch64": "linux/arm64"}[arch]
    except (ValueError, KeyError, TypeError) as exc:
        raise Refused("docker-daemon-platform-unknown") from exc


def validate(binding, root):
    selected_runtime_platform(binding)
    if binding["schema"] != "full-intcalc-c1/2" or binding["upstream"] != UPSTREAM:
        raise Refused("binding-schema-or-source")
    if binding.get("qualified") is not False or binding.get("production_controller_receipt") is not False:
        raise Refused("not-p5-required")
    selected_byte_policy(binding)
    frozen = json.loads(bound_file(root, binding["case_manifest"]))
    case_root = Path(root) / Path(binding["case_manifest"]["path"]).parent
    if (frozen["schema"] != "intcalc-frozen-cases/2" or frozen["spec_sha256"] != SPEC_SHA256
            or frozen["model_context_eligible"] is not False or frozen["all_hand_oracle_match"] is not True):
        raise Refused("frozen-case-crosscheck-required")
    crosscheck = json.loads(bound_file(case_root, frozen["crosscheck"]))
    if (crosscheck["spec_sha256"] != SPEC_SHA256 or crosscheck["all_match"] is not True
            or crosscheck["findings"] or not crosscheck["rows"]
            or any(r["status"] != "MATCH" for r in crosscheck["rows"])):
        raise Refused("hand-oracle-finding")
    if set(frozen["source_hashes"]) != set(SOURCE_PATHS):
        raise Refused("source-inventory")
    for path, expected in frozen["source_hashes"].items():
        if digest(regular(ROOT / path)) != expected:
            raise Refused("verifier-source-drift:" + path)
    governance = validate_normalization_ledger(ROOT / "spec/comparison-normalizations.json")
    if governance["status"] != "passed":
        raise Refused("normalization-governance")
    image = binding["runtime_image"]
    if not re.fullmatch(r"(?:[A-Za-z0-9./:_-]+@)?sha256:[0-9a-f]{64}", image):
        raise Refused("immutable-runtime-image-required")
    if binding["java"] != "/opt/java/openjdk/bin/java":
        raise Refused("bound-java-entrypoint")
    if binding.get("command_template") != COMMAND:
        raise Refused("exact-command-binding")
    if type(binding["max_elapsed_seconds"]) is not int or not 1 <= binding["max_elapsed_seconds"] <= 600:
        raise Refused("original-deadline-required")
    cases = frozen["cases"]
    if len(cases) != len(REQUIRED) or {c["id"] for c in cases} != REQUIRED:
        raise Refused("complete-case-inventory-required")
    artifact = bound_file(root, binding["artifact"], 64 * 1024 * 1024)
    prepared = []
    for case in cases:
        if case["codec"] != "cp037" or not re.fullmatch(r"\d{10}", case["processing_date"]):
            raise Refused("case-codec-date")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d{6}", case["timestamp"]):
            raise Refused("case-timestamp")
        kind = case["kind"]
        if kind not in ("success", "refusal"):
            raise Refused("case-kind")
        expected_dds = set(OUTPUTS) if kind == "success" else set()
        if set(case["inputs"]) != set(INPUTS) or set(case["expected"]) != expected_dds:
            raise Refused("case-dd-inventory")
        arrays = {}
        for phase, lengths in (("inputs", INPUTS), ("expected", OUTPUTS)):
            arrays[phase] = {dd: bound_file(case_root, row) for dd, row in case[phase].items()}
            if any(len(raw) % lengths[dd] for dd, raw in arrays[phase].items()):
                raise Refused("fixed-record-framing")
        if not arrays["inputs"]["ACCTFILE"]:
            raise Refused("empty-case")
        receipt = json.loads(bound_file(case_root, case["oracle_receipt"]))
        if (receipt["schema"] != "intcalc-frozen-oracle/2" or receipt["case_id"] != case["id"]
                or receipt["kind"] != kind
                or receipt["outcome"] != ("completed" if kind == "success" else "exception")
                or (kind == "refusal" and (receipt["error_type"] != "OracleExecutionError" or not receipt["diagnostic"]))
                or receipt["final_account_policy"] != "source-faithful"
                or receipt["oracle_sha256"] != frozen["source_hashes"][SOURCE_PATHS[0]]
                or receipt["processing_date"] != case["processing_date"]
                or receipt["timestamp"] != case["timestamp"]
                or receipt["inputs"] != {d: digest(b) for d, b in arrays["inputs"].items()}
                or receipt["outputs"] != {d: digest(b) for d, b in arrays["expected"].items()}):
            raise Refused("frozen-oracle-binding")
        prepared.append((case, arrays))
    return artifact, prepared, governance


_C2_CONTEXT = contextvars.ContextVar("intcalc_c2_absolute_runtime", default=None)


def absolute_capture(argv, deadline, hard_end, cap):
    """C2-only bounded pipes and child-group reap within the incoming hard end."""
    if os.name != "posix" or not time.monotonic() < deadline <= hard_end:
        raise Refused("absolute-command-deadline")
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
                            close_fds=True, start_new_session=False)
    poller = selectors.DefaultSelector()
    streams = (proc.stdout, proc.stderr)
    chunks = [bytearray(), bytearray()]
    expired = overflow = False
    try:
        for i, stream in enumerate(streams):
            os.set_blocking(stream.fileno(), False)
            poller.register(stream, selectors.EVENT_READ, i)
        while poller.get_map() or proc.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                expired = True
                break
            for key, _ in poller.select(min(0.05, remaining)):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    poller.unregister(key.fileobj)
                    continue
                target = chunks[key.data]
                space = max(0, cap - len(target))
                target.extend(block[:space])
                if len(block) > space:
                    overflow = True
                    break
            if overflow:
                break
    finally:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        if proc.poll() is None:
            remaining = hard_end - time.monotonic()
            if remaining <= 0:
                raise Refused("absolute-child-reap-deadline")
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise Refused("absolute-child-reap-unconfirmed") from None
        poller.close()
        for stream in streams:
            stream.close()
    return dict(rc=proc.returncode, timeout=expired, overflow=overflow,
                stdout=bytes(chunks[0]), stderr=bytes(chunks[1]))


def capture(argv, deadline, cap=MAX_CAPTURE):
    """Bound both pipes while reading; overflow is a fault, never a truncated pass."""
    context = _C2_CONTEXT.get()
    if context is not None:
        hard_end, prefix, _, _ = context
        if not argv or argv[0] != "docker":
            raise Refused("c2-fixed-docker-only")
        return absolute_capture([*prefix, *argv[1:]], min(deadline, hard_end - 0.05), hard_end, cap)
    remaining = deadline - time.monotonic()
    if not math.isfinite(remaining) or remaining <= 0:
        raise Refused("original-deadline-expired")
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env={"PATH": os.environ.get("PATH", "")})
    chunks, overflow = [bytearray(), bytearray()], threading.Event()
    def drain(stream, target):
        while block := stream.read(65536):
            available = cap - len(target)
            target.extend(block[:max(0, available)])
            if len(block) > available:
                overflow.set()
                proc.kill()
    threads = [threading.Thread(target=drain, args=(stream, chunks[i]), daemon=True)
               for i, stream in enumerate((proc.stdout, proc.stderr))]
    for thread in threads:
        thread.start()
    expired = False
    try:
        proc.wait(timeout=max(0.001, deadline-time.monotonic()))
    except subprocess.TimeoutExpired:
        expired = True
        proc.kill()
        proc.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
    if any(t.is_alive() for t in threads):
        raise Refused("capture-not-closed")
    return dict(rc=proc.returncode, timeout=expired, overflow=overflow.is_set(),
                stdout=bytes(chunks[0]), stderr=bytes(chunks[1]))


def public_capture(result):
    return {**{k: v for k, v in result.items() if k not in ("stdout", "stderr")},
            **{k+"_base64": base64.b64encode(result[k]).decode() for k in ("stdout", "stderr")}}


def timed_capture(argv, deadline, rows, cap=MAX_CAPTURE, **metadata):
    """Retain elapsed wall milliseconds even when Docker launch/capture raises."""
    started = time.monotonic_ns()
    row = dict(argv=argv, **metadata)
    try:
        result = capture(argv, deadline, cap)
        row.update(public_capture(result))
        return result
    except Exception as exc:
        row.update(error_type=type(exc).__name__, error=str(exc)[:300])
        raise
    finally:
        row["elapsed_ms"] = (time.monotonic_ns()-started)/1_000_000
        rows.append(row)


def require_exec_transport(result, role):
    # Reserved Docker exec statuses and daemon diagnostics never satisfy ERR cases.
    stderr = result["stderr"].lower()
    daemon_error = (b"error response from daemon" in stderr
                    or b"error response from docker daemon" in stderr
                    or b"cannot connect to the docker daemon" in stderr
                    or b"is the docker daemon running" in stderr
                    or b"error during connect:" in stderr
                    or b"docker: error" in stderr
                    or (b"daemon" in stderr and b"error" in stderr))
    if result["rc"] in (125, 126, 127) or daemon_error:
        raise Refused("docker-exec-infrastructure:"+role)


def output_tar(raw):
    outputs = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if member.isdir() and name in ("", "."):
                continue
            if (name not in {d+".bin" for d in OUTPUTS} or not member.isfile()
                    or name in outputs or member.size > MAX_DATA):
                raise OutputProblem("unexpected-output-inventory")
            stream = archive.extractfile(member)
            outputs[name] = stream.read(MAX_DATA+1)
            if len(outputs[name]) != member.size:
                raise OutputProblem("partial-output")
    if set(outputs) != {d+".bin" for d in OUTPUTS}:
        raise OutputProblem("missing-output")
    return {name[:-4]: raw for name, raw in outputs.items()}


def tar_inventory(raw):
    rows = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            if len(rows) >= 128 or member.size > MAX_DATA:
                raise OutputProblem("output-inventory-limit")
            row = dict(name=member.name[:256], bytes=member.size, type=repr(member.type))
            if member.isfile():
                row["sha256"] = digest(archive.extractfile(member).read(MAX_DATA+1))
            rows.append(row)
    return rows


def execute_case(image, artifact, inputs, case, deadline, retained, *, runtime_platform):
    runtime_platform = selected_runtime_platform({"runtime_platform": runtime_platform})
    observed_daemon_platform = None
    # Shared bounded tmpfs volume; trusted collector reads it after candidate pause.
    token = uuid.uuid4().hex
    name, collector, volume = ("intcalc-c1-"+token+s for s in ("", "-collect", "-out"))
    evidence, cleanup_rows, attempted = [], [], []
    volume_attempted = False
    pending_error = None
    def call(args, cap=MAX_CAPTURE, output_phase=False, candidate_exec=False):
        result = timed_capture(["docker", *args], deadline, evidence, cap)
        if result["timeout"]:
            if candidate_exec:
                raise CandidateTimeout("original-deadline-expired-during-candidate")
            raise Refused("original-deadline-expired")
        if candidate_exec:
            require_exec_transport(result, "candidate")
        if result["overflow"]:
            if output_phase:
                raise OutputProblem("bounded-output-capture-overflow")
            raise Refused("infrastructure-capture-overflow")
        return result
    def required(args):
        result = call(args)
        if result["rc"]:
            raise Refused("docker-operation-failed:"+args[0])
        return result
    def require_native_daemon():
        nonlocal observed_daemon_platform
        raw = required(["info", "--format", '{"os":{{json .OSType}},"architecture":{{json .Architecture}}}'])["stdout"]
        observed_daemon_platform = daemon_runtime_platform(raw)
        if observed_daemon_platform != runtime_platform:
            raise Refused("docker-daemon-platform-mismatch-emulation-refused")
    with tempfile.TemporaryDirectory(prefix="intcalc-c1-") as temp:
        temp = Path(temp)
        (temp / "input").mkdir()
        for dd, raw in inputs.items():
            (temp / "input" / (dd+".bin")).write_bytes(raw)
        (temp / "candidate.jar").write_bytes(artifact)
        command = [value.format(**case) for value in COMMAND]
        try:
            require_native_daemon()
            volume_attempted = True
            if _C2_CONTEXT.get() is not None:
                _C2_CONTEXT.get()[2]("volume", volume)
            required(["volume", "create", "--driver=local", "--opt=type=tmpfs",
                      "--opt=device=tmpfs", "--opt=o=size=32m,uid=65534,gid=65534,mode=0700", volume])
            common = ["--pull=never", "--platform="+runtime_platform, "--network=none", "--read-only",
                      "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
                      "--memory=512m", "--cpus=1", "--user=65534:65534"]
            attempted.append(name)
            if _C2_CONTEXT.get() is not None:
                _C2_CONTEXT.get()[2]("container", name)
            required(["create", "--name", name, *common,
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
                "--mount", f"type=volume,source={volume},target=/output,volume-nocopy",
                "--mount", f"type=bind,src={temp / 'input'},dst=/input,readonly",
                "--mount", f"type=bind,src={temp / 'candidate.jar'},dst=/candidate.jar,readonly",
                "--entrypoint=/bin/sh", image, "-c", "while :; do sleep 1; done"])
            required(["start", name])
            state = json.loads(required(["inspect", name])["stdout"])[0]
            mounts = {m["Destination"]:m for m in state["Mounts"]}
            if (state["HostConfig"]["NetworkMode"] != "none" or not state["HostConfig"]["ReadonlyRootfs"]
                    or state["Config"]["User"] != "65534:65534" or state["Config"]["Image"] != image
                    or mounts["/output"]["Type"] != "volume" or mounts["/output"]["Name"] != volume
                    or not mounts["/output"]["RW"] or mounts["/input"]["RW"] or mounts["/candidate.jar"]["RW"]):
                raise Refused("container-boundary-not-observed")
            run = call(["exec", name, "/usr/bin/env", "-i", "LANG=C", "TZ=UTC", *command],
                       output_phase=True, candidate_exec=True)
            required(["pause", name])
            paused = json.loads(required(["inspect", name])["stdout"])[0]["State"]["Paused"]
            if paused is not True:
                raise Refused("candidate-output-not-frozen")
            require_native_daemon()
            attempted.append(collector)
            if _C2_CONTEXT.get() is not None:
                _C2_CONTEXT.get()[2]("container", collector)
            required(["create", "--name", collector, *common,
                "--mount", f"type=volume,source={volume},target=/capture,readonly,volume-nocopy",
                "--entrypoint=/bin/sh", image, "-c", "while :; do sleep 1; done"])
            required(["start", collector])
            collect_state = json.loads(required(["inspect", collector])["stdout"])[0]
            collect_mount = next(m for m in collect_state["Mounts"] if m["Destination"]=="/capture")
            if collect_mount["Name"] != volume or collect_mount["RW"]:
                raise Refused("collector-mount-boundary")
            # No docker cp: tar reads the shared volume through the trusted collector.
            copied = timed_capture(["docker", "exec", collector, "/bin/tar", "-C", "/capture", "-cf", "-", "."],
                                   deadline, evidence, cap=2*MAX_DATA+65536)
            (retained / "output.tar").write_bytes(copied["stdout"])
            if copied["timeout"]:
                raise Refused("original-deadline-expired")
            require_exec_transport(copied, "collector")
            if copied["overflow"]:
                raise OutputProblem("output-archive-overflow")
            if copied["rc"]:
                raise OutputProblem("candidate-output-unreadable")
            try:
                inventory = tar_inventory(copied["stdout"])
            except (tarfile.TarError, OSError, EOFError) as exc:
                raise OutputProblem("output-archive-invalid") from exc
            (retained / "output-inventory.json").write_text(json.dumps(inventory, indent=2)+"\n")
            outputs = output_tar(copied["stdout"]) if run["rc"] == 0 else None
            return dict(exit_code=run["rc"], command=command, outputs=outputs,
                        captured_output_inventory=inventory, stderr_nonempty=bool(run["stderr"].strip()))
        except Exception as exc:
            pending_error = exc
            raise
        finally:
            cleanup_ok = True
            cleanup_deadline = time.monotonic()+5
            if _C2_CONTEXT.get() is not None:
                cleanup_deadline = min(time.monotonic() + _C2_CONTEXT.get()[3], _C2_CONTEXT.get()[0])
            targets = [("container", target, ["docker","rm","--force","--volumes",target])
                       for target in reversed(attempted)]
            if volume_attempted:
                targets.append(("volume",volume,["docker","volume","rm","--force",volume]))
            for kind,target,argv in targets:
                try:
                    result = timed_capture(argv, cleanup_deadline, cleanup_rows, kind=kind, name=target)
                    marker = b"no such container:" if kind=="container" else b"no such volume"
                    absent = result["rc"]==1 and marker in result["stderr"].lower()
                    cleanup_ok = cleanup_ok and not result["timeout"] and not result["overflow"] and (result["rc"]==0 or absent)
                    if _C2_CONTEXT.get() is not None:
                        probe = timed_capture(["docker", kind, "inspect", target], cleanup_deadline,
                                              cleanup_rows, kind=kind, name=target)
                        cleanup_ok = (cleanup_ok and probe["rc"] == 1 and marker in probe["stderr"].lower()
                                      and not probe["timeout"] and not probe["overflow"])
                        if cleanup_ok:
                            _C2_CONTEXT.get()[2]("removed-" + kind, target)
                except Exception as exc:
                    cleanup_ok = False
            (retained / "runtime.json").write_text(json.dumps(dict(
                operations=evidence,cleanup=cleanup_rows,cleanup_confirmed=cleanup_ok,
                runtime_platform=runtime_platform, observed_daemon_platform=observed_daemon_platform,
                cleanup_allowance_seconds=(_C2_CONTEXT.get()[3] if _C2_CONTEXT.get() is not None else 5),
                candidate_timeout=isinstance(pending_error, CandidateTimeout),
                capture_method="paused candidate; trusted tar collector on read-only shared tmpfs volume",
                cleanup_is_not_native_owner_proof=True),indent=2)+"\n")
            if not cleanup_ok and not isinstance(pending_error, CandidateTimeout):
                raise Refused("container-cleanup-unconfirmed")


def compare_case(expected, actual, codec, retained):
    for dd in OUTPUTS:
        if len(actual[dd]) % OUTPUTS[dd]:
            raise OutputProblem("wrong-record-length:"+dd)
    try:
        return _compare_case(expected, actual, codec, retained)
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, OutputProblem):
            raise
        raise OutputProblem("candidate-bytes-refused:"+str(exc)[:200], "UNDECODABLE") from exc


def _compare_case(expected, actual, codec, retained):
    deltas = {dd: compare_dataset("INTCALC", "STEP15", dd, expected[dd], actual[dd], codec=codec)
              for dd in OUTPUTS}
    for label, values in (("expected", expected), ("actual", actual)):
        folder = retained / label
        folder.mkdir()
        for dd, filename in (("ACCTFILE", "acctdata.txt"), ("TRANSACT", "transactions.txt")):
            raw, length = values[dd], OUTPUTS[dd]
            if len(raw) % length:
                raise OutputProblem("partial-fixed-record")
            lines = [raw[i:i+length].decode(codec) for i in range(0, len(raw), length)]
            if any("\n" in line or "\r" in line for line in lines):
                raise OutputProblem("embedded-record-separator")
            (folder / filename).write_bytes(("".join(line+"\n" for line in lines)).encode("ascii"))
    semantic = compare_directories(retained / "expected", retained / "actual")
    return dict(verdict="MATCH" if semantic["status"] == "passed" and
                all(d["identical"] for d in deltas.values()) else "DIFFERENT",
                dataset_deltas=deltas, governed_oracle_comparison=semantic)



REPORT_ONLY_POLICY = {"name":"TRANSACT-UNASSIGNED-REPORT-ONLY-v1",
                      "TRANSACT_56_131":"report-only; every original byte retained",
                      "TRANSACT_330_349":"report-only; every original byte retained",
                      "other_bytes":"verdict-bearing; no other exception"}


def selected_byte_policy(binding):
    policy=binding.get("byte_policy")
    if policy is None:
        return BYTE_POLICY
    if set(policy)!={"name","artifact_sha256","case_manifest_sha256","expires_at","attempt_name"}:
        raise Refused("named-byte-policy-scope-required")
    if (policy["name"]!=REPORT_ONLY_POLICY["name"]
            or policy["artifact_sha256"]!=binding["artifact"]["sha256"]
            or policy["case_manifest_sha256"]!=binding["case_manifest"]["sha256"]
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",policy["attempt_name"])):
        raise Refused("named-byte-policy-binding")
    expiry=datetime.fromisoformat(policy["expires_at"])
    if expiry.utcoffset() is None or expiry<=datetime.now(timezone.utc):
        raise Refused("named-byte-policy-expired")
    return REPORT_ONLY_POLICY

def compare_report_only_case(expected, actual, codec, retained):
    for dd in OUTPUTS:
        if len(actual[dd]) % OUTPUTS[dd]:
            raise OutputProblem("wrong-record-length:"+dd)
    # Preserve full raw bytes and all differences; only an explicit comparison view
    # excludes the two named unassigned regions. It never rewrites an artifact.
    def view(raw):
        data=bytearray(raw)
        for start in range(0,len(data),350):
            data[start+56:start+132]=b"\x40"*76
            data[start+330:start+350]=b"\x40"*20
        return bytes(data)
    observations=[]
    left,right=expected["TRANSACT"],actual["TRANSACT"]
    for index in range(max(len(left),len(right))//350):
        for lo,hi in ((56,132),(330,350)):
            a=left[index*350+lo:index*350+hi]
            b=right[index*350+lo:index*350+hi]
            observations.append(dict(record=index+1,start=lo,end_inclusive=hi-1,
                                     expected_hex=a.hex(),actual_hex=b.hex(),different=a!=b))
    raw_report={}
    for dd in OUTPUTS:
        try:
            raw_report[dd]=compare_dataset("INTCALC","STEP15",dd,expected[dd],actual[dd],codec=codec)
        except (UnicodeError,ValueError) as exc:
            raw_report[dd]=dict(decoded=False,error=str(exc)[:200],
                               before_sha256=digest(expected[dd]),after_sha256=digest(actual[dd]))
    (retained / "byte-policy-observations.json").write_text(json.dumps(dict(
        policy=REPORT_ONLY_POLICY,raw_dataset_deltas=raw_report,regions=observations),indent=2)+"\n")
    projected_expected=dict(expected,TRANSACT=view(left))
    projected_actual=dict(actual,TRANSACT=view(right))
    try:
        result=_compare_report_only_view(projected_expected,projected_actual,codec,retained)
    except (UnicodeError,ValueError) as exc:
        if isinstance(exc,OutputProblem):
            raise
        raise OutputProblem("candidate-bytes-refused-outside-policy:"+str(exc)[:200],"UNDECODABLE") from exc
    return dict(verdict=result["verdict"],comparison_policy=REPORT_ONLY_POLICY,
                dataset_deltas=raw_report,unassigned_region_observations=observations,
                comparison_view=result,raw_artifacts_changed=False)


def _compare_report_only_view(expected, actual, codec, retained):
    deltas = {dd: compare_dataset("INTCALC", "STEP15", dd, expected[dd], actual[dd], codec=codec)
              for dd in OUTPUTS}
    for label, values in (("comparison-view-expected", expected), ("comparison-view-actual", actual)):
        folder = retained / label
        folder.mkdir()
        for dd, filename in (("ACCTFILE", "acctdata.txt"), ("TRANSACT", "transactions.txt")):
            raw, length = values[dd], OUTPUTS[dd]
            if len(raw) % length:
                raise OutputProblem("partial-fixed-record")
            lines = [raw[i:i+length].decode(codec) for i in range(0, len(raw), length)]
            if any("\n" in line or "\r" in line for line in lines):
                raise OutputProblem("embedded-record-separator")
            (folder / filename).write_bytes(("".join(line+"\n" for line in lines)).encode("ascii"))
    semantic = compare_directories(retained / "comparison-view-expected", retained / "comparison-view-actual")
    return dict(verdict="MATCH" if semantic["status"] == "passed" and
                all(d["identical"] for d in deltas.values()) else "DIFFERENT",
                dataset_deltas=deltas, governed_oracle_comparison=semantic)


def run(binding_path, binding_sha256, attempt_dir, *, absolute_deadline=None,
        docker_prefix=None, resource_register=None, cleanup_seconds=5):
    """Legacy C1 behavior stays unchanged; C2 supplies one trusted absolute end."""
    if absolute_deadline is None:
        if docker_prefix is not None or resource_register is not None or cleanup_seconds != 5:
            raise Refused("absolute-runtime-incomplete")
        return _run(binding_path, binding_sha256, attempt_dir)
    started = time.monotonic()
    if (type(absolute_deadline) not in (int, float) or not math.isfinite(absolute_deadline)
            or type(cleanup_seconds) is not int or cleanup_seconds != 18
            or absolute_deadline - started <= cleanup_seconds or os.name != "posix"
            or type(docker_prefix) is not list or len(docker_prefix) != 5
            or docker_prefix[1] != "--config" or docker_prefix[3] != "--host"
            or not Path(docker_prefix[0]).is_absolute()
            or not Path(docker_prefix[2]).is_absolute()
            or not docker_prefix[4].startswith("unix:///") or not callable(resource_register)):
        raise Refused("absolute-runtime-binding")
    token = _C2_CONTEXT.set((absolute_deadline, tuple(docker_prefix), resource_register, cleanup_seconds))
    try:
        result = _run(binding_path, binding_sha256, attempt_dir, started=started)
        if time.monotonic() >= absolute_deadline:
            raise Refused("absolute-result-late")
        return result
    finally:
        _C2_CONTEXT.reset(token)


def _run(binding_path, binding_sha256, attempt_dir, *, started=None):
    raw = regular(binding_path)
    if digest(raw) != binding_sha256:
        raise Refused("approved-binding-hash-required")
    binding = json.loads(raw)
    artifact, cases, governance = validate(binding, Path(binding_path).parent)
    active_policy = selected_byte_policy(binding)
    retained = Path(attempt_dir)
    if binding.get("byte_policy") and retained.name != binding["byte_policy"]["attempt_name"]:
        raise Refused("named-byte-policy-attempt")
    retained.mkdir(parents=False, exist_ok=False)
    report = dict(schema="full-intcalc-c1-result/2", binding_sha256=binding_sha256,
                  artifact_sha256=digest(artifact), runtime_image=binding["runtime_image"],
                  runtime_platform=selected_runtime_platform(binding),
                  started_at=datetime.now(timezone.utc).isoformat(), cases=[],
                  qualified=False, production_controller_receipt=False,
                  normalization_governance=governance, comparison_policy=active_policy, all_cases_match=False)
    deadline = time.monotonic()+binding["max_elapsed_seconds"]
    if _C2_CONTEXT.get() is not None:
        deadline = min(started + binding["max_elapsed_seconds"], _C2_CONTEXT.get()[0] - _C2_CONTEXT.get()[3])
        if time.monotonic() >= deadline:
            raise Refused("absolute-validation-deadline")
    if binding.get("byte_policy"):
        expires=datetime.fromisoformat(binding["byte_policy"]["expires_at"])
        deadline=min(deadline,time.monotonic()+(expires-datetime.now(timezone.utc)).total_seconds())
    (retained / "binding.json").write_bytes(raw)
    stopped = False
    for case, arrays in cases:
        destination = retained / case["id"]
        destination.mkdir()
        row = dict(id=case["id"], kind=case["kind"], verdict="NOT_RUN", inputs=case["inputs"],
                   expected=case["expected"], comparison_policy=active_policy)
        try:
            if stopped:
                raise Refused("attempt-stopped-after-fault")
            if time.monotonic() >= deadline:
                raise Refused("original-deadline-expired")
            execution = execute_case(binding["runtime_image"], artifact,
                                     arrays["inputs"], case, deadline, destination,
                                     runtime_platform=selected_runtime_platform(binding))
            row.update(exit_code=execution["exit_code"], command=execution["command"],
                       captured_output_inventory=execution.get("captured_output_inventory", []))
            if case["kind"] == "refusal":
                row["verdict"] = ("EXPECTED_REFUSAL" if execution["exit_code"] != 0 and
                                  execution.get("stderr_nonempty") else "REFUSAL_NOT_OBSERVED")
                row["partial_output_comparison"] = "NOT_COMPARED_BY_SPEC"
            elif execution["exit_code"]:
                row["verdict"] = "EXECUTION_FAILED"
            else:
                actual = execution["outputs"]
                for dd, output in actual.items():
                    (destination / (dd+".bin")).write_bytes(output)
                row["output_inventory"] = {d: dict(bytes=len(b), sha256=digest(b)) for d, b in actual.items()}
                comparator = compare_report_only_case if active_policy is REPORT_ONLY_POLICY else compare_case
                row.update(comparator(arrays["expected"], actual, case["codec"], destination))
        except CandidateTimeout as exc:
            row.update(verdict="TIMEOUT", error_type=type(exc).__name__, error=str(exc)[:500])
            stopped = True
        except OutputProblem as exc:
            row.update(verdict=exc.verdict,error_type=type(exc).__name__,error=str(exc)[:500])
        except Exception as exc:
            not_run = str(exc) in ("attempt-stopped-after-fault", "original-deadline-expired")
            row.update(verdict="NOT_RUN" if not_run else "FAULT",
                       error_type=type(exc).__name__, error=str(exc)[:500])
            # No further candidate may start after an uncertain runtime/cleanup failure.
            stopped = True
        report["cases"].append(row)
        (destination / "result.json").write_text(json.dumps(row, indent=2)+"\n")
        (retained / "result.json").write_text(json.dumps(report, indent=2)+"\n")
    report["all_cases_match"] = all(row["verdict"] in ("MATCH", "EXPECTED_REFUSAL") for row in report["cases"])
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    (retained / "result.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--binding-sha256", required=True)
    parser.add_argument("--attempt-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.binding, args.binding_sha256, args.attempt_dir)
    print(json.dumps(dict(all_cases_match=report["all_cases_match"], qualified=False)))
    return 0 if report["all_cases_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
