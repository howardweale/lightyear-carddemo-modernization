"""Budget-approved evaluation orchestration and fail-closed evidence aggregation."""

import json
import math
import subprocess
from datetime import datetime
from pathlib import Path
from .contracts import canonical_hash, ContractError
from .routing import TASKS
from .knowledge_trust import approve
from lightyear_control_tower.decisions import digest, canonical

WORKLOADS = {"INTCALC", "POSTTRAN", "CREASTMT", "ACCTPL1"}


def check_hash(value):
    if value.get("content_sha256") != canonical_hash(value, {"content_sha256"}):
        raise ContractError("matrix evidence content hash mismatch")


def aggregate(plan, cells):
    if len(cells) != len(plan["cells"]):
        raise ContractError("matrix incomplete")
    rows = []
    for expected, cell in zip(plan["cells"], cells, strict=True):
        evaluation = cell["evaluation"]
        check_hash(evaluation)
        if (
            evaluation["catalog_sha256"] != expected["catalog_sha256"]
            or evaluation["evaluation_class"] != expected["evaluation_class"]
            or evaluation["workload_id"].upper() != expected["workload"]
        ):
            raise ContractError("matrix catalog mismatch")
        runs = {r["content_sha256"]: r for r in cell["runs"]}
        calls = {c["content_sha256"]: c for c in cell["model_calls"]}
        if len(runs) != len(cell["runs"]) or len(calls) != len(cell["model_calls"]):
            raise ContractError("duplicate matrix evidence")
        used = set()
        used_runs = set()
        wall_ms = 0
        for result in evaluation["results"]:
            ref = result["receipt_sha256"]
            if ref not in runs or ref in used_runs:
                raise ContractError("missing or reused matrix run")
            run = runs[ref]
            check_hash(run)
            used_runs.add(ref)
            if run["status"] != result["status"]:
                raise ContractError("matrix verdict mismatch")
            start, end = (
                datetime.fromisoformat(run[k]) for k in ("started_at", "completed_at")
            )
            if start.tzinfo is None or end.tzinfo is None or end < start:
                raise ContractError("invalid matrix run timing")
            wall_ms += (end - start).total_seconds() * 1000
            refs = run["intelligence"]["call_evidence_sha256"]
            if not refs or len(refs) != run["intelligence"]["calls"]:
                raise ContractError("missing model-call records")
            for ref in refs:
                if ref not in calls or ref in used:
                    raise ContractError("missing or reused model-call record")
                c = calls[ref]
                check_hash(c)
                used.add(ref)
                if c["model"] != expected.get("model_id", expected["model"]):
                    raise ContractError("matrix model mismatch")
        if used != set(calls) or used_runs != set(runs):
            raise ContractError("unbound matrix evidence")
        results = evaluation["results"]
        count = len(results)
        passed = sum(
            r["status"] == "passed" and not r["false_acceptance"] for r in results
        )
        totals = evaluation["totals"]
        if evaluation["false_acceptances"] != sum(
            bool(r["false_acceptance"]) for r in results
        ):
            raise ContractError("matrix false-acceptance total mismatch")
        for key in ("input_tokens", "output_tokens", "estimated_cost_usd"):
            actual = sum(c[key] for c in calls.values())
            if (
                not math.isfinite(actual)
                or actual < 0
                or not math.isclose(totals[key], actual, rel_tol=1e-7, abs_tol=1e-6)
            ):
                raise ContractError("matrix usage total mismatch")
        rows.append(
            dict(
                task_type=expected["task_type"],
                model=expected["model"],
                workload=expected["workload"],
                evaluation_class=expected["evaluation_class"],
                catalog_sha256=expected["catalog_sha256"],
                evaluation_sha256=evaluation["content_sha256"],
                runs=sorted(runs),
                model_calls=sorted(calls),
                pass_rate=passed / count if count else None,
                first_attempt_pass=sum(
                    bool(r.get("first_attempt_repair") or r.get("correct_no_change"))
                    for r in results
                ),
                false_acceptances=evaluation["false_acceptances"],
                tokens_per_verified_task=(
                    (totals["input_tokens"] + totals["output_tokens"]) / passed
                    if passed
                    else None
                ),
                cost_per_verified_task=(
                    totals["estimated_cost_usd"] / passed if passed else None
                ),
                wall_time_ms=wall_ms,
                model_time_ms=sum(r.get("elapsed_ms", 0) for r in results),
                closed_categories=(
                    sorted({r["category"] for r in results if r.get("category")})
                    if expected["evaluation_class"] != "sealed-holdout"
                    else []
                ),
            )
        )
    body = dict(
        schema="factory-evaluation-matrix/1",
        plan_sha256=digest(plan),
        cells=rows,
        false_acceptances=sum(r["false_acceptances"] for r in rows),
    )
    return {**body, "content_sha256": digest(body)}


