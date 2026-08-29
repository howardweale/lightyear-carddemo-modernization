from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any, Mapping

from .pilot import PilotError, canonical_hash


ASSESSMENT_SCHEMA_VERSION = "1.0"
ASSESSMENT_TYPE = "lightyear-customer-estate-assessment"

_TECHNOLOGY_BY_KIND = {
    "assembler_dsect": "HLASM",
    "assembler_instruction": "HLASM",
    "assembler_program": "HLASM",
    "assembler_symbol": "HLASM",
    "cics_program_resource": "CICS",
    "cics_transaction": "CICS",
    "cobol_program": "COBOL",
    "copybook": "COBOL",
    "db2_column": "Db2",
    "db2_constraint": "Db2",
    "db2_index": "Db2",
    "db2_sql_statement": "Db2",
    "db2_table": "Db2",
    "ims_database": "IMS",
    "ims_dataset_group": "IMS",
    "ims_field": "IMS",
    "ims_pcb": "IMS",
    "ims_psb": "IMS",
    "ims_segment": "IMS",
    "jcl_job": "JCL",
    "jcl_step": "JCL",
    "pli_program": "PL/I",
    "vsam_alternate_index": "VSAM",
    "vsam_cluster": "VSAM",
    "vsam_component": "VSAM",
    "vsam_path": "VSAM",
}

_TECHNOLOGY_BY_INTAKE = {
    "cobol": "COBOL",
    "copybook": "COBOL",
    "db2-ddl": "Db2",
    "hlasm": "HLASM",
    "ims": "IMS",
    "jcl": "JCL",
    "pli": "PL/I",
    "system-configuration": "Configuration",
    "vsam": "VSAM",
}


def load_assessment_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PilotError("assessment-policy-object-required")
    errors = validate_assessment_policy(payload)
    if errors:
        raise PilotError(errors[0])
    return payload


