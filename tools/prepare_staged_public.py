"""Key-free L1c preparation for a single graph-off operation."""
import argparse
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
        raise SystemExit("preparation-isolation")
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from lightyear_factory import public_repair_answer_key as key
from lightyear_factory import public_repair_controller as ctl
from lightyear_factory import public_repair_durable as durable
from lightyear_factory import public_repair_staged as staged
from lightyear_factory import public_repair_worker as worker
from lightyear_factory import staged_run_admission as admission
from tools import intcalc_public_freeze_wrapper as archive

CONTEXT = "4f25b42be20c5e4bb0a82030e3172b5c6751c7dfb5b36aa1f1bb42dee25a5a52"
TAG = "full-intcalc-public-answer-key-20261118-r1"
CAPS = {"REQUEST.json": 65536, "LOCAL-WORKER.json": 65536, "HOST.json": 65536,
        "CURRENT-CONTEXT.json": 98304, "answer-key.zip": 65536, "WORKER-QUALIFICATION.receipt": 2097152}
for kind in admission.PROOFS:
    CAPS[kind + ".json"] = 65536
    CAPS[kind + ".receipt"] = 2097152


def require(ok, code):
    ctl.require(ok, "preparation-" + code)


def owner_directory(path):
    _, fd, _ = durable.open_parent(path)
    durable.close_quiet(fd)


def new_directory(path):
    require(path.is_absolute() and path.name not in ("", ".", ".."), "path")
    owner_directory(path.parent)
    path.mkdir(mode=0o700)
    owner_directory(path)


def worker_join(config, qualification):
    return dict(schema="staged-worker-qualification-join/1", configuration_sha256=ctl.sha(config),
                qualification_sha256=ctl.sha(qualification))


def timing(request, now, starting):
    admission.fields(request, "schema operation_id approved_at latest_start publication")
    require(request["schema"] == "staged-preparation-request/1" and ctl.hash_ok(request["operation_id"]),
            "request")
    admission.check_descriptor(request["publication"])
    issued, end = (staged.instant(request[k]) for k in ("approved_at", "latest_start"))
    require(0 < (end-issued).total_seconds() <= ctl.WINDOW and now < end, "window")
    if starting:
        require(issued <= now, "window")
    return issued


def profile(config, modules):
    row = admission.record(config)
    admission.fields(row, "schema docker_binary docker_endpoint")
    require(row["schema"] == "staged-local-worker/1" and type(row["docker_binary"]) is str
            and type(row["docker_endpoint"]) is str and row["docker_endpoint"].startswith("unix:///"),
            "worker")
    sock = Path(row["docker_endpoint"][7:])
    require(sock.is_absolute() and sock == sock.resolve(strict=True)
            and stat.S_ISSOCK(sock.stat().st_mode) and sock.stat().st_uid == os.getuid(), "worker")
    binary = worker.safe(row["docker_binary"])
    require(os.access(binary, os.X_OK), "worker")
    return dict(cli_sha256=ctl.sha(worker.read(binary, 64*1024*1024)), helper_sha256=modules[admission.HELPER],
                jdk_sha256=worker.JDK, jre_sha256=worker.JRE)


def commitment(request, issued, asset, observation):
    dates = [staged.instant(observation[k]) for k in ("published_at","asset_created_at","asset_updated_at")]
    row = dict(schema="heldout-pre-run-commitment/1", committed_at=max(dates).isoformat(),
               commitment_sha256=admission.record(asset)["commitment_sha256"],
               publication_receipt_sha256=ctl.digest(observation))
    admission.verify_publication(request["publication"], row, asset, observation, issued)
    return row


def documents(data, source, reviewed, build, committed, now):
    request = admission.record(data["REQUEST.json"])
    require(ctl.sha(data["CURRENT-CONTEXT.json"]) == CONTEXT, "context")
    context = staged.strict(data["CURRENT-CONTEXT.json"])
    modules = source["modules"]
    binding = dict(schema="staged-public-binding/1", mode="STAGED_PUBLIC", graph_mode="off",
                   max_repairs=5, window_seconds=ctl.WINDOW, cap_microdollars=ctl.CEILING, model=ctl.MODEL,
                   service_tier="flex", output_cap=32000, retries=0, public_case_count=16,
                   implementation_sha256=ctl.digest(modules), public_context_sha256=ctl.digest(context),
                   public_suite_sha256=modules[admission.SUITE], role_instructions_sha256=ctl.ROLE_HASH,
                   feedback_contract_sha256=ctl.FEEDBACK_HASH, staged_policy_sha256=staged.POLICY_HASH,
                   pre_run_commitment=committed, heldout_commitment_sha256=ctl.digest(committed),
                   build_profile=build, runtime_profile_sha256=ctl.digest(build),
                   public_answer_key_sha256=reviewed.manifest_sha256, worker_source_sha256=modules[admission.WORKER],
                   approval_timestamp=request["approved_at"])
    proofs = {kind: (data[kind + ".json"], data[kind + ".receipt"]) for kind in admission.PROOFS}
    require(admission.record(proofs["public_worker"][1]) ==
            worker_join(data["LOCAL-WORKER.json"], data["WORKER-QUALIFICATION.receipt"]), "worker-join")
    intent = dict(schema="graph-off-admission-intent/1", source_commit=source["commit"], source_tree=source["tree"],
                  modules_sha256=ctl.digest(modules), binding_intent_sha256=ctl.digest(binding),
                  key_release_sha256=modules[admission.RELEASE_BINDING], host_qualification_sha256=ctl.sha(data["HOST.json"]),
                  publication=request["publication"], proofs={k:ctl.sha(v[0]) for k,v in proofs.items()},
                  rates=admission.RATES, holds_microdollars=ctl.HOLDS)
    proposal = dict(schema="staged-paid-run-approval/1", operator="Howard", operation_id=request["operation_id"],
                    intent_sha256=ctl.digest(intent), approved_at=request["approved_at"], latest_start=request["latest_start"],
                    mode="STAGED_PUBLIC", model=ctl.MODEL, graph_mode="off", cap_microdollars=ctl.CEILING,
                    window_seconds=ctl.WINDOW, count_billing_assumption_accepted=True)
    binding["authority_sha256"] = ctl.digest(proposal)
    staged.validate_binding(binding, context)
    admission.check_evidence(intent, binding, source, reviewed, data["HOST.json"], proofs, now)
    return {"BINDING.json":ctl.canonical(binding), "INTENT.json":ctl.canonical(intent),
            "PROPOSED-APPROVAL.json":ctl.canonical(proposal)}


