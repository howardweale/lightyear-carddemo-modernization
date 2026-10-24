"""Combined pre-run fence from trusted-base public Git records.

Standalone while #447 is pending. Neither a candidate-side record change nor
clock expiry can remove a protected path. This is a refusal guard, not approval.
"""
import argparse
from hashlib import sha256
import json
import re
import subprocess

ORIGINAL = "docs/factory/copau-factory-judge-freeze-2026-10-18.json"
AMENDMENT = "docs/factory/copau-factory-judge-freeze-amendment-2026-10-20.json"
F2 = "docs/factory/copau-f2-preparation-2026-10-22/request.json"
PLAN = "docs/factory/posttran-phase2-plan-2026-10-16.json"
KEY_CHANGE = "docs/factory/posttran-key-change-2026-10-23/amendment.json"


def safe_path(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or value.startswith("/") or any(ord(c) < 32 for c in value)
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise ValueError("invalid-fence-path")
    return value


def derive(read, names):
    paths, prefixes, inputs = set(), set(), {}

    def document(path, expected=None):
        path = safe_path(path)
        raw = read(path)
        digest = sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError("fence-record-binding")
        paths.add(path)
        inputs[path] = digest
        return json.loads(raw)

    def rows(values):
        if not isinstance(values, list) or not values:
            raise ValueError("empty-fence-inventory")
        for row in values:
            if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
                raise ValueError("fence-digest")
            paths.add(safe_path(row["path"]))

    original = document(ORIGINAL)
    amendment = document(AMENDMENT)
    if amendment["original_manifest_sha256"] != inputs[ORIGINAL]:
        raise ValueError("freeze-amendment-binding")
    rows(original["files"])
    rows(amendment["files"])
    rows([amendment["existing_authorized_change"]])
    for path in tuple(paths):
        if "/service/src/test/" in path:
            prefixes.add(path.split("/src/test/")[0] + "/src/test/")
    request = document(F2)
    if request["schema"] != "copau-f2-preparation/1":
        raise ValueError("f2-schema")
    for binding in request["engineering_source_bindings"].values():
        paths.add(safe_path(binding["path"]))
    records = {k: document(b["path"], b["sha256"]) for k, b in request["bindings"].items()}
    prefixes.add(safe_path(records["scope"]["candidate_directory"]) + "/")
    paths.add(safe_path(records["scope"]["interfaces"]["source_path"]))
    for path in request["work_order"]["scope"]["allowed_paths"]:
        prefixes.add(safe_path(path) + "/")
    workspace = records["workspace"]
    if not isinstance(workspace, dict) or not workspace:
        raise ValueError("empty-workspace-binding")
    paths.update(safe_path(p) for p in workspace)
    support = sorted(p for p in names if p.startswith("docs/factory/copau-f8-") and p.endswith(".json")
                     and ("support-bindings-" in p or "worker-packaging-" in p))
    if not support:
        raise ValueError("missing-support-bindings")
    for path in support:
        rows(document(path)["selection"]["source_bindings"])

    # No adoption of the seven current-main POSTTRAN substitutions. The original
    # sealed executable/candidate inventories and additive key amendment survive.
    plan = document(PLAN)
    for key in ("bound_files", "candidate_files"):
        if not isinstance(plan[key], dict) or not plan[key]:
            raise ValueError("empty-posttran-binding")
        paths.update(safe_path(p) for p in plan[key])
    document(KEY_CHANGE)
    paths.update(safe_path(p) for p in names if p.startswith(
        ("docs/factory/posttran-", "spec/mainframe/posttran-independent/")))
    return dict(paths=sorted(paths), prefixes=sorted(prefixes), inputs=inputs, automatic_expiry=False)


def violations(fence, changed):
    return sorted(p for p in changed if p in fence["paths"] or any(
        p == prefix.rstrip("/") or p.startswith(prefix) for prefix in fence["prefixes"]))


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)


def inspect(repo, base, head):
    # CI supplies full object IDs obtained from trusted event metadata. Do not
    # accept options, abbreviated refs or candidate-controlled branch names.
    if not all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in (base, head)):
        raise ValueError("full-git-sha-required")
    for ref in (base, head):
        git(repo, "cat-file", "-e", ref + "^{commit}")
    names = git(repo, "ls-tree", "-r", "--name-only", "-z", base).decode().split("\0")
    fence = derive(lambda p: git(repo, "show", base + ":" + p), [p for p in names if p])
    changed = git(repo, "diff", "--no-renames", "--name-only", "-z", base, head).decode().split("\0")
    blocked = violations(fence, [p for p in changed if p])
    return dict(schema="platform-fence/1", base=base, head=head,
                inventory_sha256=sha256(json.dumps(fence, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                fenced_paths=len(fence["paths"]), prefixes=fence["prefixes"], source_records=fence["inputs"],
                blocked_paths=blocked, automatic_expiry=False, fence_passed=not blocked)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.repo, args.base, args.head)
        print(json.dumps(result, sort_keys=True))
        return 1 if result["blocked_paths"] else 0
    except Exception:
        print("platform-fence: unavailable or invalid trusted-base inventory")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