def validate_assessment_policy(policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != "1.0" or policy.get("policy_type") != "lightyear-estate-assessment-policy":
        errors.append("assessment-policy-identity-invalid")
    if policy.get("content_sha256") != canonical_hash(policy, {"content_sha256"}):
        errors.append("assessment-policy-content-hash-invalid")
    technologies = policy.get("technologies")
    required = set(_TECHNOLOGY_BY_KIND.values()) | set(_TECHNOLOGY_BY_INTAKE.values())
    if not isinstance(technologies, dict) or set(technologies) != required:
        errors.append("assessment-policy-technology-matrix-incomplete")
    else:
        for name, item in technologies.items():
            if not isinstance(item, dict) or not all(
                isinstance(item.get(field), str) and item[field]
                for field in ("modernization_pattern", "required_development_evidence", "required_live_evidence")
            ):
                errors.append(f"assessment-policy-technology-invalid:{name}")
    if policy.get("planning_rules") != {
        "connected_components_define_candidate_slices": True,
        "unresolved_references_enter_boundary_closure": True,
        "business_priority_requires_human_input": True,
        "static_analysis_cannot_authorize_execution": True,
    }:
        errors.append("assessment-policy-planning-rules-invalid")
    return sorted(set(errors))


def _components(graph: Mapping[str, Any]) -> list[list[str]]:
    nodes = {str(item["id"]): item for item in graph.get("nodes", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
    adjacency = {node_id: set() for node_id in nodes}
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("source", "")), str(edge.get("target", ""))
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)
    components: list[list[str]] = []
    visited: set[str] = set()
    for start in sorted(nodes):
        if start in visited:
            continue
        queue = deque([start])
        visited.add(start)
        component: list[str] = []
        while queue:
            node_id = queue.popleft()
            component.append(node_id)
            for neighbor in sorted(adjacency[node_id]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda value: (min(value), len(value)))


def _node_path(node: Mapping[str, Any]) -> str | None:
    properties = node.get("properties")
    if isinstance(properties, dict) and isinstance(properties.get("path"), str):
        return properties["path"]
    evidence = node.get("evidence")
    if isinstance(evidence, list):
        paths = sorted({str(item.get("path")) for item in evidence if isinstance(item, dict) and item.get("path")})
        if len(paths) == 1:
            return paths[0]
    return None


def _technology(node: Mapping[str, Any]) -> str | None:
    kind = str(node.get("kind", ""))
    if kind == "source_file":
        properties = node.get("properties", {})
        return _TECHNOLOGY_BY_INTAKE.get(str(properties.get("intake_kind", ""))) if isinstance(properties, dict) else None
    return _TECHNOLOGY_BY_KIND.get(kind)


def build_estate_assessment(
    graph: Mapping[str, Any],
    analysis: Mapping[str, Any],
    intake: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    policy_errors = validate_assessment_policy(policy)
    if policy_errors:
        raise PilotError(policy_errors[0])
    if analysis.get("graph_content_sha256") != graph.get("content_sha256"):
        raise PilotError("assessment-analysis-graph-binding-invalid")
    if analysis.get("intake_sha256") != intake.get("content_sha256"):
        raise PilotError("assessment-analysis-intake-binding-invalid")

    node_by_id = {str(item["id"]): item for item in graph.get("nodes", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
    edges = [item for item in graph.get("edges", []) if isinstance(item, dict)]
    unresolved = [item for item in analysis.get("unresolved_references", []) if isinstance(item, dict)]
    technology_policy = policy["technologies"]
    clusters: list[dict[str, Any]] = []

    for component in _components(graph):
        component_set = set(component)
        component_edges = [edge for edge in edges if edge.get("source") in component_set and edge.get("target") in component_set]
        paths = sorted({path for node_id in component if (path := _node_path(node_by_id[node_id]))})
        technologies = sorted({tech for node_id in component if (tech := _technology(node_by_id[node_id]))})
        component_unresolved = sorted(
            (dict(item) for item in unresolved if item.get("path") in paths),
            key=lambda item: (str(item.get("path")), int(item.get("line", 0)), str(item.get("kind")), str(item.get("name"))),
        )
        cluster_digest = hashlib.sha256("\n".join(component).encode("utf-8")).hexdigest()[:16]
        anchor = Path(paths[0]).stem.upper() if paths else cluster_digest.upper()
        findings: list[dict[str, str]] = []
        if component_unresolved:
            findings.append({
                "code": "BOUNDARY_INCOMPLETE",
                "severity": "high",
                "finding": f"{len(component_unresolved)} referenced target(s) are absent or ambiguous in the approved intake.",
            })
        if len(technologies) >= 4:
            findings.append({
                "code": "CROSS_TECHNOLOGY_COUPLING",
                "severity": "high",
                "finding": f"The slice connects {len(technologies)} technologies and should be tested as a coordinated unit.",
            })
        native = sorted(set(technologies) & {"CICS", "Db2", "HLASM", "IMS", "VSAM"})
        if native:
            findings.append({
                "code": "NATIVE_RUNTIME_EVIDENCE_REQUIRED",
                "severity": "medium",
                "finding": f"Static source cannot establish native runtime behavior for {', '.join(native)}.",
            })
        if not findings:
            findings.append({
                "code": "STATIC_BOUNDARY_IDENTIFIED",
                "severity": "low",
                "finding": "The connected source boundary is complete within the approved intake; behavior remains unproven.",
            })

        modernization_patterns = sorted({technology_policy[name]["modernization_pattern"] for name in technologies})
        development_evidence = sorted({technology_policy[name]["required_development_evidence"] for name in technologies})
        live_evidence = sorted({technology_policy[name]["required_live_evidence"] for name in technologies})
        clusters.append({
            "cluster_id": f"cluster:{cluster_digest}",
            "label": f"{anchor} connected application slice",
            "node_count": len(component),
            "relationship_count": len(component_edges),
            "node_ids": component,
            "source_files": paths,
            "technologies": technologies,
            "relationship_types": sorted({str(edge.get("relation")) for edge in component_edges}),
            "unresolved_references": component_unresolved,
            "findings": findings,
            "modernization_patterns": modernization_patterns,
            "required_development_evidence": development_evidence,
            "required_live_evidence": live_evidence,
            "selection_posture": {
                "candidate": True,
                "automatically_approved": False,
                "business_priority_known": False,
                "human_decision_required": True,
            },
        })

    clusters.sort(key=lambda item: item["cluster_id"])
    incomplete = [item["cluster_id"] for item in clusters if item["unresolved_references"]]
    all_clusters = [item["cluster_id"] for item in clusters]
    waves = [
        {
            "wave": 0,
            "name": "boundary-closure",
            "cluster_ids": incomplete,
            "exit_criteria": "Referenced source targets are supplied or explicitly accepted as external boundaries.",
            "automatic_dispatch": False,
        },
        {
            "wave": 1,
            "name": "human-pilot-selection",
            "cluster_ids": all_clusters,
            "exit_criteria": "After required boundary closure, a business owner selects a bounded slice and approves success criteria and data policy.",
            "automatic_dispatch": False,
        },
        {
            "wave": 2,
            "name": "development-proof",
            "cluster_ids": all_clusters,
            "exit_criteria": "Selected slices have executable contracts, candidates, differential checks, and negative tests.",
            "automatic_dispatch": False,
        },
        {
            "wave": 3,
            "name": "authorized-native-validation",
            "cluster_ids": all_clusters,
            "exit_criteria": "Customer-authorized original execution and independently signed comparison evidence exist.",
            "automatic_dispatch": False,
            "status": "blocked",
        },
    ]
    evidence_backlog = sorted({
        f"Resolve {item.get('kind')} {item.get('name')} referenced by {item.get('path')}:{item.get('line')}"
        for item in unresolved
    } | {
        requirement
        for cluster in clusters
        for requirement in cluster["required_live_evidence"]
    })
    payload: dict[str, Any] = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "assessment_type": ASSESSMENT_TYPE,
        "pilot_id": str(intake.get("pilot_id", "")),
        "intake_sha256": str(intake.get("content_sha256", "")),
        "analysis_sha256": str(analysis.get("content_sha256", "")),
        "graph_content_sha256": str(graph.get("content_sha256", "")),
        "assessment_policy_sha256": str(policy.get("content_sha256", "")),
        "method": "deterministic-undirected-connected-components",
        "statistics": {
            "clusters": len(clusters),
            "clusters_with_unresolved_references": len(incomplete),
            "candidate_source_files": len({path for cluster in clusters for path in cluster["source_files"]}),
            "technologies": sorted({technology for cluster in clusters for technology in cluster["technologies"]}),
        },
        "clusters": clusters,
        "planning_waves": waves,
        "evidence_backlog": evidence_backlog,
        "decision_boundary": {
            "advisory_plan_only": True,
            "business_priority_inferred": False,
            "automatic_factory_dispatch": False,
            "authorized_execution_observed": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        },
        "claim_unlocked": "LIGHTYEAR can partition an approved source estate into explainable connected slices and produce an evidence-first modernization planning backlog.",
        "limitations": [
            "Connected components describe static coupling, not business criticality, transaction volume, runtime behavior, or ownership.",
            "The planner does not automatically approve or dispatch modernization work.",
            "Live original-system execution and signed equivalence remain blocked until separately authorized and observed.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_estate_assessment(
    assessment: Mapping[str, Any],
    graph: Mapping[str, Any],
    analysis: Mapping[str, Any],
    intake: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if assessment.get("schema_version") != ASSESSMENT_SCHEMA_VERSION or assessment.get("assessment_type") != ASSESSMENT_TYPE:
        errors.append("assessment-contract-identity-invalid")
    expected_bindings = (
        assessment.get("intake_sha256") == intake.get("content_sha256")
        and assessment.get("analysis_sha256") == analysis.get("content_sha256")
        and assessment.get("graph_content_sha256") == graph.get("content_sha256")
        and assessment.get("assessment_policy_sha256") == policy.get("content_sha256")
    )
    if not expected_bindings:
        errors.append("assessment-input-binding-invalid")
    if assessment.get("content_sha256") != canonical_hash(assessment, {"content_sha256"}):
        errors.append("assessment-content-hash-invalid")
    boundary = assessment.get("decision_boundary")
    if boundary != {
        "advisory_plan_only": True,
        "business_priority_inferred": False,
        "automatic_factory_dispatch": False,
        "authorized_execution_observed": False,
        "mainframe_equivalent": False,
        "production_ready": False,
    }:
        errors.append("assessment-overclaims-decision-or-live-readiness")
    clusters = assessment.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        errors.append("assessment-clusters-missing")
    elif any(item.get("selection_posture", {}).get("human_decision_required") is not True for item in clusters if isinstance(item, dict)):
        errors.append("assessment-cluster-selection-not-human-governed")
    try:
        rebuilt = build_estate_assessment(graph, analysis, intake, policy)
        if assessment != rebuilt:
            errors.append("assessment-no-longer-matches-bound-estate")
    except PilotError as error:
        errors.append(str(error))
    return sorted(set(errors))


def render_assessment_markdown(assessment: Mapping[str, Any]) -> str:
    rows = [
        "# LIGHTYEAR customer estate assessment",
        "",
        f"**Assessment identity:** `{assessment['content_sha256']}`",
        "",
        "## Result",
        "",
        assessment["claim_unlocked"],
        "",
        "The plan is advisory. Business priority is not inferred, factory dispatch is disabled, and live validation remains blocked.",
        "",
        "## Connected application slices",
        "",
        "| Slice | Source files | Technologies | Nodes | Unresolved | Human decision |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for cluster in assessment["clusters"]:
        rows.append(
            f"| {cluster['label']} (`{cluster['cluster_id']}`) | {len(cluster['source_files'])} | "
            f"{', '.join(cluster['technologies'])} | {cluster['node_count']} | "
            f"{len(cluster['unresolved_references'])} | required |"
        )
    rows.extend(["", "## Planning waves", ""])
    for wave in assessment["planning_waves"]:
        status = f" — **{wave['status']}**" if wave.get("status") else ""
        rows.append(f"### Wave {wave['wave']}: {wave['name']}{status}")
        rows.append("")
        rows.append(wave["exit_criteria"])
        rows.append("")
        rows.append("Affected slices: " + (", ".join(f"`{value}`" for value in wave["cluster_ids"]) or "none"))
        rows.append("")
    rows.extend(["## Evidence backlog", ""])
    rows.extend(f"- {item}" for item in assessment["evidence_backlog"])
    rows.extend(["", "## Limitations", ""])
    rows.extend(f"- {item}" for item in assessment["limitations"])
    return "\n".join(rows) + "\n"
