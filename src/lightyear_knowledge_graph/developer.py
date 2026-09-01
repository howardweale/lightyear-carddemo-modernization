from __future__ import annotations

import hashlib
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from .composite import load_json, validate_composite_estate
from .explorer import GraphExplorerIndex
from .inputs import load_semantic_inputs
from .model import load_graph
from lightyear_common.pli_build_trust import trusted_development_attestation


def doctor(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    checks = []
    checks.append(
        _check(
            "python",
            sys.version_info >= (3, 11),
            f"{platform.python_implementation()} {platform.python_version()}",
            required=True,
            remediation="Install Python 3.11 or newer and rerun the command.",
        )
    )
    for name, required in (("git", True), ("java", False), ("javac", False), ("mvn", False), ("docker", False)):
        location = shutil.which(name)
        checks.append(
            _check(
                name,
                location is not None,
                location or "not found",
                required=required,
                remediation=(
                    f"Install {name} before running the Java/container-specific verification path."
                    if not required
                    else f"Install {name} and ensure it is on PATH."
                ),
            )
        )

    paths = {
        "semantic_inputs": root / "knowledge" / "semantic-inputs.json",
        "canonical_graph": root / "knowledge" / "graph.snapshot.json.gz",
        "pli_fragment": root / "extensions" / "pli" / "pli.fragment.json",
        "oracle_reference_fragment": root / "reference-estates" / "idempiere" / "oracle-customer-large.fragment.json",
        "cloudbank_reference_fragment": root / "reference-estates" / "cloudbank" / "cloudbank-reference.fragment.json",
        "pli_coverage": root / "extensions" / "pli" / "conformance" / "coverage.receipt.json",
        "pli_build_receipt": root / "extensions" / "pli" / "attestation" / "build.receipt.json",
        "pli_build_attestation": root / "extensions" / "pli" / "attestation" / "build.attestation.json",
        "capabilities": root / "knowledge" / "capabilities" / "mainframe-readiness.json",
        "composite_estate": root / "knowledge" / "composite" / "estate.snapshot.json.gz",
        "composite_evidence": root / "knowledge" / "composite" / "source.pack.json.gz",
    }
    for name, path in paths.items():
        checks.append(
            _check(
                name,
                path.is_file(),
                str(path.relative_to(root)) if path.is_file() else "missing",
                required=True,
                remediation="Run ./lightyear.sh verify to rebuild and validate committed evidence.",
            )
        )

    structural_errors: list[str] = []
    try:
        load_semantic_inputs(paths["semantic_inputs"], root)
        base = load_graph(paths["canonical_graph"])
        fragment = load_json(paths["pli_fragment"])
        oracle_reference_fragment = load_json(paths["oracle_reference_fragment"])
        cloudbank_reference_fragment = load_json(paths["cloudbank_reference_fragment"])
        coverage = load_json(paths["pli_coverage"])
        build_receipt = load_json(paths["pli_build_receipt"])
        build_attestation = load_json(paths["pli_build_attestation"])
        capabilities = load_json(paths["capabilities"])
        composite = load_graph(paths["composite_estate"])
        structural_errors = validate_composite_estate(
            composite,
            base,
            [fragment, oracle_reference_fragment, cloudbank_reference_fragment],
            capabilities,
        )
        coverage_body = {key: value for key, value in coverage.items() if key != "content_sha256"}
        coverage_hash = hashlib.sha256(
            json.dumps(coverage_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if coverage.get("content_sha256") != coverage_hash:
            structural_errors.append("PL/I conformance coverage receipt hash is invalid")
        if capabilities.get("evidence_bindings", {}).get("pli_coverage_receipt_sha256") != coverage_hash:
            structural_errors.append("Capability projection does not bind the PL/I coverage receipt")
        receipt_hash = _canonical_hash(build_receipt)
        attestation_hash = _canonical_hash(build_attestation)
        if build_receipt.get("content_sha256") != receipt_hash:
            structural_errors.append("PL/I build attestation receipt hash is invalid")
        if build_attestation.get("content_sha256") != attestation_hash or not trusted_development_attestation(build_attestation):
            structural_errors.append("PL/I build attestation signature or identity is invalid")
        bindings = capabilities.get("evidence_bindings", {})
        if bindings.get("pli_build_receipt_sha256") != receipt_hash or bindings.get("pli_build_attestation_sha256") != attestation_hash:
            structural_errors.append("Capability projection does not bind the PL/I build attestation")
        artifact_bindings = build_receipt.get("bindings", {})
        for binding, filename in (
            ("candidate_jar_sha256", "pli-auth-risk-candidate.jar"),
            ("junit_xml_sha256", "TEST-MixedPliAuthorizationAttestation.xml"),
            ("dependency_inventory_sha256", "dependencies.json"),
            ("sbom_sha256", "sbom.cdx.json"),
        ):
            artifact = paths["pli_build_receipt"].parent / filename
            if not artifact.is_file() or artifact_bindings.get(binding) != hashlib.sha256(artifact.read_bytes()).hexdigest():
                structural_errors.append(f"PL/I build artifact is missing or tampered: {filename}")
    except (OSError, ValueError, KeyError) as exc:
        structural_errors = [str(exc)]
    checks.append(
        _check(
            "evidence_contracts",
            not structural_errors,
            "valid" if not structural_errors else "; ".join(structural_errors[:3]),
            required=True,
            remediation="Run ./lightyear.sh verify and inspect the first fail-closed error.",
        )
    )

    failed_required = [item["id"] for item in checks if item["required"] and not item["passed"]]
    optional_missing = [item["id"] for item in checks if not item["required"] and not item["passed"]]
    return {
        "status": "passed" if not failed_required else "failed",
        "project_root": str(root),
        "checks": checks,
        "failed_required": failed_required,
        "optional_missing": optional_missing,
        "next": (
            "Run ./lightyear.sh demo to inspect the bounded composite lineage."
            if not failed_required
            else "Apply the remediation for the first failed required check, then rerun doctor."
        ),
    }


def demo(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    composite_path = root / "knowledge" / "composite" / "estate.snapshot.json.gz"
    payload = load_graph(composite_path)
    index = GraphExplorerIndex(payload, max_nodes=100)
    pli = "extension:pli-program:ACCTPL1"
    cobol = "legacy:cobol-program:CBACT04C"
    table = "legacy:db2-table:CARDDEMO.AUTHFRDS"
    if not all(node in index.node_by_id for node in (pli, cobol, table)):
        raise ValueError("Composite estate is missing the bounded PL/I, COBOL, or Db2 lineage root")
    cobol_trace = index.trace(pli, cobol, audience="implementer")
    data_trace = index.trace(pli, table, audience="implementer")
    if cobol_trace is None or data_trace is None:
        raise ValueError("Composite estate does not connect ACCTPL1 to both COBOL and Db2")
    return {
        "status": "passed",
        "projection_type": payload["projection_type"],
        "composite_content_sha256": payload["content_sha256"],
        "canonical_content_sha256": index.canonical_content_sha256,
        "statistics": payload["statistics"],
        "bounded_lineage": {
            "pli_to_cobol": _trace_summary(cobol_trace),
            "pli_to_db2": _trace_summary(data_trace),
        },
        "claim_boundary": payload["claim_boundary"],
        "next": "Run ./lightyear.sh explorer to navigate the read-only estate view.",
    }


def _check(
    identifier: str,
    passed: bool,
    observed: str,
    *,
    required: bool,
    remediation: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "passed": passed,
        "required": required,
        "observed": observed,
        "remediation": None if passed else remediation,
    }


def _trace_summary(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_ids": trace["node_ids"],
        "relations": [edge["relation"] for edge in trace["edges"]],
        "evidence_paths": sorted(
            {
                item["path"]
                for edge in trace["edges"]
                for item in edge.get("evidence", [])
            }
        ),
    }


def _canonical_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