def run_matrix(
    plan,
    proof,
    trust,
    *,
    commit,
    project_root,
    output_root,
    agent_factories,
    catalogs,
    sealed_keys=None,
):
    """Explicitly invoked only after commit/matrix/models/budget operator approval.

    Each cell uses the existing judge/evidence/leak-check evaluation path. Cell
    task_type describes its workload objective, not isolated provider-role skill.
    No retries or implicit resume, and no annotations are attached to holdouts.
    """
    from .evals import run_model_evaluation, EvaluationPolicy, load_evaluation_catalog

    if plan["commit"] != commit or not plan["cells"]:
        raise ContractError("matrix commit mismatch")
    models = sorted({c["model"] for c in plan["cells"]})
    budget = plan["max_cost_usd"]
    if not math.isfinite(budget) or budget <= 0:
        raise ContractError("matrix dollar budget required")
    if sum(c["policy"]["max_cost_usd"] for c in plan["cells"]) > budget:
        raise ContractError("matrix cell budgets exceed approval")
    d = approve(
        proof,
        trust,
        "campaign-authorization",
        dict(
            campaign=digest("factory-evaluation-matrix"),
            plan=digest(plan),
            declaration=digest(models),
            limits=digest({"max_cost_usd": budget}),
            public_commit=digest(commit),
        ),
        ["authorized"],
    )
    if d["actor"]["id"] != trust["operator_id"]:
        raise ContractError("Howard matrix approval required")
    root = Path(project_root).resolve()
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if actual != commit or dirty or not Path(__file__).resolve().is_relative_to(root):
        raise ContractError(
            "matrix requires the clean approved source checkout and imports"
        )
    prepared = []
    for c in plan["cells"]:
        if c["task_type"] not in TASKS or c["workload"] not in WORKLOADS:
            raise ContractError("invalid matrix cell")
        if (
            c["evaluation_class"] not in {"public-calibration", "sealed-holdout"}
            or c["model"] not in agent_factories
        ):
            raise ContractError("invalid evaluation class or model")
        policy = EvaluationPolicy(**{**c["policy"], "require_cost_estimate": True})
        if any(
            not math.isfinite(v)
            for v in policy.to_dict().values()
            if isinstance(v, (int, float))
        ):
            raise ContractError("nonfinite matrix budget")
        path = Path(catalogs[c["catalog_sha256"]])
        binding = None
        if c["evaluation_class"] == "sealed-holdout":
            from .quality import verify_sealed_catalog

            catalog, binding = verify_sealed_catalog(
                json.loads(path.read_bytes()), sealed_keys or {}
            )
        else:
            catalog = load_evaluation_catalog(path)
        if canonical_hash(catalog) != c["catalog_sha256"]:
            raise ContractError("changed matrix catalog")
        if (
            catalog["evaluation_class"] != c["evaluation_class"]
            or catalog["workload_id"].upper() != c["workload"]
        ):
            raise ContractError("matrix catalog class or workload mismatch")
        prepared.append((c, path, catalog, binding, policy))
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=False)
    (output / "authorization.json").write_bytes(canonical(proof))
    cells = []
    for i, (c, path, catalog, binding, policy) in enumerate(prepared):
        target = output / str(i)
        evaluation = run_model_evaluation(
            Path(project_root),
            target,
            path,
            agent_factories[c["model"]],
            policy=policy,
            catalog_override=catalog,
            sealed_binding=binding,
        )
        runs = []
        calls = []
        for result in evaluation["results"]:
            matches = [
                p
                for p in (target / "runs").glob("*/receipt.json")
                if json.loads(p.read_bytes()).get("content_sha256")
                == result["receipt_sha256"]
            ]
            if len(matches) != 1:
                raise ContractError("matrix run receipt missing")
            run = json.loads(matches[0].read_bytes())
            runs.append(run)
            for ref in run["artifacts"]:
                if ref["artifact_type"] == "model-call-evidence":
                    p = (matches[0].parent / ref["path"]).resolve()
                    if not p.is_relative_to(matches[0].parent.resolve()):
                        raise ContractError("unsafe call artifact path")
                    artifact = json.loads(p.read_bytes())
                    check_hash(artifact)
                    if artifact["content_sha256"] != ref["content_sha256"]:
                        raise ContractError("call artifact mismatch")
                    calls.append(artifact["content"])
        cells.append(dict(evaluation=evaluation, runs=runs, model_calls=calls))
        if evaluation["status"] == "stopped":
            raise ContractError("evaluation stopped; preserve partial matrix")
    receipt = aggregate(plan, cells)
    (output / "matrix-receipt.json").write_bytes(canonical(receipt))
    return receipt
