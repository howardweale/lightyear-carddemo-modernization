"""Howard-only age canary. The only plaintext source is the reviewed public fixture."""
import argparse
import io
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from tools import intcalc_h3_custody as usb
from tools import intcalc_heldout_encrypted_stream as writer
from tools import intcalc_hidden_answer_receiver as rx
from tools import intcalc_private_answer_session as h2
from tools import intcalc_private_reference_host as h1

FIXTURE = Path(__file__).resolve().parents[1] / "spec/age-canary/PUBLIC-CASES.json"
FIXTURE_SHA = "d07de88be80b82909f6b672c54155ac3a04eb68a1277e55a778b5f80c6adb836"
MANIFEST = {"schema": "public-age-canary-fixture/1", "fixture_sha256": FIXTURE_SHA}
TAG = writer.sha(b"public-age-canary-only/v1")
CAP = 8192


class Refused(ValueError):
    pass


CODES = frozenset(("canary-arguments", "canary-approval", "canary-host", "canary-custody",
                   "canary-fixture", "canary-confirmation", "canary-storage", "canary-stream",
                   "canary-receive", "canary-usb-mount", "canary-refused", "canary-interrupted",
                   "canary-fault"))


def refusal(error):
    if isinstance(error, (KeyboardInterrupt, EOFError)):
        return "canary-interrupted"
    if type(error) is Refused and len(error.args) == 1:
        code = error.args[0]
        if type(code) is str and code in CODES:
            return code
    if isinstance(error, h1.Refused):
        return "canary-host"
    if isinstance(error, writer.Refused):
        return "canary-stream"
    if isinstance(error, rx.Refused):
        return "canary-receive"
    if isinstance(error, FileExistsError):
        return "canary-storage"
    return "canary-fault"


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused("canary-arguments")


def require(ok, code="canary-refused"):
    if not ok:
        raise Refused(code)


def now():
    return datetime.now(timezone.utc)


def rows():
    raw = h1.read(FIXTURE, CAP)
    require(writer.sha(raw) == FIXTURE_SHA, "canary-fixture")
    cases = h1.strict(raw)
    require(type(cases) is list and len(cases) == 2, "canary-fixture")
    for index, row in enumerate(cases):
        writer.checked_case(row, index)
    return cases


def input_commitment(cases):
    data = [dict(id=f"HC-{index+1:03d}", inputs=row["inputs"], processing_date=row["processing_date"],
                 timestamp=row["timestamp"]) for index, row in enumerate(cases)]
    return writer.sha(writer.canonical(dict(schema="fresh-heldout-inputs/1", cases=data,
        qualified=False, expected_outputs_present=False, source_manifest=MANIFEST,
        named_limit="open-source reference, not mainframe-proven; inputs only, unqualified")))


def plaintext(cases, binding):
    sink = io.BytesIO()
    framed = writer.Framer(sink, writer.checked_binding(binding), len(cases))
    for row in cases:
        framed.case(row)
    framed.finish()
    raw = sink.getvalue()
    require(0 < len(raw) <= CAP)
    return raw


def read_control(root, name):
    path = root / name
    h1.private_control_file(path)
    return h1.read(path, 65536)


def confirm(cue):
    require(sys.stdin.isatty() and input(cue+"\n").strip() == cue, "canary-confirmation")


def custody(raw, auth, p, earliest, post=False):
    row = h1.strict(raw)
    h1.custody(row, auth["operation_id"], writer.sha(h1.canonical(p)), p["source_commit"], p["source_tree"], post=post)
    require(earliest <= h1.aware(row["observed_at_with_offset"]) <= now()
            and row["public_host_qualification"] == "PASSED"
            and row["qualification_receipt_sha256"] == auth["host_sha256"], "canary-custody")


def exclusive_probe(root):
    store = writer.PrivateStore(root, "exclusive")
    marker = b"known public marker"
    path = root / "exclusive" / "answers.age"
    try:
        h1.exclusive(path, marker)
        try:
            store.start()
        except FileExistsError:
            require(h1.read(path) == marker)
        else:
            raise Refused("canary-storage")
    finally:
        store.close()


def interrupted_store(root, binding, sink, end):
    def interrupted():
        yield rows()[0]
        raise InterruptedError("canary-injected")
    path = root / "interrupted"
    try:
        writer.write_answers(interrupted(), 2, binding, writer.PrivateStore(root, "interrupted"),
                             sink, lambda: True, lambda: TAG, end)
    except InterruptedError as error:
        require(error.args == ("canary-injected",))
    else:
        raise Refused("canary-storage")
    require((path/"answers.age").is_file() and not os.path.lexists(path/"completion.json"))
    try:
        writer.PrivateStore(root, "interrupted")
    except FileExistsError:
        return
    raise Refused("canary-storage")


class CheckedPipe:
    """Expose reads only while they match the approved byte stream, including the final EOF."""
    def __init__(self, pipe, expected):
        self.pipe, self.expected, self.offset = pipe, expected, 0

    def read(self, size, end):
        block = self.pipe.read(size, end)
        require(self.expected[self.offset:self.offset+len(block)] == block
                and (block or self.offset == len(self.expected)))
        self.offset += len(block)
        return block


