"""Attended, one-use Mac launcher for the approved graph-off public stage."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    if not (sys.flags.isolated and sys.dont_write_bytecode):
        raise SystemExit("launcher-isolation")
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from lightyear_factory import public_repair_answer_key as key
from lightyear_factory import public_repair_controller as ctl
from lightyear_factory import public_repair_durable as durable
from lightyear_factory import public_repair_provider as provider
from lightyear_factory import public_repair_staged as staged
from lightyear_factory import public_repair_worker as worker
from lightyear_factory import staged_run_admission as admission

TAG = "full-intcalc-public-answer-key-20261118-r1"
CONTEXT = "766e64f8a76cf543b38f776e71b43e8a31a97043f2ca1763892ff5a2f02dd19b"


def require(condition, code):
    ctl.require(condition, "launcher-" + code)


def owner_area():
    """The replay parent does not come from the bundle, HOME, cwd or arguments."""
    require(sys.platform == "darwin" and platform.machine() == "arm64", "host")
    import pwd
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    base = home / ".lightyear-staged-public"
    for path in (base, base / "authority", base / "ledger", base / "worker"):
        _, fd, _ = durable.open_parent(path)
        durable.close_quiet(fd)
    return base


def configuration(raw):
    row = admission.record(raw)
    admission.fields(row, "schema docker_binary docker_endpoint")
    require(row["schema"] == "staged-local-worker/1", "config")
    binary = row["docker_binary"]
    endpoint = row["docker_endpoint"]
    require(type(binary) is str and Path(binary).is_absolute()
            and type(endpoint) is str and endpoint.startswith("unix:///"), "config")
    path = Path(endpoint[7:])
    require(path.is_absolute() and path.resolve(strict=True) == path
            and stat.S_ISSOCK(path.lstat().st_mode)
            and path.stat().st_uid == os.getuid(), "endpoint")
    return row


def read_bundle(folder, expected):
    _, fd, _ = durable.open_parent(folder)
    durable.close_quiet(fd)
    def read(name, cap=65536):
        return staged.read_owned(folder / name, cap)
    approval = read("APPROVAL.json")
    require(ctl.hash_ok(expected) and ctl.sha(approval) == expected, "approval")
    auth = admission.record(approval)
    require(ctl.hash_ok(auth.get("operation_id")), "operation")
    raw_binding = read("BINDING.json")
    binding = admission.record(raw_binding)
    require(ctl.canonical(binding) == raw_binding and binding["authority_sha256"] == expected,
            "binding")
    raw_context = read("CURRENT-CONTEXT.json", 98304)
    require(ctl.sha(raw_context) == CONTEXT, "context")
    context = staged.strict(raw_context)
    staged.validate_value_binding(binding, context)
    proofs = {kind: (read(kind + ".json"), read(kind + ".receipt", 2097152))
              for kind in admission.PROOFS}
    config = read("LOCAL-WORKER.json")
    qualification = read("WORKER-QUALIFICATION.receipt", 2097152)
    envelope = admission.record(proofs["public_worker"][1])
    admission.fields(envelope, "schema configuration_sha256 qualification_sha256")
    require(envelope == dict(schema="staged-worker-qualification-join/1",
                             configuration_sha256=ctl.sha(config),
                             qualification_sha256=ctl.sha(qualification)), "worker-join")
    key_binding = (ROOT / admission.RELEASE_BINDING).read_bytes()
    archive = read("answer-key.zip", 65536)
    reviewed = key.published_key(key_binding, TAG, archive)
    return dict(approval=approval, operation=auth["operation_id"], binding=binding,
                context=context, intent=read("INTENT.json"), host=read("HOST.json"),
                proofs=proofs, config=configuration(config), key_archive=archive,
                key_binding=key_binding, reviewed=reviewed)


class Storage(staged.StagedDurablePorts, provider.ProviderEvidence):
    """Single P3 operation directory and accounting shared by all stage-1 ports."""
    def retain_evaluation(self, raw):
        require(type(raw) is bytes and 0 < len(raw) <= durable.RECORD_BYTES, "evaluation")
        digest = ctl.sha(raw)
        return self._operation(lambda: self._write("evaluation-" + digest + ".json", raw))


class Ports:
    """Construct the key owner lazily on the first reserved count after admission."""
    def __init__(self, gate, assemble, deadline):
        self.gate = gate
        self.assemble = assemble
        self.deadline = deadline
        self.storage = self.adapter = self.retainer = self.models = None
        self.closed = self.claimed = False

    def admit(self, raw, deadline):
        require(not self.claimed and not self.closed, "state")
        self.claimed = True
        receipt = self.gate.admit(raw, min(deadline, self.deadline))
        self.storage, self.adapter, self.retainer = self.assemble()
        return receipt

    def record(self, name, row):
        digest = self.storage.record(name, row)
        require(digest == ctl.sha(ctl.canonical(row) + b"\n"), "readback")
        return digest

    def count(self, request, deadline):
        require(self.storage is not None and not self.closed, "state")
        deadline = min(deadline, self.deadline)
        if self.models is None:
            owner = provider.KeyOwner(deadline)
            try:
                self.models = provider.ProviderPorts(owner, self.storage, self.deadline)
            except BaseException:
                owner.close(deadline)
                raise
        return self.models.count(request, deadline)

    def generate(self, request, deadline):
        require(self.models is not None and not self.closed, "state")
        return self.models.generate(request, min(deadline, self.deadline))

    def close_models(self):
        if self.closed:
            return
        self.closed = True
        if self.models is not None:
            self.models.close_models()

    def retain_artifact(self, slot, name, value):
        return self.storage.retain_artifact(slot, name, value)

    def build(self, source, round_no, deadline):
        return self.adapter.build(source, round_no, min(deadline, self.deadline))

    def evaluate_public(self, built, suite, deadline):
        return self.adapter.evaluate_public(built, suite, min(deadline, self.deadline))

    def retain_selected_jar(self, selected, binding, closure, deadline):
        require(self.closed and self.models is not None and self.models.closed
                and not self.models.failed, "closure")
        return self.retainer.retain_selected_jar(selected, binding, closure, min(deadline, self.deadline))


def launch(folder, expected):
    started = time.monotonic()
    wall = datetime.now(timezone.utc)
    deadline = started + ctl.WINDOW
    def clock():
        now = time.monotonic()
        elapsed = (datetime.now(timezone.utc) - wall).total_seconds()
        require(now < deadline and 0 <= elapsed < ctl.WINDOW, "deadline")
        return now

    area = owner_area()
    row = read_bundle(folder, expected)
    gate = admission.GraphOffAdmission(
        root=ROOT, authority_root=area / "authority", expected_approval=expected,
        approval=row["approval"], intent=row["intent"], context=row["context"],
        key_binding=row["key_binding"], key_archive=row["key_archive"], host=row["host"],
        proofs=row["proofs"], clock=clock)
    binding = row["binding"]
    with ExitStack() as stack:
        def assemble():
            storage = Storage(area / "ledger", row["operation"], deadline, clock=clock)
            stack.callback(storage.close)
            config, profile = row["config"], binding["build_profile"]
            engine = worker.PublicWorker(area / "worker", row["operation"], config["docker_binary"],
                                        profile["cli_sha256"], config["docker_endpoint"],
                                        ROOT / admission.HELPER, profile["helper_sha256"])
            adapter = key.ValuePublicAdapter(engine, folder / "answers", (ROOT / admission.SUITE).parent,
                                              ROOT, row["reviewed"], storage.retain_evaluation, clock=clock)
            return storage, adapter, staged.P5SelectedJarRetainer(engine, storage, clock=clock)

        ports = Ports(gate, assemble, deadline)
        try:
            controller = staged.ValueStagedController(ports, binding, row["context"], clock=clock)
            result = controller.run()
            clock()
            return dict(schema="staged-launch-readback/1", operation_id=row["operation"],
                        status=result["status"], hidden=result["hidden"]["status"],
                        result_file_sha256=ctl.sha(ctl.canonical(result) + b"\n"))
        finally:
            ports.close_models()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--approval-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = launch(args.bundle, args.approval_sha256)
    except (Exception, KeyboardInterrupt):
        # P3 retains the stage and fixed refusal when admission succeeded.
        print("staged-launch-stopped-no-resume", file=sys.stderr)
        return 2
    print(ctl.canonical(result).decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
