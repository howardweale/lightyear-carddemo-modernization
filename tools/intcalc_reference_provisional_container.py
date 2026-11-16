"""CI boundary for a provisional same-job image; no registry or qualification."""
import argparse
import os
from pathlib import Path
import platform
import re
import subprocess
import time
import uuid
from tools import intcalc_reference_execution as ref
from tools import intcalc_reference_provisional as provisional


def call(args, deadline, output=None, allowed=(0,)):
    remaining = deadline - time.monotonic()
    ref.require(remaining > 0, "container-original-deadline")
    result = subprocess.run(["docker", *args], stdin=subprocess.DEVNULL,
                            stdout=output or subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=remaining, check=False)
    ref.require(result.returncode in allowed, "container-command-exit")
    return result.stdout


def execute(request_path, image, output):
    ref.require(os.environ.get("GITHUB_ACTIONS") == "true" and
                platform.system() == "Linux" and platform.machine() == "x86_64",
                "native-amd64-ci-only")
    provisional.check_inputs(request_path)
    # Fixed repository mount; no CLI option for a different source root.
    source = ref.ROOT.resolve()
    request_relative = request_path.resolve().relative_to(source)
    ref.require(not output.exists() and not output.is_symlink(), "fresh-destination")
    ref.require(re.fullmatch(r"sha256:[0-9a-f]{64}", image) is not None,
                "same-job-image-id")
    deadline = time.monotonic() + 2100
    architecture = call(["info", "--format", "{{.OSType}}/{{.Architecture}}"], deadline).decode().strip()
    ref.require(architecture in ("linux/x86_64", "linux/amd64"), "daemon-platform")
    # Image ID comes only from this job's build --iidfile; no registry pull.
    inspected = ref.strict(call(["image", "inspect", image], deadline))
    ref.require(len(inspected) == 1 and inspected[0]["Os"] == "linux" and
                inspected[0]["Architecture"] == "amd64" and inspected[0]["Id"] == image,
                "same-job-image-identity")
    output.mkdir(mode=0o700)
    name = "reference-public-" + uuid.uuid4().hex
    created = False
    outcome = None
    cleanup = False
    try:
        call(["create", "--name", name, "--network=none", "--read-only",
              "--cap-drop=ALL", "--security-opt=no-new-privileges",
              "--cpus=2", "--memory=2g", "--pids-limit=128",
              "--user", str(os.getuid()) + ":" + str(os.getgid()),
              "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
              "--tmpfs", "/work:rw,nosuid,nodev,exec,size=1g",
              "--mount", "type=bind,src=" + str(source) + ",dst=/source,readonly",
              "--mount", "type=bind,src=" + str(output.resolve()) + ",dst=/output",
              "--env", "GITHUB_ACTIONS=true", "--env", "PYTHONPATH=/source/src:/source",
              "--env", "PYTHONDONTWRITEBYTECODE=1", "--workdir", "/source",
              image, "python3", "-B", "tools/intcalc_reference_provisional.py",
              "compare", "--request", "/source/" + request_relative.as_posix(),
              "--output", "/output/public"], deadline)
        created = True
        # Bounded outer deadline independent of the program's injected clock.
        call(["start", name], deadline)
        status = call(["wait", name], deadline - 30).decode().strip()
        ref.require(status in ("0", "2"), "reference-container-fault")
        log = call(["logs", name], deadline)
        ref.require(len(log) <= 65536, "controller-log-size")
        ref.exclusive(output / "controller.log", log)
        print(log.decode("utf-8", errors="replace"), end="")
        # Output is a fresh dedicated public bind mount; tmpfs disappears at
        # container exit. Never collect a home directory or private run root.
        report = output / "public" / "report.json"
        if report.is_file():
            ref.exclusive(output / "report.json", ref.bounded(report))
        observed = output / "public" / "inventory.json"
        if observed.is_file():
            ref.exclusive(output / "inventory.json", ref.bounded(observed))
        outcome = status
    finally:
        if created:
            try:
                call(["rm", "-f", name], time.monotonic() + 20)
                remaining = call(["ps", "-a", "--filter", "name=^/" + name + "$",
                                  "--format", "{{.Names}}"], time.monotonic() + 10)
                cleanup = not remaining.strip()
            finally:
                ref.exclusive(output / "container-cleanup.json", ref.canonical({
                    "schema": "reference-container-cleanup/1", "removed_and_absent": cleanup,
                    "local_image_id": image, "provisional": True, "image_digest_bound": False,
                    "qualified": False}) + b"\n")
    ref.require(cleanup, "cleanup-unconfirmed")
    return int(outcome)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        raise SystemExit(execute(args.request, args.image_id, args.output))
    except ref.Refused as exc:
        print(str(exc))
        raise SystemExit(2) from None
