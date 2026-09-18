"""Fixed NUMBER pilot SQL and deterministic comparison of native observations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lightyear_control_tower.decisions import digest
from lightyear_data.oracle_number_native import EXPECTED, number_cases, probes, render_case, verify_harnesses
from .campaigns import CAMPAIGN, PROJECT, REGION

MARKER = "LY_PAIRED_OBSERVATION="
PROFILE = Path("work/campaigns") / CAMPAIGN / "profile.json"
ROOT = Path("work/campaigns") / CAMPAIGN


def postgres_case(case: dict) -> str:
    fields = {"arithmetic": "v_sum", "null_value": "v_null", "rounded": "v_rounded", "maximum": "v_maximum",
              "overflow_code": "v_overflow", "recovery": "v_recovery", "nls_dot": "v_dot", "nls_comma": "v_comma"}
    pairs = ", ".join(f"'{p}', {fields[p]}" for p in probes(case))
    # Explicit separator rendering is the candidate transformation for Oracle's
    # NLS behaviour. It is part of the reviewed SQL, never a comparator rewrite.
    return f"""BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL lc_numeric = 'C';
DO $pilot$
DECLARE
 v_sum text; v_null numeric; v_rounded text; v_maximum text;
 v_overflow text := '00000'; v_recovery text; v_dot text; v_comma text; v_sink numeric;
BEGIN
 SELECT to_char(123.45::numeric + 0.55::numeric, 'FM990D00'), NULL::numeric + 1,
        to_char(2.345::numeric(3,2), 'FM990D00'), to_char(999.99::numeric(5,2), 'FM990D00')
 INTO v_sum, v_null, v_rounded, v_maximum;
 BEGIN
  SELECT 1000::numeric(3,0) INTO v_sink;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow = RETURNED_SQLSTATE;
 END;
 SELECT to_char(123.45::numeric + 0.55::numeric, 'FM990D00') INTO v_recovery;
 SELECT to_char(123.45::numeric + 0.55::numeric, 'FM990D00') INTO v_dot;
 SELECT replace(to_char(123.45::numeric + 0.55::numeric, 'FM990D00'), '.', ',') INTO v_comma;
 RAISE NOTICE '{MARKER}%', json_build_object('case_id', '{case['id']}', 'observations', json_build_object({pairs}));
