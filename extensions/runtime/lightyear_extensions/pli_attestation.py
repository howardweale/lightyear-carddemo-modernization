from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree

from lightyear_common.asymmetric import rsa_pkcs1v15_sha256_sign, rsa_pkcs1v15_sha256_verify
from lightyear_common.io import write_json
from lightyear_common.pli_build_trust import (
    DEVELOPMENT_KEY_ID,
    DEVELOPMENT_PUBLIC_EXPONENT,
    DEVELOPMENT_PUBLIC_MODULUS_HEX,
    EXPECTED_WORKFLOW,
    trusted_development_attestation,
)

from .contracts import ExtensionContractError, canonical_hash


WORKLOAD_ID = "workload:carddemo-pli-auth-risk"
ARTIFACT_FILES = {
    "candidate_jar_sha256": "pli-auth-risk-candidate.jar",
    "junit_xml_sha256": "TEST-MixedPliAuthorizationAttestation.xml",
    "dependency_inventory_sha256": "dependencies.json",
    "sbom_sha256": "sbom.cdx.json",
}
SOURCE_PATHS = (
    "candidate-java/pom.xml",
    "candidate-java/src/main/java/ai/lightyear/carddemo/service/MixedPliAuthorizationService.java",
    "candidate-java/src/attestation/java/ai/lightyear/carddemo/service/MixedPliAuthorizationAttestationHarness.java",
    "extensions/pli/modernization/behavior-contract.json",
    "extensions/pli/modernization/comparison.json",
    "extensions/pli/modernization/development.receipt.json",
    "extensions/pli/modernization/fixtures.json",
    "extensions/runtime/lightyear_extensions/pli_attestation.py",
    "src/lightyear_common/asymmetric.py",
)
EXPECTED_CHECKS = {
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


def build_attestation(
    project_root: Path,
    output_root: Path,
    source_commit: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    source_commit = source_commit or _git(project_root, "rev-parse", "HEAD")
    if not _commit_exists(project_root, source_commit):
        raise ExtensionContractError("Build attestation source commit does not exist")
    if not _paths_match_commit(project_root, source_commit):
        raise ExtensionContractError("Build attestation source paths differ from the selected commit")
    clean_tree = not _git(project_root, "status", "--porcelain")
    if not clean_tree:
        raise ExtensionContractError("Build attestation requires a clean Git worktree")

    output_root.mkdir(parents=True, exist_ok=True)
    service = project_root / SOURCE_PATHS[1]
    harness = project_root / SOURCE_PATHS[2]
    with tempfile.TemporaryDirectory(prefix="lightyear-pli-build-") as directory:
        temporary = Path(directory)
        classes = temporary / "classes"
        classes.mkdir()
        _compile(service, harness, classes)
        report_path = output_root / ARTIFACT_FILES["junit_xml_sha256"]
        _run_harness(classes, report_path)
        jar_path = output_root / ARTIFACT_FILES["candidate_jar_sha256"]
        repeat_path = temporary / "repeat.jar"
        _write_reproducible_jar(classes, jar_path)
        _write_reproducible_jar(classes, repeat_path)
        reproducible = _sha256_file(jar_path) == _sha256_file(repeat_path)

    toolchain = _java_version()
    dependency_inventory = {
        "schema_version": "1.0",
        "inventory_type": "lightyear-pli-bounded-candidate-dependencies",
        "workload_id": WORKLOAD_ID,
        "artifact": ARTIFACT_FILES["candidate_jar_sha256"],
        "scope": "standalone bounded PL/I modernization service",
        "runtime_dependencies": [
            {"name": "java.base", "version": "17", "relationship": "requires"}
        ],
        "third_party_dependencies": [],
        "toolchain": toolchain,
    }
    dependency_inventory["content_sha256"] = canonical_hash(dependency_inventory)
    dependency_path = output_root / ARTIFACT_FILES["dependency_inventory_sha256"]
    write_json(dependency_path, dependency_inventory)

    jar_sha256 = _sha256_file(jar_path)
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:5b3a9590-9fb8-5a2b-9967-4a44c7012500",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "pli-auth-risk-candidate",
                "group": "ai.lightyear",
                "version": "0.25.0",
                "bom-ref": "pkg:maven/ai.lightyear/pli-auth-risk-candidate@0.25.0",
                "hashes": [{"alg": "SHA-256", "content": jar_sha256}],
            },
            "properties": [
                {"name": "lightyear.build.scope", "value": "bounded-standalone-service"},
                {"name": "lightyear.third-party-dependency-count", "value": "0"},
            ],
        },
        "components": [],
        "dependencies": [
            {"ref": "pkg:maven/ai.lightyear/pli-auth-risk-candidate@0.25.0", "dependsOn": []}
        ],
    }
    sbom_path = output_root / ARTIFACT_FILES["sbom_sha256"]
    write_json(sbom_path, sbom)

    development_receipt = _load(project_root / "extensions/pli/modernization/development.receipt.json")
    comparison = _load(project_root / "extensions/pli/modernization/comparison.json")
    contract = _load(project_root / "extensions/pli/modernization/behavior-contract.json")
    fixtures = _load(project_root / "extensions/pli/modernization/fixtures.json")
    artifact_hashes = {name: _sha256_file(output_root / filename) for name, filename in ARTIFACT_FILES.items()}
    statement: dict[str, Any] = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": filename, "digest": {"sha256": artifact_hashes[name]}}
            for name, filename in ARTIFACT_FILES.items()
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://lightyear.ai/build/pli-bounded-jdk17/v1",
                "externalParameters": {
                    "sourceCommit": source_commit,
                    "sourceTreeSha256": _source_tree_hash(project_root),
                    "workflow": EXPECTED_WORKFLOW,
                },
                "resolvedDependencies": [
                    {"uri": "extensions/pli/modernization/development.receipt.json", "digest": {"sha256": development_receipt["content_sha256"]}},
                    {"uri": "extensions/pli/modernization/behavior-contract.json", "digest": {"sha256": contract["content_sha256"]}},
                    {"uri": "extensions/pli/modernization/fixtures.json", "digest": {"sha256": fixtures["content_sha256"]}},
                    {"uri": "extensions/pli/modernization/comparison.json", "digest": {"sha256": comparison["content_sha256"]}},
                ],
            },
            "runDetails": {
                "builder": {"id": "https://lightyear.ai/builders/reproducible-jdk17-v1"},
                "metadata": {"invocationId": f"development:{source_commit}", "cleanSourceTree": clean_tree},
            },
        },
    }
    key = _load(project_root / "extensions/pli/attestation/keys/development-test-key.json")
    if (
        key.get("key_id") != DEVELOPMENT_KEY_ID
        or key.get("public_modulus_hex") != DEVELOPMENT_PUBLIC_MODULUS_HEX
        or key.get("public_exponent") != DEVELOPMENT_PUBLIC_EXPONENT
    ):
        raise ExtensionContractError("Development signing key does not match the trusted public key")
    signature = rsa_pkcs1v15_sha256_sign(statement, key["public_modulus_hex"], key["private_exponent_hex"])
    attestation: dict[str, Any] = {
        "schema_version": "1.0",
        "attestation_type": "lightyear-pli-build-attestation",
        "statement": statement,
        "signature": {
            "algorithm": key["algorithm"],
            "key_id": key["key_id"],
            "signer_class": "development-test-key",
            "release_authorized": False,
            "value": signature,
        },
    }
    attestation["content_sha256"] = canonical_hash(attestation)
    attestation_path = output_root / "build.attestation.json"
    write_json(attestation_path, attestation)

    report = ElementTree.parse(report_path).getroot()
    checks = {
        "source_commit_bound": _paths_match_commit(project_root, source_commit),
        "clean_source_tree": clean_tree,
        "compiled_candidate": jar_path.stat().st_size > 0,
        "junit_execution": report.attrib.get("failures") == "0" and report.attrib.get("errors") == "0" and int(report.attrib.get("tests", "0")) >= 5,
        "dependency_inventory": dependency_inventory["content_sha256"] == canonical_hash(dependency_inventory, {"content_sha256"}),
        "sbom": sbom.get("bomFormat") == "CycloneDX" and sbom.get("specVersion") == "1.5",
        "ms22_evidence_bound": development_receipt.get("status") == "passed" and comparison.get("equivalent") is True and comparison.get("all_mutations_detected") is True,
        "asymmetric_signature": rsa_pkcs1v15_sha256_verify(statement, signature, key["public_modulus_hex"], key["public_exponent"]),
        "reproducible_build": reproducible,
        "release_key_separation": key.get("release_authorized") is False and key.get("not_a_secret") is True,
        "live_zos_baseline": False,
    }
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "receipt_type": "lightyear-pli-build-attestation-receipt",
        "workload_id": WORKLOAD_ID,
        "evidence_class": "attested-local-build",
        "source_commit": source_commit,
        "workflow": EXPECTED_WORKFLOW,
        "bindings": {
            **artifact_hashes,
            "build_attestation_sha256": attestation["content_sha256"],
            "development_receipt_sha256": development_receipt["content_sha256"],
            "behavior_contract_sha256": contract["content_sha256"],
            "fixtures_sha256": fixtures["content_sha256"],
            "comparison_sha256": comparison["content_sha256"],
            "source_tree_sha256": _source_tree_hash(project_root),
        },
        "checks": checks,
        "development_ready": all(checks[name] for name in EXPECTED_CHECKS - {"live_zos_baseline"}),
        "mainframe_equivalent": False,
        "production_ready": False,
        "release_attestation": False,
        "status": "passed" if all(checks[name] for name in EXPECTED_CHECKS - {"live_zos_baseline"}) else "failed",
        "unresolved_gaps": [
            "The committed signature uses a public development test key and is not a release attestation.",
            "GitHub Actions workload identity attests CI artifacts separately.",
            "No authorized compiled and executed ACCTPL1 observation exists on z/OS.",
        ],
    }
    receipt["content_sha256"] = canonical_hash(receipt)
    write_json(output_root / "build.receipt.json", receipt)
    return receipt


