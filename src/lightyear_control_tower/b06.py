"""B06 controller/Tower boundary. No model, native, process or Docker operations.

The producer writes closed immutable exports; the observer never opens mutable
controller files. Tower decisions authorize the controller, not process control.
"""

import hashlib
import math
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .decisions import ZERO, canonical, digest, verify_envelope
from .requests import read_json, identifier, SHA
from .verification import check, verify_decision, verify_journal

SCOPE = "ms94-b06"
SCHEMA = "b06-tower-status/1"
LAUNCH_FIELDS = {
    "campaign",
    "plan",
    "declaration",
    "limits",
    "public_commit",
    "executable",
    "template",
    "amendment",
}
PAUSE_FIELDS = {"campaign", "plan", "executable", "pause"}
REASONS = {
    "repeated-cause",
    "equipment-suspect",
    "provider-unavailable",
    "sealed-harness-defect",
}
STATES = {"ready", "running", "paused", "completed", "stopped", "void"}
TRIAL_STATES = {"passed", "failed", "equipment-suspect", "provider-unavailable", "void"}
LIMITS = {"calls": 390, "compilations": 234, "seconds": 345600}


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    check(
        result.tzinfo is not None and result.utcoffset() == timedelta(0), "utc-required"
    )
    return result


def hash_map(value, fields):
    check(
        set(value) == fields
        and all(isinstance(v, str) and SHA.fullmatch(v) for v in value.values()),
        "b06-bindings-invalid",
    )


