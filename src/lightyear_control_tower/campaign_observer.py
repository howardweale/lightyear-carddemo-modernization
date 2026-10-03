"""Pure projections over bounded read-only campaign artifacts. Never sign or repair."""

import hashlib
import json
import math
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .decisions import canonical, digest, verify_envelope, ZERO
from .fileio import regular_reader
from .requests import read_json, read_bytes, identifier, confined

POLICY = {
    "version": 1,
    "budget_thresholds": [0.8, 1.0],
    "visible_poll_seconds": 3,
    "hidden_poll_seconds": 30,
}


def utc_time(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, timezone.utc)
        if isinstance(value, str):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (
                result.replace(tzinfo=timezone.utc)
                if result.tzinfo is None
                else result.astimezone(timezone.utc)
            )
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return None


def origin_of(value):
    origin = value.get("thrown_by", value.get("origin", "unknown"))
    return (
        origin
        if origin
        in {
            "candidate",
            "support",
            "application",
            "equipment",
            "platform",
            "outside",
            "unknown",
        }
        else "unknown"
    )


def wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    width = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {
        "method": "Wilson",
        "confidence": 0.95,
        "lower": max(0, mid - width),
        "upper": min(1, mid + width),
    }


def journal_lines(path):
    """Incomplete trailing records are ignored, never truncated or 'repaired'."""
    import json

    raw = read_bytes(path)
    return [
        json.loads(line)
        for line in raw.splitlines(keepends=True)
        if line.endswith(b"\n") and line.strip()
    ]


def closed_failures(gate, projection):
    failures = []
    error = gate.get("error") or {}
    if isinstance(error, dict) and error:
        stage = error.get("stage", gate.get("stage"))
        identity = {
            "status": gate.get("status"),
            "type": error.get("type"),
            "stage": stage,
            "message_sha256": digest(error.get("message", "")),
        }
        failures.append(
            {
                "class": "gate-failure:" + digest(identity),
                "origin": (
                    origin_of(error)
                    if origin_of(error) != "unknown"
                    else origin_of(gate)
                ),
                "location": stage or "",
                "identity": identity,
            }
        )
    diagnostics = projection.get("diagnostics", [])
    if isinstance(diagnostics, dict):
        diagnostics = [
            d
            for values in diagnostics.values()
            if isinstance(values, list)
            for d in values
        ]
    if not isinstance(diagnostics, list):
        diagnostics = []
    for d in diagnostics:
        if not isinstance(d, dict):
            continue
        frame = d.get("candidate_frame") or d.get("location") or {}
        if not isinstance(frame, dict):
            frame = {}
        origin = origin_of(d)
        failures.append(
            {
                "class": d.get("category", d.get("kind", "unknown")),
                "origin": origin,
                "location": {
                    k: frame[k] for k in ("file", "method", "line") if k in frame
                },
            }
        )
    return failures


