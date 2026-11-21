"""CI-produced MS70 evidence; historical artifacts are never projected or rewritten."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable

from lightyear_common.io import normalize_logical_source
from .contracts import canonical_bytes, content_hash, seal

BASE = "factory/idempiere-divergence-audit/"
DESCRIPTOR = "docs/factory/ms70-current-source-evidence-2026-11-02.json"
HISTORY = (
    (BASE + "stage3-retained-rebinding-2026-10-27.json",
     "eb3e3658f44d3eab2b3816fcc6a5af7b422e8325"),
    (BASE + "stage3-retained-rebinding-2026-10-28.json",
     "cbadaaaed06448924e00a01b4f6fa2042f70ddbd"),
)
ORIGINAL_NAMES = (
    "stage3-work-package.json", "stage3-calibration.json", "stage4-coverage.json",
    "stage4-divergence-register.json", "stage4-indeterminate-register.json",
    "stage4-provenance-register.json", "stage4.receipt.json",
)
SOURCE_FILES = (
    "src/lightyear_data/idempiere_triage.py",
    "src/lightyear_data/idempiere_comparison.py",
    "src/lightyear_data/contracts.py", "src/lightyear_common/io.py",
    "src/lightyear_factory/contracts.py", "src/lightyear_factory/providers.py",
    "src/lightyear_data/idempiere_divergence.py",
    "src/lightyear_data/idempiere_sql.py", "src/lightyear_data/semantic_core.py",
)
BOUND_FILES = (
    ".github/workflows/verify.yml",
    "data-modernization/schema/idempiere-dialect-pairing-manifest.schema.json",
    "data-modernization/schema/idempiere-divergence-stage1-receipt.schema.json",
    "data-modernization/schema/idempiere-semantic-comparison.schema.json",
    "data-modernization/schema/idempiere-triage.schema.json",
    "data-modernization/semantic-core/database-semantic-core.json",
    "docs/factory/ms70-current-source-evidence-2026-11-02.json",
    "factory/idempiere-divergence-audit/comparison-policy.json",
    "factory/idempiere-divergence-audit/pairing-manifest.json",
    "factory/idempiere-divergence-audit/stage1.receipt.json",
    "factory/idempiere-divergence-audit/stage2-comparison.json",
    "factory/idempiere-divergence-audit/stage2-pilot.json",
    "factory/idempiere-divergence-audit/stage2.receipt.json",
    "factory/idempiere-divergence-audit/stage3-calibration.json",
    "factory/idempiere-divergence-audit/stage3-retained-rebinding-2026-10-27.json",
    "factory/idempiere-divergence-audit/stage3-retained-rebinding-2026-10-28.json",
    "factory/idempiere-divergence-audit/stage3-work-package.json",
    "factory/idempiere-divergence-audit/stage4-coverage.json",
    "factory/idempiere-divergence-audit/stage4-divergence-register.json",
    "factory/idempiere-divergence-audit/stage4-indeterminate-register.json",
    "factory/idempiere-divergence-audit/stage4-provenance-register.json",
    "factory/idempiere-divergence-audit/stage4.receipt.json",
    "factory/idempiere-divergence-audit/triage-policy.json",
    "reference-estates/idempiere/business-slices.json",
    "reference-estates/idempiere/inventory.json",
    "reference-estates/idempiere/source-pin.json",
    "src/lightyear_common/io.py",
    "src/lightyear_data/contracts.py",
    "src/lightyear_data/idempiere_comparison.py",
    "src/lightyear_data/idempiere_divergence.py",
    "src/lightyear_data/idempiere_sql.py",
    "src/lightyear_data/idempiere_triage.py",
    "src/lightyear_data/ms70_current_evidence.py",
    "src/lightyear_data/semantic_core.py",
    "src/lightyear_factory/contracts.py",
    "src/lightyear_factory/providers.py",
    "tests/test_idempiere_triage.py",
    "tests/test_ms70_current_evidence.py",
    "tests/test_ms70_retained_rebinding.py",
    "tests/test_ms70_retained_successor.py",
    "tools/ci_test_execution.py",
    "verify.ps1",
    "verify.sh",
)
OUTPUT = Path("work/ci/test-execution/ms70-current-source")
CLAIMS = dict(deterministic_current_source_reproduced=True, native_execution=False,
              live_model_triage_complete=False, audit_complete=False,
              application_equivalence=False, production_ready=False,
              model_calls=0, builder_calls=0)
MAX_JSON_BYTES = 32 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "MS70 duplicate JSON member")
        result[key] = value
    return result


def _decode(raw):
    require(len(raw) <= MAX_JSON_BYTES, "MS70 JSON size limit")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)


def _file(root, relative):
    require(isinstance(relative, str) and relative and
            not Path(relative).is_absolute() and "\\" not in relative and ":" not in relative and
            all(part not in ("", ".", "..") for part in relative.split("/")),
            "MS70 unsafe relative path")
    root = Path(root).resolve()
    path = root
    for part in relative.split("/"):
        path = path / part
        require(not path.is_symlink(), "MS70 symlink refused")
    require(path.resolve().is_relative_to(root), "MS70 path escaped root")
    return path


def _json_file(root, relative):
    path = _file(root, relative)
    require(path.is_file() and path.stat().st_size <= MAX_JSON_BYTES,
            "MS70 missing or oversized evidence")
    return _decode(path.read_bytes())


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   stderr=subprocess.PIPE)


@lru_cache(maxsize=32)
def _historic_blob(root, commit, relative):
    # Cache immutable Git objects only, never a working file or parsed caller input.
    return _git(root, "show", commit + ":" + relative)


def _context(root):
    require(os.environ.get("GITHUB_ACTIONS") == "true", "MS70 production is CI-only")
    require(os.environ.get("GITHUB_REPOSITORY") ==
            "howardweale/lightyear-carddemo-modernization", "MS70 wrong repository")
    checkout = _git(root, "rev-parse", "HEAD").decode().strip()
    require(re.fullmatch(r"[0-9a-f]{40}", checkout) is not None and
            checkout == os.environ.get("GITHUB_SHA"), "MS70 checkout identity mismatch")
    parents = _git(root, "show", "-s", "--format=%P", checkout).decode().split()
    kind = os.environ.get("GITHUB_EVENT_NAME")
    require(kind in ("pull_request", "push"), "MS70 unsupported CI event")
    event_path = Path(os.environ["GITHUB_EVENT_PATH"])
    require(event_path.stat().st_size <= MAX_JSON_BYTES, "MS70 event size limit")
    event = _decode(event_path.read_bytes())
    require(event.get("repository", {}).get("full_name") ==
            os.environ["GITHUB_REPOSITORY"], "MS70 event repository mismatch")
    candidate = event.get("pull_request", {}).get("head", {}).get("sha")
    if kind == "pull_request":
        require(isinstance(candidate, str) and
                re.fullmatch(r"[0-9a-f]{40}", candidate) is not None and
                (checkout == candidate or len(parents) == 2 and parents[1] == candidate),
                "MS70 candidate identity mismatch")
    else:
        require(event.get("ref") == "refs/heads/main" and
                event.get("after") == checkout, "MS70 main event identity mismatch")
        candidate = checkout
    run_id, attempt, job = (os.environ.get(k, "") for k in
                           ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB"))
    require(run_id.isdecimal() and attempt.isdecimal() and int(attempt) > 0 and
            re.fullmatch(r"[A-Za-z0-9_-]+", job) is not None, "MS70 CI identity missing")
    return dict(checkout=checkout, tree=_git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
                parents=parents, candidate=candidate, event=kind, run_id=run_id,
                attempt=attempt, job=job, repository=os.environ["GITHUB_REPOSITORY"])


def input_fingerprints(root):
    result = {}
    for relative in BOUND_FILES:
        raw = _file(root, relative).read_bytes()
        result[relative] = dict(raw_sha256=sha(raw),
                               logical_sha256=sha(normalize_logical_source(raw)))
    return result


def verify_history(root, read: Callable):
    """Keep exact lineage, source identity, original bytes, and negative checks."""
    from . import idempiere_triage as triage
    root = Path(root).resolve()
    records = []
    for relative, commit in HISTORY:
        path = _file(root, relative)
        require(path.exists(), "MS70 retained rebinding identity mismatch: missing successor")
        _git(root, "merge-base", "--is-ancestor", commit, "HEAD")
        pinned_raw = _historic_blob(str(root), commit, relative)
        pinned = _decode(pinned_raw)
        record = read(path)
        require(normalize_logical_source(path.read_bytes()) ==
                normalize_logical_source(pinned_raw) and record == pinned and
                record.get("content_sha256") == content_hash(record),
                "MS70 rebinding predecessor or successor changed")
        require(record.get("schema") == "ms70-retained-rebinding/1" and
                record.get("evidence_kind") == "deterministic-binding-projection" and
                record.get("new_execution") is False and
                type(record.get("model_calls")) is int and record["model_calls"] == 0 and
                record.get("claims") == triage.CLAIMS and
                set(record.get("original_artifacts", {})) == set(ORIGINAL_NAMES) and
                set(record.get("projected_content_sha256", {})) == set(ORIGINAL_NAMES),
                "MS70 retained rebinding identity mismatch")
        identities = {p: sha(normalize_logical_source(
            _historic_blob(str(root), commit, p))) for p in triage.CODE_PATHS}
        require(record.get("implementation_logical_sha256") == identities,
                "MS70 retained rebinding source identity mismatch")
        records.append(record)
    predecessor = dict(path=HISTORY[0][0],
                       logical_sha256=sha(normalize_logical_source(
                           _file(root, HISTORY[0][0]).read_bytes())),
                       content_sha256=records[0]["content_sha256"])
    require(records[1].get("supersedes") == predecessor and
            records[1]["original_artifacts"] == records[0]["original_artifacts"],
            "MS70 rebinding successor lineage mismatch")
    originals = {}
    for name in ORIGINAL_NAMES:
        path = _file(root, BASE + name)
        original = read(path)
        pin = records[1]["original_artifacts"][name]
        require(sha(normalize_logical_source(path.read_bytes())) == pin["logical_sha256"] and
                original.get("content_sha256") == pin["content_sha256"] and
                content_hash(original) == pin["content_sha256"],
                "MS70 retained rebinding artifact mismatch: " + name)
        originals[name] = original
    originals["triage-policy.json"] = read(_file(root, BASE + "triage-policy.json"))
    return records, originals


def _descriptor(root):
    value = _json_file(root, DESCRIPTOR)
    require(value == dict(schema="ms70-current-source-production-plan/1",
                         date="2026-11-02", bound_files=list(BOUND_FILES),
                         historical_records=[p for p, _ in HISTORY],
                         production="CI-only; regenerate before full discovery",
                         historical_files="immutable",
                         evidence="new deterministic reproduction, not historical projection",
                         qualification="no native, model, equivalence or production claim",
                         authority=dict(merge=False, run=False, signing=False,
                                        spend=False, gap_acceptance=False)),
            "MS70 production descriptor changed")
    return value


def _load_bundle(root):
    pointer = _json_file(root, (OUTPUT / "current.json").as_posix())
    require(set(pointer) == {"filename", "sha256"}, "MS70 evidence pointer fields")
    filename = pointer["filename"]
    require(isinstance(filename, str) and re.fullmatch(
        r"ms70-current-source-\d{4}-\d{2}-\d{2}-[0-9a-f]{40}-\d+-\d+-[A-Za-z0-9_-]+\.json",
        filename) is not None, "MS70 evidence filename")
    path = _file(root, (OUTPUT / filename).as_posix())
    require(path.is_file() and path.stat().st_size <= MAX_JSON_BYTES,
            "MS70 missing current-source evidence")
    raw = path.read_bytes()
    require(sha(raw) == pointer["sha256"], "MS70 evidence pointer digest mismatch")
    return _decode(raw)


def verify_current(root, read=None):
    from . import idempiere_triage as triage
    root = Path(root).resolve()
    read = triage._read if read is None else read
    _descriptor(root)
    records, originals = verify_history(root, read)
    bundle = _load_bundle(root)
    require(set(bundle) == {"schema", "produced_at_utc", "context", "inputs",
                           "history", "artifacts", "artifact_hashes", "claims",
                           "content_sha256"}, "MS70 current-source fields")
    require(bundle["schema"] == "ms70-current-source-evidence/1" and
            bundle["content_sha256"] == content_hash(bundle) and
            canonical_bytes(bundle["claims"]) == canonical_bytes(CLAIMS), "MS70 current-source identity or claims")
    stamp = datetime.fromisoformat(bundle["produced_at_utc"])
    require(stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0,
            "MS70 evidence UTC timestamp")
    require(bundle["context"] == _context(root), "MS70 stale CI/checkout identity")
    before = input_fingerprints(root)
    require(bundle["inputs"] == before, "MS70 current-source input drift")
    require(bundle["history"] == [r["content_sha256"] for r in records],
            "MS70 current-source lineage mismatch")
    expected = triage.build_stage3_artifacts(root)
    require(canonical_bytes(bundle["artifacts"]) == canonical_bytes(expected), "MS70 current-source artifact drift")
    require(bundle["artifact_hashes"] == {n: content_hash(a) for n, a in expected.items()} and
            all(a.get("content_sha256") == content_hash(a) for a in bundle["artifacts"].values()),
            "MS70 current-source artifact hash mismatch")
    require(input_fingerprints(root) == before, "MS70 input changed during verification")
    return bundle, originals


def produce_and_verify(root):
    """Produce a fresh dated bundle in CI, then independently rebuild to verify it."""
    from . import idempiere_triage as triage
    root = Path(root).resolve()
    context = _context(root)
    _descriptor(root)
    records, _ = verify_history(root, triage._read)
    before = input_fingerprints(root)
    artifacts = triage.build_stage3_artifacts(root)
    require(input_fingerprints(root) == before, "MS70 input changed during production")
    now = datetime.now(timezone.utc)
    bundle = seal(dict(schema="ms70-current-source-evidence/1", produced_at_utc=now.isoformat(),
                       context=context, inputs=before,
                       history=[r["content_sha256"] for r in records],
                       artifacts=artifacts,
                       artifact_hashes={n: content_hash(a) for n, a in artifacts.items()},
                       claims=CLAIMS))
    filename = (f"ms70-current-source-{now.date()}-{context['checkout']}-"
                f"{context['run_id']}-{context['attempt']}-{context['job']}.json")
    output = _file(root, (OUTPUT / filename).as_posix())
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(bundle, sort_keys=True, indent=2) + "\n").encode("utf-8")
    with output.open("xb") as handle:
        handle.write(raw)
    pointer = _file(root, (OUTPUT / "current.json").as_posix())
    # The index is disposable CI output; dated evidence is create-only.
    pointer.write_text(json.dumps(dict(filename=filename, sha256=sha(raw))) + "\n",
                       encoding="utf-8")
    verified, _ = verify_current(root)
    require(verified == bundle, "MS70 production/readback mismatch")
    return dict(path=output.relative_to(root).as_posix(), sha256=sha(raw),
                content_sha256=bundle["content_sha256"], context=context,
                inputs=before, qualification=CLAIMS)
