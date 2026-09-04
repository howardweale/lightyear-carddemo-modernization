#!/usr/bin/env python3
"""Build the bounded Oracle CloudBank v5 reference-estate inventory.

The upstream source remains outside this repository. This tool reads a local
checkout, verifies its pinned identity, and emits only derived counts and
source-path references. It does not build, execute, or translate CloudBank.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reference-estates" / "cloudbank"
PINNED_COMMIT = "4f41b16d00c45503f691836fee8138010c969e86"
PINNED_BRANCH = "main"
UPSTREAM_PREFIX = "cloudbank-v5/"

ORACLE_PATTERN = re.compile(
    r"com\.oracle\.database|oracle\.jdbc|oracle-spring|ojdbc|\bucp\b|"
    r"Oracle(?: AI)? (?:Autonomous )?Database|spring\.datasource\.oracleucp",
    re.IGNORECASE,
)
LRA_PATTERN = re.compile(r"@(?:LRA|Compensate|Complete|AfterLRA|Status)\b|microtx[-.]lra")
TRANSACTION_PATTERN = re.compile(r"@Transactional\b|jakarta\.transaction|springframework\.transaction")
MESSAGING_PATTERN = re.compile(
    r"txeventq|aqjms|jakarta\.jms|spring[-.]kafka|\bkafka\b|transactional event queue|\bjms\b",
    re.IGNORECASE,
)
SECURITY_PATTERN = re.compile(
    r"oauth2|openid-connect|authorizationserver|jwt|jwks|SCOPE_cloudbank|"
    r"CloudBankAuthorization",
    re.IGNORECASE,
)
SPRING_ENDPOINT_PATTERN = re.compile(r"@(?:Get|Post|Put|Delete|Patch)Mapping\b")
JAXRS_ENDPOINT_PATTERN = re.compile(r"@(?:GET|POST|PUT|DELETE|PATCH)\b")
DDL_PATTERNS = {
    "table": re.compile(r'\bCREATE\s+TABLE\s+(["\w.$#]+)', re.IGNORECASE),
    "sequence": re.compile(r'\bCREATE\s+SEQUENCE\s+(["\w.$#]+)', re.IGNORECASE),
    "trigger": re.compile(r'\bCREATE(?:\s+OR\s+REPLACE)?(?:\s+EDITIONABLE)?\s+TRIGGER\s+(["\w.$#]+)', re.IGNORECASE),
    "type": re.compile(r'\bCREATE(?:\s+OR\s+REPLACE)?(?:\s+EDITIONABLE)?\s+TYPE\s+(["\w.$#]+)', re.IGNORECASE),
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
        ["git", "-C", str(source_root), "ls-files", "-z", "--", "cloudbank-v5"],
        capture_output=True,
        check=True,
    ).stdout
    return sorted(
        item.decode("utf-8")[len(UPSTREAM_PREFIX):]
        for item in output.split(b"\0")
        if item and item.decode("utf-8").startswith(UPSTREAM_PREFIX)
    )


def read_text(source_root: Path, relative: str) -> str:
    return (source_root / UPSTREAM_PREFIX / relative).read_text(
        encoding="utf-8", errors="replace"
    )


def matching_files(
    source_root: Path, paths: list[str], pattern: re.Pattern[str]
) -> tuple[list[str], int]:
    files: list[str] = []
    occurrences = 0
    for relative in paths:
        text = read_text(source_root, relative)
        matches = pattern.findall(text)
        if matches:
            files.append(relative)
            occurrences += len(matches)
    return files, occurrences


def maven_modules(source_root: Path) -> list[str]:
    tree = ET.parse(source_root / "cloudbank-v5" / "pom.xml")
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    return sorted(
        item.text.strip()
        for item in tree.findall("m:modules/m:module", namespace)
        if item.text and item.text.strip()
    )


def ddl_objects(source_root: Path, sql_paths: list[str]) -> dict[str, list[str]]:
    objects: dict[str, set[str]] = {kind: set() for kind in DDL_PATTERNS}
    for relative in sql_paths:
        text = read_text(source_root, relative)
        for kind, pattern in DDL_PATTERNS.items():
            objects[kind].update(match.upper() for match in pattern.findall(text))
    return {kind: sorted(names) for kind, names in objects.items()}


def ddl_declarations(source_root: Path, sql_paths: list[str]) -> list[dict[str, str]]:
    declarations = set()
    for relative in sql_paths:
        text = read_text(source_root, relative)
        for kind, pattern in DDL_PATTERNS.items():
            declarations.update(
                (kind, match.upper(), relative) for match in pattern.findall(text)
            )
    return [
        {"kind": kind, "name": name, "path": path}
        for kind, name, path in sorted(declarations)
    ]


def source_category(path: str) -> str:
    suffix = Path(path).suffix.lower()
    name = Path(path).name
    if suffix == ".java":
        return "java"
    if suffix == ".sql":
        return "sql"
    if name == "pom.xml":
        return "build"
    if name == "values.yaml" or suffix in {".yaml", ".yml"}:
        return "deployment"
    if suffix in {".properties", ".xml"}:
        return "configuration"
    if suffix in {".sh", ".imports"}:
        return "operations"
    if suffix in {".md", ".txt", ".manual"}:
        return "documentation"
    if suffix in {".png"}:
        return "asset"
    return "other"


def structural_graph(
    paths: list[str], texts: dict[str, str]
) -> dict[str, Any]:
    java_paths = [path for path in paths if path.endswith(".java")]
    types: dict[str, dict[str, Any]] = {}
    packages: dict[str, str] = {}
    package_types: dict[str, dict[str, str]] = defaultdict(dict)

    coupling_patterns = {
        "local-transaction": TRANSACTION_PATTERN,
        "lra": LRA_PATTERN,
        "messaging": MESSAGING_PATTERN,
        "oracle": ORACLE_PATTERN,
        "security": SECURITY_PATTERN,
    }
    for path in java_paths:
        text = texts[path]
        package_match = PACKAGE_RE.search(text)
        if package_match is None:
            continue
        package = package_match.group(1)
        simple_name = Path(path).stem
        fqcn = f"{package}.{simple_name}"
        endpoint_counts = {
            "spring": len(SPRING_ENDPOINT_PATTERN.findall(text)),
            "jaxrs": len(JAXRS_ENDPOINT_PATTERN.findall(text)),
        }
        types[fqcn] = {
            "coupling_categories": sorted(
                name for name, pattern in coupling_patterns.items() if pattern.search(text)
            ),
            "endpoint_annotations": endpoint_counts,
            "module": path.split("/", 1)[0],
            "node": fqcn,
            "package": package,
            "path": path,
            "source_set": "test" if "/src/test/" in f"/{path}" else "main",
        }
        packages[fqcn] = package
        package_types[package][simple_name] = fqcn

    dependencies: set[tuple[str, str]] = set()
    for source, record in types.items():
        text = texts[record["path"]]
        package = packages[source]
        imports = IMPORT_RE.findall(text)
        wildcard_packages = [item[:-2] for item in imports if item.endswith(".*")]
        for target in imports:
            if target in types and target != source:
                dependencies.add((source, target))
        for token in set(TYPE_TOKEN_RE.findall(text)):
            same_package = package_types[package].get(token)
            if same_package and same_package != source:
                dependencies.add((source, same_package))
            for wildcard_package in wildcard_packages:
                target = package_types[wildcard_package].get(token)
                if target and target != source:
                    dependencies.add((source, target))

    return {
        "dependency_edges": [
            {"source": source, "target": target}
            for source, target in sorted(dependencies)
        ],
        "java_types": [types[node] for node in sorted(types)],
        "source_files": [
            {
                "category": source_category(path),
                "extension": Path(path).suffix.lower() or "[none]",
                "module": path.split("/", 1)[0] if "/" in path else "root",
                "path": path,
            }
            for path in paths
        ],
    }


def build_inventory(source_root: Path) -> dict[str, Any]:
    commit = git(source_root, "rev-parse", "HEAD")
    if commit != PINNED_COMMIT:
        raise ValueError(f"expected pinned commit {PINNED_COMMIT}; found {commit}")
    if git(source_root, "status", "--porcelain"):
        raise ValueError("upstream checkout must be clean")

    paths = tracked_paths(source_root)
    texts = {path: read_text(source_root, path) for path in paths}
    java_paths = [path for path in paths if path.endswith(".java")]
    main_java = [path for path in java_paths if "/src/main/" in f"/{path}"]
    test_java = [path for path in java_paths if "/src/test/" in f"/{path}"]
    sql_paths = [path for path in paths if path.endswith(".sql")]
    pom_paths = [path for path in paths if Path(path).name == "pom.xml"]
    values_paths = [path for path in paths if Path(path).name == "values.yaml"]
    shell_paths = [path for path in paths if path.endswith(".sh")]
    modules = maven_modules(source_root)

    signals: dict[str, dict[str, Any]] = {}
    for name, pattern in (
        ("oracle_coupling", ORACLE_PATTERN),
        ("lra_distributed_transactions", LRA_PATTERN),
        ("local_transactions", TRANSACTION_PATTERN),
        ("messaging", MESSAGING_PATTERN),
        ("security", SECURITY_PATTERN),
    ):
        files, occurrences = matching_files(source_root, paths, pattern)
        signals[name] = {
            "files": len(files),
            "occurrences": occurrences,
            "sample_paths": files[:12],
        }

    spring_endpoint_files, spring_endpoints = matching_files(
        source_root, main_java, SPRING_ENDPOINT_PATTERN
    )
    jaxrs_endpoint_files, jaxrs_endpoints = matching_files(
        source_root, main_java, JAXRS_ENDPOINT_PATTERN
    )
    extension_counts = Counter(Path(path).suffix.lower() or "[none]" for path in paths)
    deployable_units = sorted(str(Path(path).parent) for path in values_paths)
    root_scripts = sorted(path for path in shell_paths if "/" not in path)

    return {
        "schema_version": "1.0",
        "claim_class": "upstream-static-modern-oracle-inventory",
        "source": {
            # The inventory records the pinned upstream branch, not the local
            # checkout state. CI intentionally checks the commit out detached.
            "branch": PINNED_BRANCH,
            "commit": commit,
            "commit_time": git(source_root, "show", "-s", "--format=%cI", "HEAD"),
            "repository": "https://github.com/oracle/microservices-backend",
            "root_tree": git(source_root, "rev-parse", "HEAD^{tree}"),
            "subtree": "cloudbank-v5",
            "subtree_tree": git(source_root, "rev-parse", "HEAD:cloudbank-v5"),
        },
        "estate": {
            "tracked_files": len(paths),
            "extension_counts": dict(sorted(extension_counts.items())),
            "maven_modules": modules,
            "maven_module_count": len(modules),
            "runtime_service_modules": sorted(
                module for module in modules if module not in {"buildtools", "common"}
            ),
            "runtime_service_module_count": sum(
                module not in {"buildtools", "common"} for module in modules
            ),
            "deployable_units": deployable_units,
            "deployable_unit_count": len(deployable_units),
            "java_source_units": len(java_paths),
            "main_java_source_units": len(main_java),
            "test_java_source_units": len(test_java),
            "java_source_lines": sum(len(texts[path].splitlines()) for path in java_paths),
            "sql_files": len(sql_paths),
            "sql_source_lines": sum(len(texts[path].splitlines()) for path in sql_paths),
            "maven_pom_files": len(pom_paths),
            "helm_values_files": len(values_paths),
            "root_operational_scripts": root_scripts,
            "root_operational_script_count": len(root_scripts),
        },
        "api_surface": {
            "spring_endpoint_annotations": spring_endpoints,
            "spring_endpoint_files": spring_endpoint_files,
            "jaxrs_endpoint_annotations": jaxrs_endpoints,
            "jaxrs_endpoint_files": jaxrs_endpoint_files,
        },
        "database_surface": {
            "ddl_objects": ddl_objects(source_root, sql_paths),
            "ddl_declarations": ddl_declarations(source_root, sql_paths),
            "sql_paths": sql_paths,
        },
        "coupling_signals": signals,
        "structural_graph": structural_graph(paths, texts),
        "inventory_method": {
            "scope": "tracked files under the pinned cloudbank-v5 subtree",
            "endpoint_scope": "Spring mapping and JAX-RS verb annotations in tracked Java source",
            "database_scope": "DDL objects and Oracle-specific dependency/configuration signals in tracked source",
            "not_included": [
                "compiled dependency bytecode",
                "runtime database metadata",
                "executed API traces",
                "observed transaction outcomes",
                "PostgreSQL compatibility or target equivalence",
            ],
            "structural_projection": (
                "tracked source files, package-qualified Java types, and deterministic "
                "internal Java source dependencies"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "inventory.json")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    inventory = build_inventory(args.source_root.resolve())
    rendered = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    if args.verify:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("committed CloudBank inventory is stale")
        print(json.dumps({"status": "verified", "commit": PINNED_COMMIT}, sort_keys=True))
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "written", "path": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
