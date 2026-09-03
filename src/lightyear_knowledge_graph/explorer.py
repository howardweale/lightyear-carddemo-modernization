from __future__ import annotations

import hmac
import ipaddress
import json
import mimetypes
import queue
import secrets
import threading
import webbrowser
from collections import defaultdict, deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .chat import ChatError, GraphChatService
from .evidence_pack import EvidenceStore, load_evidence_pack, validate_evidence_pack
from .model import load_graph
from .ontology import load_ontology
from .validation import rule_gaps
from lightyear_factory.memory import SemanticMemoryStore
from lightyear_factory.store import DurableStore, EvaluationStore, FactoryRunStore, PortfolioStore
from lightyear_runtime.engine import load_snapshot as load_runtime_snapshot
from lightyear_runtime.store import RuntimeEvidenceStore
from lightyear_audit.ledger import load_snapshot as load_audit_snapshot
from lightyear_audit.store import AuditStore
from lightyear_control_tower.operational import (
    OperationalControlTower,
    OperationalEventStore,
    OperationalMonitor,
    OperationalSource,
)


NON_LOOPBACK_WARNING = (
    "WARNING: the LIGHTYEAR Control Tower is unauthenticated for implementer views. "
    "A non-loopback bind exposes graph, source, runtime, and audit evidence to the network."
)


def is_loopback_host(host: str) -> bool:
    """Return true only for an explicit loopback hostname or address."""
    normalized = host.strip().casefold().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def validate_bind_host(host: str, allow_unauthenticated_network: bool = False) -> None:
    if is_loopback_host(host):
        return
    if not allow_unauthenticated_network:
        raise ValueError(
            f"Refusing non-loopback bind {host!r}. {NON_LOOPBACK_WARNING} "
            "Pass --i-understand-this-is-unauthenticated only after placing the service "
            "behind an approved reverse proxy or accepting the exposure explicitly."
        )


DEFAULT_PERSPECTIVES = [
    {
        "id": "intcalc-workload",
        "name": "INTCALC workload",
        "description": "Legacy entry point, modern candidate, rules, scenarios, and scheduler.",
        "root": "workload:carddemo-intcalc",
        "depth": 2,
    },
    {
        "id": "monthly-interest",
        "name": "Monthly-interest rule",
        "description": "Source evidence, implementation, and independent verification.",
        "root": "rule:intcalc:monthly-interest",
        "depth": 2,
    },
    {
        "id": "intcalc-job",
        "name": "INTCALC job lineage",
        "description": "JCL job, execution step, program, DD allocations, and datasets.",
        "root": "legacy:jcl-job:INTCALC",
        "depth": 3,
    },
    {
        "id": "account-copybook",
        "name": "Account data contract",
        "description": "Account copybook fields and the programs that depend on the layout.",
        "root": "legacy:copybook:CVACT01Y",
        "depth": 2,
    },
    {
        "id": "final-account-behavior",
        "name": "Final-account behavior",
        "description": "The discovered EOF behavior and its implementation and tests.",
        "root": "rule:intcalc:source-final-account",
        "depth": 2,
    },
    {
        "id": "authfrds-data-lineage",
        "name": "AUTHFRDS data lineage",
        "description": "Db2 table, columns, DCL, embedded SQL, business rules, and PostgreSQL proof.",
        "root": "workload:carddemo-db2-authfrds",
        "depth": 3,
    },
    {
        "id": "cics-vsam-account-view",
        "name": "CICS/VSAM account view",
        "description": "CICS transaction, COBOL program, BMS map, VSAM paths, and read-only account behavior.",
        "root": "workload:carddemo-cics-vsam-account-view",
        "depth": 3,
    },
    {
        "id": "ims-expired-authorization-purge",
        "name": "IMS authorization purge",
        "description": "BMP route, DLI traversal, expiry rules, segment deletes, and checkpoints.",
        "root": "workload:carddemo-ims-expired-authorization-purge",
        "depth": 3,
    },
    {
        "id": "asm-date-format",
        "name": "HLASM date service",
        "description": "COBOL call boundary, assembler routine, parameter layout, and date-format rules.",
        "root": "workload:carddemo-asm-date-format",
        "depth": 3,
    },
    {
        "id": "pli-auth-risk-lineage",
        "name": "PL/I authorization-risk lineage",
        "description": "PL/I files, include, Db2 SQL, internal procedure, and COBOL call boundary.",
        "root": "extension:pli-program:ACCTPL1",
        "depth": 3,
    },
    {
        "id": "oracle-reference-order-to-cash",
        "name": "Oracle order-to-cash reference",
        "description": "Pinned static document-flow scenarios for the Oracle Customer (Large) reference estate.",
        "root": "oracle-reference:workload:order-to-cash",
        "depth": 1,
    },
    {
        "id": "oracle-reference-procure-to-pay",
        "name": "Oracle procure-to-pay reference",
        "description": "Pinned static document-flow scenarios for the Oracle Customer (Large) reference estate.",
        "root": "oracle-reference:workload:procure-to-pay",
        "depth": 1,
    },
    {
        "id": "cloudbank-customer-account",
        "name": "CloudBank customer and account reference",
        "description": "Pinned static Oracle schema, service, API, and migration-risk evidence.",
        "root": "cloudbank-reference:workload:customer-account-management",
        "depth": 1,
    },
    {
        "id": "cloudbank-money-transfer",
        "name": "CloudBank money transfer reference",
        "description": "Pinned static LRA, compensation, journal, and transaction-boundary evidence.",
        "root": "cloudbank-reference:workload:money-transfer",
        "depth": 1,
    },
    {
        "id": "cloudbank-check-processing",
        "name": "CloudBank cheque processing reference",
        "description": "Pinned static event-queue, delivery, authorization, and consistency evidence.",
        "root": "cloudbank-reference:workload:check-deposit-clearance",
        "depth": 1,
    },
    {
        "id": "cloudbank-identity",
        "name": "CloudBank identity reference",
        "description": "Pinned static user-schema, audit-trigger, OAuth, and secret-boundary evidence.",
        "root": "cloudbank-reference:workload:identity-service-authorization",
        "depth": 1,
    },
    {
        "id": "cloudbank-credit-score",
        "name": "CloudBank credit decision and AI reference",
        "description": "Pinned source plus MS #64 synthetic-score, OAuth, chatbot guardrail, and model-egress evidence.",
        "root": "cloudbank-reference:workload:credit-score-service",
        "depth": 1,
    },
]


OPERATOR_CUSTOMERS = [
    {
        "id": "carddemo-reference",
        "name": "CardDemo Reference Estate",
        "evidence_class": "reference",
        "description": "Bundled reference evidence; no customer system is attached.",
    },
    {
        "id": "oracle-customer-large",
        "name": "Oracle Customer (Large)",
        "evidence_class": "upstream-static-reference",
        "description": "Pinned public reference-estate evidence; no customer system is attached.",
    },
    {
        "id": "cloudbank-reference",
        "name": "CloudBank Reference Estate",
        "evidence_class": "upstream-static-modern-oracle-reference",
        "description": "Pinned modern Oracle reference application; no customer system or target equivalence is attached.",
    },
]

