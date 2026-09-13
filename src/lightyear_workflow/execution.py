"""Bounded headless CloudBank loop and read-only, replay-verified projections."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

from lightyear_data.contracts import content_hash, seal
from .artifacts import _atomic_write
from .cloudbank import BOUNDARY, SERVICES, action_for, build_execution_plan, observe, observed_status
from .execution_policy import permitted
from .policy import _unique_object
from .run_store import RunStore

RUN_PATH = Path("work/workflow/cloudbank")
EXAMPLE_PATH = Path("control-tower/cloudbank-execution.example.json")
FAILURES = {"worker-timeout", "worker-failed", "worker-output-limit", "interrupted"}


class WorkerFailure(ValueError):
    pass


def run_worker(root: Path, action: dict, policy: dict, timeout: float) -> dict:
    """No shell or supplied command. No credentials passed to the worker."""
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"}
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    command = [sys.executable, "-m", "lightyear_workflow.worker"]
    job = json.dumps({"root": str(root), "service": action["service"], "lane": action["lane"]}).encode()
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.PIPE,
                                   stdout=output, stderr=errors, start_new_session=os.name != "nt")
        deadline = time.monotonic() + timeout
        try:
            process.stdin.write(job)
            process.stdin.close()
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise WorkerFailure("worker-timeout")
                if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > policy["max_output_bytes"]:
                    raise WorkerFailure("worker-output-limit")
                time.sleep(0.02)
            if process.returncode:
                raise WorkerFailure("worker-failed")
            if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > policy["max_output_bytes"]:
                raise WorkerFailure("worker-output-limit")
            output.seek(0)
            try:
                return json.loads(output.read(), object_pairs_hook=_unique_object)
            except (ValueError, UnicodeError) as exc:
                raise ValueError("Worker returned invalid structured evidence") from exc
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def candidates(plan: dict, state: dict) -> list[dict]:
    result = []
    for service in SERVICES:
        status = state["services"][service]
        lane = {"unobserved": "contract", "contract-verified": "retained-execution"}.get(status)
        if lane is None:
            continue
        action = action_for(plan, service, lane)
        if permitted(action["kind"], plan["action_policy"]) and state["attempts"].get(action["id"], 0) < plan["policy"]["max_attempts"]:
            result.append(action)
    return result


def _require(condition: bool, message: str):
    if not condition:
        raise ValueError(message)


def replay(root: Path, events: list[dict]) -> dict:
    """Replay every transition. Hashes alone cannot legitimize a forged receipt."""
    _require(bool(events) and events[0]["type"] == "started", "Missing execution plan")
    plan = events[0]["payload"]
    _require(plan == build_execution_plan(root), "Execution inputs, implementation or policy changed")
    state = {"plan": plan, "services": {s: "unobserved" for s in SERVICES}, "attempts": {},
             "iterations": 0, "actions_executed": 0, "queue": [], "in_flight": None,
             "receipts": [], "failures": [], "status": "running", "halt_reason": None}
    previous, last_time = None, None
    for index, event in enumerate(events):
        _require(event.get("sequence") == index + 1 and event.get("previous_sha256") == previous and event.get("content_sha256") == content_hash(event), "Execution event chain changed")
        when = datetime.fromisoformat(event["at"])
        _require(when.tzinfo is not None and (last_time is None or when >= last_time), "Invalid execution event time")
        previous, last_time = event["content_sha256"], when
        if index == 0:
            started = when
            continue
        _require(state["halt_reason"] is None, "Events after terminal halt")
        kind, payload = event["type"], event["payload"]
        if "divergent" in state["services"].values():
            _require(kind == "halted" and payload == {"reason": "divergent"}, "Execution continued after raw divergence")
        if kind == "round":
            _require(not state["queue"] and not state["in_flight"], "Round overlaps existing work")
            expected = candidates(plan, state)
            _require(payload == {"actions": expected} and bool(expected), "Unadmitted actions in execution round")
            state["iterations"] += 1
            _require(state["iterations"] <= plan["policy"]["max_iterations"], "Iteration budget exceeded")
            state["queue"] = list(expected)
        elif kind == "attempt":
            _require(bool(state["queue"]) and not state["in_flight"], "No admitted pending action")
            action = state["queue"][0]
            count = state["attempts"].get(action["id"], 0) + 1
            _require(payload == {"action": action, "attempt": count}, "Worker action or attempt changed")
            _require(count <= plan["policy"]["max_attempts"], "Retry budget exceeded")
            _require((when - started).total_seconds() < plan["policy"]["max_seconds"], "Action began after run deadline")
            state["attempts"][action["id"]] = count
            state["actions_executed"] += 1
            _require(state["actions_executed"] <= plan["policy"]["max_actions"], "Action budget exceeded")
            state["in_flight"] = action
            state["status"] = "running"
        elif kind in {"result", "failed"}:
            action = state["in_flight"]
            _require(action is not None, "Result without admitted attempt")
            if kind == "failed":
                _require(set(payload) == {"action_id", "reason"} and payload["action_id"] == action["id"] and payload["reason"] in FAILURES, "Invalid failure receipt")
                state["failures"].append(payload)
            else:
                observation = observe(root, action["service"], action["lane"])
                status = observed_status(observation)
                receipt = seal({"artifact_type": "lightyear-evidence-action-receipt", "action": action,
                                "attempt": state["attempts"][action["id"]],
                                "before": state["services"][action["service"]], "after": status,
                                "observation": observation, "boundary": BOUNDARY})
                _require(payload == receipt, "Worker evidence or verdict transition does not match deterministic verification")
                state["services"][action["service"]] = status
                state["receipts"].append(receipt)
            state["queue"].pop(0)
            state["in_flight"] = None
        elif kind == "paused":
            _require(not state["in_flight"] and payload == {}, "Invalid pause checkpoint")
            state["status"] = "paused"
        elif kind == "halted":
            _require(set(payload) == {"reason"}, "Invalid halt receipt")
            reason = payload["reason"]
            _require(reason in {"completed", "divergent", "budget", "no-permitted-action", "scope-boundary", "untrusted-worker"}, "Unknown halt reason")
            if reason == "completed":
                _require(all(v == "retained-evidence-verified" for v in state["services"].values()), "Unsupported convergence claim")
            if reason == "divergent":
                _require("divergent" in state["services"].values(), "Invented divergence")
            if reason == "no-permitted-action":
                _require(not state["queue"] and not candidates(plan, state), "Permitted work remains")
            state["halt_reason"] = reason
            state["status"] = "completed" if reason == "completed" else "halted"
        else:
            raise ValueError("Unknown execution event")
    state.update(journal_head_sha256=previous, last_event_at=events[-1]["at"], started_at=events[0]["at"])
    return state


def summary(state: dict) -> dict:
    plan = state["plan"]
    items = []
    for service, status in state["services"].items():
        receipts = [r for r in state["receipts"] if r["action"]["service"] == service]
        next_lane = {"unobserved": "contract", "contract-verified": "retained-execution"}.get(status)
        action = action_for(plan, service, next_lane) if next_lane else None
        reason = "Missing or unreadable evidence; acquire inputs within an authorized scope" if status == "unavailable" else None
        if action and not permitted(action["kind"], plan["action_policy"]):
            reason = "Human decision required by narrowed action policy"
        elif action and state["attempts"].get(action["id"], 0) >= plan["policy"]["max_attempts"]:
            reason = "Retry budget exhausted"
        items.append({"service": service, "status": status, "reason": reason,
                      "receipts": receipts, "next_action": action})
    resolved = sum(v == "retained-evidence-verified" for v in state["services"].values())
    return seal({"artifact_type": "lightyear-cloudbank-convergence-receipt", "schema_version": "1.0",
                 "estate": "CloudBank", "scope": plan["scope"], "status": state["status"],
                 "halt_reason": state["halt_reason"], "plan_sha256": plan["content_sha256"],
                 "journal_head_sha256": state["journal_head_sha256"],
                 "started_at": state["started_at"], "last_event_at": state["last_event_at"],
                 "source_run_id": plan["source_run_id"], "boundary": BOUNDARY,
                 "summary": {"services": len(SERVICES), "resolved": resolved,
                             "unresolved": len(SERVICES) - resolved,
                             "divergent": sum(v == "divergent" for v in state["services"].values()),
                             "actions_executed": state["actions_executed"], "iterations": state["iterations"],
                             "worker_failures": len(state["failures"]),
                             "claims_promoted": 0, "measured": True,
                             "converged_within_scope": state["halt_reason"] == "completed",
                             "cannot_improve_globally": False},
                 "budgets": plan["policy"], "items": items, "failures": state["failures"]})


def _output_scope(root: Path, directory: Path):
    work = root / "work"
    _require(not work.is_symlink() and directory.resolve().is_relative_to(work.resolve()), "Run directory must be inside the repository work directory")
    _require(not any(p.is_symlink() for p in [directory, *directory.parents] if p != root.parent), "Symbolic execution output path")


def execute(root: Path, directory: Path, *, max_steps: int | None = None) -> dict:
    root = root.resolve()
    _output_scope(root, directory)
    if max_steps is not None and (type(max_steps) is not int or not 1 <= max_steps <= 32):
        raise ValueError("max_steps must be an integer from 1 to 32")
    store = RunStore(directory)
    try:
        if not store.events():
            store.append("started", build_execution_plan(root))
        state = replay(root, store.events())
        if state["halt_reason"]:
            return summary(state)
        if state["in_flight"]:
            store.append("failed", {"action_id": state["in_flight"]["id"], "reason": "interrupted"})
        steps = 0
        while True:
            state = replay(root, store.events())
            plan, policy = state["plan"], state["plan"]["policy"]
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(state["started_at"])).total_seconds()
            reason = None
            if "divergent" in state["services"].values():
                reason = "divergent"
            elif all(v == "retained-evidence-verified" for v in state["services"].values()):
                reason = "completed"
            elif elapsed >= policy["max_seconds"] or state["actions_executed"] >= policy["max_actions"]:
                reason = "budget"
            elif not state["queue"]:
                if not candidates(plan, state):
                    reason = "no-permitted-action"
                elif state["iterations"] >= policy["max_iterations"]:
                    reason = "budget"
            if reason:
                store.append("halted", {"reason": reason})
                break
            if max_steps is not None and steps >= max_steps:
                store.append("paused", {})
                break
            if not state["queue"]:
                store.append("round", {"actions": candidates(plan, state)})
                continue
            action = state["queue"][0]
            attempt = state["attempts"].get(action["id"], 0) + 1
            store.append("attempt", {"action": action, "attempt": attempt})
            try:
                result = run_worker(root, action, policy, min(policy["action_timeout_seconds"], policy["max_seconds"] - elapsed))
            except WorkerFailure as exc:
                store.append("failed", {"action_id": action["id"], "reason": str(exc)})
                steps += 1
                continue
            except ValueError:
                store.append("halted", {"reason": "untrusted-worker"})
                break
            try:
                try:
                    unchanged = build_execution_plan(root) == plan
                except (ValueError, OSError):
                    unchanged = False
                if not unchanged:
                    store.append("halted", {"reason": "scope-boundary"})
                    raise ValueError("Execution inputs changed during worker observation")
                expected = observe(root, action["service"], action["lane"])
                if result != expected:
                    store.append("halted", {"reason": "untrusted-worker"})
                    break
                if (datetime.now(timezone.utc) - datetime.fromisoformat(state["started_at"])).total_seconds() >= policy["max_seconds"]:
                    raise WorkerFailure("worker-timeout")
                status = observed_status(result)
                store.append("result", seal({"artifact_type": "lightyear-evidence-action-receipt", "action": action,
                    "attempt": attempt, "before": state["services"][action["service"]], "after": status,
                    "observation": expected, "boundary": BOUNDARY}))
            except WorkerFailure as exc:
                store.append("failed", {"action_id": action["id"], "reason": str(exc)})
            steps += 1
        result = summary(replay(root, store.events()))
        _atomic_write(directory / "convergence.receipt.json", (json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
        return result
    finally:
        store.close()


def read_execution(root: Path, directory: Path | None = None) -> dict:
    """No writes, workers, or refreshed timestamps in the browser's read path."""
    try:
        directory = directory or root / RUN_PATH
        events = RunStore(directory, read_only=True).events()
        source = "engine-journal"
        if not events and directory == root / RUN_PATH and (root / EXAMPLE_PATH).is_file():
            events = json.loads((root / EXAMPLE_PATH).read_text(), object_pairs_hook=_unique_object)["events"]
            source = "recorded-example"
        if not events:
            return {"status": "unavailable", "read_only": True, "reason": "No CloudBank execution has been recorded.", "items": []}
        _require(len(events) <= 256, "Execution journal exceeds bounded event count")
        result = summary(replay(root, events))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(result["last_event_at"])).total_seconds()
        _require(age >= -60, "Execution time is in the future")
        return {**result, "read_only": True, "source": source,
                "activity": "historical" if source == "recorded-example" or result["status"] != "running" else ("recent-engine-activity" if age < 45 else "interrupted-or-unobserved"),
                "age_seconds": max(0, int(age))}
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        return {"status": "invalid", "read_only": True, "reason": str(exc), "items": []}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "verify", "export"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-dir", type=Path, default=RUN_PATH)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    directory = args.run_dir if args.run_dir.is_absolute() else root / args.run_dir
    try:
        if args.command == "run":
            result = execute(root, directory, max_steps=args.max_steps)
        else:
            result = read_execution(root, directory)
            if args.command == "export":
                _require(args.output is not None and result["status"] not in {"invalid", "unavailable"}, "Export requires a verified run and --output")
                events = RunStore(directory, read_only=True).events()
                _require(bool(events), "Export requires the original engine journal")
                output = args.output if args.output.is_absolute() else root / args.output
                _atomic_write(output, (json.dumps({"events": events}, sort_keys=True, indent=2) + "\n").encode())
        print(json.dumps({k: v for k, v in result.items() if k not in {"items", "failures"}}, indent=2))
        return 0 if result["status"] in {"completed", "paused"} else 1
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
