#!/usr/bin/env python3
"""Build the bounded iDempiere release-13 reference-estate inventory.

The upstream source remains outside this repository.  This tool reads a local
checkout, verifies its pinned identity, and emits only derived counts and
source-path references.  It does not build or execute iDempiere.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reference-estates" / "idempiere"
PINNED_COMMIT = "731515dcdd5278b843db33b9d3109d155b881951"

SLICE_SEEDS = {
    "order-to-cash": (
        "org.compiere.model.MOrder",
        "org.compiere.model.MOrderLine",
        "org.compiere.model.MInOut",
        "org.compiere.model.MInOutLine",
        "org.compiere.model.MInvoice",
        "org.compiere.model.MInvoiceLine",
        "org.compiere.model.MPayment",
        "org.compiere.model.MAllocationHdr",
        "org.compiere.model.MAllocationLine",
        "org.compiere.process.InOutGenerate",
        "org.compiere.process.InvoiceGenerate",
        "org.compiere.process.AllocationAuto",
    ),
    "procure-to-pay": (
        "org.compiere.model.MOrder",
        "org.compiere.model.MOrderLine",
        "org.compiere.model.MInOut",
        "org.compiere.model.MInOutLine",
        "org.compiere.model.MInvoice",
        "org.compiere.model.MInvoiceLine",
        "org.compiere.model.MPayment",
        "org.compiere.model.MAllocationHdr",
        "org.compiere.model.MAllocationLine",
        "org.compiere.process.OrderPOCreate",
        "org.compiere.process.InOutCreateInvoice",
        "org.compiere.process.AllocationAuto",
    ),
}

ORACLE_SIGNALS = {
    "blob": r"\bBLOB\b",
    "clob": r"\bCLOB\b",
    "connect-by": r"\bCONNECT\s+BY\b",
    "date": r"\bDATE\b",
    "decode": r"\bDECODE\s*\(",
    "for-update": r"\bFOR\s+UPDATE\b",
    "merge-into": r"\bMERGE\s+INTO\b",
    "no-data-found": r"\bNO_DATA_FOUND\b",
    "number": r"\bNUMBER(?:\s*\([^)]*\))?",
    "nvl": r"\bNVL\s*\(",
    "rownum": r"\bROWNUM\b",
    "sequence-nextval": r"\b[A-Z][A-Z0-9_$#]*\s*\.\s*NEXTVAL\b",
    "timestamp": r"\bTIMESTAMP\b",
    "varchar2": r"\bVARCHAR2\b",
}

PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.MULTILINE)
TYPE_TOKEN_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]*\b")


def git(source_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def tracked_paths(source_root: Path) -> list[str]:
    output = subprocess.run(
        ["git", "-C", str(source_root), "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    return sorted(item.decode("utf-8") for item in output.split(b"\0") if item)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def java_graph(source_root: Path, paths: list[str]) -> tuple[dict[str, str], set[tuple[str, str]], int]:
    java_paths = [path for path in paths if path.lower().endswith(".java")]
    nodes: dict[str, str] = {}
    texts: dict[str, str] = {}
    packages: dict[str, str] = {}
    package_types: dict[str, dict[str, str]] = defaultdict(dict)
    line_count = 0

    for relative in java_paths:
        text = read_text(source_root / relative)
        match = PACKAGE_RE.search(text)
        if not match:
            continue
        package = match.group(1)
        fqcn = f"{package}.{Path(relative).stem}"
        nodes[fqcn] = relative
        texts[fqcn] = text
        packages[fqcn] = package
        package_types[package][Path(relative).stem] = fqcn
        line_count += len(text.splitlines())

    edges: set[tuple[str, str]] = set()
    for source, text in texts.items():
        package = packages[source]
        imports = IMPORT_RE.findall(text)
        wildcard_packages = [item[:-2] for item in imports if item.endswith(".*")]
        for target in imports:
            if target in nodes and target != source:
                edges.add((source, target))
        tokens = set(TYPE_TOKEN_RE.findall(text))
        for token in tokens:
            same_package = package_types[package].get(token)
            if same_package and same_package != source:
                edges.add((source, same_package))
            for wildcard_package in wildcard_packages:
                wildcard_target = package_types[wildcard_package].get(token)
                if wildcard_target and wildcard_target != source:
                    edges.add((source, wildcard_target))
    return nodes, edges, line_count


def slice_graph(
    slice_id: str,
    nodes: dict[str, str],
    edges: set[tuple[str, str]],
    source_root: Path,
    *,
    include_structural_graph: bool = False,
) -> dict[str, Any]:
    seeds = set(SLICE_SEEDS[slice_id])
    missing = sorted(seeds - set(nodes))
    if missing:
        raise ValueError(f"missing {slice_id} seed nodes: {missing}")
    direct_edges = sorted(edge for edge in edges if edge[0] in seeds)
    graph_nodes = sorted(seeds | {target for _, target in direct_edges})
    seed_lines = sum(len(read_text(source_root / nodes[node]).splitlines()) for node in seeds)
    result = {
        "dependency_depth": 1,
        "edge_definition": "unique internal Java source-unit references from a seed source unit",
        "edges": len(direct_edges),
        "nodes": len(graph_nodes),
        "seed_nodes": len(seeds),
        "seed_source_lines": seed_lines,
        "seeds": [
            {"node": node, "path": nodes[node]}
            for node in sorted(seeds)
        ],
    }
    if include_structural_graph:
        result["source_units"] = [
            {
                "node": node,
                "package": node.rsplit(".", 1)[0],
                "path": nodes[node],
                "role": "seed" if node in seeds else "direct-dependency",
            }
            for node in graph_nodes
        ]
        result["dependency_edges"] = [
            {"source": source, "target": target}
            for source, target in direct_edges
        ]
    return result


def oracle_signals(source_root: Path, paths: list[str]) -> dict[str, Any]:
    oracle_sql = [
        path for path in paths
        if path.lower().endswith(".sql") and "oracle" in Path(path).parts
    ]
    result: dict[str, Any] = {}
    compiled = {key: re.compile(pattern, re.IGNORECASE) for key, pattern in ORACLE_SIGNALS.items()}
    for signal, pattern in compiled.items():
        occurrences = 0
        files: list[str] = []
        for relative in oracle_sql:
            matches = pattern.findall(read_text(source_root / relative))
            if matches:
                occurrences += len(matches)
                files.append(relative)
        result[signal] = {
            "files": len(files),
            "occurrences": occurrences,
            "sample_paths": files[:5],
        }
    return result


def build_inventory(
    source_root: Path, *, include_structural_graph: bool = False
) -> dict[str, Any]:
    commit = git(source_root, "rev-parse", "HEAD")
    if commit != PINNED_COMMIT:
        raise ValueError(f"expected pinned commit {PINNED_COMMIT}; found {commit}")
    if git(source_root, "status", "--porcelain"):
        raise ValueError("upstream checkout must be clean")

    paths = tracked_paths(source_root)
    nodes, edges, java_lines = java_graph(source_root, paths)
    extension_counts = Counter(Path(path).suffix.lower() or "[none]" for path in paths)
    sql_paths = [path for path in paths if path.lower().endswith(".sql")]
    oracle_sql_paths = [path for path in sql_paths if "oracle" in Path(path).parts]
    package_count = len({node.rsplit(".", 1)[0] for node in nodes})
    tree = git(source_root, "rev-parse", "HEAD^{tree}")
    commit_time = git(source_root, "show", "-s", "--format=%cI", "HEAD")

    slices = {
        slice_id: slice_graph(
            slice_id,
            nodes,
            edges,
            source_root,
            include_structural_graph=include_structural_graph,
        )
        for slice_id in sorted(SLICE_SEEDS)
    }
    shared_seeds = set(SLICE_SEEDS["order-to-cash"]) & set(SLICE_SEEDS["procure-to-pay"])
    inventory = {
        "schema_version": "1.0",
        "claim_class": "upstream-static-inventory",
        "source": {
            "branch": "release-13",
            "commit": commit,
            "commit_time": commit_time,
            "repository": "https://github.com/idempiere/idempiere",
            "tree": tree,
        },
        "estate": {
            "extension_counts": dict(sorted(extension_counts.items())),
            "generated_model_source_units": sum(
                path.startswith("org.adempiere.base/src/org/compiere/model/X_")
                and path.endswith(".java")
                for path in paths
            ),
            "internal_java_dependency_edges": len(edges),
            "java_packages": package_count,
            "java_source_lines": java_lines,
            "java_source_units": len(nodes),
            "model_interface_source_units": sum(
                path.startswith("org.adempiere.base/src/org/compiere/model/I_")
                and path.endswith(".java")
                for path in paths
            ),
            "oracle_sql_files": len(oracle_sql_paths),
            "oracle_sql_files_current_migration": sum(
                path.startswith("migration/") and "oracle" in Path(path).parts
                for path in sql_paths
            ),
            "oracle_sql_files_historic_migration": sum(
                path.startswith("migration-historic/") and "oracle" in Path(path).parts
                for path in sql_paths
            ),
            "process_source_units": sum(
                path.startswith("org.adempiere.base.process/src/") and path.endswith(".java")
                for path in paths
            ),
            "sql_files": len(sql_paths),
            "tracked_files": len(paths),
        },
        "graph_method": {
            "edge_scope": "explicit internal imports plus same-package and wildcard-import type references",
            "node_scope": "one package-qualified node per tracked Java source unit with a package declaration",
            "not_included": [
                "runtime dispatch",
                "reflection-only dependencies",
                "application-dictionary runtime relationships",
                "database foreign keys not referenced by a selected Java source unit",
            ],
        },
        "oracle_semantic_signals": oracle_signals(source_root, paths),
        "slices": slices,
        "shared_slice_seed_nodes": len(shared_seeds),
    }
    if include_structural_graph:
        inventory["structural_graph"] = {
            "dependency_edges": [
                {"source": source, "target": target}
                for source, target in sorted(edges)
            ],
            "source_units": [
                {
                    "node": node,
                    "package": node.rsplit(".", 1)[0],
                    "path": nodes[node],
                }
                for node in sorted(nodes)
            ],
        }
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "inventory.json")
    parser.add_argument("--include-structural-graph", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    inventory = build_inventory(
        args.source_root.resolve(),
        include_structural_graph=args.include_structural_graph,
    )
    rendered = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    if args.verify:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("committed iDempiere inventory is stale")
        print(json.dumps({"status": "verified", "commit": PINNED_COMMIT}, sort_keys=True))
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "written", "path": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