END $pilot$;
ROLLBACK;
"""


def parse_observation(output: str, case: dict, lane: str) -> dict:
    from lightyear_data.oracle_number_native import MARKER as ORACLE_MARKER
    marker = ORACLE_MARKER if lane == "oracle" else MARKER
    values = [line.split(marker, 1)[1].strip() for line in output.splitlines() if marker in line]
    if len(values) != 1:
        raise ValueError("A case requires exactly one native observation")
    value = json.loads(values[0])
    if value.get("case_id") != case["id"] or set(value.get("observations", {})) != set(probes(case)):
        raise ValueError("Native observation does not match the bound case")
    observed = value["observations"]
    if any(v is not None and (type(v) not in (str, int) or len(str(v)) > 64) for v in observed.values()):
        raise ValueError("Unexpected observation value")
    return observed


def compare(case: dict, oracle: dict, target: dict) -> dict:
    """Keep raw diagnostic codes; match their explicitly approved semantic class."""
    expected = {p: EXPECTED[p] for p in probes(case)}
    target_expected = {**expected}
    if "overflow_code" in target_expected:
        target_expected["overflow_code"] = "22003"
    source_ok = oracle == expected
    target_ok = target == target_expected
    differences = []
    for probe in probes(case):
        equivalent = oracle.get(probe) == target.get(probe)
        if probe == "overflow_code":
            equivalent = type(oracle.get(probe)) is int and oracle[probe] == -1438 and target.get(probe) == "22003"
        if not equivalent:
            differences.append({"probe": probe, "oracle": oracle.get(probe), "alloydb": target.get(probe)})
    return {"case_id": case["id"], "source_expectations_met": source_ok, "target_expectations_met": target_ok,
            "equivalent": source_ok and target_ok and not differences, "differences": differences,
            "diagnostic_mapping": "ORA-01438 ↔ SQLSTATE 22003 (numeric precision overflow)" if "overflow_code" in probes(case) else None}


def profile(root: Path, relative: Path = PROFILE) -> dict:
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents)) or path.stat().st_size > 16384:
        raise ValueError("Invalid campaign profile path or size")
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"oracle_image", "budget_usd", "estimated_hourly_usd", "max_seconds", "runner_zone"}
    if set(value) != required:
        raise ValueError("Campaign profile fields differ from the supported contract")
    import re
    if not re.fullmatch(r"container-registry\.oracle\.com/database/free@sha256:[a-f0-9]{64}", value["oracle_image"]):
        raise ValueError("A digest-pinned official Oracle Free image is required")
    if value["runner_zone"] not in {"us-west1-a", "us-west1-b", "us-west1-c"}:
        raise ValueError("Runner must use the existing us-west1 lab")
    if type(value["max_seconds"]) is not int or not 600 <= value["max_seconds"] <= 3600:
        raise ValueError("Campaign duration must be 10–60 minutes")
    for key in ("budget_usd", "estimated_hourly_usd"):
        if type(value[key]) not in (int, float) or not 0 < value[key] <= 10:
            raise ValueError("Invalid campaign spending terms")
    if value["estimated_hourly_usd"] * value["max_seconds"] / 3600 > value["budget_usd"]:
        raise ValueError("Estimated run cost exceeds proposed budget")
    return value


def plan(root: Path) -> dict:
    verify_harnesses(root)
    config = profile(root)
    cases = number_cases(root)
    sources = {name: hashlib.sha256((root / "src/lightyear_workflow" / name).read_bytes()).hexdigest()
               for name in ("paired_number.py", "campaign_engine.py", "campaign_gcp.py")}
    sources["oracle_number_native.py"] = hashlib.sha256((root / "src/lightyear_data/oracle_number_native.py").read_bytes()).hexdigest()
    value = {
        "campaign_id": CAMPAIGN, "project": PROJECT, "region": REGION, "profile": config,
        "cases": [{"id": c["id"], "behavior_id": c["behavior_id"],
                   "oracle_sql_sha256": hashlib.sha256(render_case(c, "26ai").encode()).hexdigest(),
                   "alloydb_sql_sha256": hashlib.sha256(postgres_case(c).encode()).hexdigest()} for c in cases],
        "implementation": sources, "alloydb_cluster": "cloudbank-ms71-alloydb", "alloydb_instance": "primary",
        "resource_policy": "Create one ephemeral e2-standard-2 runner; resume only the stopped AlloyDB primary. Delete owned runner and IAP firewall; restore AlloyDB to STOPPED.",
        "data_policy": "Synthetic expressions only; PostgreSQL transaction rollback; no application data read or changed.",
        "identity_policy": "Oracle digest, 26ai version and PDB are verified. AlloyDB PGHOST is bound to fresh fixed-resource GCP API readback and PostgreSQL 16; the separately recorded server socket address may differ behind managed routing.",
        "comparison_policy": "Exact values and nulls; approved ORA-01438/22003 overflow-class mapping. Target SQL explicitly renders decimal separators; raw observations are retained.",
        "cost_policy": "Estimated incremental budget; elapsed-time guard is enforceable, dollar cap is not a billing guarantee. Existing storage charges continue.",
        "interruption_policy": "No automatic replay of SQL after interruption. Record cleanup separately; unresolved cleanup requires recovery. Closing the browser does not stop the worker.",
        "qualification": "Bounded NUMBER equivalence only; no new platform or application qualification.",
    }
    return {**value, "plan_sha256": digest(value)}