def roundtrip(broker, projection, expected, end):
    claim = broker.claim(projection, end)
    raw = broker.read_completion(claim, end)
    completion = rx.completion(raw, projection)
    with broker.open_cipher(claim, end) as cipher:
        rx.verify_cipher(cipher, completion["ciphertext"], end)
        with broker.decrypt(cipher, claim, projection["age_sha256"], end) as session:
            with session.pipe() as pipe:
                decoded = rx.decode(CheckedPipe(pipe, expected), projection, MANIFEST, end)
                require(decoded == [writer.canonical(row) for row in rows()])
            require(session.join_success(end) is True)
    proof = broker.removal_receipt(claim, end)
    require(proof["claim_sha256"] == claim and proof["operation_id"] == projection["operation_id"]
            and all(proof[k] is True for k in ("decryptor_exited", "group_absent", "handles_closed",
                    "usb_mount_absent", "howard_removed_usb", "howard_no_identity_copy", "codex_absent")))
    return writer.sha(writer.canonical(proof))


def inspect_controls(control, digest):
    approval = read_control(control, "APPROVAL.json")
    require(h1.hashed(digest) and writer.sha(approval) == digest, "canary-approval")
    a = h1.strict(approval)
    writer.closed(a, ("schema", "operator", "mode", "operation_id", "source_commit", "source_tree",
                      "profile_sha256", "custody_sha256", "host_sha256", "recipient_sha256",
                      "age_sha256", "plaintext_sha256", "valid_from", "expires_at"))
    require(a["schema"] == "operator-public-age-canary/1" and a["operator"] == "Howard"
            and a["mode"] == "PUBLIC_CANARY_ONLY" and h1.hashed(a["operation_id"])
            and all(h1.hashed(v) for k, v in a.items() if k.endswith("_sha256")), "canary-approval")
    start, end = map(h1.aware, (a["valid_from"], a["expires_at"]))
    require(start <= now() < end and (end-start).total_seconds() <= 7200, "canary-approval")
    p = h1.strict(read_control(control, "PROFILE.json"))
    h1.profile(p)
    profile_hash = writer.sha(h1.canonical(p))
    require(profile_hash == a["profile_sha256"] and (a["source_commit"],a["source_tree"]) ==
            (p["source_commit"],p["source_tree"]))
    pre = read_control(control, "CUSTODY.json")
    require(writer.sha(pre) == a["custody_sha256"], "canary-custody")
    custody(pre, a, p, start)
    host_raw = read_control(control, "HOST.json")
    require(writer.sha(host_raw) == a["host_sha256"], "canary-host")
    host = h1.strict(host_raw)
    require(host["schema"] == "ha-public-host-qualification/1" and host["status"] == "CRITERION_MET"
            and host["source_commit"] == a["source_commit"] and host["source_tree"] == a["source_tree"]
            and host["profile_sha256"] == profile_hash and host["public_only"] is True
            and host["cleanup"] is True and host["comparison_criterion_met"] is True
            and (host["cases"],host["probes"]) == (16,9))
    return a, p, end


def parse_usb_pair(mount_id, device):
    require(re.fullmatch(r"[1-9][0-9]{0,9}", mount_id) and
            re.fullmatch(r"[0-9]{1,10}:[0-9]{1,10}", device), "canary-usb-mount")
    return int(mount_id), device


def mount_record(lines, mount_id, device):
    # Presence requires both identifiers on one read-only mount. Removal uses
    # the broker's broader OR check so aliases and residual mounts refuse.
    found = False
    for line in lines:
        left, sep, right = line.partition(" - ")
        fields, kind = left.split(), right.split()
        require(sep and len(fields) >= 6 and len(kind) >= 3, "canary-usb-mount")
        if fields[0] == str(mount_id) or fields[2] == device:
            options = set(fields[5].split(","))
            require(not found and fields[0] == str(mount_id) and fields[2] == device
                    and fields[3] == "/" and kind[0] in ("ext4", "vfat")
                    and {"ro", "nodev", "nosuid", "noexec"} <= options and "rw" not in options,
                    "canary-usb-mount")
            found = True
    require(found, "canary-usb-mount")


def check_usb_mount(mount_id, device):
    try:
        major, minor = (int(n) for n in device.split(":"))
        require(os.makedev(major, minor) != os.stat("/").st_dev and
                (Path("/sys/dev/block")/device).is_dir(), "canary-usb-mount")
        mount_record(Path("/proc/self/mountinfo").read_text().splitlines(), mount_id, device)
    except (OSError, OverflowError, UnicodeError) as error:
        raise Refused("canary-usb-mount") from error