def check_approval(proposed, actual, independent):
    require(ctl.hash_ok(independent) and ctl.sha(actual) == independent and actual == proposed, "approval")


def inputs(folder):
    owner_directory(folder)
    return {name:staged.read_owned(folder/name, limit) for name,limit in CAPS.items()}


def review(data, starting):
    source = admission.checkout(ROOT)
    request = admission.record(data["REQUEST.json"])
    utc = lambda: datetime.now(timezone.utc)
    issued = timing(request, utc(), starting)
    reviewed = key.published_key((ROOT / admission.RELEASE_BINDING).read_bytes(), TAG, data["answer-key.zip"])
    build = profile(data["LOCAL-WORKER.json"], source["modules"])
    asset, observation = admission.github_publication(request["publication"], time.monotonic()+60)
    committed = commitment(request, issued, asset, observation)
    now = utc()
    timing(request, now, starting)
    return documents(data, source, reviewed, build, committed, now), reviewed


def exclusive_files(folder, rows):
    new_directory(folder)
    for name, raw in rows.items():
        archive.exclusive(folder/name, raw)


def summary(status, docs):
    return dict(schema="staged-preparation-readback/1", status=status,
                binding_sha256=ctl.sha(docs["BINDING.json"]), intent_sha256=ctl.sha(docs["INTENT.json"]),
                proposed_approval_sha256=ctl.sha(docs["PROPOSED-APPROVAL.json"]))


def execute(args):
    require(sys.platform == "darwin" and platform.machine() == "arm64", "host")
    folder = args.directory
    if args.mode == "worker-join":
        owner_directory(folder)
        return worker_join(staged.read_owned(folder/"LOCAL-WORKER.json",65536),
                           staged.read_owned(folder/"WORKER-QUALIFICATION.receipt",2097152))
    data = inputs(folder)
    docs, reviewed = review(data, starting=args.mode == "preflight")
    if args.mode == "draft":
        exclusive_files(args.output, docs)
        return summary("PROPOSED", docs)
    if args.mode == "seal":
        actual = staged.read_owned(args.approval, 65536)
        check_approval(docs["PROPOSED-APPROVAL.json"], actual, args.approval_sha256)
        rows = dict(data, **{"INTENT.json":docs["INTENT.json"], "BINDING.json":docs["BINDING.json"],
                             "APPROVAL.json":actual})
        exclusive_files(args.output, rows)
        archive.unpack(data["answer-key.zip"], args.output/"answers")
        key.load(args.output/"answers", (ROOT/admission.SUITE).parent, reviewed)
        return summary("SEALED", docs)
    actual = staged.read_owned(folder/"APPROVAL.json",65536)
    check_approval(docs["PROPOSED-APPROVAL.json"], actual, args.approval_sha256)
    for name in ("INTENT.json","BINDING.json"):
        require(staged.read_owned(folder/name,65536) == docs[name], "bundle")
    key.load(folder/"answers", (ROOT/admission.SUITE).parent, reviewed)
    operation = admission.record(actual)["operation_id"]
    inspect_placement(operation)
    return summary("PREFLIGHT_READY", docs)


def inspect_placement(operation):
    """Read-only absence and custody check; launch performs the exclusive claims."""
    import pwd
    require(ctl.hash_ok(operation), "operation")
    base = Path(pwd.getpwuid(os.getuid()).pw_dir)/".lightyear-staged-public"
    owner_directory(base)
    for name, prefix in (("authority","public-repair-"),("ledger","public-repair-"),("worker","public-worker-")):
        parent = base/name
        owner_directory(parent)
        try:
            (parent/(prefix+operation)).lstat()
        except FileNotFoundError:
            continue
        raise ctl.Refused("preparation-spent")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    for name in ("worker-join","draft","seal","preflight"):
        sub = modes.add_parser(name)
        sub.add_argument("--directory", required=True, type=Path)
        if name in ("draft","seal"):
            sub.add_argument("--output", required=True, type=Path)
        if name in ("seal","preflight"):
            sub.add_argument("--approval-sha256", required=True)
        if name == "seal":
            sub.add_argument("--approval", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        row = execute(args)
    except (Exception, KeyboardInterrupt):
        print("staged-preparation-refused",file=sys.stderr)
        return 2
    print(ctl.canonical(row).decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
