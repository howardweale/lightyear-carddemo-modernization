from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json
from lightyear_common.pli_build_trust import EXPECTED_WORKFLOW, trusted_development_attestation


GATE_NAMES = {
    1: "typed native asset parsing",
    2: "connected dependency and control-flow graph",
    3: "curated behavior contract",
    4: "bounded modernization candidate",
    5: "mutation and negative verification",
    6: "authorized execution of the original on z/OS",
    7: "independent differential comparison",
    8: "signed equivalence receipt with unresolved gaps",
}


def _canonical_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _unsigned_hash(payload: dict[str, Any]) -> str:
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"content_sha256", "signature"}
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _gate(number: int, status: str, evidence: list[str], gap: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "gate": number,
        "name": GATE_NAMES[number],
        "status": status,
        "evidence": sorted(evidence),
    }
    if gap:
        result["gap"] = gap
    return result


def _hashed_and_bound(payload: dict[str, Any], graph_sha256: str) -> bool:
    return bool(
        payload
        and payload.get("content_sha256") == _canonical_hash(payload)
        and payload.get("base_graph", {}).get("content_sha256") == graph_sha256
    )


def _offline_data_receipt_passed(payload: dict[str, Any], target: str) -> bool:
    checks = payload.get("checks", {})
    expected_checks = {
        "keys_and_constraints",
        "query_results",
        "row_counts_and_checksums",
        "schema_structure",
        "transaction_commit",
        "transaction_rollback",
    }
    return bool(
        payload.get("receipt_type") == "factorydark-data-equivalence"
        and payload.get("evidence_class") == "offline-db2-to-target-development-proof"
        and payload.get("target") == target
        and payload.get("status") == "passed"
        and payload.get("production_ready") is False
        and payload.get("content_sha256") == _unsigned_hash(payload)
        and set(checks) == expected_checks
        and all(value is True for value in checks.values())
    )


def _pli_development_receipt_passed(
    payload: dict[str, Any], graph_sha256: str, fragment_sha256: str | None
) -> bool:
    checks = payload.get("checks", {})
    expected_checks = {
        "bounded_candidate",
        "curated_behavior_contract",
        "db2_lookup_contract",
        "differential_behavior_match",
        "live_zos_baseline",
        "mixed_language_call_contract",
        "mutation_and_negative_verification",
        "typed_static_graph",
    }
    bindings = payload.get("bindings", {})
    return bool(
        payload.get("receipt_type") == "lightyear-pli-mixed-development-proof"
        and payload.get("evidence_class") == "local_observed"
        and payload.get("status") == "passed"
        and payload.get("development_ready") is True
        and payload.get("mainframe_equivalent") is False
        and payload.get("production_ready") is False
        and payload.get("content_sha256") == _canonical_hash(payload)
        and set(checks) == expected_checks
        and checks.get("live_zos_baseline") is False
        and all(checks.get(name) is True for name in expected_checks - {"live_zos_baseline"})
        and bindings.get("canonical_graph_sha256") == graph_sha256
        and bindings.get("pli_fragment_sha256") == fragment_sha256
    )


