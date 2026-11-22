"""Prepare a job-local CloudBank dependency repository and a Central-only cache seed."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def pom_digest(roots):
    rows = []
    for root in sorted(roots):
        if not (root / "pom.xml").is_file():
            raise ValueError(f"Missing root POM: {root}")
        for path in sorted(root.rglob("pom.xml")):
            rows.append([path.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def cache_key(roots):
    version_output = subprocess.check_output(["mvn", "--version"], text=True)
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", version_output)
    version = re.search(r"^Apache Maven ([0-9]+\.[0-9]+\.[0-9]+)\b", clean_output, re.M)
    if not version:
        raise ValueError("Maven release version unavailable")
    return "-".join(("cloudbank-m2-v1", os.environ["GITHUB_JOB"],
                     os.environ["CLOUDBANK_RUNNER_LABEL"], os.environ["RUNNER_ARCH"],
                     version[1], pom_digest(roots)))


def prepare_work(directory, exact_hit):
    seed = directory / "seed"
    work = directory / "work"
    if exact_hit:
        seed.rename(work)
        print("CloudBank Maven cache: exact hit; using trusted main dependencies.")
    else:
        # An incomplete download or a prefix match is never a Maven repository.
        if seed.exists():
            seed.rename(directory / "unused-restore")
        work.mkdir(parents=True)
        print("CloudBank Maven cache: miss, eviction or unavailable; resolving from Central (-C).")


def matching_checksum(path):
    for algorithm in ("sha512", "sha256", "sha1"):
        sidecar = path.with_name(path.name + "." + algorithm)
        if sidecar.is_symlink() or not sidecar.is_file() or sidecar.stat().st_size > 1024:
            continue
        expected = sidecar.read_bytes().strip().lower()
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, algorithm).hexdigest().encode()
        if actual == expected:
            return sidecar
    return None


def stage_seed(directory):
    work = directory / "work"
    seed = directory / "seed"
    seed.mkdir()
    copied = 0
    for marker in work.rglob("_remote.repositories"):
        relative = marker.parent.relative_to(work)
        if marker.is_symlink() or any("SNAPSHOT" in part for part in relative.parts):
            continue
        origins = {}
        for line in marker.read_text(encoding="latin-1").splitlines():
            match = re.fullmatch(r"([\w.+-]+\.(?:jar|pom))>([^=]*)=", line)
            if match:
                origins.setdefault(match[1], set()).add(match[2])
        destination = seed / relative
        accepted = []
        for name, repositories in sorted(origins.items()):
            artifact = marker.parent / name
            if repositories != {"central"} or artifact.is_symlink() or not artifact.is_file():
                continue
            sidecar = matching_checksum(artifact)
            if sidecar is None:
                continue
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact, destination / name)
            shutil.copyfile(sidecar, destination / sidecar.name)
            accepted.append(f"{name}>central=\n")
        if accepted:
            (destination / marker.name).write_text("".join(accepted), encoding="ascii")
            copied += len(accepted)
    print(f"CloudBank Maven cache: staged {copied} checksum-verified Central JAR/POM files.")
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("key").add_argument("roots", nargs="+", type=Path)
    commands.add_parser("prepare").add_argument("--cache-hit", default="")
    commands.add_parser("stage")
    args = parser.parse_args()
    directory = Path(os.environ["RUNNER_TEMP"]) / "cloudbank-m2"
    if args.command == "key":
        directory.mkdir()
        key = cache_key(args.roots)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"key={key}\n")
        print(f"CloudBank Maven cache key: {key}")
    elif args.command == "prepare":
        prepare_work(directory, args.cache_hit == "true")
    else:
        count = stage_seed(directory)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"count={count}\n")


if __name__ == "__main__":
    main()
