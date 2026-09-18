"""Read-only campaign preparation. No execution, authorization or qualification."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from lightyear_data.oracle_number_native import number_cases, verify_harnesses
from .policy import _unique_object

CAMPAIGN = "oracle26ai-alloydb-number"
PROJECT = "lightyear-ms67-nonproduction"
REGION = "us-west1"
SNAPSHOT = Path("work/campaigns") / CAMPAIGN / "readiness.json"
MAX_AGE_SECONDS = 900


def validate_context(estate: str, campaign: str) -> None:
    from .paired_types import CAMPAIGN as CORE100
    from .history import estate_name
    estate_name(estate)
    if campaign != "retained" and (estate != "cloudbank" or campaign not in (CAMPAIGN, CORE100)):
        raise ValueError("Unknown campaign for the selected estate")


def commands() -> dict[str, list[str]]:
    """Fixed project and resource identities; no browser-controlled commands."""
    scope = ["--project", PROJECT, "--quiet", "--format=json"]
    return {
        "alloydb": ["alloydb", "instances", "describe", "primary", "--cluster", "cloudbank-ms71-alloydb", "--region", REGION, *scope],
        "cloud_sql": ["sql", "instances", "describe", "cloudbank-ms67-postgres", *scope],
        "gke": ["container", "clusters", "describe", "cloudbank-ms67", "--region", REGION, *scope],
    }


def _hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _path(root: Path) -> Path:
    path = root.resolve() / SNAPSHOT
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic readiness path")
    return path


def read_readiness(root: Path, *, now: datetime | None = None) -> dict:
    """Only read a bounded saved observation; never contact GCP on an HTTP GET."""
    empty = {"status": "unavailable", "observations": [], "observed_at": None,
             "evidence_class": "unsigned-operational-readback", "max_age_seconds": MAX_AGE_SECONDS}
    try:
        path = _path(root)
        if not path.exists():
            return {**empty, "reason": "No environment readback recorded."}
        if path.stat().st_size > 65536:
            raise ValueError("Readback exceeds size bound")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        body = value["readback"]
        if value["sha256"] != _hash(body) or body["campaign_id"] != CAMPAIGN or body["project"] != PROJECT or body["region"] != REGION:
            raise ValueError("Readback scope or digest mismatch")
        when = datetime.fromisoformat(body["observed_at"])
        if when.tzinfo is None:
            raise ValueError("Missing readback timezone")
        age = ((now or datetime.now(timezone.utc)) - when).total_seconds()
        if age < 0:
            raise ValueError("Readback is in the future")
        rows = body["observations"]
        if not isinstance(rows, list) or [r["resource"] for r in rows] != list(commands()):
            raise ValueError("Readback resources mismatch")
        for row in rows:
            if row["status"] not in {"observed", "unavailable"} or not isinstance(row["state"], str) or len(row["state"]) > 64:
                raise ValueError("Invalid resource readback")
        return {**empty, "status": "stale" if age > MAX_AGE_SECONDS else "recent", "observed_at": body["observed_at"],
                "age_seconds": int(age), "observations": rows, "sha256": value["sha256"],
                "reason": "Operational readback only; this does not establish database access, execution or qualification."}
    except (ValueError, OSError, KeyError, TypeError):
        return {**empty, "status": "invalid", "reason": "Saved environment readback could not be validated."}


def read_campaign(root: Path, estate: str, campaign: str, run_id: str | None = None) -> dict:
    from . import paired_types
    validate_context(estate, campaign)
    if campaign == "retained":
        return {"campaign_id": campaign, "estate": estate, "read_only": True, "status": "retained-evidence"}
    cases = []
    preparation = "unavailable"
    core = campaign == paired_types.CAMPAIGN
    try:
        (paired_types.verify if core else verify_harnesses)(root)
        cases = [{key: case[key] for key in ("id", "behavior_id", "focus", "dimension", "topic")} for case in (paired_types.cases if core else number_cases)(root)]
        preparation = "verified-files"
    except (ValueError, OSError, KeyError):
        pass
    from .campaign_service import review
    from .campaign_engine import AUTHORITY, read_run
    execution = read_run(root, run_id, campaign)
    proposed = review(root, campaign)
    measured = execution.get("identities") is not None and execution.get("evidence_class") == "native-database-observed"
    from lightyear_data.oracle_paired_coverage import report
    return {
        "campaign_id": campaign, "estate": estate, "name": paired_types.NAME if core else "Oracle 26ai → AlloyDB · NUMBER pilot",
        "status": execution["status"] if execution.get("run_id") else "planned", "read_only": True,
        "dispatch_available": proposed["status"] == "reviewable" and (root / AUTHORITY).is_file(),
        "scope": "Independent database catalog tests in the CloudBank lab; not CloudBank application scenarios.",
        "planned_cases": 100 if core else 20, "planned_behaviors": 25 if core else 5,
        "topic_family": ', '.join(paired_types.FAMILIES) if core else "types/number",
        "source": ("Oracle Database 26ai Free · " + execution["identities"]["oracle"]["version"] if measured else
                   "Oracle Database 26ai Free (proposed; runtime identity not recorded)"),
        "target": "Managed AlloyDB · cloudbank-ms71-alloydb / primary",
        "project": PROJECT, "region": REGION, "preparation": preparation, "cases": cases,
        "source_prepared_cases": len(cases) if preparation == "verified-files" else None,
        "native_executed_cases": execution.get("source_completed") if measured else None,
        "target_equivalent_cases": execution.get("matched") if measured and execution.get("comparisons_completed") else None,
        "current_run_status": execution["status"],
        "blockers": ([proposed["reason"]] if proposed["status"] != "reviewable" else
                     ["Review and authorize the exact campaign terms below. Fresh database identities are checked by the detached engine before case execution."]),
        "readiness": read_readiness(root),
        "catalog_coverage": report(root),
    }


def collect(root: Path) -> dict:
    """Explicit CLI observation, with no resource creation, start or stop."""
    executable = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not executable:
        raise ValueError("gcloud is required to collect environment readback")
    observed_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for resource, args in commands().items():
        row = {"resource": resource, "status": "unavailable", "state": "Unknown"}
        try:
            process = subprocess.run([executable, *args], capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
            value = json.loads(process.stdout)
            expected = {"alloydb": f"projects/{PROJECT}/locations/{REGION}/clusters/cloudbank-ms71-alloydb/instances/primary",
                        "cloud_sql": "cloudbank-ms67-postgres", "gke": "cloudbank-ms67"}[resource]
            if value["name"] != expected:
                raise ValueError("Unexpected resource identity")
            state = value.get("state") or value.get("status")
            if not isinstance(state, str) or len(state) > 64:
                raise ValueError("Missing resource state")
            row.update(status="observed", state=state)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            # Never persist command output: it can contain private connectivity details.
            pass
        rows.append(row)
    body = {"campaign_id": CAMPAIGN, "project": PROJECT, "region": REGION,
            "observed_at": observed_at, "observations": rows}
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    if temporary.is_symlink():
        raise ValueError("Symbolic temporary readback path")
    temporary.write_text(json.dumps({"readback": body, "sha256": _hash(body)}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return read_readiness(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect"])
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    result = collect(args.root)
    print(json.dumps(result, indent=2))
    return 0 if all(row["status"] == "observed" for row in result["observations"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
