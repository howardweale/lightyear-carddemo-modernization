"""JSON CLI for the same project-bound operations exposed through local MCP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import uuid

from .service import OPERATIONS, Workflow, WorkflowError, initialize


def exit_code(result):
    if not result["ok"]:
        return 2
    status = result["status"]
    if status == "human-decision-required":
        return 3
    if status in {"comparison-failed", "execution-failed"}:
        return 1
    if status in {"accepted", "queued", "dispatch-unconfirmed", "running-or-interrupted", "resume-requested"}:
        return 4
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "worker", "run", *OPERATIONS))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--request-id")
    parser.add_argument("--run-id")
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--wait-seconds", type=int, default=360)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            if args.evidence_root is None or args.project_id is None:
                parser.error("init requires --evidence-root and --project-id")
            result = initialize(args.project, args.evidence_root, args.project_id)
        else:
            workflow = Workflow(args.project)
            if args.command == "worker":
                try:
                    workflow.serve_worker()
                except KeyboardInterrupt:
                    pass
                return 0
            elif args.command in {"start", "run"}:
                if args.command == "start" and (not args.plan_sha256 or not args.request_id):
                    parser.error("start requires --plan-sha256 and --request-id")
                if not 0 <= args.wait_seconds <= 600:
                    parser.error("--wait-seconds must be between 0 and 600")
                plan = workflow.invoke("plan") if args.command == "run" else None
                if plan and not plan["ok"]:
                    result = plan
                else:
                    result = workflow.invoke("start", plan_sha256=plan["plan_sha256"] if plan else args.plan_sha256,
                                             request_id=args.request_id or str(uuid.uuid4()))
                if args.command == "run" and result["ok"]:
                    run_id = result["run_id"]
                    print("run_id=" + run_id, file=sys.stderr)
                    deadline = time.monotonic() + args.wait_seconds
                    while True:
                        result = workflow.invoke("status", run_id=run_id)
                        if (not result["ok"] or (result.get("terminal") and result.get("dispatch_state") == "finished")
                                or result.get("dispatch_state") == "execution-failed"
                                or time.monotonic() >= deadline):
                            break
                        time.sleep(0.25)
            elif args.command in {"capabilities", "plan"}:
                result = workflow.invoke(args.command)
            else:
                if not args.run_id:
                    parser.error(args.command + " requires --run-id")
                arguments = {"run_id": args.run_id}
                if args.command == "events":
                    arguments.update(after=args.after, limit=args.limit)
                result = workflow.invoke(args.command, **arguments)
    except (ValueError, OSError) as exc:
        result = {"schema_version": "1.0", "ok": False, "status": "error", "error": {
            "code": exc.code if isinstance(exc, WorkflowError) else "configuration-required",
            "message": "Check the project manifest and evidence checkout; no authorization was created."}}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