OPERATOR_PROBLEMS = [
    {
        "id": "account-and-card-servicing",
        "company_id": "carddemo-reference",
        "name": "Account and card servicing",
        "description": "Modernize account calculation and inquiry without losing financial or record-layout behavior.",
        "workload_ids": [
            "workload:carddemo-intcalc",
            "workload:carddemo-cics-vsam-account-view",
        ],
    },
    {
        "id": "authorization-and-fraud",
        "company_id": "carddemo-reference",
        "name": "Authorization and fraud operations",
        "description": "Modernize authorization data and expiry processing while preserving transaction and hierarchy semantics.",
        "workload_ids": [
            "workload:carddemo-db2-authfrds",
            "workload:carddemo-ims-expired-authorization-purge",
        ],
    },
    {
        "id": "shared-platform-services",
        "company_id": "carddemo-reference",
        "name": "Shared platform services",
        "description": "Recover and modernize shared routines used across application boundaries.",
        "workload_ids": ["workload:carddemo-asm-date-format"],
    },
    {
        "id": "oracle-order-to-cash",
        "company_id": "oracle-customer-large",
        "name": "Order to cash",
        "description": "Trace accepted sales orders through shipment, invoicing, receipt, and allocation using pinned static reference evidence.",
        "workload_ids": ["oracle-reference:workload:order-to-cash"],
    },
    {
        "id": "oracle-procure-to-pay",
        "company_id": "oracle-customer-large",
        "name": "Procure to pay",
        "description": "Trace approved purchase orders through receipt, vendor invoicing, payment, and allocation using pinned static reference evidence.",
        "workload_ids": ["oracle-reference:workload:procure-to-pay"],
    },
    {
        "id": "cloudbank-customer-account",
        "company_id": "cloudbank-reference",
        "name": "Customer and account platform",
        "description": "Separate modern service behavior from Oracle schema, datatype, identity, constraint, and ORM assumptions.",
        "workload_ids": ["cloudbank-reference:workload:customer-account-management"],
    },
    {
        "id": "cloudbank-money-movement",
        "company_id": "cloudbank-reference",
        "name": "Money movement",
        "description": "Preserve transfer, local transaction, LRA compensation, journal, retry, and recovery behavior.",
        "workload_ids": ["cloudbank-reference:workload:money-transfer"],
    },
    {
        "id": "cloudbank-check-processing",
        "company_id": "cloudbank-reference",
        "name": "Cheque processing",
        "description": "Preserve asynchronous deposit and clearance delivery, authorization, replay, and consistency behavior.",
        "workload_ids": ["cloudbank-reference:workload:check-deposit-clearance"],
    },
    {
        "id": "cloudbank-identity-access",
        "company_id": "cloudbank-reference",
        "name": "Identity and access",
        "description": "Preserve OAuth, service scope, ownership, credential, secret, user-schema, and audit behavior.",
        "workload_ids": ["cloudbank-reference:workload:identity-service-authorization"],
    },
    {
        "id": "cloudbank-credit-decision",
        "company_id": "cloudbank-reference",
        "name": "Credit decision and AI services",
        "description": "Govern identity-bound synthetic scoring and fail-closed model interaction without claiming bureau or model quality equivalence.",
        "workload_ids": ["cloudbank-reference:workload:credit-score-service"],
    },
]

OPERATOR_WORKLOADS = [
    {
        "id": "workload:carddemo-intcalc",
        "problem_id": "account-and-card-servicing",
        "perspective_id": "intcalc-workload",
        "recommended_scope": "mainframe",
        "description": "Monthly interest batch calculation, fixed-width contracts, rules, candidate, and verification.",
    },
    {
        "id": "workload:carddemo-cics-vsam-account-view",
        "problem_id": "account-and-card-servicing",
        "perspective_id": "cics-vsam-account-view",
        "recommended_scope": "mainframe",
        "description": "Read-only CICS account inquiry across COBOL, BMS, alternate indexes, and VSAM files.",
    },
    {
        "id": "workload:carddemo-db2-authfrds",
        "problem_id": "authorization-and-fraud",
        "perspective_id": "authfrds-data-lineage",
        "recommended_scope": "database",
        "description": "Authorization and fraud data lineage across COBOL, Db2, schema rules, and target proof.",
    },
    {
        "id": "workload:carddemo-ims-expired-authorization-purge",
        "problem_id": "authorization-and-fraud",
        "perspective_id": "ims-expired-authorization-purge",
        "recommended_scope": "mainframe",
        "description": "IMS BMP traversal, expiry decisions, segment mutation, checkpoint, and restart boundaries.",
    },
    {
        "id": "workload:carddemo-asm-date-format",
        "problem_id": "shared-platform-services",
        "perspective_id": "asm-date-format",
        "recommended_scope": "mainframe",
        "description": "Shared COBOL-to-HLASM date conversion contract and its bounded business rules.",
    },
    {
        "id": "oracle-reference:workload:order-to-cash",
        "problem_id": "oracle-order-to-cash",
        "perspective_id": "oracle-reference-order-to-cash",
        "recommended_scope": "database",
        "description": "Pinned static sales-order, shipment, invoice, receipt, and allocation relationships; no Oracle runtime is attached.",
    },
    {
        "id": "oracle-reference:workload:procure-to-pay",
        "problem_id": "oracle-procure-to-pay",
        "perspective_id": "oracle-reference-procure-to-pay",
        "recommended_scope": "database",
        "description": "Pinned static purchase-order, receipt, vendor-invoice, payment, and allocation relationships; no Oracle runtime is attached.",
    },
    {
        "id": "cloudbank-reference:workload:customer-account-management",
        "problem_id": "cloudbank-customer-account",
        "perspective_id": "cloudbank-customer-account",
        "recommended_scope": "database",
        "description": "Customer is qualified, all eight services are planned, and MS #61 adds bounded normalized Oracle/PostgreSQL equivalence for Customer, Account, and Transfer.",
        "target_dialect": "postgresql-16",
        "target_status": "bounded equivalence ready · operator receipt required",
        "mapping_artifact": "reference-estates/cloudbank/customer-postgresql/mapping.json",
        "factory_artifact": "factory/cloudbank/oracle-equivalence/readiness.receipt.json",
        "production_readiness_status": "production-like deployment and cutover rehearsal ready · operator evidence required",
        "production_readiness_artifact": "factory/cloudbank/production-readiness/readiness.receipt.json",
        "whole_application_status": "dual-lane whole-application equivalence ready · operator evidence required",
        "whole_application_artifact": "factory/cloudbank/whole-application-equivalence/readiness.receipt.json",
        "platform_qualification_status": "real non-production GKE qualification ready · live operator evidence required",
        "platform_qualification_artifact": "factory/cloudbank/platform-qualification/readiness.receipt.json",
    },
    {
        "id": "cloudbank-reference:workload:money-transfer",
        "problem_id": "cloudbank-money-movement",
        "perspective_id": "cloudbank-money-transfer",
        "recommended_scope": "database",
        "description": "MS #62 adds live OAuth-issued, audience-bound caller and service JWTs to the MS #61-equivalent Account/Transfer target, including persistent-key restart evidence.",
        "target_dialect": "postgresql-16",
        "target_status": "production OAuth application boundary ready · operator receipt required",
        "factory_artifact": "factory/cloudbank/production-oauth/readiness.receipt.json",
        "production_readiness_status": "production-like deployment and cutover rehearsal ready · operator evidence required",
        "production_readiness_artifact": "factory/cloudbank/production-readiness/readiness.receipt.json",
        "whole_application_status": "dual-lane whole-application equivalence ready · operator evidence required",
        "whole_application_artifact": "factory/cloudbank/whole-application-equivalence/readiness.receipt.json",
        "platform_qualification_status": "real non-production GKE qualification ready · live operator evidence required",
        "platform_qualification_artifact": "factory/cloudbank/platform-qualification/readiness.receipt.json",
    },
    {
        "id": "cloudbank-reference:workload:check-deposit-clearance",
        "problem_id": "cloudbank-check-processing",
        "perspective_id": "cloudbank-check-processing",
        "recommended_scope": "database",
        "description": "MS #63 replaces Oracle AQ/JMS with a durable PostgreSQL work queue covering idempotency, per-aggregate order, exclusive claims, redelivery, retry, and dead-letter handling.",
        "target_dialect": "postgresql-16",
        "target_status": "Checks target messaging ready · operator receipt required",
        "factory_artifact": "factory/cloudbank/checks-messaging/readiness.receipt.json",
        "production_readiness_status": "production-like deployment and cutover rehearsal ready · operator evidence required",
        "production_readiness_artifact": "factory/cloudbank/production-readiness/readiness.receipt.json",
        "whole_application_status": "dual-lane whole-application equivalence ready · operator evidence required",
        "whole_application_artifact": "factory/cloudbank/whole-application-equivalence/readiness.receipt.json",
        "platform_qualification_status": "real non-production GKE qualification ready · live operator evidence required",
        "platform_qualification_artifact": "factory/cloudbank/platform-qualification/readiness.receipt.json",
    },
    {
        "id": "cloudbank-reference:workload:identity-service-authorization",
        "problem_id": "cloudbank-identity-access",
        "perspective_id": "cloudbank-identity",
        "recommended_scope": "database",
        "description": "MS #62 moves the user repository to PostgreSQL and natively exercises OAuth2/OIDC discovery, JWT signature, issuer, audience, scope, ownership, service identity, and key-restart boundaries.",
        "target_dialect": "postgresql-16",
        "target_status": "production OAuth application boundary ready · operator receipt required",
        "factory_artifact": "factory/cloudbank/production-oauth/readiness.receipt.json",
        "production_readiness_status": "production-like deployment and cutover rehearsal ready · operator evidence required",
        "production_readiness_artifact": "factory/cloudbank/production-readiness/readiness.receipt.json",
        "whole_application_status": "dual-lane whole-application equivalence ready · operator evidence required",
        "whole_application_artifact": "factory/cloudbank/whole-application-equivalence/readiness.receipt.json",
        "platform_qualification_status": "real non-production GKE qualification ready · live operator evidence required",
        "platform_qualification_artifact": "factory/cloudbank/platform-qualification/readiness.receipt.json",
    },
    {
        "id": "cloudbank-reference:workload:credit-score-service",
        "problem_id": "cloudbank-credit-decision",
        "perspective_id": "cloudbank-credit-score",
        "recommended_scope": "database",
        "description": "MS #64 replaces the random score demo with subject-bound synthetic evidence and adds distinct-audience Chatbot input, output, rate-limit, failure, and egress controls.",
        "target_dialect": "postgresql-16",
        "target_status": "eight-service edge and AI boundary ready · operator receipt required",
        "factory_artifact": "factory/cloudbank/edge-ai/readiness.receipt.json",
        "production_readiness_status": "production-like deployment and cutover rehearsal ready · operator evidence required",
        "production_readiness_artifact": "factory/cloudbank/production-readiness/readiness.receipt.json",
        "whole_application_status": "dual-lane whole-application equivalence ready · operator evidence required",
        "whole_application_artifact": "factory/cloudbank/whole-application-equivalence/readiness.receipt.json",
        "platform_qualification_status": "real non-production GKE qualification ready · live operator evidence required",
        "platform_qualification_artifact": "factory/cloudbank/platform-qualification/readiness.receipt.json",
    },
]