def _pli_build_attestation_passed(
    receipt: dict[str, Any], attestation: dict[str, Any], development_receipt_sha256: str | None
) -> bool:
    expected_checks = {
        "asymmetric_signature",
        "clean_source_tree",
        "compiled_candidate",
        "dependency_inventory",
        "junit_execution",
        "live_zos_baseline",
        "ms22_evidence_bound",
        "release_key_separation",
        "reproducible_build",
        "sbom",
        "source_commit_bound",
    }
    checks = receipt.get("checks", {})
    bindings = receipt.get("bindings", {})
    subjects = {
        item.get("name"): item.get("digest", {}).get("sha256")
        for item in attestation.get("statement", {}).get("subject", [])
    }
    parameters = (
        attestation.get("statement", {})
        .get("predicate", {})
        .get("buildDefinition", {})
        .get("externalParameters", {})
    )
    return bool(
        receipt.get("schema_version") == "1.0"
        and receipt.get("receipt_type") == "lightyear-pli-build-attestation-receipt"
        and receipt.get("evidence_class") == "attested-local-build"
        and receipt.get("status") == "passed"
        and receipt.get("development_ready") is True
        and receipt.get("mainframe_equivalent") is False
        and receipt.get("production_ready") is False
        and receipt.get("release_attestation") is False
        and receipt.get("workflow") == EXPECTED_WORKFLOW
        and receipt.get("source_commit") == parameters.get("sourceCommit")
        and receipt.get("content_sha256") == _canonical_hash(receipt)
        and attestation.get("content_sha256") == _canonical_hash(attestation)
        and trusted_development_attestation(attestation)
        and bindings.get("build_attestation_sha256") == attestation.get("content_sha256")
        and bindings.get("development_receipt_sha256") == development_receipt_sha256
        and subjects.get("pli-auth-risk-candidate.jar") == bindings.get("candidate_jar_sha256")
        and subjects.get("TEST-MixedPliAuthorizationAttestation.xml") == bindings.get("junit_xml_sha256")
        and subjects.get("dependencies.json") == bindings.get("dependency_inventory_sha256")
        and subjects.get("sbom.cdx.json") == bindings.get("sbom_sha256")
        and set(checks) == expected_checks
        and checks.get("live_zos_baseline") is False
        and all(checks.get(name) is True for name in expected_checks - {"live_zos_baseline"})
    )


def _pli_coverage_receipt_passed(payload: dict[str, Any], graph_sha256: str) -> bool:
    checks = payload.get("checks", {})
    corpus = payload.get("corpus", {})
    coverage = payload.get("coverage", {})
    boundary = payload.get("claim_boundary", {})
    return bool(
        payload.get("receipt_type") == "lightyear-pli-discovery-conformance"
        and payload.get("evidence_class") == "synthetic-static-conformance"
        and payload.get("status") == "passed"
        and payload.get("content_sha256") == _canonical_hash(payload)
        and payload.get("language_pack") == {"id": "lightyear.pli", "version": "1.2"}
        and payload.get("bindings", {}).get("canonical_graph_sha256") == graph_sha256
        and corpus.get("case_count", 0) >= 20
        and corpus.get("synthetic") is True
        and corpus.get("customer_source") is False
        and coverage.get("supported_matrix_construct_count", 0) >= 20
        and coverage.get("exercised_supported_construct_count")
        == coverage.get("supported_matrix_construct_count")
        and bool(checks)
        and all(value is True for value in checks.values())
        and boundary.get("static_discovery_only") is True
        and boundary.get("runtime_executed") is False
        and boundary.get("ibm_compiler_semantics_proven") is False
        and boundary.get("arbitrary_enterprise_pli_supported") is False
        and boundary.get("mainframe_equivalent") is False
        and boundary.get("production_ready") is False
        and payload.get("production_ready") is False
    )