def atomic_new(path, value):
    """Publish a closed file without replacing an existing name (also on POSIX)."""
    path = Path(path)
    check(
        not any(p.is_symlink() for p in (path, *path.parents)), "export-symlink-refused"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".pending")
    with temporary.open("xb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, path)  # Final name only appears after the file is closed.
    finally:
        temporary.unlink()


def validate_status(v):
    fields = {
        "schema",
        "scope",
        "campaign_id",
        "sequence",
        "previous_sha256",
        "at_utc",
        "bindings",
        "state",
        "active_trial",
        "pause",
        "limits",
        "used",
        "calendar",
        "trials",
        "fixture",
    }
    check(set(v) - {"signature", "content_sha256"} == fields, "status-fields-invalid")
    check(v["schema"] == SCHEMA and v["scope"] == SCOPE, "status-scope-invalid")
    identifier(v["campaign_id"])
    hash_map(v["bindings"], LAUNCH_FIELDS)
    check(v["state"] in STATES and type(v["fixture"]) is bool, "status-state-invalid")
    check(
        type(v["sequence"]) is int
        and v["sequence"] > 0
        and SHA.fullmatch(v["previous_sha256"]),
        "status-sequence-invalid",
    )
    utc(v["at_utc"])
    check(
        v["limits"] == LIMITS and set(v["used"]) == set(LIMITS), "budget-fields-invalid"
    )
    check(
        all(
            type(x) in (int, float) and math.isfinite(x) and x >= 0
            for x in v["used"].values()
        ),
        "budget-values-invalid",
    )
    cal = v["calendar"]
    check(
        set(cal) == {"clock_mode", "period_end_exclusive_utc", "latest_launch_utc"},
        "calendar-fields-invalid",
    )
    check(cal["clock_mode"] == "unmodified-real-time", "real-clock-required")
    check(
        utc(cal["latest_launch_utc"]) + timedelta(seconds=LIMITS["seconds"])
        < utc(cal["period_end_exclusive_utc"]),
        "latest-launch-crosses-period",
    )
    check(
        isinstance(v["trials"], list) and len(v["trials"]) <= 78, "trial-count-invalid"
    )
    ids = set()
    for trial in v["trials"]:
        check(
            set(trial)
            == {"id", "journey", "phase", "state", "fingerprints", "receipt_sha256"},
            "trial-fields-invalid",
        )
        identifier(trial["id"])
        check(trial["id"] not in ids, "duplicate-trial")
        ids.add(trial["id"])
        check(
            trial["journey"] in {"J1", "J2", "J3"}
            and trial["phase"] in {"pilot", "cohort"}
            and trial["state"] in TRIAL_STATES,
            "trial-state-invalid",
        )
        check(
            SHA.fullmatch(trial["receipt_sha256"])
            and isinstance(trial["fingerprints"], list)
            and len(trial["fingerprints"]) <= 100
            and all(SHA.fullmatch(f) for f in trial["fingerprints"]),
            "trial-evidence-invalid",
        )
    for journey in ("J1", "J2", "J3"):
        for phase, maximum in (("pilot", 2), ("cohort", 24)):
            check(
                sum(
                    t["journey"] == journey and t["phase"] == phase for t in v["trials"]
                )
                <= maximum,
                "journey-slot-cap",
            )
    active = v["active_trial"]
    if active is not None:
        check(set(active) == {"id", "journey", "phase"}, "active-fields-invalid")
        identifier(active["id"])
        check(
            active["id"] not in ids
            and active["journey"] in {"J1", "J2", "J3"}
            and active["phase"] in {"pilot", "cohort"},
            "active-trial-invalid",
        )
    if v["pause"] is not None:
        p = v["pause"]
        check(
            set(p) == {"sha256", "reasons", "request_id"}
            and SHA.fullmatch(p["sha256"]),
            "pause-fields-invalid",
        )
        check(p["reasons"] and set(p["reasons"]) <= REASONS, "pause-reasons-invalid")
        identifier(p["request_id"])
    check((v["state"] == "paused") == (v["pause"] is not None), "pause-state-invalid")


class StatusWriter:
    def __init__(self, directory, sign, key):
        self.directory = Path(directory)
        self.sign = sign
        self.key = key
        check(
            not self.directory.exists() or not list(self.directory.iterdir()),
            "export-writer-already-started",
        )
        self.sequence = 0
        self.previous = ZERO

    def emit(self, payload):
        value = json_load(
            canonical(
                {
                    **payload,
                    "schema": SCHEMA,
                    "scope": SCOPE,
                    "sequence": self.sequence + 1,
                    "previous_sha256": self.previous,
                }
            )
        )
        validate_status(value)
        signed = self.sign(value)
        check(verify_envelope(signed, self.key), "producer-signature-invalid")
        atomic_new(self.directory / f'{value["sequence"]:06}.json', signed)
        self.sequence += 1
        self.previous = signed["content_sha256"]
        return signed


def read_exports(directory, key, campaign_id, bindings):
    directory = Path(directory)
    check(
        not any(p.is_symlink() for p in (directory, *directory.parents)),
        "export-directory-symlink",
    )
    check(
        not any(
            p.suffix == ".json" and not re.fullmatch(r"\d{6}\.json", p.name)
            for p in directory.iterdir()
        ),
        "unexpected-export-file",
    )
    names = sorted(
        p for p in directory.iterdir() if re.fullmatch(r"\d{6}\.json", p.name)
    )
    check(0 < len(names) <= 10000, "exports-unavailable-or-excessive")
    previous = ZERO
    last = None
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
            value["campaign_id"] == campaign_id and value["bindings"] == bindings,
            "export-campaign-mismatch",
        )
        if last:
            check(utc(value["at_utc"]) >= utc(last["at_utc"]), "export-time-regressed")
            check(
                all(value["used"][k] >= last["used"][k] for k in LIMITS),
                "budget-regressed",
            )
            check(
                value["trials"][: len(last["trials"])] == last["trials"],
                "prior-verdict-changed",
            )
        previous = value["content_sha256"]
        last = value
    return last


