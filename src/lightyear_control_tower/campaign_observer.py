"""Pure projections over bounded read-only campaign artifacts. Never sign or repair."""

import hashlib
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .decisions import canonical, digest, verify_envelope
from .requests import read_json, read_bytes, identifier, confined

POLICY = {
    "version": 1,
    "budget_thresholds": [0.8, 1.0],
    "visible_poll_seconds": 3,
    "hidden_poll_seconds": 30,
}
ACCOUNTING_CACHE = "Accounting period cache is not bound to journey postings"


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
    if (
        error.get("type") == "BusinessViolation"
        and error.get("message", "").rstrip(".") == ACCOUNTING_CACHE
    ):
        failures.append(
            {
                "class": "accounting_cache",
                "origin": "unknown",
                "location": "combined-native-judge/accounting_cache",
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
    for d in diagnostics:
        if not isinstance(d, dict):
            continue
        frame = d.get("candidate_frame") or d.get("location") or {}
        if not isinstance(frame, dict):
            frame = {}
        origin = d.get("thrown_by", d.get("origin", "unknown"))
        if origin not in {
            "candidate",
            "support",
            "application",
            "equipment",
            "platform",
            "outside",
            "unknown",
        }:
            origin = "unknown"
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
            groups.setdefault(key, set()).add(t["id"])
            if origin not in {None, "candidate", "unknown"}:
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
    if not view["integrity"].get("verified"):
        add(
            "integrity",
            decision_kind="measurement-validity",
            details=view["integrity"].get("issues", []),
        )
    calendar = view.get("calendar", {})
    if calendar.get("clock_mode") in {
        "unmodified-real-time",
        "real-time-period-guarded",
    } and calendar.get("period_end_exclusive_utc"):
        end = datetime.fromisoformat(calendar["period_end_exclusive_utc"])
        remaining = max(
            0, view["limits"].get("seconds", 0) - view["used"].get("seconds", 0)
        )
        if now + timedelta(seconds=remaining) >= end:
            add("clock-boundary", decision_kind="measurement-validity")
    last = view.get("last_event_utc")
    if (
        last
        and not view.get("terminal")
        and (now - datetime.fromisoformat(last)).total_seconds()
        > view.get("per_trial_seconds", 7200)
    ):
        add("stale", observation_only=True)
    return output


class CampaignSource:
    family = "ms94-stage-b"

    def __init__(self, root, published, campaign, key, *, snapshot=None, policy=None):
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

    def project(self, campaign_id, *, now):
        records = {}
        issues = []
        signature_status = {}
        times = []

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
                    signature_status[
                        path.name
                        + ":"
                        + hashlib.sha256(str(path).encode()).hexdigest()[:12]
                    ] = ("verified" if "signature" in value and valid else "invalid")
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
                records[
                    path.name
                    + ":"
                    + hashlib.sha256(str(path).encode()).hexdigest()[:12]
                ] = hashlib.sha256(raw).hexdigest()
                for field in (
                    "recorded_at_utc",
                    "issued_at_utc",
                    "created_at_utc",
                    "started_at_utc",
                    "ended_at",
                    "finished_at",
                ):
                    if isinstance(value.get(field), str):
                        try:
                            dt = datetime.fromisoformat(value[field])
                            if dt.tzinfo:
                                times.append(dt.isoformat())
                        except ValueError:
                            pass
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
        if declared_snapshot and snapshot.get("content_sha256") != declared_snapshot:
            issues.append("snapshot-mismatch")
        if not declared_snapshot:
            issues.append("snapshot-binding-unavailable")
        if not snapshot:
            issues.append("snapshot-unavailable")
        if snapshot.get("files"):
            for name, sha in snapshot["files"].items():
                try:
                    # Streaming to bound memory even for large declared files.
                    with confined(self.root, name).open("rb") as f:
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
            receipt = load(folder / "receipt.json", signed=True) or load(
                self.published / "terminal/trials" / name / "receipt.json", signed=True
            )
            r = receipt or result
            status = r.get("status")
            if (
                receipt
                and result.get("receipt_sha256")
                and receipt["content_sha256"] != result["receipt_sha256"]
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
                                else "pending"
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
                    a.get("gate_sha256")
                    and gate.get("content_sha256") != a["gate_sha256"]
                ):
                    issues.append("gate-binding-mismatch:" + name)
                if projection.get("gate_sha256") and projection[
                    "gate_sha256"
                ] != gate.get("content_sha256"):
                    issues.append("diagnostic-gate-binding-mismatch:" + name)
                if not gate:
                    issues.append("native-gate-unavailable:" + name)
                failures.extend(closed_failures(gate, projection))
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
                for d in feedback.get("analyst_proposal", {}).get("decisions", []):
                    if d.get("reason") == "insufficient-type-evidence":
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
                    "calls": cost.get("client_invocations", 0),
                    "compilations": cost.get("compilations", 0),
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
        v = {
            "schema": "tower-campaign-view/1",
            "id": campaign_id,
            "family": self.family,
            "read_only": True,
            "terminal": terminal,
            "state": (
                "void"
                if void
                else "terminal" if terminal else "running" if active else "pending"
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
                ).get("calls", sum(t["calls"] for t in trials)),
                "compilations": (
                    None
                    if report.get("interrupted_slot")
                    else sum(t["compilations"] for t in trials)
                ),
                "seconds": report.get("elapsed_seconds"),
                "slots": sum(t["state"] not in {"pending", "not-run"} for t in trials),
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
                "journal_chain": "not-applicable-artifact-layout",
            },
            "calendar": plan.get("calendar", {}),
            "stop_rules": {k: v for k, v in plan.items() if k.startswith("stop_")},
            "decision_rules": plan.get("decision_rules", {}),
            "per_trial_seconds": plan.get("per_trial_elapsed_seconds", 7200),
            "last_event_utc": max(times) if times else None,
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
                    "content_sha256": legacy.get("content_sha256"),
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
        adapter = {
            "ms94-stage-b": CampaignSource,
            "ms94-equipment": EquipmentSource,
            "number-pilot": NumberSource,
        }[row["adapter"]]
        # Absolute source roots are LOCAL operator configuration only, never request input.
        path = self.root / "control-tower/policy.json"
        policy = (
            read_json(path).get("decision_console_observer", POLICY)
            if path.exists()
            else POLICY
        )
        if not isinstance(policy.get("version"), int) or policy.get(
            "budget_thresholds"
        ) != [0.8, 1.0]:
            raise ValueError("Unsupported observer policy")
        src = adapter(
            row["root"],
            row["published_directory"],
            row["work_directory"],
            Path(row["trusted_public_key"]).read_bytes(),
            snapshot=row.get("snapshot"),
            policy=policy,
        )
        return src.project(campaign_id, now=now)
