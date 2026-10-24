"""Resolve the base actually used by a GitHub PR merge checkout, fail closed."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL).decode().strip()


def comparison_base(root, base, event_name, event, checkout):
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("comparison-base-identity")
    if event_name == "push":
        if event.get("before") != base or event.get("after") != checkout or git(root, "rev-parse", "HEAD") != checkout:
            raise ValueError("comparison-push-identity")
        git(root, "merge-base", "--is-ancestor", base, checkout)
        return base
    if event_name != "pull_request":
        raise ValueError("comparison-event")
    pr = event["pull_request"]
    if pr["base"]["sha"] != base or pr["merge_commit_sha"] != checkout:
        raise ValueError("comparison-event-identity")
    parents = git(root, "rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) != 3 or parents[0] != checkout or parents[2] != pr["head"]["sha"]:
        raise ValueError("comparison-merge-parents")
    # Old event base must be an ancestor of the independently bound merge base.
    # A candidate head or an unrelated branch can never be substituted here.
    git(root, "merge-base", "--is-ancestor", base, parents[1])
    expected = git(root, "merge-tree", "--write-tree", parents[1], parents[2])
    if expected != git(root, "rev-parse", "HEAD^{tree}"):
        raise ValueError("comparison-merge-tree")
    return parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise ValueError("ci-only")
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        print(comparison_base(Path.cwd(), args.base, os.environ["GITHUB_EVENT_NAME"], event, os.environ["GITHUB_SHA"]))
        return 0
    except Exception:
        print("CI comparison identity refused", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