def project_exports(directory, key, campaign_id, bindings, now):
    from .campaign_observer import wilson

    v = read_exports(directory, key, campaign_id, bindings)
    now = utc(now.isoformat())
    check(utc(v["at_utc"]) <= now + timedelta(seconds=5), "export-from-future")
    alerts = []

    def alert(code, **extra):
        alerts.append({"code": code, "changes_verdict": False, **extra})

    groups = {}
    for trial in v["trials"]:
        for f in set(trial["fingerprints"]):
            groups.setdefault((trial["journey"], f), set()).add(trial["id"])
        if trial["state"] in {"equipment-suspect", "provider-unavailable"}:
            alert(trial["state"], trial=trial["id"], journey=trial["journey"])
    for (journey, fingerprint), ids in sorted(groups.items()):
        if len(ids) > 1:
            alert(
                "repeated-cause",
                journey=journey,
                trials=sorted(ids),
                fingerprint=fingerprint,
            )
    if v["pause"]:
        for reason in v["pause"]["reasons"]:
            alert(reason, request_id=v["pause"]["request_id"])
    for budget, limit in LIMITS.items():
        for threshold in (0.8, 1):
            if v["used"][budget] >= limit * threshold:
                alert(
                    "budget",
                    budget=budget,
                    threshold=threshold,
                    used=v["used"][budget],
                    limit=limit,
                )
    if (
        v["active_trial"]
        and v["state"] in {"running", "paused"}
        and (now - utc(v["at_utc"])).total_seconds() > 2700
    ):
        alert("stale", observation_only=True)
    if v["state"] == "ready" and now > utc(v["calendar"]["latest_launch_utc"]):
        alert("latest-launch-expired")
    if now + timedelta(seconds=max(0, LIMITS["seconds"] - v["used"]["seconds"])) >= utc(
        v["calendar"]["period_end_exclusive_utc"]
    ):
        alert("clock-boundary")
    journeys = []
    for journey in ("J1", "J2", "J3"):
        rows = [
            t
            for t in v["trials"]
            if t["journey"] == journey
            and t["phase"] == "cohort"
            and t["state"] != "provider-unavailable"
        ]
        passed = sum(t["state"] == "passed" for t in rows)
        void = any(t["state"] == "void" for t in rows) or v["state"] == "void"
        journeys.append(
            {
                "id": journey,
                "cohort_completed": len(rows),
                "cohort_passed": passed,
                "planned": 24,
                "rate": passed / len(rows) if rows and not void else None,
                "wilson_95": wilson(passed, len(rows)) if not void else None,
                "void": void,
                "interim": len(rows) != 24,
            }
        )
    result = {
        "schema": "tower-campaign-view/1",
        "id": campaign_id,
        "family": "ms94-b06",
        "state": v["state"],
        "read_only": True,
        "fixture": v["fixture"],
        "controller_reads_tower_decisions": True,
        "last_event_utc": v["at_utc"],
        "trials": v["trials"],
        "journeys": journeys,
        "active_trial": v["active_trial"],
        "pause": v["pause"],
        "totals": {
            "cohort_completed": sum(j["cohort_completed"] for j in journeys),
            "cohort_passed": sum(j["cohort_passed"] for j in journeys),
            "pilots_excluded": True,
            "label": "Combined, equal weight by design; primary results are per journey",
        },
        "limits": v["limits"],
        "used": v["used"],
        "calendar": v["calendar"],
        "alerts": alerts,
        "integrity": {
            "verified": True,
            "issues": [],
            "journal_chain": "verified immutable export prefix",
            "last_export_sha256": v["content_sha256"],
            "sequence": v["sequence"],
            "private_capture_replay_claimed": False,
        },
        "plan_sha256": v["bindings"]["plan"],
        "declaration_sha256": v["bindings"]["declaration"],
        "snapshot_sha256": v["bindings"]["executable"],
    }
    result["content_sha256"] = digest(result)
    return result


