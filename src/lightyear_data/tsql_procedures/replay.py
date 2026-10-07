"""Offline authenticated capture replay. No subprocess, network or database code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from lightyear_control_tower.decisions import verify_envelope
from lightyear_data.contracts import seal
from .adapters import Coverage, Observation, coverage_gate
from .capture import state_changes
from .comparison import compare_observations

MAX_FILE_BYTES = 256 * 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{64}$")


class ReplayFailure(ValueError):
    pass


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReplayFailure("duplicate-json-key")
            result[key] = value
        return result
    def nonfinite(_):
        raise ReplayFailure("nonfinite-json")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ReplayFailure("evidence-file-too-large")
    return raw, json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def observation(value):
    expected = set(Observation.__dataclass_fields__)
    if not isinstance(value, dict) or set(value) != expected:
        raise ReplayFailure("observation-contract")
    args = dict(value)
    c = args["coverage"]
    if c is not None:
        if set(c) != set(Coverage.__dataclass_fields__):
            raise ReplayFailure("coverage-contract")
        args["coverage"] = Coverage(**c)
    result = Observation(**args)
    result.validate()
    return result


def replay(directory, trusted_public_key, expected_manifest_sha256):
    """Authenticate a private directory of retained native observations.

    A signed manifest is a claim by its configured evidence signer, not an
    independent witness that a database ran. Coverage/mapping qualification is
    not implemented yet, so this cannot issue an equivalence certificate.
    """
    directory = Path(directory).resolve()
    _, manifest = read_json(directory / "manifest.json")
    if (manifest.get("schema") != "tsql-capture-manifest/1"
            or manifest.get("content_sha256") != expected_manifest_sha256
            or not verify_envelope(manifest, trusted_public_key)):
        raise ReplayFailure("manifest-signature-or-binding")
    if manifest.get("model_calls") != 0:
        raise ReplayFailure("not-zero-model")
    files = manifest.get("files")
    required = {lane + "-" + kind + ".json"
                for lane in ("source", "target")
                for kind in ("before", "after", "observation")}
    if not isinstance(files, dict) or set(files) != required:
        raise ReplayFailure("capture-file-closure")
    loaded = {}
    for name, expected in files.items():
        if not isinstance(expected, str) or not SHA.fullmatch(expected):
            raise ReplayFailure("file-hash-shape")
        path = directory / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory):
            raise ReplayFailure("capture-path")
        raw, loaded[name] = read_json(path)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ReplayFailure("capture-file-changed")
    if {p.name for p in directory.iterdir()} != required | {"manifest.json"}:
        raise ReplayFailure("unlisted-evidence-file")
    lanes = {}
    for lane in ("source", "target"):
        obs = observation(loaded[lane + "-observation.json"])
        changes = state_changes(loaded[lane + "-before.json"], loaded[lane + "-after.json"])
        # JSON arrays replace tuples during serialization; compare canonical JSON.
        if json.dumps(obs.side_effects, sort_keys=True) != json.dumps(changes, sort_keys=True):
            raise ReplayFailure("side-effect-replay-differs")
        lanes[lane] = obs
    comparison = compare_observations(lanes["source"], lanes["target"],
                                      trap_family=manifest["trap_family"])
    coverage = coverage_gate(lanes["source"].coverage, lanes["target"].coverage)
    return seal({
        "schema": "tsql-offline-replay/1",
        "manifest_sha256": expected_manifest_sha256,
        "signature_verified": True, "capture_hashes_verified": True,
        "side_effects_recomputed": True, "comparison": comparison,
        "coverage": coverage, "verdict": "insufficient-evidence",
        "limitations": [
            "native-reset-and-cleanup-admission-pending",
            "cross-engine-mapping-admission-pending",
            "coverage-collector-qualification-pending",
        ],
        "model_calls": 0, "database_calls": 0,
    })