OPERATOR_SCOPES = [
    {
        "id": "all-estate",
        "name": "Unified estate",
        "platforms": [],
        "description": "Keep every evidenced technology visible in one dependency graph.",
    },
    {
        "id": "mainframe",
        "name": "Mainframe",
        "platforms": ["COBOL", "PL/I", "JCL", "CICS", "IMS", "VSAM", "DB2", "Assembler", "BMS", "Mainframe data"],
        "description": "Focus the graph on mainframe programs, transactions, jobs, and data stores.",
    },
    {
        "id": "database",
        "name": "Database modernization",
        "platforms": ["DB2", "Oracle", "SAP ASE"],
        "description": "Focus on database lineage while retaining connected application context.",
    },
    {
        "id": "sap-estate",
        "name": "SAP estate",
        "platforms": ["SAP", "SAP ASE"],
        "description": "Reserved for customer SAP application and integration evidence.",
        "planned": True,
    },
]

OPERATOR_LENSES = [
    {
        "id": "dependencies",
        "name": "Dependencies",
        "description": "Follow calls, execution, resource use, and data access across technologies.",
    },
    {
        "id": "data-flow",
        "name": "Data flow",
        "description": "Emphasize reads, writes, SQL, datasets, DB2, VSAM, and IMS relationships.",
    },
    {
        "id": "modernization",
        "name": "Modernization",
        "description": "Emphasize workloads, rules, modern implementations, and verification evidence.",
    },
    {
        "id": "runtime",
        "name": "Runtime evidence",
        "description": "Review observed behavior without promoting static relationships to runtime truth.",
    },
    {
        "id": "qualification",
        "name": "Qualification evidence",
        "description": "Review gates, receipts, limitations, and promotion posture.",
    },
    {
        "id": "security",
        "name": "Security vulnerabilities",
        "description": "Reserved for governed vulnerability findings and remediation evidence.",
        "planned": True,
    },
]

PLATFORM_PREFIXES = {
    "assembler_": "Assembler",
    "bms_": "BMS",
    "cics_": "CICS",
    "cobol_": "COBOL",
    "db2_": "DB2",
    "ims_": "IMS",
    "java_": "Java",
    "jcl_": "JCL",
    "oracle_": "Oracle",
    "pli_": "PL/I",
    "sap_ase_": "SAP ASE",
    "ase_": "SAP ASE",
    "sap_": "SAP",
    "vsam_": "VSAM",
}

PLANNED_GRAPH_PLATFORMS = [
    {
        "id": "oracle",
        "name": "Oracle",
        "status": "qualification-not-projected",
        "description": "Oracle qualification evidence exists outside the graph; no customer integration edges are attached.",
    },
    {
        "id": "sap-ase",
        "name": "SAP ASE",
        "status": "qualification-not-projected",
        "description": "SAP ASE adapter evidence exists outside the graph; no customer integration edges are attached.",
    },
    {
        "id": "sap",
        "name": "SAP",
        "status": "planned",
        "description": "SAP application evidence is a future capability.",
    },
]


@dataclass(frozen=True)
class GraphSelection:
    root: str
    depth: int
    audience: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "depth": self.depth,
            "audience": self.audience,
            "truncated": self.truncated,
            "nodes": self.nodes,
            "edges": self.edges,
        }