def validate_attestation(project_root: Path, artifact_root: Path) -> list[str]:
    errors: list[str] = []
    receipt = _load_optional(artifact_root / "build.receipt.json")
    attestation = _load_optional(artifact_root / "build.attestation.json")
    if receipt.get("receipt_type") != "lightyear-pli-build-attestation-receipt" or receipt.get("schema_version") != "1.0":
        errors.append("PL/I build receipt identity is invalid")
    if receipt.get("content_sha256") != canonical_hash(receipt, {"content_sha256"}):
        errors.append("PL/I build receipt content hash is invalid")
    if attestation.get("attestation_type") != "lightyear-pli-build-attestation" or attestation.get("schema_version") != "1.0":
        errors.append("PL/I build attestation identity is invalid")
    if attestation.get("content_sha256") != canonical_hash(attestation, {"content_sha256"}):
        errors.append("PL/I build attestation content hash is invalid")
    bindings = receipt.get("bindings", {})
    for binding, filename in ARTIFACT_FILES.items():
        path = artifact_root / filename
        if not path.exists() or bindings.get(binding) != _sha256_file(path):
            errors.append(f"PL/I build artifact is missing or tampered: {filename}")
    if bindings.get("build_attestation_sha256") != attestation.get("content_sha256"):
        errors.append("PL/I build receipt does not bind the attestation")
    key = _load(project_root / "extensions/pli/attestation/keys/development-test-key.json")
    signature = attestation.get("signature", {})
    statement = attestation.get("statement", {})
    if not trusted_development_attestation(attestation):
        errors.append("PL/I build asymmetric signature or signer identity is invalid")
    parameters = statement.get("predicate", {}).get("buildDefinition", {}).get("externalParameters", {})
    source_commit = receipt.get("source_commit", "")
    if parameters.get("sourceCommit") != source_commit or not _valid_commit_digest(source_commit):
        errors.append("PL/I build source commit binding is invalid")
    if parameters.get("workflow") != EXPECTED_WORKFLOW or receipt.get("workflow") != EXPECTED_WORKFLOW:
        errors.append("PL/I build attestation targets a foreign workflow")
    if parameters.get("sourceTreeSha256") != _source_tree_hash(project_root) or bindings.get("source_tree_sha256") != _source_tree_hash(project_root):
        errors.append("PL/I build source tree is stale")
    # A PR checkout can resolve the pre-evidence source commit and receives the
    # stronger path-by-path Git comparison.  After a squash merge that commit
    # may no longer be reachable, so the independently signed source-tree
    # digest remains the portable content binding.
    if _commit_exists(project_root, source_commit) and not _paths_match_commit(project_root, source_commit):
        errors.append("PL/I build source paths differ from the attested commit")
    development = _load(project_root / "extensions/pli/modernization/development.receipt.json")
    comparison = _load(project_root / "extensions/pli/modernization/comparison.json")
    contract = _load(project_root / "extensions/pli/modernization/behavior-contract.json")
    fixtures = _load(project_root / "extensions/pli/modernization/fixtures.json")
    expected_evidence = {
        "development_receipt_sha256": development.get("content_sha256"),
        "comparison_sha256": comparison.get("content_sha256"),
        "behavior_contract_sha256": contract.get("content_sha256"),
        "fixtures_sha256": fixtures.get("content_sha256"),
    }
    if any(bindings.get(name) != value for name, value in expected_evidence.items()):
        errors.append("PL/I build receipt is stale against MS #22 evidence")
    checks = receipt.get("checks", {})
    if set(checks) != EXPECTED_CHECKS or checks.get("live_zos_baseline") is not False or not all(checks.get(name) is True for name in EXPECTED_CHECKS - {"live_zos_baseline"}):
        errors.append("PL/I build receipt checks are incomplete or overclaim live evidence")
    if receipt.get("development_ready") is not True or receipt.get("mainframe_equivalent") is not False or receipt.get("production_ready") is not False or receipt.get("release_attestation") is not False or receipt.get("status") != "passed":
        errors.append("PL/I build receipt truth boundary is invalid")
    try:
        report = ElementTree.parse(artifact_root / ARTIFACT_FILES["junit_xml_sha256"]).getroot()
        if report.attrib.get("failures") != "0" or report.attrib.get("errors") != "0" or int(report.attrib.get("tests", "0")) < 5:
            errors.append("PL/I JUnit-compatible execution report is not green")
    except (ElementTree.ParseError, OSError, ValueError):
        errors.append("PL/I JUnit-compatible execution report is invalid")
    return errors