def alerts(view, *, now, policy=POLICY):
    output = []
    groups = {}

    def add(code, **fields):
        output.append(
            {
                "code": code,
                "policy_sha256": digest(policy),
                "changes_verdict": False,
                **fields,
            }
        )

    for t in view["trials"]:
        for f in t.get("failures", []):
            loc = f.get("location")
            origin = f.get("origin")
            key = (t["phase"], f.get("class"), canonical(loc).decode())
            if loc:
                groups.setdefault(key, set()).add(t["id"])
            if loc and origin not in {None, "candidate", "unknown"}:
                groups.setdefault((t["phase"], "origin:" + origin, ""), set()).add(
                    t["id"]
                )
            if origin in {"equipment", "support", "platform", "outside"}:
                add(
                    "equipment-origin",
                    trial=t["id"],
                    origin=origin,
                    decision_kind="measurement-validity",
                )
        if t.get("equipment_suspect"):
            add(
                "equipment-suspect", trial=t["id"], decision_kind="measurement-validity"
            )
        if t.get("gate_decline") == "insufficient-type-evidence" and any(
            f["class"] == "candidate-runtime-exception" for f in t.get("failures", [])
        ):
            add(
                "gate-decline-pattern",
                trial=t["id"],
                decision_kind="measurement-validity",
            )
    for (phase, cls, loc), ids in sorted(groups.items()):
        if len(ids) >= 2:
            add(
                "repeated-cause",
                phase=phase,
                diagnostic_class=cls,
                location=loc,
                trials=sorted(ids),
                decision_kind="measurement-validity",
            )
    for key, limit in view["limits"].items():
        if key not in {"calls", "compilations", "seconds"}:
            continue
        used = view["used"].get(key)
        if (
            isinstance(limit, (int, float))
            and limit > 0
            and isinstance(used, (int, float))
        ):
            for threshold in policy["budget_thresholds"]:
                if used >= limit * threshold:
                    add(
                        "budget",
                        budget=key,
                        threshold=threshold,
                        used=used,
                        limit=limit,
                    )
    invalid = [
        issue
        for issue in view["integrity"].get("issues", [])
        if "unavailable" not in issue
    ]
    if invalid:
        add(
            "integrity",
            decision_kind="measurement-validity",
            details=invalid,
        )
    now = utc_time(now.isoformat() if isinstance(now, datetime) else now)
    calendar = view.get("calendar") or {}
    end = utc_time(calendar.get("period_end_exclusive_utc"))
    limit = view["limits"].get("seconds")
    used = view["used"].get("seconds")
    if (
        now
        and end
        and calendar.get("clock_mode")
        in {"unmodified-real-time", "real-time-period-guarded"}
    ):
        if isinstance(limit, (int, float)) and isinstance(used, (int, float)):
            if now + timedelta(seconds=max(0, limit - used)) >= end:
                add("clock-boundary", decision_kind="measurement-validity")
    last = utc_time(view.get("last_event_utc"))
    if (
        now
        and last
        and not view.get("terminal")
        and (now - last).total_seconds() > (view.get("per_trial_seconds") or 7200)
    ):
        add("stale", observation_only=True)
    return output


