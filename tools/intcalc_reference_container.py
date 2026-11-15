"""CI host boundary for public reference qualification, not a candidate gate."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
import time
import uuid
from tools import intcalc_reference_execution as ref


def call(args, deadline, output=None, allowed=(0,)):
    remaining = deadline - time.monotonic()
    ref.require(remaining > 0, "container-original-deadline")
    result = subprocess.run(["docker", *args], stdin=subprocess.DEVNULL,
                            stdout=output or subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=remaining, check=False)
    ref.require(result.returncode in allowed, "container-command-exit")
    return result.stdout


def saved_config_hash(image, deadline):
    with tempfile.TemporaryFile() as stream:
        call(["image", "save", image], deadline, stream)
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:") as archive:
            manifests = [m for m in archive.getmembers() if m.name == "manifest.json"]
            ref.require(len(manifests) == 1 and manifests[0].isfile()
                        and manifests[0].size < 65536, "image-save-manifest")
            rows = ref.strict(archive.extractfile(manifests[0]).read())
            ref.require(len(rows) == 1, "image-save-inventory")
            configs = [m for m in archive.getmembers() if m.name == rows[0]["Config"]]
            ref.require(len(configs) == 1 and configs[0].isfile()
                        and configs[0].size < 1048576, "image-save-config")
            return ref.sha(archive.extractfile(configs[0]).read())


def execute(binding_path, suite, output):
    ref.require(os.environ.get("GITHUB_ACTIONS") == "true" and
                platform.system() == "Linux" and platform.machine() == "x86_64",
                "native-amd64-ci-only")
    row = ref.binding(ref.bounded(binding_path))
    # Fixed repository mount; no CLI option for a different source root.
    source = ref.ROOT.resolve()
    binding_relative = binding_path.resolve().relative_to(source)
    suite_relative = suite.resolve().relative_to(source)
    ref.require(not output.exists() and not output.is_symlink(), "fresh-destination")
    ref.require("image_repository" in row and
                row["image_repository"] == "ghcr.io/howardweale/lightyear-reference", "image-repository")
    image = row["image_repository"] + "@sha256:" + row["image_manifest"]
    deadline = time.monotonic() + 2100
    architecture = call(["info", "--format", "{{.OSType}}/{{.Architecture}}"], deadline).decode().strip()
    ref.require(architecture in ("linux/x86_64", "linux/amd64"), "daemon-platform")
    # Pull is a separate, explicit workflow step. This runner never pulls.
    inspected = ref.strict(call(["image", "inspect", image], deadline))
    ref.require(len(inspected) == 1 and inspected[0]["Os"] == "linux"
                and inspected[0]["Architecture"] == "amd64"
                and image in inspected[0].get("RepoDigests", []), "image-identity")
    ref.require(saved_config_hash(image, deadline) == row["image_config"], "image-config")
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
              image, "python3", "-B", "tools/intcalc_reference_execution.py",
              "public", "--binding", "/source/" + binding_relative.as_posix(),
              "--suite", "/source/" + suite_relative.as_posix(),
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
                    "image_manifest": row["image_manifest"], "image_config": row["image_config"],
                    "qualified": False}) + b"\n")
    ref.require(cleanup, "cleanup-unconfirmed")
    return int(outcome)


def pull(binding_path):
    ref.require(os.environ.get("GITHUB_ACTIONS") == "true" and
                platform.system() == "Linux" and platform.machine() == "x86_64",
                "native-amd64-ci-only")
    row = ref.binding(ref.bounded(binding_path))
    ref.require(row["image_repository"] == "ghcr.io/howardweale/lightyear-reference",
                "image-repository")
    call(["pull", "--platform", "linux/amd64",
          row["image_repository"] + "@sha256:" + row["image_manifest"]],
         time.monotonic() + 180)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--suite", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pull-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.pull_only:
            pull(args.binding)
        else:
            ref.require(args.suite is not None and args.output is not None, "arguments")
            raise SystemExit(execute(args.binding, args.suite, args.output))
    except ref.Refused as exc:
        print(str(exc))
        raise SystemExit(2) from None
