from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .pilot import PilotError, canonical_hash


SELECTION_SCHEMA_VERSION = "1.0"
SELECTION_REQUEST_TYPE = "lightyear-pilot-selection-request"
SELECTION_TYPE = "lightyear-governed-pilot-selection"
WORK_PACKAGE_SCHEMA_VERSION = "1.0"
WORK_PACKAGE_TYPE = "lightyear-pilot-work-package"


def _safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise PilotError(f"work-package-unsafe-path:{value}")
    return path.as_posix()


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not result:
        raise PilotError("work-package-empty-slug")
    return result


def _nonempty_strings(value: Any, code: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise PilotError(code)
    return [item.strip() for item in value]


def _cluster(assessment: Mapping[str, Any], cluster_id: str) -> dict[str, Any]:
    matches = [
        item
        for item in assessment.get("clusters", [])
        if isinstance(item, dict) and item.get("cluster_id") == cluster_id
    ]
    if len(matches) != 1:
        raise PilotError("selection-cluster-not-in-assessment")
    return matches[0]


def _reference_id(item: Mapping[str, Any]) -> str:
    return canonical_hash(dict(item))


def validate_selection_request(
    request: Mapping[str, Any], assessment: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    if (
        request.get("schema_version") != SELECTION_SCHEMA_VERSION
        or request.get("request_type") != SELECTION_REQUEST_TYPE
    ):
        errors.append("selection-request-identity-invalid")
    if request.get("content_sha256") != canonical_hash(
        dict(request), {"content_sha256"}
    ):
        errors.append("selection-request-content-hash-invalid")
    if request.get("assessment_sha256") != assessment.get("content_sha256"):
        errors.append("selection-request-assessment-binding-invalid")
    try:
        cluster = _cluster(assessment, str(request.get("cluster_id", "")))
    except PilotError as error:
        errors.append(str(error))
        cluster = None

    decision = request.get("decision")
    if not isinstance(decision, dict):
        errors.append("selection-request-decision-missing")
    else:
        for name in ("business_owner_id", "technical_owner_id", "rationale"):
            if not isinstance(decision.get(name), str) or not decision[name].strip():
                errors.append(f"selection-request-{name.replace('_', '-')}-missing")
        for name in ("business_outcomes", "success_criteria"):
            try:
                _nonempty_strings(
                    decision.get(name), f"selection-request-{name.replace('_', '-')}-missing"
                )
            except PilotError as error:
                errors.append(str(error))
        policy = decision.get("data_policy")
        if not isinstance(policy, dict) or set(policy) != {
            "classification",
            "permitted_use",
            "raw_customer_data_allowed",
            "retention_days",
        }:
            errors.append("selection-request-data-policy-invalid")
        elif (
            not isinstance(policy.get("classification"), str)
            or not policy["classification"]
            or not isinstance(policy.get("permitted_use"), str)
            or not policy["permitted_use"]
            or policy.get("raw_customer_data_allowed") is not False
            or not isinstance(policy.get("retention_days"), int)
            or not 1 <= policy["retention_days"] <= 365
        ):
            errors.append("selection-request-data-policy-invalid")

    authorization = request.get("authorization")
    if authorization != {
        "work_package_generation_approved": True,
        "factory_dispatch_approved": False,
        "native_execution_approved": False,
        "production_release_approved": False,
    }:
        errors.append("selection-request-authorization-boundary-invalid")
    approval = request.get("approval_record")
    if not isinstance(approval, dict) or not all(
        isinstance(approval.get(name), str) and approval[name].strip()
        for name in (
            "approval_id",
            "approver_id",
            "system",
            "recorded_at",
            "evidence_class",
        )
    ):
        errors.append("selection-request-approval-record-invalid")
    elif approval.get("evidence_class") not in {"recorded", "simulated"}:
        errors.append("selection-request-approval-class-invalid")

    if cluster is not None:
        expected = {
            _reference_id(item): item
            for item in cluster.get("unresolved_references", [])
            if isinstance(item, dict)
        }
        dispositions = request.get("boundary_dispositions")
        if not isinstance(dispositions, list):
            errors.append("selection-request-boundary-dispositions-invalid")
        else:
            actual: dict[str, Mapping[str, Any]] = {}
            for item in dispositions:
                if not isinstance(item, dict) or not isinstance(
                    item.get("reference_id"), str
                ):
                    errors.append("selection-request-boundary-disposition-invalid")
                    continue
                reference_id = item["reference_id"]
                if reference_id in actual:
                    errors.append("selection-request-boundary-disposition-duplicate")
                actual[reference_id] = item
                if item.get("disposition") not in {
                    "accepted-external-boundary",
                    "deferred-blocker",
                }:
                    errors.append("selection-request-boundary-disposition-invalid")
                if not isinstance(item.get("owner_id"), str) or not item["owner_id"].strip():
                    errors.append("selection-request-boundary-owner-missing")
                if not isinstance(item.get("rationale"), str) or not item["rationale"].strip():
                    errors.append("selection-request-boundary-rationale-missing")
            if set(actual) != set(expected):
                errors.append("selection-request-boundary-coverage-incomplete")
    return sorted(set(errors))


def build_pilot_selection(
    request: Mapping[str, Any],
    assessment: Mapping[str, Any],
    dossier: Mapping[str, Any],
) -> dict[str, Any]:
    errors = validate_selection_request(request, assessment)
    if errors:
        raise PilotError(errors[0])
    if dossier.get("assessment_sha256") != assessment.get("content_sha256"):
        raise PilotError("selection-dossier-assessment-binding-invalid")
    if dossier.get("content_sha256") != canonical_hash(
        dict(dossier), {"content_sha256"}
    ):
        raise PilotError("selection-dossier-content-hash-invalid")

    cluster = _cluster(assessment, str(request["cluster_id"]))
    dispositions = sorted(
        (dict(item) for item in request.get("boundary_dispositions", [])),
        key=lambda item: item["reference_id"],
    )
    deferred = [
        item["reference_id"]
        for item in dispositions
        if item.get("disposition") == "deferred-blocker"
    ]
    selection_ready = not deferred
    payload: dict[str, Any] = {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "selection_type": SELECTION_TYPE,
        "selection_id": str(request["selection_id"]),
        "request_sha256": str(request["content_sha256"]),
        "assessment_sha256": str(assessment["content_sha256"]),
        "dossier_sha256": str(dossier["content_sha256"]),
        "selected_cluster": {
            "cluster_id": cluster["cluster_id"],
            "label": cluster["label"],
            "source_files": list(cluster["source_files"]),
            "node_ids": list(cluster["node_ids"]),
            "technologies": list(cluster["technologies"]),
            "unresolved_reference_ids": sorted(
                _reference_id(item) for item in cluster["unresolved_references"]
            ),
        },
        "decision": dict(request["decision"]),
        "boundary_dispositions": dispositions,
        "approval_record": dict(request["approval_record"]),
        "selection_ready": selection_ready,
        "deferred_boundary_reference_ids": sorted(deferred),
        "authorization": {
            "work_package_generation_allowed": selection_ready,
            "factory_dispatch_allowed": False,
            "native_execution_allowed": False,
            "production_release_allowed": False,
        },
        "claim_boundary": {
            "business_priority_recorded": True,
            "approval_identity_cryptographically_verified": False,
            "work_order_admitted": False,
            "authorized_execution_observed": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        },
        "limitations": [
            "The approval record is bound and attributable but remains external evidence; LIGHTYEAR does not cryptographically verify the approver identity in this source-only flow.",
            "Selection authorizes deterministic work-package generation only, never factory dispatch or native execution.",
            "Accepted external boundaries remain explicit dependencies and are not relabelled as resolved source.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_pilot_selection(
    selection: Mapping[str, Any],
    request: Mapping[str, Any],
    assessment: Mapping[str, Any],
    dossier: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if (
        selection.get("schema_version") != SELECTION_SCHEMA_VERSION
        or selection.get("selection_type") != SELECTION_TYPE
    ):
        errors.append("selection-contract-identity-invalid")
    if selection.get("content_sha256") != canonical_hash(
        dict(selection), {"content_sha256"}
    ):
        errors.append("selection-content-hash-invalid")
    if (
        selection.get("request_sha256") != request.get("content_sha256")
        or selection.get("assessment_sha256") != assessment.get("content_sha256")
        or selection.get("dossier_sha256") != dossier.get("content_sha256")
    ):
        errors.append("selection-input-binding-invalid")
    authorization = selection.get("authorization")
    if not isinstance(authorization, dict) or any(
        authorization.get(name) is not False
        for name in (
            "factory_dispatch_allowed",
            "native_execution_allowed",
            "production_release_allowed",
        )
    ):
        errors.append("selection-overclaims-authorization")
    boundary = selection.get("claim_boundary")
    if not isinstance(boundary, dict) or any(
        boundary.get(name) is not False
        for name in (
            "approval_identity_cryptographically_verified",
            "work_order_admitted",
            "authorized_execution_observed",
            "mainframe_equivalent",
            "production_ready",
        )
    ):
        errors.append("selection-overclaims-readiness")
    try:
        rebuilt = build_pilot_selection(request, assessment, dossier)
        if selection != rebuilt:
            errors.append("selection-no-longer-matches-bound-inputs")
    except PilotError as error:
        errors.append(str(error))
    return sorted(set(errors))


def load_work_package_policy(path: Path) -> dict[str, Any]:
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    errors = validate_work_package_policy(payload)
    if errors:
        raise PilotError(errors[0])
    return payload


def validate_work_package_policy(policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if (
        policy.get("schema_version") != "1.0"
        or policy.get("policy_type") != "lightyear-pilot-work-package-policy"
    ):
        errors.append("work-package-policy-identity-invalid")
    if policy.get("content_sha256") != canonical_hash(
        dict(policy), {"content_sha256"}
    ):
        errors.append("work-package-policy-content-hash-invalid")
    technologies = policy.get("technologies")
    expected = {
        "CICS",
        "COBOL",
        "Configuration",
        "Db2",
        "HLASM",
        "IMS",
        "JCL",
        "PL/I",
        "VSAM",
    }
    if not isinstance(technologies, dict) or set(technologies) != expected:
        errors.append("work-package-policy-technology-matrix-incomplete")
    else:
        for name, item in technologies.items():
            if not isinstance(item, dict):
                errors.append(f"work-package-policy-technology-invalid:{name}")
                continue
            if item.get("risk") not in {"medium", "high", "critical"}:
                errors.append(f"work-package-policy-risk-invalid:{name}")
            for field in ("deliverables", "acceptance_evidence", "live_evidence"):
                try:
                    _nonempty_strings(
                        item.get(field),
                        f"work-package-policy-{field.replace('_', '-')}-invalid:{name}",
                    )
                except PilotError as error:
                    errors.append(str(error))
    if policy.get("dispatch_boundary") != {
        "draft_work_scopes_only": True,
        "signed_work_order_required": True,
        "automatic_dispatch": False,
        "native_execution": False,
        "production_release": False,
    }:
        errors.append("work-package-policy-dispatch-boundary-invalid")
    max_parallel = policy.get("max_parallel")
    if (
        isinstance(max_parallel, bool)
        or not isinstance(max_parallel, int)
        or not 1 <= max_parallel <= 16
    ):
        errors.append("work-package-policy-max-parallel-invalid")
    return sorted(set(errors))


def _node_path(node: Mapping[str, Any]) -> str | None:
    properties = node.get("properties")
    if isinstance(properties, dict) and isinstance(properties.get("path"), str):
        return properties["path"]
    evidence = node.get("evidence")
    if isinstance(evidence, list):
        paths = sorted(
            {
                str(item.get("path"))
                for item in evidence
                if isinstance(item, dict) and item.get("path")
            }
        )
        if len(paths) == 1:
            return paths[0]
    return None


def _technology(node: Mapping[str, Any]) -> str | None:
    from .planner import _technology as planner_technology

    return planner_technology(node)


def build_work_package(
    selection: Mapping[str, Any],
    assessment: Mapping[str, Any],
    analysis_graph: Mapping[str, Any],
    dossier: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    policy_errors = validate_work_package_policy(policy)
    if policy_errors:
        raise PilotError(policy_errors[0])
    if selection.get("content_sha256") != canonical_hash(
        dict(selection), {"content_sha256"}
    ):
        raise PilotError("work-package-selection-content-hash-invalid")
    if selection.get("assessment_sha256") != assessment.get("content_sha256"):
        raise PilotError("work-package-selection-assessment-binding-invalid")
    if selection.get("dossier_sha256") != dossier.get("content_sha256"):
        raise PilotError("work-package-selection-dossier-binding-invalid")
    if selection.get("selection_ready") is not True or selection.get(
        "authorization", {}
    ).get("work_package_generation_allowed") is not True:
        raise PilotError("work-package-selection-not-ready")
    if any(
        selection.get("authorization", {}).get(name) is not False
        for name in (
            "factory_dispatch_allowed",
            "native_execution_allowed",
            "production_release_allowed",
        )
    ):
        raise PilotError("work-package-selection-overclaims-authorization")
    if any(
        selection.get("claim_boundary", {}).get(name) is not False
        for name in (
            "approval_identity_cryptographically_verified",
            "work_order_admitted",
            "authorized_execution_observed",
            "mainframe_equivalent",
            "production_ready",
        )
    ):
        raise PilotError("work-package-selection-overclaims-readiness")
    cluster = _cluster(
        assessment, str(selection.get("selected_cluster", {}).get("cluster_id", ""))
    )
    expected_cluster = {
        "cluster_id": cluster["cluster_id"],
        "label": cluster["label"],
        "source_files": list(cluster["source_files"]),
        "node_ids": list(cluster["node_ids"]),
        "technologies": list(cluster["technologies"]),
        "unresolved_reference_ids": sorted(
            _reference_id(item) for item in cluster["unresolved_references"]
        ),
    }
    if selection.get("selected_cluster") != expected_cluster:
        raise PilotError("work-package-selection-cluster-scope-drift")
    if analysis_graph.get("content_sha256") != assessment.get("graph_content_sha256"):
        raise PilotError("work-package-analysis-graph-binding-invalid")

    nodes = {
        str(item["id"]): item
        for item in analysis_graph.get("nodes", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    cluster_nodes = set(cluster["node_ids"])
    technology_nodes: dict[str, set[str]] = {
        name: set() for name in cluster["technologies"]
    }
    for node_id in cluster_nodes:
        node = nodes.get(node_id)
        if node is None:
            raise PilotError("work-package-cluster-node-missing")
        technology = _technology(node)
        if technology in technology_nodes:
            technology_nodes[technology].add(node_id)
    if any(not node_ids for node_ids in technology_nodes.values()):
        raise PilotError("work-package-selected-technology-has-no-graph-node")

    dependency_technologies: dict[str, set[str]] = {
        name: set() for name in technology_nodes
    }
    for edge in analysis_graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source_id, target_id = edge.get("source"), edge.get("target")
        if source_id not in cluster_nodes or target_id not in cluster_nodes:
            continue
        source_technology = _technology(nodes[source_id])
        target_technology = _technology(nodes[target_id])
        if (
            source_technology in dependency_technologies
            and target_technology in dependency_technologies
            and source_technology != target_technology
        ):
            dependency_technologies[source_technology].add(target_technology)

    package_slug = _slug(str(selection["selection_id"]))
    cell_ids = {
        name: f"cell:{package_slug}:{_slug(name)}" for name in technology_nodes
    }
    cells: list[dict[str, Any]] = []
    for technology in sorted(technology_nodes):
        tech_policy = policy["technologies"][technology]
        node_ids = sorted(technology_nodes[technology])
        source_files = sorted(
            {
                path
                for node_id in node_ids
                if (path := _node_path(nodes[node_id])) is not None
            }
        )
        if not source_files:
            source_files = list(cluster["source_files"])
        output_root = _safe_path(f"pilot/work/{package_slug}/{_slug(technology)}")
        cells.append(
            {
                "cell_id": cell_ids[technology],
                "technology": technology,
                "risk": tech_policy["risk"],
                "goal": f"Materialize the bounded {technology} development proof for {cluster['label']}.",
                "read_only_source_paths": [_safe_path(item) for item in source_files],
                "graph_node_ids": node_ids,
                "coordination_dependencies": sorted(
                    cell_ids[item] for item in dependency_technologies[technology]
                ),
                "allowed_output_root": output_root,
                "required_deliverables": list(tech_policy["deliverables"]),
                "required_acceptance_evidence": list(
                    tech_policy["acceptance_evidence"]
                ),
                "required_live_evidence": list(tech_policy["live_evidence"]),
                "work_order_status": "draft-scope-not-admitted",
                "dispatch_ready": False,
            }
        )

    boundary_ids = [
        item["reference_id"] for item in selection["boundary_dispositions"]
    ]
    payload: dict[str, Any] = {
        "schema_version": WORK_PACKAGE_SCHEMA_VERSION,
        "work_package_type": WORK_PACKAGE_TYPE,
        "package_id": f"package:{package_slug}",
        "selection_sha256": str(selection["content_sha256"]),
        "assessment_sha256": str(assessment["content_sha256"]),
        "analysis_graph_sha256": str(analysis_graph["content_sha256"]),
        "dossier_sha256": str(dossier["content_sha256"]),
        "policy_sha256": str(policy["content_sha256"]),
        "selected_cluster_id": str(cluster["cluster_id"]),
        "source_scope": {
            "files": list(cluster["source_files"]),
            "node_ids": list(cluster["node_ids"]),
            "technologies": list(cluster["technologies"]),
            "boundary_reference_ids": sorted(boundary_ids),
        },
        "cells": cells,
        "planning_waves": [
            {
                "wave": 0,
                "name": "boundary-disposition-verification",
                "cell_ids": [],
                "status": "passed",
                "automatic_dispatch": False,
            },
            {
                "wave": 1,
                "name": "bounded-work-order-authoring",
                "cell_ids": sorted(cell_ids.values()),
                "status": "ready-for-human-governed-authoring",
                "automatic_dispatch": False,
            },
            {
                "wave": 2,
                "name": "integrated-development-proof",
                "cell_ids": sorted(cell_ids.values()),
                "status": "blocked-until-cell-evidence-passes",
                "automatic_dispatch": False,
            },
            {
                "wave": 3,
                "name": "authorized-native-validation",
                "cell_ids": sorted(cell_ids.values()),
                "status": "blocked-no-mainframe-access",
                "automatic_dispatch": False,
            },
        ],
        "portfolio_policy": {
            "max_parallel": int(policy.get("max_parallel", 2)),
            "human_approval_required": True,
            "signed_work_orders_required": True,
            "conflict_analysis_required": True,
            "automatic_dispatch": False,
        },
        "work_package_ready": True,
        "factory_dispatch_allowed": False,
        "authorized_execution_observed": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can turn one recorded human pilot selection into a deterministic, graph-scoped, multi-technology development work package.",
        "limitations": [
            "Cells are bounded draft scopes, not signed or admitted factory work orders.",
            "No candidate, behavior comparison, model qualification, or native execution is created by packaging.",
            "Every cell retains a separate live-evidence backlog and remains blocked from production promotion.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_work_package(
    package: Mapping[str, Any],
    selection: Mapping[str, Any],
    assessment: Mapping[str, Any],
    analysis_graph: Mapping[str, Any],
    dossier: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if (
        package.get("schema_version") != WORK_PACKAGE_SCHEMA_VERSION
        or package.get("work_package_type") != WORK_PACKAGE_TYPE
    ):
        errors.append("work-package-contract-identity-invalid")
    if package.get("content_sha256") != canonical_hash(
        dict(package), {"content_sha256"}
    ):
        errors.append("work-package-content-hash-invalid")
    if any(
        package.get(name) is not False
        for name in (
            "factory_dispatch_allowed",
            "authorized_execution_observed",
            "mainframe_equivalent",
            "production_ready",
        )
    ):
        errors.append("work-package-overclaims-readiness")
    cells = package.get("cells")
    if not isinstance(cells, list) or not cells:
        errors.append("work-package-cells-missing")
    elif any(
        not isinstance(item, dict)
        or item.get("work_order_status") != "draft-scope-not-admitted"
        or item.get("dispatch_ready") is not False
        for item in cells
    ):
        errors.append("work-package-cell-admission-boundary-invalid")
    try:
        rebuilt = build_work_package(
            selection, assessment, analysis_graph, dossier, policy
        )
        if package != rebuilt:
            errors.append("work-package-no-longer-matches-bound-inputs")
    except PilotError as error:
        errors.append(str(error))
    return sorted(set(errors))


def render_work_package_markdown(package: Mapping[str, Any]) -> str:
    rows = [
        "# LIGHTYEAR governed pilot work package",
        "",
        f"**Package identity:** `{package['content_sha256']}`",
        "",
        "## Outcome",
        "",
        str(package["claim_unlocked"]),
        "",
        "This package is ready for human-governed work-order authoring. It cannot dispatch the factory, authorize native execution, or approve production.",
        "",
        "## Development cells",
        "",
        "| Cell | Technology | Risk | Source files | Dependencies | Dispatch ready |",
        "|---|---|---|---:|---:|---:|",
    ]
    for cell in package["cells"]:
        rows.append(
            f"| `{cell['cell_id']}` | {cell['technology']} | {cell['risk']} | "
            f"{len(cell['read_only_source_paths'])} | {len(cell['coordination_dependencies'])} | no |"
        )
    rows.extend(["", "## Planning waves", ""])
    for wave in package["planning_waves"]:
        rows.append(
            f"- **Wave {wave['wave']} — {wave['name']}:** {wave['status']}; automatic dispatch is disabled."
        )
    rows.extend(["", "## Limitations", ""])
    rows.extend(f"- {item}" for item in package["limitations"])
    return "\n".join(rows) + "\n"
