"""Retry only a transient snapshot-index failure of the unchanged twin build."""
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import time

RECIPE = Path("tools/legacy_twin/reproducible.Containerfile")
RECIPE_SHA256 = "a5825203f639f0cb9c847291f115bccfe256efcd9905b921eb4a56ee3a9f8e85"
COMMAND = ("docker", "build", "--progress=plain", "--platform", "linux/amd64",
           "-f", str(RECIPE), "-t", "twin-repro-toolchain", ".")
TRANSIENT_FETCH = re.compile(
    r"Failed to fetch https://snapshot\.ubuntu\.com/ubuntu/20261001T000000Z/"
    r"dists/[^\s]+\s+(502|503|504)\s+.+")
INDEX_SUMMARY = ("Some index files failed to download. They have been ignored, "
                 "or old ones used instead.")
INTEGRITY_ERROR = re.compile(
    r"checksum mismatch|unexpected commit digest|hash sum mismatch|signature|NO_PUBKEY|certificate verification|"
    r"unauthenticated|not signed|CAPTURE_LIMIT", re.IGNORECASE)


def transient_index_outage(result):
    if result.returncode != 1 or INTEGRITY_ERROR.search(result.stdout):
        return False
    errors = []
    final = []
    for line in result.stdout.splitlines():
        match = re.search(r"(?:^|\s)E:\s+(.*)$", line)
        if match:
            errors.append(match.group(1))
        if line.startswith("ERROR: failed to build:"):
            final.append(line)
    # Tie the transport diagnostic to the failed APT layer, not an earlier warning.
    return (bool(errors) and len(final) == 1
            and "apt-get update" in final[0]
            and "exit code: 100" in final[0]
            and any(TRANSIENT_FETCH.fullmatch(e) for e in errors)
            and all(TRANSIENT_FETCH.fullmatch(e) or e == INDEX_SUMMARY
                    for e in errors))


def execute_build():
    # Stream every byte of text to CI; bounded capture is only for classification.
    captured = []
    size = 0
    overflow = False
    with subprocess.Popen(COMMAND, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace") as process:
        for line in process.stdout:
            print(line, end="", flush=True)
            size += len(line)
            if size <= 200_000:
                captured.append(line)
            else:
                overflow = True
        status = process.wait()
    return subprocess.CompletedProcess(COMMAND, status,
        "".join(captured) + ("\nCAPTURE_LIMIT\n" if overflow else ""))


def build_with_retry(build=execute_build, pause=time.sleep):
    for attempt in (1, 2):
        # Recheck before each invocation; never patch or replace the recipe.
        if hashlib.sha256(RECIPE.read_bytes()).hexdigest() != RECIPE_SHA256:
            print("Protected toolchain recipe differs; refusing build.", file=sys.stderr)
            return 1
        print(f"Unchanged pinned toolchain build: attempt {attempt}/2", flush=True)
        result = build()
        if result.returncode == 0:
            return 0
        if attempt == 2 or not transient_index_outage(result):
            return result.returncode if result.returncode > 0 else 1
        print("Snapshot index HTTP outage; retrying the same build once in 60s.",
              flush=True)
        pause(60)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(build_with_retry())