def _capability(
    technology: str,
    capability_kind: str,
    gates: list[dict[str, Any]],
    breadth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    development_ready = all(item["status"] == "passed" for item in gates[:5])
    mainframe_equivalent = all(item["status"] == "passed" for item in gates)
    result = {
        "technology": technology,
        "capability_kind": capability_kind,
        "discovery_ready": all(item["status"] == "passed" for item in gates[:2]),
        "development_ready": development_ready,
        "mainframe_equivalent": mainframe_equivalent,
        "support_claim": (
            "mainframe-equivalent"
            if mainframe_equivalent
            else "development-proof; live z/OS evidence pending"
            if development_ready
            else "discovery and dependency analysis only"
        ),
        "gates": gates,
    }
    if breadth is not None:
        result["breadth"] = breadth
    return result


def analyze_capabilities(
    graph: dict[str, Any],
    cics_vsam_receipt: dict[str, Any] | None = None,
    asm_receipt: dict[str, Any] | None = None,
    ims_receipt: dict[str, Any] | None = None,
    pli_fragment: dict[str, Any] | None = None,
    extension_catalog: dict[str, Any] | None = None,
    pli_coverage_receipt: dict[str, Any] | None = None,
    pli_development_receipt: dict[str, Any] | None = None,
    pli_build_receipt: dict[str, Any] | None = None,
    pli_build_attestation: dict[str, Any] | None = None,
    postgres_data_receipt: dict[str, Any] | None = None,
    oracle_data_receipt: dict[str, Any] | None = None,
    campaign_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = {node["id"]: node for node in graph["nodes"]}
    kind_counts = graph["statistics"]["nodes_by_kind"]
    relation_counts = graph["statistics"]["edges_by_relation"]
    scenario_status = {
        node["id"]: node.get("properties", {}).get("status")
        for node in graph["nodes"]
        if node["kind"] == "verification_scenario"
    }
    rule_counts = {
        prefix: sum(
            node["kind"] == "business_rule" and node["id"].startswith(prefix)
            for node in graph["nodes"]
        )
        for prefix in ("rule:cics-vsam:", "rule:asm-date:", "rule:ims-expiry:")
    }

    receipt = cics_vsam_receipt or {}
    live_equivalent = bool(receipt.get("mainframe_equivalent"))
    receipt_status = "passed" if live_equivalent else "blocked"
    receipt_gap = None if live_equivalent else "A signed, authorized z/OS CAVW observation is not yet bound."

    cics_common = [
        _gate(1, "passed", [
            f"{kind_counts.get('cics_transaction', 0)} cics_transaction nodes",
            f"{kind_counts.get('cics_command', 0)} cics_command nodes",
            f"{kind_counts.get('bms_field', 0)} bms_field nodes",
        ]),
        _gate(2, "passed", [
            f"{relation_counts.get('STARTS_PROGRAM', 0)} STARTS_PROGRAM edges",
            f"{relation_counts.get('ISSUES', 0)} ISSUES edges",
            f"{relation_counts.get('USES_MAP', 0)} USES_MAP edges",
        ]),
        _gate(3, "passed", [f"{rule_counts['rule:cics-vsam:']} curated CICS/VSAM rules"]),
        _gate(4, "passed", ["modern:file:factory/benchmarks/cics_vsam_account_candidate.py"]),
        _gate(5, "passed", ["scenario:cics-vsam:private-mutation-gate"]),
        _gate(6, "passed" if live_equivalent else "blocked", ["readiness/cics-vsam/readiness-receipt.json"], receipt_gap),
        _gate(7, "passed" if live_equivalent else "mechanism_ready", ["readiness/cics-vsam/comparison.json"], receipt_gap),
        _gate(8, receipt_status, ["readiness/cics-vsam/readiness-receipt.json"], receipt_gap),
    ]
    vsam_common = [dict(item) for item in cics_common]
    vsam_common[0] = _gate(1, "passed", [
        f"{kind_counts.get('vsam_cluster', 0)} vsam_cluster nodes",
        f"{kind_counts.get('vsam_alternate_index', 0)} alternate indexes",
        f"{kind_counts.get('vsam_path', 0)} VSAM paths",
    ])
    vsam_common[1] = _gate(2, "passed", [
        f"{relation_counts.get('BACKED_BY', 0)} BACKED_BY edges",
        f"{relation_counts.get('TARGETS', 0)} TARGETS edges",
        f"{relation_counts.get('ACCESSES', 0)} CICS file access edges",
    ])

    asm_live = bool((asm_receipt or {}).get("mainframe_equivalent"))
    asm_gap = None if asm_live else "No authorized COBDATFT z/OS execution capture exists."
    asm_gates = [
        _gate(1, "passed", [
            f"{kind_counts.get('assembler_program', 0)} assembler programs",
            f"{kind_counts.get('assembler_instruction', 0)} assembler instructions",
            f"{kind_counts.get('assembler_dsect', 0)} DSECTs",
            f"{kind_counts.get('assembler_macro', 0)} macros",
        ]),
        _gate(2, "passed", [
            f"{relation_counts.get('BRANCHES_TO', 0)} BRANCHES_TO edges",
            f"{relation_counts.get('USES_DSECT', 0)} USES_DSECT edges",
            f"{relation_counts.get('USES_MACRO', 0)} USES_MACRO edges",
            "legacy:cobol-program:CBACT01C -> legacy:assembler-program:COBDATFT",
        ]),
        _gate(3, "passed", [f"{rule_counts['rule:asm-date:']} curated COBDATFT rules"]),
        _gate(4, "passed", ["modern:file:factory/benchmarks/asm_date_candidate.py"]),
        _gate(5, "passed", ["scenario:asm-date:private-mutation-gate"]),
        _gate(6, "passed" if asm_live else "blocked", ["readiness/asm-date/readiness-receipt.json"], asm_gap),
        _gate(7, "passed" if asm_live else "mechanism_ready", ["readiness/asm-date/comparison.json"], asm_gap),
        _gate(8, "passed" if asm_live else "blocked", ["readiness/asm-date/readiness-receipt.json"], asm_gap),
    ]

    ims_live = bool((ims_receipt or {}).get("mainframe_equivalent"))
    ims_gap = None if ims_live else "No authorized CBPAUP0C IMS BMP execution capture exists."
    ims_gates = [
        _gate(1, "passed", [
            f"{kind_counts.get('ims_database', 0)} IMS DBDs",
            f"{kind_counts.get('ims_psb', 0)} IMS PSBs",
            f"{kind_counts.get('ims_segment', 0)} IMS segments",
            f"{kind_counts.get('ims_pcb', 0)} IMS PCBs",
        ]),
        _gate(2, "passed", [
            f"{relation_counts.get('USES_DBD', 0)} USES_DBD edges",
            f"{relation_counts.get('SENSITIVE_TO', 0)} SENSITIVE_TO edges",
            f"{relation_counts.get('USES_PSB', 0)} program-to-PSB edges",
        ]),
        _gate(3, "passed", [f"{rule_counts['rule:ims-expiry:']} curated CBPAUP0C IMS rules"]),
        _gate(4, "passed", ["modern:file:factory/benchmarks/ims_expiry_candidate.py"]),
        _gate(5, "passed", ["scenario:ims-expiry:private-mutation-gate"]),
        _gate(6, "passed" if ims_live else "blocked", ["readiness/ims-expiry/readiness-receipt.json"], ims_gap),
        _gate(7, "passed" if ims_live else "mechanism_ready", ["readiness/ims-expiry/comparison.json"], ims_gap),
        _gate(8, "passed" if ims_live else "blocked", ["readiness/ims-expiry/readiness-receipt.json"], ims_gap),
    ]

    fragment = pli_fragment or {}
    catalog = extension_catalog or {}
    graph_sha256 = graph["content_sha256"]
    pli_cataloged = bool(
        catalog.get("content_sha256") == _canonical_hash(catalog)
        and any(
            item.get("id") == "lightyear.pli"
            and item.get("language") == "PL/I"
            and item.get("version") == "1.2"
            and item.get("status") == "development-proof"
            for item in catalog.get("language_packs", [])
        )
    )
    pli_coverage = _pli_coverage_receipt_passed(pli_coverage_receipt or {}, graph_sha256)
    pli_parsed = _hashed_and_bound(fragment, graph_sha256) and pli_cataloged and pli_coverage
    fragment_stats = fragment.get("statistics", {})
    fragment_kinds = fragment_stats.get("nodes_by_kind", {})
    fragment_relations = fragment_stats.get("edges_by_relation", {})
    external_ids = {
        item.get("entity_id") for item in fragment.get("external_references", [])
    }
    pli_connected = bool(
        pli_parsed
        and fragment_kinds.get("pli_program", 0) >= 1
        and fragment_kinds.get("pli_include", 0) >= 1
        and fragment_relations.get("CALLS", 0) >= 2
        and fragment_relations.get("READS_TABLE", 0) >= 1
        and {
            "legacy:cobol-program:CBACT04C",
            "legacy:db2-table:CARDDEMO.AUTHFRDS",
        }.issubset(external_ids)
    )
    pli_parse_gap = (
        None if pli_parsed
        else "The PL/I fragment, language-pack catalog, or synthetic conformance coverage binding is invalid."
    )
    pli_graph_gap = None if pli_connected else "The PL/I-to-COBOL and PL/I-to-Db2 dependency links are incomplete."
    pli_source_development = _pli_development_receipt_passed(
        pli_development_receipt or {}, graph_sha256, fragment.get("content_sha256")
    )
    pli_attested_build = _pli_build_attestation_passed(
        pli_build_receipt or {},
        pli_build_attestation or {},
        (pli_development_receipt or {}).get("content_sha256"),
    )
    pli_development = pli_source_development and pli_attested_build
    pli_development_gap = (
        None if pli_development
        else "The graph-bound PL/I proof or its compiled-artifact attestation is missing, stale, foreign, incomplete, or tampered."
    )
    pli_live_gap = "No authorized compiled and executed ACCTPL1 observation exists on z/OS."
    pli_gates = [
        _gate(1, "passed" if pli_parsed else "blocked", [
            "extensions/pli/pli.fragment.json",
            "extensions/pli/conformance/coverage.receipt.json",
            f"{fragment_kinds.get('pli_program', 0)} PL/I program",
            f"{fragment_kinds.get('pli_include', 0)} PL/I include",
            f"{(pli_coverage_receipt or {}).get('corpus', {}).get('case_count', 0)} synthetic conformance cases",
            f"{(pli_coverage_receipt or {}).get('coverage', {}).get('supported_matrix_construct_count', 0)} supported construct categories",
        ], pli_parse_gap),
        _gate(2, "passed" if pli_connected else "blocked", [
            f"{fragment_relations.get('CALLS', 0)} CALLS edges",
            f"{fragment_relations.get('READS_TABLE', 0)} READS_TABLE edge",
            "PL/I -> COBOL and PL/I -> Db2 external references",
        ], pli_graph_gap),
        _gate(3, "passed" if pli_development else "blocked", [
            "extensions/pli/modernization/behavior-contract.json",
            "fixed-width, decimal, Db2 lookup, and COBOL-call semantics",
        ], pli_development_gap),
        _gate(4, "passed" if pli_development else "blocked", [
            "factory/benchmarks/pli_authorization_candidate.py",
            "candidate-java MixedPliAuthorizationService",
            "extensions/pli/attestation/pli-auth-risk-candidate.jar",
            "asymmetrically signed build provenance and SBOM",
        ], pli_development_gap),
        _gate(5, "passed" if pli_development else "blocked", [
            "extensions/pli/modernization/comparison.json",
            "nine mutation probes and seven boundary cases",
            "attested JUnit-compatible execution report",
        ], pli_development_gap),
        _gate(6, "blocked", [], pli_live_gap),
        _gate(7, "mechanism_ready" if pli_development else "blocked", [
            "independent source-faithful oracle and modernization candidate comparator",
        ], pli_live_gap if pli_development else pli_development_gap),
        _gate(8, "blocked", [], "No signed PL/I equivalence receipt exists."),
    ]

    postgres = postgres_data_receipt or {}
    oracle = oracle_data_receipt or {}
    postgres_passed = _offline_data_receipt_passed(postgres, "postgresql-16")
    oracle_passed = _offline_data_receipt_passed(oracle, "oracle-26ai-free")
    data_parsed = bool(
        kind_counts.get("db2_table", 0) >= 1
        and kind_counts.get("db2_column", 0) >= 26
        and kind_counts.get("db2_sql_statement", 0) >= 1
    )
    data_connected = bool(
        data_parsed
        and relation_counts.get("HAS_COLUMN", 0) >= 26
        and relation_counts.get("ISSUES_SQL", 0) >= 1
        and relation_counts.get("REFERENCES_COLUMN", 0) >= 26
    )
    data_development = postgres_passed and oracle_passed
    data_receipt_gap = None if data_development else "Both target-specific offline development receipts must pass."
    data_live_gap = "Live Db2 catalog, source rows, CDC, cutover, and rollback evidence remain pending."
    data_gates = [
        _gate(1, "passed" if data_parsed else "blocked", [
            f"{kind_counts.get('db2_table', 0)} Db2 tables",
            f"{kind_counts.get('db2_column', 0)} Db2 columns",
            f"{kind_counts.get('db2_sql_statement', 0)} embedded SQL statements",
        ], None if data_parsed else "Db2 schema and SQL assets are incomplete."),
        _gate(2, "passed" if data_connected else "blocked", [
            f"{relation_counts.get('HAS_COLUMN', 0)} HAS_COLUMN edges",
            f"{relation_counts.get('ISSUES_SQL', 0)} ISSUES_SQL edges",
            f"{relation_counts.get('REFERENCES_COLUMN', 0)} REFERENCES_COLUMN edges",
        ], None if data_connected else "Db2 schema and embedded-SQL lineage is incomplete."),
        _gate(3, "passed" if data_development else "blocked", [
            "data-modernization/receipts/authfrds.offline.receipt.json",
            "data-modernization/receipts/authfrds.oracle-offline.receipt.json",
        ], data_receipt_gap),
        _gate(4, "passed" if data_development else "blocked", [
            "PostgreSQL 16 AUTHFRDS projection",
            "Oracle 26ai Free AUTHFRDS projection",
        ], data_receipt_gap),
        _gate(5, "passed" if data_development else "blocked", [
            "schema, key, index, row, query, commit, and rollback checks",
            "fail-closed evidence-marker mutation tests",
        ], data_receipt_gap),
        _gate(6, "blocked", ["extensions/adapters/campaign/campaign.receipt.json"], data_live_gap),
        _gate(7, "mechanism_ready", [
            "PostgreSQL and Oracle differential-verification adapters",
            "lightyear.db2-zos-catalog read-only collector",
        ], data_live_gap),
        _gate(8, "blocked", [], "No signed live Db2-to-target equivalence receipt exists."),
    ]

    capabilities = [
        _capability("CICS", "runtime", cics_common),
        _capability("VSAM", "data", vsam_common),
        _capability("IMS", "runtime", ims_gates),
        _capability("HLASM", "language", asm_gates),
        _capability("PL/I", "language", pli_gates, {
            "scope": "synthetic-static-supported-subset",
            "corpus_case_count": (pli_coverage_receipt or {}).get("corpus", {}).get("case_count", 0),
            "positive_case_count": (pli_coverage_receipt or {}).get("corpus", {}).get("positive_case_count", 0),
            "blocked_case_count": (pli_coverage_receipt or {}).get("corpus", {}).get("blocked_case_count", 0),
            "mutation_case_count": (pli_coverage_receipt or {}).get("corpus", {}).get("mutation_case_count", 0),
            "supported_construct_count": (pli_coverage_receipt or {}).get("coverage", {}).get("supported_matrix_construct_count", 0),
            "explicit_gap_count": sum((pli_coverage_receipt or {}).get("coverage", {}).get("explicit_gap_codes", {}).values()),
            "customer_source": False,
            "runtime_evidence": False,
        }),
        _capability("Db2/Data", "data", data_gates),
    ]

    campaign = campaign_receipt or {}
    campaign_valid = bool(
        campaign.get("content_sha256") == _canonical_hash(campaign)
        and campaign.get("status") == "passed"
        and campaign.get("graph_binding", {}).get("content_sha256") == graph_sha256
        and campaign.get("production_ready") is False
    )
    campaign_class = campaign.get("evidence_class") if campaign_valid else None
    collection_status = (
        "live_observed" if campaign_class == "live" else "simulated_ready" if campaign_class == "simulated" else "blocked"
    )
    collection_mechanisms = [{
        "mechanism": "Mainframe Access Campaign",
        "status": collection_status,
        "evidence_class": campaign_class or "unverified",
        "live_observed": campaign_class == "live",
        "production_ready": False,
        "adapters": sorted(campaign.get("required_adapters", [])) if campaign_valid else [],
        "receipt_sha256": campaign.get("content_sha256") if campaign_valid else None,
    }]

    evidence_bindings = {
        "canonical_graph_sha256": graph_sha256,
        "extension_catalog_sha256": catalog.get("content_sha256"),
        "pli_fragment_sha256": fragment.get("content_sha256"),
        "pli_coverage_receipt_sha256": (pli_coverage_receipt or {}).get("content_sha256"),
        "pli_development_receipt_sha256": (pli_development_receipt or {}).get("content_sha256"),
        "pli_build_receipt_sha256": (pli_build_receipt or {}).get("content_sha256"),
        "pli_build_attestation_sha256": (pli_build_attestation or {}).get("content_sha256"),
        "postgres_data_receipt_sha256": postgres.get("content_sha256"),
        "oracle_data_receipt_sha256": oracle.get("content_sha256"),
        "mainframe_campaign_receipt_sha256": campaign.get("content_sha256"),
    }

    payload = {
        "schema_version": "1.3",
        "analysis_type": "factorydark-mainframe-capability-readiness",
        "graph_content_sha256": graph_sha256,
        "truth_boundary": (
            "Local, simulated, fixture, static, and offline target evidence cannot satisfy live z/OS observation or equivalence gates."
        ),
        "evidence_bindings": evidence_bindings,
        "capabilities": capabilities,
        "collection_mechanisms": collection_mechanisms,
    }
    payload["content_sha256"] = _canonical_hash(payload)
    return payload


def validate_capability_analysis(
    payload: dict[str, Any],
    graph: dict[str, Any],
    expected: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "1.3":
        errors.append("unsupported capability analysis schema_version")
    if payload.get("graph_content_sha256") != graph.get("content_sha256"):
        errors.append("capability analysis is not bound to the canonical graph")
    if payload.get("content_sha256") != _canonical_hash(payload):
        errors.append("capability analysis content_sha256 is invalid")
    technologies = [item.get("technology") for item in payload.get("capabilities", [])]
    expected_technologies = ["CICS", "VSAM", "IMS", "HLASM", "PL/I", "Db2/Data"]
    if technologies != expected_technologies:
        errors.append("capability analysis must cover CICS, VSAM, IMS, HLASM, PL/I, and Db2/Data in order")
    for capability in payload.get("capabilities", []):
        gates = capability.get("gates", [])
        if capability.get("capability_kind") not in {"runtime", "language", "data"}:
            errors.append(f"{capability.get('technology')} has an invalid capability_kind")
        if [gate.get("gate") for gate in gates] != list(range(1, 9)):
            errors.append(f"{capability.get('technology')} does not contain readiness gates 1-8")
        if capability.get("mainframe_equivalent") and any(
            gate.get("status") != "passed" for gate in gates
        ):
            errors.append(f"{capability.get('technology')} overstates mainframe equivalence")
    mechanisms = payload.get("collection_mechanisms", [])
    if len(mechanisms) != 1 or mechanisms[0].get("mechanism") != "Mainframe Access Campaign":
        errors.append("capability analysis must include the mainframe access campaign")
    elif mechanisms[0].get("evidence_class") != "live" and mechanisms[0].get("live_observed"):
        errors.append("non-live campaign evidence cannot be reported as live observed")
    if payload.get("evidence_bindings", {}).get("canonical_graph_sha256") != graph.get("content_sha256"):
        errors.append("capability evidence bindings do not include the canonical graph")
    if expected is not None and payload != expected:
        errors.append("capability analysis is stale against bound extension, data, or campaign evidence")
    return errors


def write_capability_analysis(payload: dict[str, Any], path: Path) -> None:
    write_json(path, payload)