def write_request(root, kind, artifacts):
    """Controller-side producer. Only explicit public review artifacts belong here."""
    fields = LAUNCH_FIELDS if kind == "campaign-authorization" else PAUSE_FIELDS
    check(
        kind in {"campaign-authorization", "b06-pause"} and set(artifacts) == fields,
        "request-fields-invalid",
    )
    bound = {}
    evidence = {}
    root = Path(root)
    for name, raw in artifacts.items():
        check(isinstance(raw, bytes), "exact-artifact-bytes-required")
        value = json_load(raw)
        sha = hashlib.sha256(raw).hexdigest()
        path = root / "evidence/b06" / f"{sha}.json"
        # Preserve original bytes, rather than silently canonicalizing reviewed evidence.
        check(canonical(value) == raw, "canonical-review-artifact-required")
        if path.exists():
            check(path.read_bytes() == raw, "review-artifact-changed")
        else:
            atomic_new(path, value)
        bound[name] = sha
        evidence[name] = path.relative_to(root).as_posix()
    request = {
        "schema": "tower-request/1",
        "scope": SCOPE,
        "kind": kind,
        "bound": bound,
        "evidence": evidence,
        "summary": (
            "B06 launch authorization"
            if kind == "campaign-authorization"
            else "B06 pause: continue, stop or void"
        ),
        "proposed_by": "b06-controller",
    }
    request["id"] = "b06-" + digest(request)
    path = root / "work/control-tower/requests" / SCOPE / (request["id"] + ".json")
    if not path.exists():
        atomic_new(path, request)
    return request["id"], {**bound, "request": digest(request)}


def json_load(raw):
    import json

    return json.loads(raw)


class DecisionReader:
    """Read fresh signed history over authenticated loopback; never submit decisions."""

    def __init__(self, client, credential, key):
        self.client = client
        self.credential = credential
        self.key = key

    def get(self, kind, bound, now):
        token = self.client.login(self.credential)["token"]
        try:
            journal = self.client._call("history", token)
            events = verify_journal(journal, self.key, scope=SCOPE)
            check(
                abs((now - utc(journal["exported_at"])).total_seconds()) < 60,
                "tower-history-not-fresh",
            )
            matches = [
                e
                for e in events
                if e["kind"] == "tower_decision"
                and e["payload"].get("kind") == kind
                and e["payload"].get("bound") == bound
            ]
            if not matches:
                return None
            proof = {
                "schema": "tower-decision-proof/1",
                "decision_sha256": matches[-1]["content_sha256"],
                "journal": journal,
            }
            verify_decision(
                proof,
                self.key,
                kind,
                bound,
                scope=SCOPE,
                expected_head=journal["journal_head_sha256"],
                now=now,
            )
            return proof
        finally:
            self.client.logout(token)