def _compile(service: Path, harness: Path, classes: Path) -> None:
    command = ["java", "--module", "jdk.compiler/com.sun.tools.javac.Main", "--release", "17", "-d", str(classes), str(service), str(harness)]
    _run(command, "JDK compiler")


def _run_harness(classes: Path, report: Path) -> None:
    _run(["java", "-cp", str(classes), "ai.lightyear.carddemo.service.MixedPliAuthorizationAttestationHarness", str(report)], "PL/I Java attestation harness")


def _write_reproducible_jar(classes: Path, output: Path) -> None:
    manifest = b"Manifest-Version: 1.0\r\nCreated-By: LIGHTYEAR reproducible builder\r\n\r\n"
    # Stored entries avoid zlib-version variance, while explicit creator,
    # permissions, timestamps, ordering, and empty extension fields prevent
    # ZIP headers from inheriting host-operating-system metadata.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(_canonical_jar_entry("META-INF/MANIFEST.MF"), manifest)
        for path in sorted(classes.rglob("MixedPliAuthorizationService*.class")):
            relative = path.relative_to(classes).as_posix()
            archive.writestr(_canonical_jar_entry(relative), path.read_bytes())


def _canonical_jar_entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.compress_type = zipfile.ZIP_STORED
    info.extra = b""
    info.comment = b""
    return info