class CampaignSource:
    family = "ms94-stage-b"

    def __init__(
        self,
        root,
        published,
        campaign,
        key,
        *,
        snapshot=None,
        policy=None,
        read_mode="live",
    ):
        self.root = Path(root).resolve()
        self.published = Path(published).resolve()
        self.campaign = Path(campaign).resolve()
        self.key = key
        self.snapshot = (
            Path(snapshot).resolve()
            if snapshot
            else self.root / "execution-snapshot.json"
        )
        self.policy = policy or POLICY
        if read_mode not in {"live", "immutable-export"}:
            raise ValueError("Unsupported campaign read mode")
        self.read_mode = read_mode

    def project(self, campaign_id, *, now):
        if os.name == "nt" and self.read_mode == "live":
            return unavailable_campaign(
                campaign_id, "live-windows-observation-unavailable-use-immutable-export"
            )
        try:
            return self._project(campaign_id, now=now)
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OSError,
            RecursionError,
        ):
            return unavailable_campaign(campaign_id)

    def _project(self, campaign_id, *, now):
        now = utc_time(now.isoformat() if isinstance(now, datetime) else now)
        records = {}
        issues = []
        signature_status = {}
        times = []

        def record_name(path):
            path = Path(path)
            for label, base in (
                ("root", self.root),
                ("published", self.published),
                ("campaign", self.campaign),
            ):
                if path.is_relative_to(base):
                    return label + "/" + path.relative_to(base).as_posix()
            return "snapshot/" + path.name

        def load(path, *, signed=False):
            if not path.exists():
                return {}
            try:
                raw = read_bytes(path)
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("Wrong record type")
                sha = value.get("content_sha256")
                valid = (
                    verify_envelope(value, self.key)
                    if "signature" in value
                    else sha
                    == digest({k: v for k, v in value.items() if k != "content_sha256"})
                )
                if signed or "signature" in value:
                    signature_status[record_name(path)] = (
                        "verified" if "signature" in value and valid else "invalid"
                    )
                if sha and not valid:
                    issues.append("record-hash-or-signature-invalid:" + path.name)
                if not sha and path.name in {
                    "plan.json",
                    "gate.json",
                    "execution-snapshot.json",
                }:
                    issues.append("record-hash-missing:" + path.name)
                if signed and "signature" not in value:
                    issues.append("missing-signature:" + path.name)
                records[record_name(path)] = hashlib.sha256(raw).hexdigest()
                for field in (
                    "recorded_at_utc",
                    "issued_at_utc",
                    "created_at_utc",
                    "started_at_utc",
                    "started_at",
                    "ended_at",
                    "finished_at",
                ):
                    dt = utc_time(value.get(field))
                    if dt:
                        times.append(dt)
                return value
            except (ValueError, OSError, TypeError):
                issues.append("incomplete-or-invalid-record:" + path.name)
                return {}

        plan = load(self.campaign / "plan.json") or load(self.published / "plan.json")
        declaration = (
            load(self.campaign / "executable-declaration.json", signed=True)
            or load(self.campaign / "declaration.json", signed=True)
            or load(self.published / "declaration.json", signed=True)
        )
        auth = load(self.campaign / "authorization.json", signed=True) or load(
            self.published / "authorization.json", signed=True
        )
        published_plan = load(self.published / "plan.json")
        snapshot = load(self.snapshot) or load(
            self.published / "execution-snapshot.json"
        )
        report = (
            load(self.campaign / "report.json", signed=True)
            or load(self.published / "terminal/report.json", signed=True)
            or load(self.published / "report.json", signed=True)
        )
        progress = load(self.campaign / "progress.json", signed=True) or load(
            self.published / "progress.json", signed=True
        )
        active = load(self.campaign / "active.json", signed=True)
        published_receipt = load(
            self.campaign / "published-executable.json", signed=True
        ) or load(self.campaign / "published-plan.json", signed=True)
        journal_status = "unavailable"
        journal_path = self.campaign / "events.jsonl"
        if journal_path.exists():
            try:
                raw = read_bytes(journal_path)
                records[record_name(journal_path)] = hashlib.sha256(raw).hexdigest()
                complete = [
                    json.loads(line)
                    for line in raw.splitlines(keepends=True)
                    if line.endswith(b"\n") and line.strip()
                ]
                if complete and all(
                    isinstance(e, dict) and "sequence" in e and "previous_sha256" in e
                    for e in complete
                ):
                    previous = ZERO
                    for index, event in enumerate(complete, 1):
                        if (
                            event["sequence"] != index
                            or event["previous_sha256"] != previous
                            or not verify_envelope(event, self.key)
                        ):
                            raise ValueError("Invalid journal chain")
                        previous = event["content_sha256"]
                        dt = utc_time(
                            event.get("occurred_at", event.get("recorded_at_utc"))
                        )
                        if dt:
                            times.append(dt)
                    journal_status = (
                        "verified-complete-prefix"
                        if raw and not raw.endswith(b"\n")
                        else "verified"
                    )
                elif complete and any(
                    isinstance(e, dict) and ("sequence" in e or "previous_sha256" in e)
                    for e in complete
                ):
                    raise ValueError("Incomplete journal chain fields")
            except (ValueError, OSError, TypeError, KeyError):
                journal_status = "invalid"
                issues.append("journal-chain-invalid")
        if not plan:
            issues.append("plan-unavailable")
        if not declaration:
            issues.append("declaration-unavailable")
        if not auth:
            issues.append("authorization-unavailable")
        for bound_record in (declaration, auth, report):
            if bound_record.get("plan_sha256") and bound_record[
                "plan_sha256"
            ] != plan.get("content_sha256"):
                issues.append("plan-binding-mismatch")
        # An executable campaign plan may explicitly bind a separate approved plan.
        matching_plan = plan.get("approved_plan_sha256", plan.get("content_sha256"))
        if published_plan and matching_plan != published_plan.get("content_sha256"):
            issues.append("published-plan-mismatch")
        if not published_plan:
            issues.append("published-plan-unavailable")
        declared_snapshot = auth.get(
            "snapshot_sha256", declaration.get("snapshot_sha256")
        )
        if (
            declared_snapshot
            and snapshot
            and snapshot.get("content_sha256") != declared_snapshot
        ):
            issues.append("snapshot-mismatch")
        if not declared_snapshot:
            issues.append("snapshot-binding-unavailable")
        if not snapshot:
            issues.append("snapshot-unavailable")
        if snapshot.get("files"):
            for name, sha in snapshot["files"].items():
                try:
                    # Streaming to bound memory even for large declared files.
                    with regular_reader(confined(self.root, name, internal=True)) as f:
                        actual = hashlib.file_digest(f, "sha256").hexdigest()
                    if actual != sha:
                        issues.append("frozen-input-mismatch")
                        break
                except (OSError, ValueError):
                    issues.append("frozen-input-unavailable")
                    break
        results = (report or progress).get("results", [])
        trials = []
        schedule = plan.get("slots", plan.get("schedule", results))
        for slot in schedule:
            phase = slot.get(
                "phase", "control" if self.family == "ms94-equipment" else "cohort"
            )
            idx = slot.get("index", slot.get("slot", len(trials) + 1))
            name = (
                f"{phase}-{int(idx):02d}"
                if isinstance(idx, int)
                else identifier(str(idx))
            )
            result = next(
                (
                    r
                    for r in results
                    if r.get("phase", phase) == phase
                    and r.get("index", r.get("slot")) == idx
                ),
                {},
            )
            trial_path = slot.get("path")
            folder = (
                confined(self.root, trial_path)
                if trial_path
                else self.campaign / "trials" / name
            )
            receipt = (
                load(folder / "receipt.json", signed=True)
                or load(
                    self.published / "terminal/trials" / name / "receipt.json",
                    signed=True,
                )
                or load(self.published / "trials" / name / "receipt.json", signed=True)
            )
            r = receipt or result
            status = r.get("status")
            if (
                receipt
                and result.get("receipt_sha256")
                and receipt.get("content_sha256") != result["receipt_sha256"]
            ):
                issues.append("trial-receipt-binding-mismatch:" + name)
            started = load(folder / "supervision-start.json") or load(
                folder / "started.json"
            )
            state = (
                "passed"
                if status == "passed"
                else (
                    "void"
                    if status and ("void" in status or "provenance" in status)
                    else (
                        "failed"
                        if status
                        else (
                            "not-run"
                            if report
                            else (
                                "running"
                                if active.get("phase") == phase
                                and active.get("index") == idx
                                else "pending" if active else "unavailable"
                            )
                        )
                    )
                )
            )
            interrupted = report.get("interrupted_slot") or {}
            if interrupted.get("phase") == phase and interrupted.get("index") == idx:
                state = "void"
            failures = []
            trace = []
            gate_decline = None
            equipment_suspect = bool(r.get("equipment_suspect"))
            attempts = r.get("attempts", [])
            if self.family == "ms94-equipment" and result.get("run_directory"):
                attempts = [result]
            for n, a in enumerate(attempts, 1):
                run = a.get("run_directory")
                if not run:
                    continue
                native = confined(self.root, run)
                gate = load(native / "gate.json")
                projection = load(native / "diagnostic-projection.json", signed=True)
                if (
                    gate
                    and a.get("gate_sha256")
                    and gate.get("content_sha256") != a["gate_sha256"]
                ):
                    issues.append("gate-binding-mismatch:" + name)
                if (
                    gate
                    and projection.get("gate_sha256")
                    and projection["gate_sha256"] != gate.get("content_sha256")
                ):
                    issues.append("diagnostic-gate-binding-mismatch:" + name)
                if not gate:
                    issues.append("native-gate-unavailable:" + name)
                failures.extend(closed_failures(gate, projection))
                equipment_suspect = equipment_suspect or bool(
                    projection.get("equipment_suspect")
                )
                # Public traces are explicitly named sanitized artifacts; never captures.
                t = load(native / "public-trace.json")
                trace.extend(
                    [
                        {
                            k: e[k]
                            for k in ("stage", "status", "elapsed_seconds")
                            if k in e
                        }
                        for e in t.get("events", [])
                        if isinstance(e, dict)
                    ]
                    if t.get("disclosure") == "public"
                    else []
                )
                feedback = load(folder / f"feedback-{n}.json", signed=True)
                for d in (feedback.get("analyst_proposal") or {}).get("decisions", []):
                    if (
                        d.get("disposition") == "reject"
                        and d.get("reason") == "insufficient-type-evidence"
                    ):
                        gate_decline = d["reason"]
            cost = r.get("cost", {})
            verdict = attempts[-1].get("result_class", status) if attempts else status
            trials.append(
                {
                    "id": name,
                    "phase": phase,
                    "index": idx,
                    "state": state,
                    "verdict": verdict,
                    "failures": failures,
                    "gate_decline": gate_decline,
                    "equipment_suspect": equipment_suspect,
                    "calls": cost.get("client_invocations"),
                    "compilations": cost.get("compilations"),
                    "start_utc": started.get("started_at_utc"),
                    "end_utc": r.get("finished_at"),
                    "trace": trace,
                    "receipt_sha256": r.get(
                        "content_sha256", result.get("receipt_sha256")
                    ),
                }
            )
        cohort = [t for t in trials if t["phase"] == "cohort"]
        terminal = bool(report)
        void = bool(report.get("cohort_void"))
        passed = sum(t["state"] == "passed" for t in cohort)
        completed = sum(t["state"] in {"passed", "failed"} for t in cohort)
        measured = terminal and not void and bool(cohort) and completed == len(cohort)
        campaign_start = next(
            (
                stamp
                for record in (progress, auth, active)
                if (
                    stamp := utc_time(
                        record.get("started_at", record.get("started_at_utc"))
                    )
                )
            ),
            None,
        )

        def recorded_cost(field):
            observed = [t for t in trials if t["state"] not in {"pending", "not-run"}]
            if any(t[field] is None for t in observed):
                return None
            return sum(t[field] for t in observed)

        v = {
            "schema": "tower-campaign-view/1",
            "id": campaign_id,
            "family": self.family,
            "read_only": True,
            "terminal": terminal,
            "state": (
                "void"
                if void
                else "terminal" if terminal else "running" if active else "unavailable"
            ),
            "plan_sha256": plan.get("content_sha256"),
            "declaration_sha256": declaration.get("content_sha256"),
            "snapshot_sha256": snapshot.get("content_sha256"),
            "authorization_sha256": auth.get("content_sha256"),
            "public_commit": published_receipt.get(
                "public_commit", published_receipt.get("commit")
            ),
            "limits": {
                "calls": plan.get("max_client_invocations", 0),
                "compilations": plan.get("max_compilations", 0),
                "seconds": plan.get("max_elapsed_seconds", 0),
                "slots": len(trials),
            },
            "used": {
                "calls": report.get(
                    "all_recorded_call_cost_including_interrupted_trial", {}
                ).get("calls", recorded_cost("calls")),
                "compilations": (
                    None
                    if report.get("interrupted_slot")
                    else recorded_cost("compilations")
                ),
                "seconds": (
                    report.get("elapsed_seconds")
                    if report
                    else (
                        max(0, (now - campaign_start).total_seconds())
                        if campaign_start
                        else None
                    )
                ),
                "slots": sum(
                    t["state"] in {"passed", "failed", "void"} for t in trials
                ),
            },
            "trials": trials,
            "totals": {
                "cohort_passed": passed,
                "cohort_completed": completed,
                "cohort_failed": sum(t["state"] == "failed" for t in cohort),
                "rate": passed / len(cohort) if measured else None,
                "wilson_95": wilson(passed, len(cohort)) if measured else None,
                "pilots_excluded": True,
            },
            "integrity": {
                "verified": not issues,
                "issues": sorted(set(issues)),
                "signatures": signature_status,
                "record_hashes": records,
                "journal_chain": journal_status,
            },
            "calendar": plan.get("calendar", {}),
            "stop_rules": {k: v for k, v in plan.items() if k.startswith("stop_")},
            "decision_rules": plan.get("decision_rules", {}),
            "per_trial_seconds": plan.get("per_trial_elapsed_seconds", 7200),
            "last_event_utc": max(times).isoformat() if times else None,
            "legacy_approvals": [],
            "controller_reads_tower_decisions": False,
            "observer_policy": self.policy,
        }
        legacy = load(self.published / "operator-adjudication.json")
        if legacy:
            v["legacy_approvals"] = [
                {
                    "label": "legacy: typed statement, not countersigned",
                    "signature_type": legacy.get("signature_type"),
                    "independent_review": False,
                    "content_sha256": hashlib.sha256(
                        read_bytes(self.published / "operator-adjudication.json")
                    ).hexdigest(),
                }
            ]
        if auth.get("operator_approval"):
            v["legacy_approvals"].append(
                {
                    "label": "legacy: typed statement, not countersigned",
                    "signature_type": "Typed operator approval embedded in campaign authorization",
                    "independent_review": False,
                    "authorization_sha256": auth.get("content_sha256"),
                }
            )
        v["alerts"] = alerts(v, now=now, policy=self.policy)
        v["content_sha256"] = digest(v)
        return v


