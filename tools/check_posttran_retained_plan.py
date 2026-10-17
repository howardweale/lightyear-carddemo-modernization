"""Inspect a retained POSTTRAN plan at its recorded commit; never authorize a run."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


PLAN = "docs/factory/posttran-phase2-plan-2026-10-16.json"
ORIGINAL = "docs/factory/posttran-phase2-plan-2026-10-14.json"
REQUEST = "docs/factory/posttran-phase2-authorization-request-2026-10-16.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sealed(value):
    payload = {k: v for k, v in value.items() if k != "content_sha256"}
    if sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()) != value.get("content_sha256"):
        raise ValueError("phase2-retained-plan-seal")


def read_blob(root, revision, path):
    parts = PurePosixPath(path)
    if parts.is_absolute() or str(parts) != path or ".." in parts.parts or "\\" in path:
        raise ValueError("phase2-retained-path")
    row = subprocess.check_output(["git", "ls-tree", "-z", revision, "--", path], cwd=root)
    if not row or row.count(b"\0") != 1:
        raise ValueError("phase2-retained-file-missing:" + path)
    metadata, name = row[:-1].split(b"\t", 1)
    mode, kind, oid = metadata.split()
    if mode not in (b"100644", b"100755") or kind != b"blob" or name.decode() != path:
        raise ValueError("phase2-retained-regular-file-required:" + path)
    return subprocess.check_output(["git", "cat-file", "blob", oid.decode()], cwd=root)


def inspect(root):
    root = Path(root).resolve()
    request = json.loads((root / REQUEST).read_bytes())
    revision = request["details"]["executable_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("phase2-retained-exact-commit-required")
    if subprocess.run(["git", "merge-base", "--is-ancestor", revision, "HEAD"], cwd=root,
                      capture_output=True).returncode:
        raise ValueError("phase2-retained-commit-not-ancestor")
    raw = read_blob(root, revision, PLAN)
    if raw != (root / PLAN).read_bytes() or not any(
        s.get("path") == PLAN and s.get("commit") == revision and s.get("sha256") == sha(raw)
        for s in request["sources"]
    ):
        raise ValueError("phase2-retained-request-binding")
    plan = json.loads(raw)
    sealed(plan)
    if request["details"]["request_seal"] != plan["content_sha256"]:
        raise ValueError("phase2-retained-request-seal")
    if plan.get('schema') == 'posttran-phase2-plan/2':
        # Publication checks Git objects at the executable pin. The reserve
        # path still calls bound_plan() against the actual execution checkout.
        trees = ('src/lightyear_mainframe', 'src/carddemo_oracle', 'spec/mainframe',
                 'tests/mainframe/fixtures', 'tools/legacy_twin')
        inventory = set(subprocess.check_output(
            ['git', 'ls-tree', '-r', '--name-only', revision, '--', *trees],
            cwd=root, text=True).splitlines())
        inventory.update(('tools/prepare_posttran_phase2.py', 'tools/run_posttran_phase2.py',
            'tools/check_posttran_attempt1_phase1.py', 'tools/posttran_phase2_authorization.py',
            '.github/workflows/posttran-phase2.yml', 'docs/factory/keep-or-fix-register.json',
            'docs/factory/twin-limits.md'))
        if set(plan['bound_files']) != inventory:
            raise ValueError('phase2-retained-binding-inventory')
    else:
        original_raw = read_blob(root, revision, ORIGINAL)
        if original_raw != (root / ORIGINAL).read_bytes() or sha(original_raw) != plan["original_plan_sha256"]:
            raise ValueError("phase2-retained-original-binding")
        original = json.loads(original_raw)
        sealed(original)
        for key in ("candidate_files", "twin", "scenarios", "scenario_count", "compared_outputs",
                    "normalization_rules", "preparation_run"):
            if plan[key] != original[key]:
                raise ValueError("phase2-retained-preparation-changed:" + key)
    bindings = {**plan["bound_files"], **plan["candidate_files"]}
    drift = []
    for path, expected in sorted(bindings.items()):
        if sha(read_blob(root, revision, path)) != expected:
            raise ValueError("phase2-retained-bound-file-changed:" + path)
        current = root / path
        if (current.is_symlink() or not current.resolve().is_relative_to(root)
                or not current.is_file() or sha(current.read_bytes()) != expected):
            drift.append(path)
    return dict(schema="posttran-retained-plan-inspection/1", retained_commit=revision,
                validated_plan_sha256=plan["content_sha256"], validated_files=len(bindings),
                current_checkout_matches_plan=not drift, changed_bound_files=drift,
                execution_authorized=False,
                next_step="Execution still requires a matching plan, exact head and signed proof; execution-checkout drift requires a new reviewed plan; later main changes do not authorize execution.")


if __name__ == "__main__":
    print(json.dumps(inspect(Path(__file__).resolve().parents[1]), sort_keys=True))