class GraphExplorerIndex:
    """Read-optimized index for bounded, audience-aware visual exploration."""

    def __init__(
        self,
        payload: dict[str, Any],
        max_nodes: int = 300,
        ontology: dict[str, Any] | None = None,
        runtime_store: RuntimeEvidenceStore | None = None,
    ) -> None:
        self.payload = payload
        self.max_nodes = max_nodes
        self.ontology = ontology or load_ontology()
        self.relation_definitions = self.ontology["relations"]
        self.runtime_store = runtime_store
        self.node_by_id = {node["id"]: node for node in payload["nodes"]}
        self.edge_by_id = {edge["id"]: edge for edge in payload["edges"]}
        self.adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.outgoing: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for edge in payload["edges"]:
            self.adjacency[edge["source"]].append((edge["id"], edge["target"]))
            self.adjacency[edge["target"]].append((edge["id"], edge["source"]))
            self.outgoing[edge["source"]].append((edge["id"], edge["target"]))
        for values in self.adjacency.values():
            values.sort(key=lambda item: (self.edge_by_id[item[0]]["relation"], item[1]))
        for values in self.outgoing.values():
            values.sort(key=lambda item: (self.edge_by_id[item[0]]["relation"], item[1]))

    @classmethod
    def from_path(cls, graph_path: Path, max_nodes: int = 300) -> "GraphExplorerIndex":
        return cls(load_graph(graph_path), max_nodes=max_nodes)

    def metadata(self) -> dict[str, Any]:
        metadata = {
            "graph_id": self.payload["graph_id"],
            "schema_version": self.payload["schema_version"],
            "content_sha256": self.payload["content_sha256"],
            "canonical_content_sha256": self.canonical_content_sha256,
            "statistics": self.payload["statistics"],
            "relationship_ontology": self.payload["relationship_ontology"],
            "perspectives": self.perspectives(),
            "operator_context": self.operator_context(),
        }
        for key in (
            "projection_type",
            "base_graph",
            "fragments",
            "capability_projection",
            "claim_boundary",
        ):
            if key in self.payload:
                metadata[key] = self.payload[key]
        return metadata

    @property
    def canonical_content_sha256(self) -> str:
        return self.payload.get("base_graph", {}).get(
            "content_sha256", self.payload["content_sha256"]
        )

    def perspectives(self) -> list[dict[str, Any]]:
        return [item for item in DEFAULT_PERSPECTIVES if item["root"] in self.node_by_id]

    def operator_context(self) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        for node in self.node_by_id.values():
            counts[self._platform(node)] += 1
        platforms = [
            {
                "id": name.casefold().replace("/", "-").replace(" ", "-"),
                "name": name,
                "node_count": count,
                "status": "projected",
            }
            for name, count in sorted(counts.items())
        ]
        projected_names = {item["name"] for item in platforms}
        platforms.extend(
            item for item in PLANNED_GRAPH_PLATFORMS if item["name"] not in projected_names
        )
        scopes = []
        for definition in OPERATOR_SCOPES:
            item = dict(definition)
            item["available"] = not item.get("planned", False) and (
                not item["platforms"] or bool(projected_names.intersection(item["platforms"]))
            )
            scopes.append(item)
        examples = []
        for definition in (
            {
                "id": "cobol-db2-update",
                "name": "COBOL → DB2 update",
                "source": "legacy:cobol-program:COPAUS2C",
                "target": "legacy:db2-table:CARDDEMO.AUTHFRDS",
                "claim": "Static source shows COBOL issuing SQL that writes the DB2 table.",
                "evidence_class": "static-source",
                "runtime_observed": False,
            },
            {
                "id": "cobol-ims-dependency",
                "name": "COBOL → IMS dependency",
                "source": "legacy:cobol-program:CBPAUP0C",
                "target": "legacy:ims-database:DBPAUTP0",
                "claim": "Static declarations connect COBOL through a PSB and PCB to the IMS DBD; this is not an update claim.",
                "evidence_class": "static-declaration",
                "runtime_observed": False,
            },
            {
                "id": "cobol-ims-delete",
                "name": "COBOL → IMS delete",
                "source": "legacy:cobol-paragraph:CBPAUP0C:5000-DELETE-AUTH-DTL",
                "target": "legacy:ims-segment:DBPAUTP0:PAUTDTL1",
                "claim": "Static source shows CBPAUP0C issuing DLI DLET against the PSB-authorized PAUTDTL1 segment.",
                "evidence_class": "static-source",
                "runtime_observed": False,
            },
            {
                "id": "pli-db2-read",
                "name": "PL/I → DB2 read",
                "source": "extension:pli-program:ACCTPL1",
                "target": "legacy:db2-table:CARDDEMO.AUTHFRDS",
                "claim": "Static source shows PL/I issuing SQL that reads the DB2 table.",
                "evidence_class": "static-reference-fixture",
                "runtime_observed": False,
            },
            {
                "id": "pli-db2-write-reference",
                "name": "PL/I → DB2 write · reference",
                "source": "extension:pli-program:AUTHUPD1",
                "target": "legacy:db2-table:CARDDEMO.AUTHFRDS",
                "claim": "A bundled non-customer PL/I fixture shows embedded UPDATE extraction into WRITES_TABLE.",
                "evidence_class": "static-reference-fixture",
                "runtime_observed": False,
            },
        ):
            if definition["source"] not in self.node_by_id or definition["target"] not in self.node_by_id:
                continue
            item = dict(definition)
            item["source_name"] = self.node_by_id[item["source"]]["name"]
            item["source_kind"] = self.node_by_id[item["source"]]["kind"]
            item["source_platform"] = self._platform(self.node_by_id[item["source"]])
            item["target_name"] = self.node_by_id[item["target"]]["name"]
            item["target_kind"] = self.node_by_id[item["target"]]["kind"]
            item["target_platform"] = self._platform(self.node_by_id[item["target"]])
            item["customer_evidence"] = False
            examples.append(item)
        workloads = []
        for definition in OPERATOR_WORKLOADS:
            node = self.node_by_id.get(definition["id"])
            if node is None:
                continue
            item = dict(definition)
            item["name"] = node["name"]
            item["root"] = node["id"]
            item["status"] = node.get("properties", {}).get("status", "unknown")
            workloads.append(item)
        available_workload_ids = {item["id"] for item in workloads}
        problems = []
        for definition in OPERATOR_PROBLEMS:
            item = dict(definition)
            item["workload_ids"] = [
                workload_id for workload_id in item["workload_ids"]
                if workload_id in available_workload_ids
            ]
            if item["workload_ids"]:
                problems.append(item)
        available_company_ids = {item["company_id"] for item in problems}
        companies = [
            item for item in OPERATOR_CUSTOMERS if item["id"] in available_company_ids
        ]
        limitations = [
            "A static path does not prove that a transaction executed in production.",
            "Only a path containing WRITES_SEGMENT proves a static IMS mutation; PSB/DBD dependency alone does not.",
            "The AUTHUPD1 PL/I write is a bundled reference fixture, not customer source.",
        ]
        if "Oracle" in projected_names:
            limitations.append(
                "Oracle Customer (Large) is pinned static reference evidence; no customer system or Oracle runtime is attached."
            )
        else:
            limitations.append("No Oracle customer integration edges are currently projected.")
        if "cloudbank-reference" in available_company_ids:
            limitations.append(
                "CloudBank is pinned modern-Oracle reference evidence. The Customer qualification result remains operator-held and the whole application has an ordered wave plan; Account/Transfer native execution, messaging, LRA replacement, whole-estate equivalence, and migration completion are not attached."
            )
        limitations.append("No SAP ASE customer integration edges are currently projected.")
        return {
            "companies": companies,
            "customers": companies,
            "problems": problems,
            "workloads": workloads,
            "scopes": scopes,
            "lenses": OPERATOR_LENSES,
            "platforms": platforms,
            "trace": {
                "directed": True,
                "evidence_class": "static-source-and-declaration-evidence",
                "claim": "A found path proves that the committed graph contains the displayed relationships.",
                "limitations": limitations,
                "examples": examples,
            },
        }

    def search(
        self,
        query: str,
        kind: str = "",
        limit: int = 25,
        audience: str = "implementer",
    ) -> list[dict[str, Any]]:
        audience = self._audience(audience)
        normalized = query.strip().casefold()
        if not normalized:
            return []
        matches = []
        for node in self.node_by_id.values():
            if self._hidden(node, audience):
                continue
            if kind and node["kind"] != kind:
                continue
            haystack = " ".join(
                [node["id"], node["name"], str(node.get("properties", {}).get("statement", ""))]
            ).casefold()
            if normalized not in haystack:
                continue
            score = 0 if node["name"].casefold().startswith(normalized) else 1
            matches.append((score, node["kind"], node["name"], node))
        matches.sort(key=lambda item: (item[0], item[1], item[2], item[3]["id"]))
        return [self._summary(item[3]) for item in matches[: max(1, min(limit, 100))]]

    def node(self, node_id: str, audience: str = "implementer") -> dict[str, Any]:
        audience = self._audience(audience)
        node = self.node_by_id[node_id]
        if self._hidden(node, audience):
            raise KeyError(node_id)
        incoming = []
        outgoing = []
        for edge_id, _ in self.adjacency.get(node_id, []):
            edge = self.edge_by_id[edge_id]
            if self._edge_hidden(edge, audience):
                continue
            other_id = edge["source"] if edge["target"] == node_id else edge["target"]
            if self._hidden(self.node_by_id[other_id], audience):
                continue
            target = incoming if edge["target"] == node_id else outgoing
            target.append(
                {
                    "id": edge["id"],
                    "relation": edge["relation"],
                    "source": edge["source"],
                    "target": edge["target"],
                }
            )
        result = self._operator_node(node)
        result["incoming"] = sorted(incoming, key=lambda item: (item["relation"], item["source"]))
        result["outgoing"] = sorted(outgoing, key=lambda item: (item["relation"], item["target"]))
        result["runtime"] = self.runtime_projection("node", node_id)
        return result

    def edge(self, edge_id: str, audience: str = "implementer") -> dict[str, Any]:
        audience = self._audience(audience)
        edge = self.edge_by_id[edge_id]
        source = self.node_by_id[edge["source"]]
        target = self.node_by_id[edge["target"]]
        if (
            self._edge_hidden(edge, audience)
            or self._hidden(source, audience)
            or self._hidden(target, audience)
        ):
            raise KeyError(edge_id)
        result = dict(edge)
        result["source_node"] = self._summary(source)
        result["target_node"] = self._summary(target)
        result["definition"] = self.relation_definitions[edge["relation"]]
        result["runtime"] = self.runtime_projection("edge", edge_id)
        supporting_evidence = []
        seen_evidence: set[tuple[Any, ...]] = set()
        for owner_type, owner, role in (
            ("edge", edge, "relationship"),
            ("node", source, "source endpoint"),
            ("node", target, "target endpoint"),
        ):
            for evidence_index, item in enumerate(owner.get("evidence", [])):
                identity = (
                    item.get("source_id"), item.get("path"), item.get("line_start"),
                    item.get("line_end"), item.get("method"), item.get("confidence"),
                )
                if identity in seen_evidence:
                    continue
                seen_evidence.add(identity)
                supporting_evidence.append(
                    {
                        "evidence": item,
                        "evidence_index": evidence_index,
                        "owner_id": owner["id"],
                        "owner_type": owner_type,
                        "role": role,
                    }
                )
                if len(supporting_evidence) >= 24:
                    break
            if len(supporting_evidence) >= 24:
                break
        result["supporting_evidence"] = supporting_evidence
        return result

    def runtime_projection(self, entity_kind: str, entity_id: str) -> dict[str, Any]:
        if self.runtime_store is None:
            return {
                "state": "static_only",
                "confidence": 0.35,
                "evidence_classes": [],
                "observation_count": 0,
                "runs": [],
                "operations": [],
                "events": [],
            }
        return self.runtime_store.projection(entity_kind, entity_id)

    def decorate_runtime(self, entity_kind: str, item: dict[str, Any]) -> dict[str, Any]:
        result = dict(item)
        result["runtime"] = self.runtime_projection(entity_kind, item["id"])
        return result

    def neighborhood(
        self,
        node_id: str,
        depth: int = 2,
        audience: str = "implementer",
        limit: int | None = None,
    ) -> GraphSelection:
        if node_id not in self.node_by_id:
            raise KeyError(node_id)
        audience = self._audience(audience)
        if self._hidden(self.node_by_id[node_id], audience):
            raise KeyError(node_id)
        depth = max(0, min(depth, 5))
        node_limit = max(10, min(limit or self.max_nodes, 1000))
        seen = {node_id}
        selected_edges: set[str] = set()
        queue = deque([(node_id, 0)])
        truncated = False
        while queue:
            current, distance = queue.popleft()
            if distance >= depth:
                continue
            for edge_id, neighbor in self.adjacency.get(current, []):
                if self._edge_hidden(self.edge_by_id[edge_id], audience):
                    continue
                neighbor_node = self.node_by_id[neighbor]
                if self._hidden(neighbor_node, audience):
                    continue
                if neighbor not in seen and len(seen) >= node_limit:
                    truncated = True
                    continue
                selected_edges.add(edge_id)
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, distance + 1))
        nodes = [self._operator_node(self.node_by_id[item]) for item in sorted(seen)]
        edges = [
            self.edge_by_id[item]
            for item in sorted(selected_edges)
            if self.edge_by_id[item]["source"] in seen and self.edge_by_id[item]["target"] in seen
        ]
        return GraphSelection(node_id, depth, audience, nodes, edges, truncated)

    def trace(
        self,
        source: str,
        target: str,
        audience: str = "implementer",
        direction: str = "any",
    ) -> dict[str, Any] | None:
        audience = self._audience(audience)
        if direction not in {"any", "directed"}:
            raise ValueError("direction must be any or directed")
        for node_id in (source, target):
            if node_id not in self.node_by_id or self._hidden(self.node_by_id[node_id], audience):
                raise KeyError(node_id)
        queue = deque([source])
        previous: dict[str, tuple[str, str]] = {}
        seen = {source}
        while queue:
            current = queue.popleft()
            if current == target:
                break
            adjacency = self.outgoing if direction == "directed" else self.adjacency
            for edge_id, neighbor in adjacency.get(current, []):
                if (
                    neighbor in seen
                    or self._edge_hidden(self.edge_by_id[edge_id], audience)
                    or self._hidden(self.node_by_id[neighbor], audience)
                ):
                    continue
                seen.add(neighbor)
                previous[neighbor] = (current, edge_id)
                queue.append(neighbor)
        if target not in seen:
            return None
        node_ids = [target]
        edge_ids = []
        while node_ids[-1] != source:
            parent, edge_id = previous[node_ids[-1]]
            node_ids.append(parent)
            edge_ids.append(edge_id)
        node_ids.reverse()
        edge_ids.reverse()
        nodes = [self._operator_node(self.node_by_id[node_id]) for node_id in node_ids]
        platforms = list(dict.fromkeys(node["operator_platform"] for node in nodes))
        reference_fixture = any(
            bool(node.get("properties", {}).get("reference_fixture")) for node in nodes
        )
        upstream_classes = {
            value
            for node in nodes
            if isinstance(
                value := node.get("properties", {}).get("evidence_class"), str
            ) and value.startswith("upstream-static")
        }
        cloudbank_reference = any(
            node.get("properties", {}).get("customer_id") == "cloudbank-reference"
            for node in nodes
        )
        if upstream_classes:
            evidence_class = sorted(upstream_classes)[0]
            limitation = (
                "This is a pinned modern-Oracle reference-estate path. It is not customer or runtime evidence, "
                "and it does not prove PostgreSQL mapping, target equivalence, or migration completion."
                if cloudbank_reference
                else
                "This is a pinned public reference-estate path. It is not customer evidence, "
                "an observed Oracle transaction, or native Oracle runtime evidence."
            )
        elif reference_fixture:
            evidence_class = "static-reference-fixture"
            limitation = (
                "This is a non-customer reference-fixture path. It proves static extraction "
                "support, not a production transaction."
            )
        else:
            evidence_class = "static-source"
            limitation = (
                "This source-backed path proves committed static relationships, not a "
                "production transaction."
            )
        return {
            "direction": direction,
            "hop_count": len(edge_ids),
            "platforms": platforms,
            "evidence_class": evidence_class,
            "customer_evidence": False,
            "runtime_observed": False,
            "limitation": limitation,
            "node_ids": node_ids,
            "nodes": nodes,
            "edges": [self.edge_by_id[edge_id] for edge_id in edge_ids],
        }

    def gaps(self) -> list[dict[str, Any]]:
        return rule_gaps(self.payload)

    @staticmethod
    def _hidden(node: dict[str, Any], audience: str) -> bool:
        return (
            audience == "implementer"
            and node.get("properties", {}).get("visibility") == "inspector_private"
        )

    @staticmethod
    def _edge_hidden(edge: dict[str, Any], audience: str) -> bool:
        return (
            audience == "implementer"
            and edge.get("properties", {}).get("visibility") == "inspector_private"
        )

    @staticmethod
    def _audience(value: str) -> str:
        if value not in {"implementer", "verifier"}:
            raise ValueError("audience must be implementer or verifier")
        return value

    @classmethod
    def _operator_node(cls, node: dict[str, Any]) -> dict[str, Any]:
        result = dict(node)
        result["operator_platform"] = cls._platform(node)
        return result

    @staticmethod
    def _platform(node: dict[str, Any]) -> str:
        declared = node.get("properties", {}).get("operator_platform")
        if isinstance(declared, str) and declared.strip():
            return declared.strip()
        kind = node["kind"]
        for prefix, platform in PLATFORM_PREFIXES.items():
            if kind.startswith(prefix):
                return platform
        if kind in {"copybook", "cobol_field"}:
            return "COBOL"
        if kind in {"dataset", "executable"}:
            return "Mainframe data"
        if kind in {"modernization_workload", "business_rule", "test_case", "verification_scenario"}:
            return "Modernization"
        if kind in {"software_dependency", "source_file"}:
            return "Shared evidence"
        return "Other"

    @classmethod
    def _summary(cls, node: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": node["id"],
            "kind": node["kind"],
            "name": node["name"],
            "statement": node.get("properties", {}).get("statement", ""),
            "operator_platform": cls._platform(node),
        }


class ExplorerServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        index: GraphExplorerIndex,
        viewer_root: Path,
        chat_service: GraphChatService | None = None,
        evidence_store: EvidenceStore | None = None,
        factory_store: FactoryRunStore | None = None,
        evaluation_store: EvaluationStore | None = None,
        portfolio_store: PortfolioStore | None = None,
        durable_store: DurableStore | None = None,
        memory_store: SemanticMemoryStore | None = None,
        runtime_store: RuntimeEvidenceStore | None = None,
        audit_store: AuditStore | None = None,
        operational_store: OperationalEventStore | None = None,
        graph_path: Path | None = None,
        evidence_pack_path: Path | None = None,
        verifier_token: str | None = None,
    ) -> None:
        super().__init__(address, ExplorerRequestHandler)
        self.index = index
        self.viewer_root = viewer_root.resolve()
        self.project_root = self.viewer_root.parents[1]
        self.graph_path = (graph_path or self.project_root / "knowledge" / "graph.snapshot.json.gz").resolve()
        self.evidence_pack_path = (
            evidence_pack_path or self.graph_path.parent / "evidence" / "source.pack.json.gz"
        ).resolve()
        self.verifier_token = verifier_token or secrets.token_urlsafe(32)
        self._projection_lock = threading.RLock()
        self._binding_errors: dict[str, str] = {}
        self.chat_service = chat_service or GraphChatService.from_environment(index)
        if evidence_store is None:
            default_pack = self.evidence_pack_path
            evidence_store = EvidenceStore(load_evidence_pack(default_pack)) if default_pack.is_file() else None
        self.evidence_store = evidence_store
        if self.evidence_store is not None:
            evidence_errors = validate_evidence_pack(
                self.index.payload, self.evidence_store.payload
            )
            if evidence_errors:
                self.evidence_store = None
                self._binding_errors["evidence"] = "graph-identity-mismatch"
        self.factory_store = factory_store or FactoryRunStore(
            self.viewer_root.parents[1] / "work"
        )
        self.evaluation_store = evaluation_store or EvaluationStore(
            self.viewer_root.parents[1] / "work"
        )
        self.portfolio_store = portfolio_store or PortfolioStore(
            self.viewer_root.parents[1] / "factory" / "portfolio" / "carddemo-plan.snapshot.json",
            self.viewer_root.parents[1] / "work" / "portfolio",
        )
        self.durable_store = durable_store or DurableStore(
            self.viewer_root.parents[1] / "work" / "durable" / "control.sqlite3"
        )
        self.memory_store = memory_store or SemanticMemoryStore(
            self.viewer_root.parents[1] / "factory" / "memory" / "store"
        )
        self.runtime_path = self.viewer_root.parent / "runtime" / "runtime.snapshot.json.gz"
        if runtime_store is None:
            default_runtime = self.runtime_path
            runtime_store = (
                RuntimeEvidenceStore(load_runtime_snapshot(default_runtime))
                if default_runtime.is_file()
                else None
            )
        self.runtime_store = runtime_store
        if (
            self.runtime_store is not None
            and self.runtime_store.snapshot.get("graph_content_sha256")
            != self.index.canonical_content_sha256
        ):
            raise ValueError("Runtime evidence snapshot targets a different graph identity")
        self.index.runtime_store = self.runtime_store
        self.audit_path = self.project_root / "audit" / "audit.snapshot.json.gz"
        if audit_store is None:
            default_audit = self.audit_path
            audit_store = AuditStore(load_audit_snapshot(default_audit)) if default_audit.is_file() else None
        self.audit_store = audit_store
        if (
            self.audit_store is not None
            and self.audit_store.snapshot.get("graph_content_sha256")
            != self.index.canonical_content_sha256
        ):
            raise ValueError("Audit snapshot targets a different graph identity")
        self._runtime_file_state = self._file_state(self.runtime_path)
        self._audit_file_state = self._file_state(self.audit_path)
        self._graph_file_state = self._file_state(self.graph_path)
        self._evidence_file_state = self._file_state(self.evidence_pack_path)
        self.operational_store = operational_store or OperationalEventStore(
            self.project_root / "work" / "control-tower" / "events.sqlite3"
        )
        sources = (
            OperationalSource(
                "graph", (self.graph_path, self.evidence_pack_path),
                "content-addressed-graph", 5, self.graph_identity,
                identity_provider=self.graph_identity,
            ),
            OperationalSource(
                "factory", (self.factory_store.root,), "controller-receipt", 2,
                lambda: {"runs": self.factory_store.list_runs(200)},
            ),
            OperationalSource(
                "portfolio", (self.portfolio_store.plan_path, self.portfolio_store.runs_root),
                "approved-plan", 5, self.portfolio_store.summary,
            ),
            OperationalSource(
                "recovery", (self.durable_store.path,), "transactional-ledger", 2,
                self.durable_store.summary,
            ),
            OperationalSource(
                "quality", (self.evaluation_store.root,), "evaluation-receipt", 10,
                lambda: {"evaluations": self.evaluation_store.list_evaluations(200)},
            ),
            OperationalSource(
                "memory", (self.memory_store.root,), "verified-semantic-memory", 15,
                self.memory_store.summary,
            ),
            OperationalSource(
                "data", (self.project_root / "data-modernization",), "data-equivalence-receipt", 15,
                self.data_summary,
            ),
            OperationalSource(
                "runtime", (self.runtime_path,), "runtime-observation", 30,
                self.runtime_summary,
            ),
            OperationalSource(
                "audit", (self.audit_path,), "hash-chained-audit", 5,
                self.audit_summary,
            ),
        )
        self.control_tower = OperationalControlTower(self.operational_store, sources)
        self.operational_monitor = OperationalMonitor(self.control_tower)

    @staticmethod
    def _file_state(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def refresh_live_projections(self) -> None:
        with self._projection_lock:
            graph_state = self._file_state(self.graph_path)
            evidence_state = self._file_state(self.evidence_pack_path)
            graph_changed = graph_state != self._graph_file_state
            if graph_changed:
                refreshed = GraphExplorerIndex(
                    load_graph(self.graph_path),
                    max_nodes=self.index.max_nodes,
                    ontology=self.index.ontology,
                )
                self.index = refreshed
                self.chat_service = GraphChatService.from_environment(refreshed)
                self._graph_file_state = graph_state
            if evidence_state != self._evidence_file_state or graph_changed:
                candidate = (
                    EvidenceStore(load_evidence_pack(self.evidence_pack_path))
                    if evidence_state is not None else None
                )
                if candidate is not None and validate_evidence_pack(
                    self.index.payload, candidate.payload
                ):
                    self.evidence_store = None
                    self._binding_errors["evidence"] = "graph-identity-mismatch"
                else:
                    self.evidence_store = candidate
                    self._binding_errors.pop("evidence", None)
                self._evidence_file_state = evidence_state

            runtime_state = self._file_state(self.runtime_path)
            if runtime_state != self._runtime_file_state or self.index.runtime_store is None:
                candidate = (
                    RuntimeEvidenceStore(load_runtime_snapshot(self.runtime_path))
                    if runtime_state is not None else None
                )
                if (
                    candidate is not None
                    and candidate.snapshot.get("graph_content_sha256")
                    != self.index.canonical_content_sha256
                ):
                    self.runtime_store = None
                    self._binding_errors["runtime"] = "graph-identity-mismatch"
                else:
                    self.runtime_store = candidate
                    self._binding_errors.pop("runtime", None)
                self.index.runtime_store = self.runtime_store
                self._runtime_file_state = runtime_state

            audit_state = self._file_state(self.audit_path)
            if audit_state != self._audit_file_state or graph_changed:
                candidate = (
                    AuditStore(load_audit_snapshot(self.audit_path))
                    if audit_state is not None else None
                )
                if (
                    candidate is not None
                    and candidate.snapshot.get("graph_content_sha256")
                    != self.index.canonical_content_sha256
                ):
                    self.audit_store = None
                    self._binding_errors["audit"] = "graph-identity-mismatch"
                else:
                    self.audit_store = candidate
                    self._binding_errors.pop("audit", None)
                self._audit_file_state = audit_state

    def graph_identity(self) -> dict[str, Any]:
        self.refresh_live_projections()
        statistics = self.index.payload["statistics"]
        return {
            "graph_id": self.index.payload["graph_id"],
            "schema_version": self.index.payload["schema_version"],
            "content_sha256": self.index.payload["content_sha256"],
            "canonical_content_sha256": self.index.canonical_content_sha256,
            "node_count": statistics["node_count"],
            "edge_count": statistics["edge_count"],
            "binding_status": "invalidated" if self._binding_errors else "bound",
            "invalidated_projections": sorted(self._binding_errors),
        }

    def runtime_summary(self) -> dict[str, Any]:
        self.refresh_live_projections()
        if self.runtime_store is None:
            return {"runs": [], "statistics": {"run_count": 0, "event_count": 0}}
        return self.runtime_store.summary()

    def audit_summary(self) -> dict[str, Any]:
        self.refresh_live_projections()
        if self.audit_store is None:
            return {
                "statistics": {"event_count": 0, "decisions": {}, "active_exceptions": 0},
                "promotion_decisions": [],
                "trust_posture": {
                    "promotion_status": "not_evaluated", "unresolved_gaps": []
                },
            }
        return self.audit_store.summary()

    def data_summary(self) -> dict[str, Any]:
        root = self.project_root / "data-modernization"

        def load(relative: str) -> dict[str, Any]:
            path = root / relative
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

        model = load("canonical/authfrds.model.json")
        mapping = load("mappings/authfrds-postgresql.json")
        oracle_mapping = load("mappings/authfrds-oracle.json")
        receipt = load("receipts/authfrds.offline.receipt.json")
        oracle_offline = load("receipts/authfrds.oracle-offline.receipt.json")
        rehearsal = load("rehearsal/receipt.json")
        live_root = self.project_root / "work/data-modernization"
        def load_live(name: str) -> dict[str, Any]:
            path = live_root / name
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        targets = []
        for target_mapping, offline, filename in (
            (mapping, receipt, "live-postgresql.receipt.json"),
            (oracle_mapping, oracle_offline, "live-oracle.receipt.json"),
        ):
            live = load_live(filename)
            active = live or offline
            targets.append({
                "dialect": target_mapping.get("target_dialect", "not_available"),
                "target_table": target_mapping.get("target_table", ""),
                "adapter": target_mapping.get("adapter", {}),
                "evidence": "live-container" if live else "offline-development",
                "status": active.get("status", "not_available"),
                "production_ready": active.get("production_ready", False),
                "checks": active.get("checks", {}),
                "gaps": active.get("gaps", []),
                "content_sha256": active.get("content_sha256"),
                "image_identity": live.get("image_identity"),
            })
        rehearsal_checks = {
            f"rehearsal_{name}": value
            for name, value in rehearsal.get("checks", {}).items()
        }
        gaps = sorted(set(receipt.get("gaps", [])) | set(rehearsal.get("gaps", [])))
        return {
            "workload": receipt.get("workload", "carddemo-authorization-authfrds"),
            "status": (
                "passed"
                if receipt.get("status") == rehearsal.get("status") == "passed"
                else "blocked"
            ),
            "production_ready": False,
            "evidence_class": rehearsal.get(
                "evidence_class", receipt.get("evidence_class", "not_available")
            ),
            "source_table": f"{model.get('schema', '')}.{model.get('name', '')}".strip("."),
            "target_table": mapping.get("target_table", ""),
            "targets": targets,
            "statistics": {
                "columns": len(model.get("columns", [])),
                "constraints": len(model.get("constraints", [])),
                "indexes": len(model.get("indexes", [])),
                "fixture_rows": receipt.get("statistics", {}).get("rows", 0),
            },
            "checks": {**receipt.get("checks", {}), **rehearsal_checks},
            "gaps": gaps,
            "content_sha256": rehearsal.get("content_sha256", receipt.get("content_sha256")),
            "signature": receipt.get("signature"),
            "operational_rehearsal": {
                "status": rehearsal.get("status", "not_available"),
                "evidence_class": rehearsal.get("evidence_class", "not_available"),
                "events": rehearsal.get("journal", {}).get("events", 0),
                "resume_count": rehearsal.get("recovery", {}).get("resume_count", 0),
                "observed_rpo_events": rehearsal.get("recovery", {}).get(
                    "observed_rpo_events", 0
                ),
                "observed_rto_steps": rehearsal.get("recovery", {}).get(
                    "observed_rto_steps", 0
                ),
                "cutover_opened": rehearsal.get("cutover", {}).get("opened", False),
                "production_authorized": rehearsal.get("cutover", {}).get(
                    "production_authorized", False
                ),
                "rollback_exact": rehearsal.get("rollback", {}).get("exact", False),
                "receipt_sha256": rehearsal.get("content_sha256"),
            },
        }


class ExplorerRequestHandler(BaseHTTPRequestHandler):
    server: ExplorerServer

    def do_GET(self) -> None:  # noqa: N802 - standard-library handler API
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/"):
                query = parse_qs(parsed.query)
                if self._value(query, "audience") == "verifier" and not self._verifier_authorized():
                    self._verifier_required()
                    return
                self._api(parsed.path, query)
            else:
                self._static(parsed.path)
        except KeyError as exc:
            self._json(
                {"error": f"Unknown or hidden graph entity: {exc.args[0]}"},
                HTTPStatus.NOT_FOUND,
            )
        except (TypeError, ValueError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._json({"error": f"Explorer request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802 - standard-library handler API
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/chat":
                payload = self._request_json()
                if payload.get("audience") == "verifier" and not self._verifier_authorized():
                    self._verifier_required()
                    return
                self._json(self.server.chat_service.answer(payload))
                return
            self._json({"error": f"Unknown API route: {parsed.path}"}, HTTPStatus.NOT_FOUND)
        except KeyError as exc:
            self._json(
                {"error": f"Unknown or hidden graph entity: {exc.args[0]}"},
                HTTPStatus.NOT_FOUND,
            )
        except (ChatError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._json({"error": f"Chat request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _verifier_authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.verifier_token}"
        return hmac.compare_digest(supplied, expected)

    def _verifier_required(self) -> None:
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Bearer realm="LIGHTYEAR verifier"')
        body = b'{"error":"A valid per-session verifier token is required."}\n'
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        self.server.refresh_live_projections()
        index = self.server.index
        if path == "/api/operations/stream":
            self._event_stream(query)
            return
        if path == "/api/operations/status":
            self.server.control_tower.scan()
            self._json(self.server.control_tower.status())
            return
        if path == "/api/operations/events":
            self._json({
                "events": self.server.operational_store.events(
                    self._integer(query, "after", 0), self._integer(query, "limit", 200)
                ),
                "read_only": True,
            })
            return
        if path == "/api/meta":
            metadata = index.metadata()
            metadata["runtime"] = self.server.runtime_summary()["statistics"]
            metadata["audit"] = self.server.audit_summary()["statistics"]
            metadata["operations"] = self.server.control_tower.status()
            metadata["memory"] = self.server.memory_store.summary()["statistics"]
            portfolio = self.server.portfolio_store.summary()
            metadata["portfolio"] = {
                "status": portfolio.get("status"),
                "orders": len(portfolio.get("orders", [])),
                "waves": len(portfolio.get("waves", [])),
            }
            metadata["durable"] = self.server.durable_store.summary()["statistics"]
            metadata["data"] = self.server.data_summary()["statistics"]
            self._json(metadata)
            return
        if path == "/api/chat/status":
            self._json(self.server.chat_service.status())
            return
        if path == "/api/factory/runs":
            self._json(
                {
                    "runs": self.server.factory_store.list_runs(
                        self._integer(query, "limit", 50)
                    )
                }
            )
            return
        if path == "/api/factory/run":
            audience = self._value(query, "audience") or "implementer"
            if audience not in {"implementer", "verifier"}:
                raise ValueError("audience must be implementer or verifier")
            self._json(
                self.server.factory_store.run(
                    self._value(query, "id", required=True),
                    include_private=audience == "verifier",
                )
            )
            return
        if path == "/api/portfolio/summary":
            self._json(self.server.portfolio_store.summary())
            return
        if path == "/api/durable/summary":
            self._json(self.server.durable_store.summary())
            return
        if path == "/api/evaluations":
            self._json({
                "evaluations": self.server.evaluation_store.list_evaluations(
                    self._integer(query, "limit", 50)
                )
            })
            return
        if path == "/api/evaluation":
            self._json(self.server.evaluation_store.evaluation(
                self._value(query, "id", required=True)
            ))
            return
        if path == "/api/memory/summary":
            self._json(self.server.memory_store.summary())
            return
        if path == "/api/memory/experience":
            self._json(self.server.memory_store.experience(
                self._value(query, "id", required=True)
            ))
            return
        if path == "/api/runtime/summary":
            self._json(self.server.runtime_summary())
            return
        if path == "/api/data/summary":
            self._json(self.server.data_summary())
            return
        if path == "/api/runtime/run":
            self.server.refresh_live_projections()
            if self.server.runtime_store is None:
                raise KeyError(self._value(query, "id", required=True))
            self._json(self.server.runtime_store.run(self._value(query, "id", required=True)))
            return
        if path == "/api/audit/summary":
            self._json(self.server.audit_summary())
            return
        if path == "/api/audit/events":
            self.server.refresh_live_projections()
            if self.server.audit_store is None:
                self._json({"events": [], "total": 0})
            else:
                self._json(self.server.audit_store.events(
                    self._value(query, "audience") or "implementer",
                    self._integer(query, "limit", 100),
                ))
            return
        if path == "/api/audit/decision":
            self.server.refresh_live_projections()
            if self.server.audit_store is None:
                raise KeyError(self._value(query, "id", required=True))
            self._json(self.server.audit_store.decision(self._value(query, "id", required=True)))
            return
        if path == "/api/audit/dossier":
            self.server.refresh_live_projections()
            if self.server.audit_store is None:
                raise KeyError(self._value(query, "release", required=True))
            self._json(self.server.audit_store.dossier(
                self._value(query, "release", required=True)
            ))
            return
        if path == "/api/edge":
            edge_id = self._value(query, "id", required=True)
            result = index.edge(
                edge_id,
                self._value(query, "audience") or "implementer",
            )
            result["runtime"] = self._runtime_projection("edge", edge_id)
            self._json(result)
            return
        if path == "/api/evidence":
            self._json(self._evidence(index, query))
            return
        if path == "/api/search":
            self._json(
                {
                    "results": index.search(
                        self._value(query, "q"),
                        self._value(query, "kind"),
                        self._integer(query, "limit", 25),
                        self._value(query, "audience") or "implementer",
                    )
                }
            )
            return
        if path == "/api/node":
            node_id = self._value(query, "id", required=True)
            result = index.node(
                node_id,
                self._value(query, "audience") or "implementer",
            )
            result["runtime"] = self._runtime_projection("node", node_id)
            self._json(result)
            return
        if path == "/api/neighborhood":
            selection = index.neighborhood(
                self._value(query, "node", required=True),
                self._integer(query, "depth", 2),
                self._value(query, "audience") or "implementer",
                self._integer(query, "limit", index.max_nodes),
            )
            self._json(selection.to_dict())
            return
        if path == "/api/trace":
            result = index.trace(
                self._value(query, "from", required=True),
                self._value(query, "to", required=True),
                self._value(query, "audience") or "implementer",
                self._value(query, "direction") or "any",
            )
            self._json({
                "status": "found" if result else "not_found",
                "trace": result,
                "evidence_boundary": index.operator_context()["trace"],
            })
            return
        if path == "/api/gaps":
            gaps = index.gaps()
            self._json({"status": "passed" if not gaps else "failed", "gaps": gaps})
            return
        self._json({"error": f"Unknown API route: {path}"}, HTTPStatus.NOT_FOUND)

    def _event_stream(self, query: dict[str, list[str]]) -> None:
        after = self._integer(query, "after", 0)
        header_sequence = self.headers.get("Last-Event-ID", "")
        if header_sequence.isdigit():
            after = max(after, int(header_sequence))
        channel = self.server.operational_store.subscribe(after)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 2000\nevent: ready\ndata: {\"status\":\"live\"}\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = channel.get(timeout=15)
                    body = json.dumps(event, sort_keys=True, separators=(",", ":"))
                    packet = (
                        f"id: {event['sequence']}\nevent: operational-event\ndata: {body}\n\n"
                    ).encode("utf-8")
                except queue.Empty:
                    packet = b": heartbeat\n\n"
                self.wfile.write(packet)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            self.server.operational_store.unsubscribe(channel)

    def _runtime_projection(self, entity_kind: str, entity_id: str) -> dict[str, Any]:
        return self.server.index.runtime_projection(entity_kind, entity_id)

    def _evidence(
        self, index: GraphExplorerIndex, query: dict[str, list[str]]
    ) -> dict[str, Any]:
        if self.server.evidence_store is None:
            raise ValueError("Source evidence pack is not available.")
        owner_type = self._value(query, "owner_type", required=True)
        owner_id = self._value(query, "owner_id", required=True)
        evidence_index = self._integer(query, "evidence_index", -1)
        audience = self._value(query, "audience") or "implementer"
        if owner_type == "node":
            owner = index.node(owner_id, audience)
        elif owner_type == "edge":
            owner = index.edge(owner_id, audience)
        else:
            raise ValueError("owner_type must be node or edge")
        evidence_items = owner.get("evidence", [])
        if evidence_index < 0 or evidence_index >= len(evidence_items):
            raise ValueError("evidence_index is outside the selected owner")
        try:
            excerpt = self.server.evidence_store.excerpt(
                owner_type, owner_id, evidence_index
            )
        except KeyError as exc:
            raise ValueError("No source capsule exists for this evidence item") from exc
        return {
            **excerpt,
            "graph_content_sha256": index.payload["content_sha256"],
            "owner_id": owner_id,
            "owner_type": owner_type,
        }

    def _static(self, raw_path: str) -> None:
        requested = "index.html" if raw_path in {"", "/"} else unquote(raw_path.lstrip("/"))
        candidate = (self.server.viewer_root / requested).resolve()
        if self.server.viewer_root not in candidate.parents and candidate != self.server.viewer_root:
            self._json({"error": "Invalid static path"}, HTTPStatus.BAD_REQUEST)
            return
        if not candidate.is_file():
            self._json({"error": "Static asset not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(candidate.name)
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _request_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ChatError("Request body is required.")
        if content_length > 65536:
            raise ChatError("Request body exceeds the 64 KiB limit.")
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            raise ChatError("Content-Type must be application/json.")
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ChatError("Request body must be a JSON object.")
        return payload

    @staticmethod
    def _value(query: dict[str, list[str]], key: str, required: bool = False) -> str:
        value = query.get(key, [""])[0]
        if required and not value:
            raise ValueError(f"Missing required query parameter: {key}")
        return value

    @classmethod
    def _integer(cls, query: dict[str, list[str]], key: str, default: int) -> int:
        value = cls._value(query, key)
        return int(value) if value else default


def serve(
    graph_path: Path,
    viewer_root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    ontology_path: Path | None = None,
    evidence_pack_path: Path | None = None,
    factory_runs_path: Path | None = None,
    runtime_snapshot_path: Path | None = None,
    audit_snapshot_path: Path | None = None,
    allow_unauthenticated_network: bool = False,
    verifier_token: str | None = None,
) -> None:
    validate_bind_host(host, allow_unauthenticated_network)
    if not is_loopback_host(host):
        print(NON_LOOPBACK_WARNING)
    ontology = load_ontology(ontology_path) if ontology_path else load_ontology()
    index = GraphExplorerIndex(load_graph(graph_path), ontology=ontology)
    pack_path = evidence_pack_path or graph_path.parent / "evidence" / "source.pack.json.gz"
    evidence_store = EvidenceStore(load_evidence_pack(pack_path))
    factory_store = FactoryRunStore(
        factory_runs_path or viewer_root.resolve().parents[1] / "work"
    )
    runtime_path = runtime_snapshot_path or graph_path.parent / "runtime" / "runtime.snapshot.json.gz"
    runtime_store = (
        RuntimeEvidenceStore(load_runtime_snapshot(runtime_path))
        if runtime_path.is_file()
        else None
    )
    audit_path = audit_snapshot_path or viewer_root.resolve().parents[1] / "audit" / "audit.snapshot.json.gz"
    audit_store = AuditStore(load_audit_snapshot(audit_path)) if audit_path.is_file() else None
    server = ExplorerServer(
        (host, port), index, viewer_root, evidence_store=evidence_store,
        factory_store=factory_store,
        evaluation_store=EvaluationStore(factory_runs_path or viewer_root.resolve().parents[1] / "work"),
        runtime_store=runtime_store, audit_store=audit_store,
        graph_path=graph_path, evidence_pack_path=pack_path,
        verifier_token=verifier_token,
    )
    display_host = f"[{host.strip('[]')}]" if ":" in host else host
    url = f"http://{display_host}:{server.server_port}/"
    print(f"LIGHTYEAR Graph Explorer: {url}")
    print("Live Evidence Plane: connected (read-only command posture)")
    print(f"Verifier token (this session only): {server.verifier_token}")
    print("Customer deployments must place the Control Tower behind approved SSO/OIDC.")
    print("Press Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.operational_monitor.start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.operational_monitor.stop()
        server.server_close()