def _source_tree_hash(project_root: Path) -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_PATHS:
        path = project_root / relative
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _paths_match_commit(project_root: Path, source_commit: str) -> bool:
    if not _commit_exists(project_root, source_commit):
        return False
    for relative in SOURCE_PATHS:
        result = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"], cwd=project_root,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        )
        if result.returncode or result.stdout != (project_root / relative).read_bytes():
            return False
    return True


def _commit_exists(project_root: Path, source_commit: str) -> bool:
    if not _valid_commit_digest(source_commit):
        return False
    return subprocess.run(["git", "cat-file", "-e", f"{source_commit}^{{commit}}"], cwd=project_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0


def _valid_commit_digest(source_commit: Any) -> bool:
    return (
        isinstance(source_commit, str)
        and len(source_commit) == 40
        and source_commit != "0" * 40
        and all(character in "0123456789abcdef" for character in source_commit)
    )


def _git(project_root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=project_root, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()


def _run(command: list[str], label: str) -> None:
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        raise ExtensionContractError(f"{label} failed: {detail}") from exc


def _java_version() -> dict[str, str]:
    # Vendor/build strings from ``java -version`` are observations of the
    # current runner, not inputs to this bounded build.  Keeping them in a
    # content-addressed inventory made otherwise identical Temurin, OpenJDK,
    # and OpenJ9 builds produce different receipts.  CI workload-identity
    # provenance records the concrete runner separately.
    return {
        "runtime_contract": "Java SE 17",
        "language_release": "17",
        "compiler": "jdk.compiler module",
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional(path: Path) -> dict[str, Any]:
    try:
        return _load(path)
    except (OSError, json.JSONDecodeError):
        return {}