class EquipmentSource(CampaignSource):
    family = "ms94-equipment"


class NumberSource(CampaignSource):
    family = "number-pilot"

    def project(self, campaign_id, *, now):
        if os.name == "nt" and self.read_mode == "live":
            return unavailable_campaign(
                campaign_id, "live-windows-observation-unavailable-use-immutable-export"
            )
        from lightyear_workflow.campaign_journals import exported
        from lightyear_workflow.campaign_engine import project as replay_projection

        auth = read_json(self.campaign / "authorization.json")
        if not verify_envelope(auth, self.key):
            raise ValueError("Invalid NUMBER authorization")
        events = read_json(self.campaign / "events.json")
        exported(events, auth, self.key)
        checked = replay_projection(self.root, auth, events)
        # Signed checkpointed exported journals, not a writable SQLite connection.
        public = [
            {
                "sequence": e["sequence"],
                "type": e["type"],
                "content_sha256": e["content_sha256"],
            }
            for e in events
        ]
        trials = []
        terminal = any(e["type"] == "terminal" for e in events)
        for row in checked["case_results"]:
            comparison = row["comparison"]
            state = (
                ("passed" if comparison["equivalent"] else "failed")
                if comparison
                else ("not-run" if terminal else "pending")
            )
            trials.append(
                {
                    "id": row["case_id"],
                    "phase": "control",
                    "state": state,
                    "verdict": (
                        ("equivalent" if comparison["equivalent"] else "divergent")
                        if comparison
                        else None
                    ),
                    "failures": (
                        []
                        if state != "failed"
                        else [
                            {
                                "class": "number-divergence",
                                "origin": "unknown",
                                "location": row["case_id"],
                            }
                        ]
                    ),
                    "trace": [],
                    "comparison_sha256": digest(comparison) if comparison else None,
                }
            )
        result = {
            "schema": "tower-campaign-view/1",
            "id": campaign_id,
            "family": self.family,
            "read_only": True,
            "events": public,
            "integrity": {"verified": True, "issues": [], "journal_chain": "verified"},
            "trials": trials,
            "terminal": terminal,
            "state": checked["status"],
            "evidence_class": checked["evidence_class"],
            "plan_sha256": auth["plan"]["plan_sha256"],
            "authorization_sha256": auth["content_sha256"],
            "limits": {"slots": len(trials)},
            "used": {"slots": checked["comparisons_completed"]},
            "totals": {
                "cohort_passed": 0,
                "cohort_completed": 0,
                "rate": None,
                "wilson_95": None,
                "controls_passed": checked["matched"],
                "pilots_excluded": True,
            },
            "last_event_utc": checked["last_event_at"],
            "controller_reads_tower_decisions": False,
        }
        result["alerts"] = alerts(result, now=now, policy=self.policy)
        result["content_sha256"] = digest(result)
        return result