class B06TowerBoundary:
    """State-change hooks for the B06 controller; no measurement worker is provided.

    Call launch only after all admission/preflight checks. Emit used totals after
    each call/compile/state change. Feed verified terminal trial records to finish.
    """

    def __init__(
        self, writer, bindings, calendar, campaign_id="ms94-b06", fixture=False
    ):
        hash_map(bindings, LAUNCH_FIELDS)
        self.writer = writer
        self.started = None
        self.value = {
            "campaign_id": campaign_id,
            "bindings": dict(bindings),
            "calendar": dict(calendar),
            "state": "ready",
            "active_trial": None,
            "pause": None,
            "limits": dict(LIMITS),
            "used": dict.fromkeys(LIMITS, 0),
            "trials": [],
            "fixture": fixture,
        }
        self.pending_bound = None

    def emit(self, now):
        self.value["at_utc"] = now.isoformat()
        if self.started:
            self.value["used"]["seconds"] = (now - self.started).total_seconds()
        return self.writer.emit(self.value)

    def guard(self, now):
        check(
            now < utc(self.value["calendar"]["period_end_exclusive_utc"]),
            "accounting-period-closed",
        )
        if self.started:
            check(
                (now - self.started).total_seconds() < LIMITS["seconds"],
                "campaign-hard-deadline",
            )
        check(
            self.value["used"]["calls"] <= LIMITS["calls"]
            and self.value["used"]["compilations"] <= LIMITS["compilations"],
            "campaign-budget-exceeded",
        )

    def record_usage(self, calls, compilations, now):
        check(
            self.started is not None and self.value["state"] in {"running", "paused"},
            "usage-requires-live-campaign",
        )
        check(
            type(calls) is int
            and type(compilations) is int
            and calls >= self.value["used"]["calls"]
            and compilations >= self.value["used"]["compilations"],
            "usage-must-be-monotonic",
        )
        self.value["used"].update(calls=calls, compilations=compilations)
        self.guard(now)
        return self.emit(now)

    def launch(self, proof, key, bound, head, now, admit):
        check(
            self.started is None and self.value["state"] == "ready",
            "single-launch-only",
        )
        check(
            {k: bound.get(k) for k in LAUNCH_FIELDS} == self.value["bindings"]
            and set(bound) == LAUNCH_FIELDS | {"request"},
            "launch-binding-mismatch",
        )
        verify_decision(
            proof,
            key,
            "campaign-authorization",
            bound,
            scope=SCOPE,
            expected_head=head,
            outcomes={"authorized"},
            now=now,
        )
        check(
            now <= utc(self.value["calendar"]["latest_launch_utc"])
            and now + timedelta(seconds=LIMITS["seconds"])
            < utc(self.value["calendar"]["period_end_exclusive_utc"]),
            "latest-launch-refused",
        )
        check(admit() is True, "admission-refused")
        self.started = now
        self.value["state"] = "running"
        return self.emit(now)

    def start_trial(self, trial, now):
        self.guard(now)
        check(
            self.value["state"] == "running" and self.value["active_trial"] is None,
            "next-slot-paused-or-active",
        )
        check(
            self.value["used"]["calls"] < LIMITS["calls"]
            and self.value["used"]["compilations"] < LIMITS["compilations"],
            "no-next-slot-budget",
        )
        self.value["active_trial"] = dict(trial)
        return self.emit(now)

    def finish_trial(self, trial, now):
        self.guard(now)
        check(
            self.value["state"] == "running"
            and self.value["active_trial"]
            == {k: trial[k] for k in ("id", "journey", "phase")},
            "trial-binding-mismatch",
        )
        row = {**trial, "fingerprints": sorted(set(trial["fingerprints"]))}
        reasons = []
        if any(
            p["journey"] == row["journey"]
            and set(p["fingerprints"]) & set(row["fingerprints"])
            for p in self.value["trials"]
        ):
            reasons.append("repeated-cause")
        if row["state"] in {"equipment-suspect", "provider-unavailable"}:
            reasons.append(row["state"])
        self.value["trials"].append(row)
        self.value["active_trial"] = None
        self.emit(now)
        # The controller MUST call pause with a signed, exact pause record before
        # another slot; lock this boundary even before the inbox write completes.
        if reasons:
            self.value["state"] = "paused"
            self.pending_bound = {}
        return reasons

    def pause(self, request_bound, reasons, request_id, now):
        self.guard(now)
        check(
            self.started is not None
            and self.value["state"] in {"running", "paused"}
            and not self.pending_bound,
            "pause-cannot-replace-or-restart",
        )
        check(
            set(request_bound) == PAUSE_FIELDS | {"request"}
            and all(
                request_bound[k] == self.value["bindings"][k]
                for k in ("campaign", "plan", "executable")
            ),
            "pause-binding-mismatch",
        )
        self.pending_bound = dict(request_bound)
        self.value["state"] = "paused"
        self.value["pause"] = {
            "sha256": request_bound["pause"],
            "reasons": sorted(set(reasons)),
            "request_id": request_id,
        }
        return self.emit(now)

    def request_pause(self, review_root, artifacts, reasons, now):
        """Publish the producer-signed pause and its exact Tower inbox request."""
        self.guard(now)
        check(
            self.started is not None
            and self.value["state"] in {"running", "paused"}
            and not self.pending_bound,
            "pause-cannot-replace-or-restart",
        )
        check(bool(reasons) and set(reasons) <= REASONS, "pause-reasons-invalid")
        check(
            set(artifacts) == {"campaign", "plan", "executable"},
            "pause-artifact-fields",
        )
        check(
            all(
                hashlib.sha256(raw).hexdigest() == self.value["bindings"][k]
                for k, raw in artifacts.items()
            ),
            "pause-artifact-mismatch",
        )
        pause = self.writer.sign(
            {
                "schema": "b06-controller-pause/1",
                "scope": SCOPE,
                "campaign_id": self.value["campaign_id"],
                "at_utc": now.isoformat(),
                "previous_export_sha256": self.writer.previous,
                "reasons": sorted(set(reasons)),
                "bindings": {k: self.value["bindings"][k] for k in artifacts},
                "trial_receipt_sha256": (
                    self.value["trials"][-1]["receipt_sha256"]
                    if self.value["trials"]
                    else None
                ),
                "verdicts_changed": False,
                "review": "Operator review; not independent",
            }
        )
        check(verify_envelope(pause, self.writer.key), "pause-signature-invalid")
        atomic_new(
            self.writer.directory.parent
            / "tower-pauses"
            / (pause["content_sha256"] + ".json"),
            pause,
        )
        item, bound = write_request(
            review_root, "b06-pause", {**artifacts, "pause": canonical(pause)}
        )
        self.pause(bound, reasons, item, now)
        return item, bound

    def finish_and_review(self, trial, review_root, artifacts, now):
        reasons = self.finish_trial(trial, now)
        return (
            self.request_pause(review_root, artifacts, reasons, now)
            if reasons
            else None
        )

    def resolve(self, proof, key, head, now):
        self.guard(now)
        check(
            self.value["state"] == "paused" and self.pending_bound,
            "no-bound-current-pause",
        )
        p = verify_decision(
            proof,
            key,
            "b06-pause",
            self.pending_bound,
            scope=SCOPE,
            expected_head=head,
            outcomes={"continue", "stop", "void"},
            now=now,
        )
        self.value["state"] = {
            "continue": "running",
            "stop": "stopped",
            "void": "void",
        }[p["outcome"]]
        self.value["pause"] = None
        self.pending_bound = None
        self.emit(now)
        return p["outcome"]

    def poll_pause(self, reader, now):
        self.guard(now)
        check(
            self.value["state"] == "paused" and self.pending_bound,
            "no-bound-current-pause",
        )
        proof = reader.get("b06-pause", self.pending_bound, now)
        if proof is None:
            return None
        return self.resolve(
            proof, reader.key, proof["journal"]["journal_head_sha256"], now
        )


