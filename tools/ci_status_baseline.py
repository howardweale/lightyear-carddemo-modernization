"""Disposable CI-only status baseline and clean attestation handoff."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

FILES = ("docs/factory/current-status.json", "docs/factory/current-status.md")


def git(root, *args):
    return subprocess.check_output(["git", "--no-optional-locks", *args],
                                   cwd=root, text=True).strip()


def hashes(root):
    result = {}
    for name in FILES:
        path = root / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("status baseline requires regular files")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def capture(root, state):
    if state.exists():
        raise ValueError("status baseline already exists")
    if git(root, "diff", "--cached", "--name-only"):
        raise ValueError("unexpected staged paths")
    if set(git(root, "diff", "--name-only").splitlines()) - set(FILES):
        raise ValueError("unexpected input/evidence changes")
    if git(root, "ls-files", "--others", "--exclude-standard"):
        raise ValueError("unexpected untracked changes")
    record = {"root": str(root.resolve()), "head": git(root, "rev-parse", "HEAD"),
              "files": hashes(root)}
    git(root, "add", "--", *FILES)
    record["index"] = git(root, "write-tree")
    with state.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True)


def finish(root, state):
    record = json.loads(state.read_text(encoding="utf-8"))
    if set(record) != {"root", "head", "files", "index"}:
        raise ValueError("invalid status baseline")
    if record["root"] != str(root.resolve()) or record["head"] != git(root, "rev-parse", "HEAD"):
        raise ValueError("status baseline checkout changed")
    if record["files"] != hashes(root):
        raise ValueError("generated status mutated")
    if record["index"] != git(root, "write-tree"):
        raise ValueError("staged baseline mutated")
    if set(git(root, "diff", "--cached", "--name-only").splitlines()) - set(FILES):
        raise ValueError("unexpected staged paths")
    if git(root, "diff", "--name-only") or git(root, "ls-files", "--others", "--exclude-standard"):
        raise ValueError("input/evidence or untracked mutation")
    # Refuse mutations before restoring only the two disposable outputs.
    git(root, "restore", "--source=HEAD", "--staged", "--worktree", "--", *FILES)
    if git(root, "status", "--porcelain=v1"):
        raise ValueError("attestation handoff is not clean")
    state.unlink()


def cli_context(environ):
    if environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("status baseline is CI-only")
    root = Path(environ["GITHUB_WORKSPACE"]).resolve(strict=True)
    temporary = Path(environ["RUNNER_TEMP"]).resolve(strict=True)
    state = Path(environ["LIGHTYEAR_CI_STATUS_BASELINE"]).absolute()
    if state.parent.resolve(strict=True) != temporary or state.name != "lightyear-status-baseline.json":
        raise ValueError("status baseline must be in RUNNER_TEMP")
    if state.is_symlink() or root == temporary or root in temporary.parents:
        raise ValueError("unsafe status baseline location")
    return root, state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("capture", "finish"))
    args = parser.parse_args()
    root, state = cli_context(os.environ)
    (capture if args.operation == "capture" else finish)(root, state)


if __name__ == "__main__":
    main()