class CampaignRegistry:
    def __init__(self, root, scope):
        self.root = Path(root)
        self.scope = scope

    def entries(self):
        p = self.root / "control-tower/campaigns.json"
        if not p.exists():
            return []
        value = read_json(p)
        return [r for r in value["campaigns"] if r.get("scope") == self.scope]

    def view(self, campaign_id, *, now):
        row = next((r for r in self.entries() if r["id"] == campaign_id), None)
        if row is None:
            raise KeyError("Unknown campaign in this scope")
        try:
            return self._view(row, campaign_id, now=now)
        except ValueError as exc:
            # Closed issue code only; never expose arbitrary paths or exception text.
            if str(exc) == "export-sequence-gap":
                return unavailable_campaign(campaign_id, "export-sequence-gap")
            return unavailable_campaign(campaign_id)
        except (
            KeyError,
            TypeError,
            OSError,
            AttributeError,
            RecursionError,
        ):
            return unavailable_campaign(campaign_id)

    def _view(self, row, campaign_id, *, now):
        if row["adapter"] == "tower-status-export":
            from .status_export import project_exports

            if row.get("read_mode") != "write-once-status":
                raise ValueError("Status exports require the write-once adapter")
            args = (
                row["export_directory"],
                read_bytes(Path(row["trusted_public_key"])),
                campaign_id,
                row["bindings"],
                now,
            )
            if row.get("producer_profile") == "ms94-b06":
                from .b06 import project_exports as project_b06, SCOPE

                if self.scope != SCOPE:
                    raise ValueError("B06 scope mismatch")
                return project_b06(*args)
            return project_exports(
                *args, scope=self.scope, profile=row.get("producer_profile")
            )
        adapter = {
            "ms94-stage-b": CampaignSource,
            "ms94-equipment": EquipmentSource,
            "number-pilot": NumberSource,
        }[row["adapter"]]
        # Absolute source roots are LOCAL operator configuration only, never request input.
        path = self.root / "control-tower/decision-console-policy.json"
        policy = read_json(path) if path.exists() else POLICY
        if not isinstance(policy.get("version"), int) or policy.get(
            "budget_thresholds"
        ) != [0.8, 1.0]:
            raise ValueError("Unsupported observer policy")
        src = adapter(
            row["root"],
            row["published_directory"],
            row["work_directory"],
            read_bytes(Path(row["trusted_public_key"])),
            snapshot=row.get("snapshot"),
            policy=policy,
            read_mode=row.get("read_mode", "live"),
        )
        return src.project(campaign_id, now=now)


def unavailable_campaign(campaign_id, reason="campaign-records-unavailable"):
    value = {
        "schema": "tower-campaign-view/1",
        "id": campaign_id,
        "state": "unavailable",
        "read_only": True,
        "trials": [],
        "alerts": [],
        "limits": {},
        "used": {},
        "integrity": {
            "verified": False,
            "issues": [reason],
            "journal_chain": "unavailable",
        },
    }
    return {**value, "content_sha256": digest(value)}