def execute(control, digest):
    require(sys.stdin.isatty() and os.name == "posix" and os.getuid() != 0 and not os.environ.get("GITHUB_ACTIONS"))
    os.umask(0o077)
    control = h1.private_directory(control)
    a, p, wall = inspect_controls(control, digest)
    parent = h1.private_directory(p["private_root"])
    require(control.parent == parent and control.name == "canary-controls-"+a["operation_id"]
            and not os.path.lexists(control/"POSTFLIGHT.json"))
    end = time.monotonic() + (wall-now()).total_seconds()
    commands = h1.Commands(p["binaries"], end, wall.timestamp())
    host = h1.Host(p, commands)
    h1.source_identity(commands, p)
    require(commands.out(["git","-C",str(h1.ref.ROOT.resolve()),"rev-parse","refs/heads/main"]).decode().strip()
            == a["source_commit"])
    host.observe()
    local = h1.strict(read_control(control, "LOCAL.json"))
    writer.closed(local, ("age_path", "public_recipient"))
    age, recipient = local["age_path"], local["public_recipient"]
    writer.pin_executable(age, a["age_sha256"])
    require(writer.sha(recipient.encode("ascii")) == a["recipient_sha256"])
    cases = rows()
    # Domain-separated placeholders denote synthetic roles; no private producer or seed exists.
    binding = dict.fromkeys(writer.BINDINGS, TAG)
    binding.update(source_commit=a["source_commit"], source_tree=a["source_tree"],
                   profile_sha256=a["profile_sha256"], host_qualification_sha256=a["host_sha256"],
                   input_commitment_sha256=input_commitment(cases), recipient_sha256=a["recipient_sha256"],
                   encryptor_sha256=a["age_sha256"])
    expected = plaintext(cases, binding)
    require(writer.sha(expected) == a["plaintext_sha256"], "canary-fixture")
    confirm("PUBLIC ONLY USB UNPLUGGED "+digest)
    root = parent/("age-canary-"+a["operation_id"])
    root.mkdir(mode=0o700)
    root = h1.private_directory(root)
    host.filesystem(root)
    h1.exclusive(root/"OPERATION", digest.encode("ascii"))

    def sink(fd, deadline):
        return writer.AgeSink(age, a["age_sha256"], recipient, a["recipient_sha256"], fd, deadline)
    exclusive_probe(root)
    interrupted_store(root, binding, sink, end)
    commitment = writer.write_answers(iter(cases), 2, binding, writer.PrivateStore(root, "positive"),
                                      sink, lambda: True, lambda: TAG, end)
    projection = dict(operation_id=a["operation_id"], stage1_sha256=TAG, jar_sha256=TAG,
                      completion_sha256=commitment["commitment_sha256"], bindings_sha256=writer.checked_binding(binding),
                      input_sha256=binding["input_commitment_sha256"], age_sha256=a["age_sha256"],
                      source_manifest_sha256=writer.sha(writer.canonical(MANIFEST)), count=2, plaintext_cap=CAP)
    claim_raw = writer.canonical(projection)
    def claim():
        h1.exclusive(root/"CLAIM", claim_raw)
        return writer.sha(claim_raw)
    confirm("INSERT DEDICATED USB FOR PUBLIC CANARY")
    mount_id, device = parse_usb_pair(input("Dedicated USB mount ID: ").strip(),
                                      input("Dedicated USB major:minor: ").strip())
    check_usb_mount(mount_id, device)
    broker = usb.CustodyBroker(root,"positive",age,mount_id,device,projection,a["host_sha256"],
                               claim,usb.terminal_note,usb.terminal_removal)
    removal = roundtrip(broker, projection, expected, end)
    finished = now()
    confirm("POSTFLIGHT COMPLETE")
    post = read_control(control, "POSTFLIGHT.json")
    custody(post, a, p, finished, post=True)
    require(now() < wall and time.monotonic() < end and not usb.mounted(device,mount_id))
    row = dict(schema="heldout-age-host-canary/1", operator="Howard", encryptor_sha256=a["age_sha256"],
               recipient_sha256=a["recipient_sha256"], public_canary_only=True, roundtrip_match=True,
               interruption_refused=True, exclusive_write=True, file_directory_sync_readback=True,
               usb_identity_only=True, raw_private_values_included=False)
    receipt = writer.canonical(row)+b"\n"
    h2.canary_receipt(receipt, dict(host_canary_sha256=writer.sha(receipt), age={"sha256":a["age_sha256"]},
                                   recipient_sha256=a["recipient_sha256"]))
    h1.exclusive(root/"EVIDENCE.json",writer.canonical(dict(approval_sha256=digest, removal_sha256=removal,
                 ciphertext_commitment=commitment["commitment_sha256"], postflight_sha256=writer.sha(post))))
    h1.exclusive(root/"CANARY.json",receipt)
    return writer.sha(receipt)


def main():
    try:
        parser = Parser(prog="public-age-canary", allow_abbrev=False)
        parser.add_argument("--control", required=True, type=Path)
        parser.add_argument("--approval-sha256", required=True)
        args = parser.parse_args()
        digest = execute(args.control,args.approval_sha256)
    except (Exception, KeyboardInterrupt) as error:
        print(refusal(error), file=sys.stderr)
        return 2
    print("public-age-canary-complete",digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
