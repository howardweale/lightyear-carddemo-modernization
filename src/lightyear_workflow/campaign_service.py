"""Local operator commands; only the detached engine touches database resources."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from lightyear_control_tower.decisions import DecisionService, initialize_authority
from .campaign_engine import AUTHORITY, authorize, dispatch, records, campaign_plan
from .campaigns import CAMPAIGN


def review(root, campaign=CAMPAIGN):
    try:
        return {"status": "reviewable", "plan": campaign_plan(root, campaign)}
    except (ValueError, OSError, KeyError, TypeError):
        return {"status": "unconfigured", "reason": "A validated campaign profile, digest-pinned Oracle image and campaign operator authority are required."}


def list_runs(root, campaign=CAMPAIGN):
    try:
        rows = records(root, campaign)
        return {"campaign_id": campaign, "estate": "cloudbank", "read_only": True,
                "runs": [{"run_id": r["authorization"]["run_id"], "started_at": r["authorization"]["authorized_at"],
                          "actions_completed": (r["terminal"] or {}).get("matched"),
                          "terminal": (r["terminal"] or {}).get("status", "authorized / awaiting terminal result")}
                         for r in rows], "reason": None if rows else "no-runs-recorded"}
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        return {"campaign_id": campaign, "runs": [], "reason": "invalid-run-index"}


def history(root, campaign=CAMPAIGN):
    # Never opens a run journal. Signed terminal summaries remain independently
    # verifiable after the customer's journal retention policy removes detail.
    try:
        rows = records(root, campaign)
        terminal = [r["terminal"] for r in rows if r["terminal"]]
        return {"campaign_id": campaign, "metric_unit": "paired-cases", "read_only": True,
                "weeks": [],
                "runs": terminal, "reason": None if terminal else "no-runs-recorded",
                "recoveries": {r["authorization"]["run_id"]: r["recovery"] for r in rows if r["recovery"]},
                "limit": 100, "note": "Latest 100 authorizations; simulated runs remain labelled. Repeated cases are not distinct catalog coverage."}
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        return {"campaign_id": campaign, "runs": [], "reason": "invalid-run-index", "metric_unit": "paired-cases"}


class CampaignService:
    def __init__(self, root: Path, *, dispatcher=dispatch):
        self.root = root
        self.authority = DecisionService(root, root / AUTHORITY, database=(root / AUTHORITY).with_name("sessions.sqlite3"),
                                         recover_runs=False, decision_only=True)
        self.dispatcher = dispatcher

    def status(self, campaign=CAMPAIGN):
        return {"enabled": True, **review(self.root, campaign)}

    def login(self, credential):
        result = self.authority.login(credential)
        self.authority.authenticate(result["token"], "campaign-approver")
        return result

    def start(self, token, payload):
        session = self.authority.authenticate(token, "campaign-approver")
        auth, created = authorize(self.root, self.authority, session["actor"], payload)
        if created:
            try:
                self.dispatcher(self.root, auth["run_id"])
            except OSError:
                # Authorization is preserved. A retry never launches a second
                # worker; explicit recovery is required for uncertain dispatch.
                return {"status": "dispatch-unconfirmed", "run_id": auth["run_id"]}
        return {"status": "authorized", "run_id": auth["run_id"], "new_dispatch": created}

    def close(self):
        self.authority.close()


def initialize(root: Path, operator_id: str, operator_name: str):
    authority = root / AUTHORITY
    credential = initialize_authority(authority, operator_id, operator_name, workload_id="cloudbank:retained-value-conservation")
    config = json.loads(authority.read_text(encoding="utf-8"))
    for operator in config["operators"]:
        operator["roles"] = ["campaign-approver"]
    authority.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return credential


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init-operator", "review"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--operator-id")
    parser.add_argument("--operator-name")
    parser.add_argument('--campaign-id', default=CAMPAIGN)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "init-operator":
        credential = initialize(root, args.operator_id, args.operator_name)
        print(json.dumps({"status": "provisioned-not-authorized", "credential_file": str(credential)}))
    else:
        print(json.dumps(review(root, args.campaign_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