def register(root, export_directory, key_path, bindings, campaign_id="ms94-b06"):
    """Explicit local wiring, never an authority grant or a campaign launch."""
    from .requests import read_bytes

    root = Path(root).resolve()
    export_directory = Path(export_directory).resolve()
    key_path = Path(key_path).resolve()
    hash_map(bindings, LAUNCH_FIELDS)
    identifier(campaign_id)
    check(export_directory.name == "tower-export", "separate-export-directory-required")
    # Only register a producer whose first signed export is already available.
    read_exports(export_directory, read_bytes(key_path), campaign_id, bindings)
    config = {
        "schema": "tower-campaign-registry/1",
        "campaigns": [
            {
                "id": campaign_id,
                "scope": SCOPE,
                "adapter": "ms94-b06",
                "read_mode": "write-once-status",
                "export_directory": str(export_directory),
                "trusted_public_key": str(key_path),
                "bindings": bindings,
            }
        ],
    }
    atomic_new(root / "control-tower/campaigns.json", config)
    return {"registered": campaign_id, "scope": SCOPE, "process_started": False}


if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(
        description="Register a verified B06 status-export stream; never launch a campaign"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--producer-public-key", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            register(
                args.root,
                args.exports,
                args.producer_public_key,
                read_json(args.bindings),
            )
        )
    )
