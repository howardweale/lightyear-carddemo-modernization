"""Campaign-neutral signed, immutable status transport. No process operations."""

import ctypes
import json
import math
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .decisions import ZERO, canonical, digest, verify_envelope
from .requests import SHA, identifier, read_json
from .verification import check

SCHEMA = "tower-status-export/1"
STATES = {"ready", "running", "paused", "completed", "stopped", "void"}


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    check(
        result.tzinfo is not None and result.utcoffset() == timedelta(0), "utc-required"
    )
    return result


def rename_new(source, destination):
    """Atomic rename with OS-enforced no-replace semantics; no unsafe fallback."""
    if os.name == "nt":
        os.rename(source, destination)  # Windows refuses an existing destination.
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        fn = libc.renameat2
        fn.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        fn.restype = ctypes.c_int
        result = fn(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    elif sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        fn = libc.renamex_np
        fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        fn.restype = ctypes.c_int
        result = fn(os.fsencode(source), os.fsencode(destination), 4)
    else:
        raise OSError("Exclusive atomic rename is unavailable")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def atomic_new(path, value):
    path = Path(path)
    check(
        not any(p.is_symlink() for p in (path, *path.parents)), "export-symlink-refused"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".pending")
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        rename_new(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_status(value):
    fields = {
        "schema",
        "scope",
        "campaign_id",
        "profile",
        "sequence",
        "previous_sha256",
        "at_utc",
        "bindings",
        "state",
        "active_trial",
        "limits",
        "used",
        "fixture",
        "details",
    }
    check(
        set(value) - {"signature", "content_sha256"} == fields, "status-fields-invalid"
    )
    check(value["schema"] == SCHEMA, "status-schema-invalid")
    for name in ("scope", "campaign_id", "profile"):
        identifier(value[name])
    check(
        value["state"] in STATES and type(value["fixture"]) is bool,
        "status-state-invalid",
    )
    check(
        type(value["sequence"]) is int
        and 0 < value["sequence"] <= 999999
        and SHA.fullmatch(value["previous_sha256"]),
        "status-sequence-invalid",
    )
    utc(value["at_utc"])
    check(
        isinstance(value["bindings"], dict) and value["bindings"],
        "status-bindings-invalid",
    )
    for name, sha in value["bindings"].items():
        identifier(name)
        check(isinstance(sha, str) and SHA.fullmatch(sha), "status-bindings-invalid")
    limits, used = value["limits"], value["used"]
    check(
        isinstance(limits, dict)
        and isinstance(used, dict)
        and set(limits) == set(used),
        "budget-fields-invalid",
    )
    for name, limit in limits.items():
        identifier(name)
        check(
            type(limit) in (int, float)
            and math.isfinite(limit)
            and limit > 0
            and type(used[name]) in (int, float)
            and math.isfinite(used[name])
            and used[name] >= 0,
            "budget-values-invalid",
        )
    active = value["active_trial"]
    if active is not None:
        check(
            isinstance(active, dict)
            and "id" in active
            and set(active) <= {"id", "journey", "phase"},
            "active-fields-invalid",
        )
        for label in active.values():
            identifier(label)
        check(value["state"] in {"running", "paused"}, "active-state-invalid")
    check(isinstance(value["details"], dict), "status-details-invalid")


class StatusWriter:
    def __init__(
        self, directory, sign, key, *, scope, profile="generic", validator=None
    ):
        identifier(scope)
        identifier(profile)
        self.directory, self.sign, self.key = Path(directory), sign, key
        self.scope, self.profile, self.validator = scope, profile, validator
        check(
            not self.directory.exists() or not list(self.directory.iterdir()),
            "export-writer-already-started",
        )
        self.sequence, self.previous = 0, ZERO

    def emit(self, payload):
        value = json.loads(
            canonical(
                {
                    **payload,
                    "schema": SCHEMA,
                    "scope": self.scope,
                    "profile": self.profile,
                    "sequence": self.sequence + 1,
                    "previous_sha256": self.previous,
                }
            )
        )
        validate_status(value)
        if self.validator:
            self.validator(value)
        signed = self.sign(value)
        check(verify_envelope(signed, self.key), "producer-signature-invalid")
        atomic_new(self.directory / f'{value["sequence"]:06}.json', signed)
        self.sequence += 1
        self.previous = signed["content_sha256"]
        return signed


def read_exports(
    directory,
    key,
    campaign_id,
    bindings,
    *,
    scope,
    profile=None,
    validator=None,
    transition=None,
):
    directory = Path(directory)
    check(
        not any(p.is_symlink() for p in (directory, *directory.parents)),
        "export-directory-symlink",
    )
    # One directory snapshot: a concurrently renamed next file appears next poll.
    entries = list(directory.iterdir())
    names = []
    for path in entries:
        if path.name.startswith(".") and path.name.endswith(".pending"):
            continue
        check(
            re.fullmatch(r"\d{6}\.json", path.name) is not None,
            "unexpected-export-file",
        )
        names.append(path)
    names.sort()
    check(0 < len(names) <= 10000, "exports-unavailable-or-excessive")
    previous, last = ZERO, None
    for seq, path in enumerate(names, 1):
        check(path.name == f"{seq:06}.json", "export-sequence-gap")
        value = read_json(path)
        validate_status(value)
        check(verify_envelope(value, key), "export-signature-invalid")
        check(
            value["sequence"] == seq and value["previous_sha256"] == previous,
            "export-chain-invalid",
        )
        check(
            value["campaign_id"] == campaign_id
            and value["bindings"] == bindings
            and value["scope"] == scope
            and (profile is None or value["profile"] == profile),
            "export-campaign-mismatch",
        )
        if validator:
            validator(value)
        if last:
            check(utc(value["at_utc"]) >= utc(last["at_utc"]), "export-time-regressed")
            check(
                value["profile"] == last["profile"]
                and value["limits"] == last["limits"]
                and value["fixture"] == last["fixture"],
                "export-policy-changed",
            )
            check(
                all(value["used"][k] >= last["used"][k] for k in last["used"]),
                "budget-regressed",
            )
            if transition:
                transition(last, value)
        previous, last = value["content_sha256"], value
    return last


def freshness(value, now):
    now = utc(now.isoformat())
    check(utc(value["at_utc"]) <= now + timedelta(seconds=5), "export-from-future")
    return bool(
        value["active_trial"]
        and value["state"] in {"running", "paused"}
        and (now - utc(value["at_utc"])).total_seconds() >= 2700
    )


def project_exports(directory, key, campaign_id, bindings, now, *, scope, profile=None):
    value = read_exports(
        directory, key, campaign_id, bindings, scope=scope, profile=profile
    )
    stale = freshness(value, now)
    result = {
        "schema": "tower-campaign-view/1",
        "id": campaign_id,
        "family": value["profile"],
        "status_export_schema": SCHEMA,
        "state": value["state"],
        "read_only": True,
        "fixture": value["fixture"],
        "stale": stale,
        "last_event_utc": value["at_utc"],
        "active_trial": value["active_trial"],
        "limits": value["limits"],
        "used": value["used"],
        "trials": [],
        "controller_reads_tower_decisions": False,
        "alerts": (
            [{"code": "stale", "observation_only": True, "changes_verdict": False}]
            if stale
            else []
        ),
        "integrity": {
            "verified": True,
            "issues": [],
            "sequence": value["sequence"],
            "last_export_sha256": value["content_sha256"],
            "journal_chain": "verified immutable export prefix",
            "private_capture_replay_claimed": False,
        },
    }
    # Profile details are never exposed by the generic projection.
    result["content_sha256"] = digest(result)
    return result
