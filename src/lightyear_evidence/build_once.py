"""Digest-bound build-once bytes and saved consumer replay; no launch authority.

Callers pin the manifest digest through their own trusted channel. A digest is
integrity evidence, not a signature or proof that a process ran. Native command,
loader and provenance checks belong to the target adapter.
"""
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(value):
    require("content_sha256" not in value, "already-sealed")
    return dict(value, content_sha256=digest(value))


def verify_seal(value, reason="manifest-hash"):
    require(value.get("content_sha256") == digest({k: v for k, v in value.items() if k != "content_sha256"}), reason)


def descriptor(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def compare_package(base, current, replacements=None, *, missing="replacement-missing",
                    changed="replacement-bytes", different="shared-content-differs"):
    """Only explicitly named entries may differ; all metadata stays exact."""
    left, right = copy.deepcopy(base), copy.deepcopy(current)
    for name, expected in (replacements or {}).items():
        require(name in left["entries"] and name in right["entries"], missing)
        actual = right["entries"].pop(name)
        left["entries"].pop(name)
        require(actual == expected, changed)
    require(left == right, different)
    return True


def verify_consumer_states(states, manifest_sha256, consumer, *, reason="consumer-pre-post-binding"):
    require(len(states) == 2, reason)
    for state in states:
        require(state == dict(manifest_sha256=manifest_sha256, variant=consumer, verified=True), reason)


def _file(root, name):
    require(isinstance(name, str) and bool(name) and "\\" not in name and ":" not in name,
            "artifact-path")
    rel = PurePosixPath(name)
    require(not rel.is_absolute() and ".." not in rel.parts, "artifact-path")
    path = root.joinpath(*rel.parts)
    require(path.resolve().is_relative_to(root.resolve()), "artifact-path")
    require(all(not p.is_symlink() for p in (path, *path.parents) if p != root.parent), "artifact-symlink")
    require(path.is_file(), "artifact-missing:" + name)
    return path


def replay_saved(root, manifest, expected_manifest_sha256):
    """Verify saved public outputs against a pinned contract, without execution."""
    root = Path(root)
    verify_seal(manifest)
    require(manifest["content_sha256"] == expected_manifest_sha256, "manifest-binding")
    require(manifest["schema"] == "build-once-consumer-contract/1", "contract-schema")
    for name, expected in manifest["shared_files"].items():
        require(descriptor(_file(root, name).read_bytes()) == expected, "shared-artifact-changed:" + name)
    results = {}
    for consumer, spec in manifest["consumers"].items():
        prefix = spec["directory"]
        candidate = prefix + "/" + spec["candidate_file"]
        require(descriptor(_file(root, candidate).read_bytes()) == spec["candidate"], "candidate-bytes")
        record = json.loads(_file(root, prefix + "/execution.json").read_bytes())
        verify_seal(record, "execution-hash")
        require(record["manifest_sha256"] == expected_manifest_sha256 and record["consumer"] == consumer,
                "execution-binding")
        require(record["argv"] == spec["argv"] and record["returncode"] == spec["returncode"], "consumer-command-or-exit")
        require(record["shared_before"] == record["shared_after"] == manifest["shared_files"], "shared-pre-post")
        require(record["candidate_before"] == record["candidate_after"] == spec["candidate"], "candidate-pre-post")
        for stream in ("stdout", "stderr"):
            actual = descriptor(_file(root, prefix + "/" + stream + ".txt").read_bytes())
            require(actual == record[stream] == spec[stream], "consumer-output:" + stream)
        states = [json.loads(_file(root, prefix + "/" + when + ".json").read_bytes()) for when in ("before", "after")]
        verify_consumer_states(states, expected_manifest_sha256, consumer)
        results[consumer] = dict(replayed=True, execution_sha256=record["content_sha256"])
    require(bool(results), "consumers-required")
    return dict(manifest_sha256=expected_manifest_sha256, consumers=results,
                claim="Saved-output integrity replay only; no native admission or qualification")
