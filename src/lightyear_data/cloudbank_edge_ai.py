from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from lightyear_common.io import write_json, write_text

from .cloudbank_baseline import PINNED_COMMIT, PINNED_ROOT_TREE, PINNED_SUBTREE, PINNED_SUBTREE_TREE
from .cloudbank_checks_messaging import (
    RECEIPT_TYPE as MS63_RECEIPT_TYPE,
    materialize_target as materialize_ms63_target,
    validate_checks_source,
    validate_execution_receipt as validate_ms63_receipt,
)
from .cloudbank_customer_postgres import POSTGRES_IMAGE
from .cloudbank_dark_factory import PATCHES as CUSTOMER_PATCHES
from .cloudbank_production_qualification import (
    RECEIPT_TYPE as MS57_RECEIPT_TYPE,
    validate_execution_receipt as validate_ms57_receipt,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.64.0"
OUTPUT_ROOT = Path("factory/cloudbank/edge-ai")
PATCH_ROOT = OUTPUT_ROOT / "patches"
CUSTOMER_PATCH_ROOT = Path("factory/cloudbank/customer-postgresql/patches")
RECEIPT_TYPE = "lightyear-cloudbank-edge-ai-execution"
RECEIPT_NAME = "cloudbank-edge-ai.receipt.json"
FAILURE_NAME = "cloudbank-edge-ai.failure.json"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
# Generated-target overrides for the vulnerabilities found by the MS67 image scan.
RUNTIME_DEPENDENCY_VERSIONS = {
    "httpcore5.version": "5.4.3",
    "tomcat.version": "10.1.59",
    "postgresql.version": "42.7.12",
    "spring-ai.version": "1.0.7",
}

SCENARIO_IDS = [
    "eight-service-target-packaged",
    "oracle-and-microtx-runtime-absent",
    "azn-server-target-workcell-generated",
    "azn-server-target-workcell-executed",
    "checks-target-workcell-generated",
    "checks-target-workcell-executed",
    "testrunner-target-workcell-generated",
    "testrunner-target-workcell-executed",
    "creditscore-target-workcell-generated",
    "creditscore-target-workcell-executed",
    "chatbot-target-workcell-generated",
    "chatbot-target-workcell-executed",
    "creditscore-missing-token-rejected",
    "creditscore-wrong-audience-rejected",
    "creditscore-missing-scope-rejected",
    "creditscore-subject-bound",
    "creditscore-same-subject-date-stable",
    "creditscore-declared-range-enforced",
    "creditscore-synthetic-provenance-returned",
    "chatbot-missing-token-rejected",
    "chatbot-wrong-audience-rejected",
    "chatbot-missing-scope-rejected",
    "chatbot-input-policy-fails-closed",
    "chatbot-output-policy-fails-closed",
    "chatbot-caller-rate-limit-enforced",
    "chatbot-model-egress-policy-enforced",
    "chatbot-model-failure-safe",
    "raw-prompts-responses-and-secrets-not-persisted",
]
CONTRACT_SHA256 = hashlib.sha256(";".join(SCENARIO_IDS).encode()).hexdigest()

PATCHES = {
    "account/src/main/java/com/example/accounts/config/AccountOAuthSecurityConfiguration.java":
        "AccountOAuthSecurityConfiguration.java",
    "transfer/src/main/java/com/example/transfer/config/TransferOAuthSecurityConfiguration.java":
        "TransferOAuthSecurityConfiguration.java",
    "account/src/test/java/com/example/accounts/AccountKubernetesProbeSecurityTest.java":
        "AccountKubernetesProbeSecurityTest.java",
    "transfer/src/test/java/com/example/transfer/TransferKubernetesProbeSecurityTest.java":
        "TransferKubernetesProbeSecurityTest.java",
    **{
        f"{service}/src/test/java/com/example/qualification/AbstractKubernetesProbeSecurityTest.java":
            "AbstractKubernetesProbeSecurityTest.java"
        for service in ("account", "transfer", "creditscore", "chatbot")
    },
    "azn-server/src/main/resources/application.yaml": "azn-application.yaml",
    (
        "azn-server/src/main/java/oracle/obaas/aznserver/securityconfig/"
        "ProductionAudienceTokenCustomizer.java"
    ): "ProductionAudienceTokenCustomizer.java",
    (
        "azn-server/src/test/java/oracle/obaas/aznserver/securityconfig/"
        "ProductionAudienceTokenCustomizerTest.java"
    ): "ProductionAudienceTokenCustomizerTest.java",
    "checks/src/test/java/com/example/checks/ChecksTargetWorkcellTest.java":
        "ChecksTargetWorkcellTest.java",
    "testrunner/src/test/java/com/example/testrunner/TestrunnerTargetWorkcellTest.java":
        "TestrunnerTargetWorkcellTest.java",
    "creditscore/pom.xml": "creditscore-pom.xml",
    "creditscore/src/main/java/com/example/creditscore/controller/CreditScoreController.java":
        "CreditScoreController.java",
    "creditscore/src/main/java/com/example/creditscore/service/SyntheticCreditScoreService.java":
        "SyntheticCreditScoreService.java",
    "creditscore/src/main/java/com/example/creditscore/config/CreditScoreOAuthSecurityConfiguration.java":
        "CreditScoreOAuthSecurityConfiguration.java",
    "creditscore/src/main/resources/application.yaml": "creditscore-application.yaml",
    "creditscore/src/test/java/com/example/creditscore/CreditscoreApplicationTests.java":
        "CreditscoreApplicationTests.java",
    "chatbot/pom.xml": "chatbot-pom.xml",
    "chatbot/src/main/java/com/example/chatbot/controller/ChatController.java": "ChatController.java",
    "chatbot/src/main/java/com/example/chatbot/config/ChatbotOAuthSecurityConfiguration.java":
        "ChatbotOAuthSecurityConfiguration.java",
    "chatbot/src/main/java/com/example/chatbot/config/ChatbotEndpointPolicy.java":
        "ChatbotEndpointPolicy.java",
    "chatbot/src/main/resources/application.yaml": "chatbot-application.yaml",
    "chatbot/src/test/java/com/example/chatbot/ChatbotApplicationTest.java":
        "ChatbotApplicationTest.java",
}

WORKCELL_TEST_SPECS = [
    {
        "service": "account",
        "disposition": "migrated",
        "migration_milestone": 62,
        "test_class": "AccountKubernetesProbeSecurityTest",
        "report": "account/target/surefire-reports/TEST-com.example.accounts.AccountKubernetesProbeSecurityTest.xml",
        "tests": 4,
    },
    {
        "service": "transfer",
        "disposition": "migrated",
        "migration_milestone": 62,
        "test_class": "TransferKubernetesProbeSecurityTest",
        "report": "transfer/target/surefire-reports/TEST-com.example.transfer.TransferKubernetesProbeSecurityTest.xml",
        "tests": 4,
    },
    {
        "service": "azn-server",
        "disposition": "migrated",
        "migration_milestone": 62,
        "test_class": "ProductionAudienceTokenCustomizerTest",
        "report": (
            "azn-server/target/surefire-reports/"
            "TEST-oracle.obaas.aznserver.securityconfig.ProductionAudienceTokenCustomizerTest.xml"
        ),
        "tests": 3,
    },
    {
        "service": "checks",
        "disposition": "migrated",
        "migration_milestone": 63,
        "test_class": "ChecksTargetWorkcellTest",
        "report": "checks/target/surefire-reports/TEST-com.example.checks.ChecksTargetWorkcellTest.xml",
        "tests": 4,
    },
    {
        "service": "testrunner",
        "disposition": "migrated",
        "migration_milestone": 63,
        "test_class": "TestrunnerTargetWorkcellTest",
        "report": (
            "testrunner/target/surefire-reports/"
            "TEST-com.example.testrunner.TestrunnerTargetWorkcellTest.xml"
        ),
        "tests": 4,
    },
    {
        "service": "creditscore",
        "disposition": "migrated",
        "migration_milestone": 64,
        "test_class": "CreditscoreApplicationTests",
        "report": (
            "creditscore/target/surefire-reports/"
            "TEST-com.example.creditscore.CreditscoreApplicationTests.xml"
        ),
        "tests": 8,
    },
    {
        "service": "chatbot",
        "disposition": "migrated",
        "migration_milestone": 64,
        "test_class": "ChatbotApplicationTest",
        "report": "chatbot/target/surefire-reports/TEST-com.example.chatbot.ChatbotApplicationTest.xml",
        "tests": 10,
    },
]
REQUIRED_TESTS = {"tests": 37, "failures": 0, "errors": 0, "skipped": 0}


def required_workcells() -> list[dict[str, Any]]:
    return [
        {
            "service": spec["service"],
            "disposition": spec["disposition"],
            "migration_milestone": spec["migration_milestone"],
            "generated": True,
            "executed": True,
            "tests": spec["tests"],
            "failures": 0,
            "errors": 0,
            "skipped": 0,
        }
        for spec in WORKCELL_TEST_SPECS
    ]

SOURCE_FILES = {
    "creditscore/pom.xml": "204bfb6d11c83e794a90daff2aeac48fbbcdd194fec4b63187c23ff6ddf18b6e",
    "creditscore/src/main/java/com/example/creditscore/CreditscoreApplication.java":
        "590057cf3868b7dfb639204cb146b6539383be3b3fb5d9725a184f54210a893c",
    "creditscore/src/main/java/com/example/creditscore/controller/CreditScoreController.java":
        "134de61504c2d087c41462393cbe2e98f02343f19694049fe1c5af94865b0e66",
    "creditscore/src/main/resources/application.yaml":
        "4475f51ef4abd3ee4b3368e9148581a0d970ff9aaf69a2eadde22ba867de08ff",
    "creditscore/src/test/java/com/example/creditscore/CreditscoreApplicationTests.java":
        "a83870a5fabf67e73d393304325378870ed7b28476375c4a7d8772f0da7914af",
    "chatbot/pom.xml": "df1ddc7455eed43a1c3de81a43d3099734f39d41f00defdf747673f3de26292f",
    "chatbot/src/main/java/com/example/chatbot/ChatbotApplication.java":
        "19c5036a178ed60bb723eabe5122d8433d16918f0c9462a13a0b08c32ba3c47b",
    "chatbot/src/main/java/com/example/chatbot/controller/ChatController.java":
        "d9c86b21e23dd47954a180589833c190f8fed8483463caa2afd8cc6cee2079c1",
    "chatbot/src/main/resources/application.yaml":
        "b11066c83bc85d388ecb55ba6a77dfcb678907e903412273210c6f34c6f401b9",
    "chatbot/src/test/java/com/example/chatbot/ChatbotApplicationTest.java":
        "3409abe2cc5ea5115dc03ec9ab13d79bfa2bba61d7acf8e644b889413c3dcbc1",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-edge-ai-source",
        "release": RELEASE,
        "source": {
            "commit": PINNED_COMMIT,
            "root_tree": PINNED_ROOT_TREE,
            "subtree": PINNED_SUBTREE,
            "subtree_tree": PINNED_SUBTREE_TREE,
        },
        "source_bindings": [
            {"path": path, "sha256": digest} for path, digest in sorted(SOURCE_FILES.items())
        ],
        "source_semantics": {
            "creditscore": "unauthenticated-random-500-through-899-demo-score",
            "chatbot": "oauth-scoped-ollama-chat-with-in-process-basic-guardrails",
            "database_dependency": False,
            "production_bureau_integration": False,
            "model_quality_baseline": False,
        },
    })


def edge_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-credit-decision-ai-boundary",
        "release": RELEASE,
        "creditscore": {
            "identity": "signed-jwt-subject",
            "audience": "cloudbank-creditscore",
            "scope": "cloudbank.read",
            "provider": "deterministic-hmac-sha256-synthetic-v1",
            "range": {"minimum": 500, "maximum": 899},
            "stability": "same-subject-and-utc-date",
            "pepper": "runtime-only-minimum-32-characters",
            "persistence": False,
            "real_credit_decision": False,
        },
        "chatbot": {
            "identity": "signed-jwt-subject",
            "audience": "cloudbank-chatbot",
            "scope": "cloudbank.read",
            "input_limit_characters": 2000,
            "output_limit_characters": 4000,
            "prompt_boundary": "system-and-user-messages-separated",
            "input_and_output_policy": "fail-closed",
            "rate_limit": "per-authenticated-subject-window",
            "model_egress": "host-allowlisted-https-except-loopback",
            "model_failure": "safe-503-no-upstream-detail",
            "raw_prompt_or_response_persistence": False,
            "model_quality_qualified": False,
        },
        "required_scenarios": SCENARIO_IDS,
    })


def execution_plan(project_root: Path) -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "plan_type": "lightyear-cloudbank-eight-service-edge-ai-wave",
        "release": RELEASE,
        "requires": ["signed-ms63-receipt", "signed-ms57-receipt", "same-evidence-key",
                     "same-postgresql-image"],
        "services": ["azn-server", "customer", "account", "transfer", "checks", "testrunner",
                     "creditscore", "chatbot"],
        "base_targets": ["ms63-five-service-target", "ms57-qualified-customer-target"],
        "runtime_dependency_versions": dict(RUNTIME_DEPENDENCY_VERSIONS),
        "remaining_service_workcells": [
            {
                "service": spec["service"],
                "disposition": spec["disposition"],
                "migration_milestone": spec["migration_milestone"],
                "generated_and_executed_by_ms64": True,
                "test_class": spec["test_class"],
            }
            for spec in WORKCELL_TEST_SPECS
        ],
        "customer_target_paths": sorted(CUSTOMER_PATCHES),
        "patches": [
            {"path": target, "template": f"patches/{template}",
             "template_sha256": _sha256(project_root / PATCH_ROOT / template)}
            for target, template in sorted(PATCHES.items())
        ],
        "stages": [
            "validate-signed-ms63-ms57-and-pinned-source",
            "materialize-fresh-isolated-eight-service-target",
            "carry-qualified-postgresql-customer-target",
            "pin-reviewed-runtime-dependency-versions-in-target-parent",
            "replace-random-score-with-subject-bound-synthetic-provider",
            "bind-credit-and-chat-tokens-to-distinct-audiences",
            "enforce-chat-input-output-rate-and-egress-guardrails",
            "package-eight-zero-oracle-zero-microtx-executable-jars",
            "execute-azn-checks-testrunner-credit-chat-and-kubernetes-probe-workcell-tests",
            "sign-bounded-edge-ai-receipt",
        ],
        "source_checkout_mutated": False,
        "fresh_output_required": True,
        "production_data": False,
        "external_credit_bureau": False,
        "external_model_called_by_acceptance": False,
        "whole_application_equivalence": False,
    })


def compatibility_ledger() -> dict[str, Any]:
    rows = [
        ("creditscore-authentication", "target-native-qualified", "oauth-jwt"),
        ("creditscore-audience-isolation", "target-native-qualified", "cloudbank-creditscore"),
        ("creditscore-randomness", "replaced-by-policy", "subject-date-hmac"),
        ("creditscore-real-bureau-result", "not-qualified", "provider-integration-required"),
        ("chatbot-authentication", "target-native-qualified", "oauth-jwt"),
        ("chatbot-audience-isolation", "target-native-qualified", "cloudbank-chatbot"),
        ("chatbot-prompt-separation", "target-native-qualified", "system-user-message-boundary"),
        ("chatbot-input-output-filtering", "target-native-qualified", "negative-tests"),
        ("chatbot-caller-rate-limit", "target-native-qualified", "subject-window"),
        ("chatbot-model-egress", "target-native-qualified", "allowlist-and-tls-policy"),
        ("chatbot-model-answer-quality", "not-qualified", "approved-model-evaluation-required"),
        ("eight-service-package", "target-native-qualified", "zero-oracle-zero-microtx"),
        ("azn-server-disposition", "migrated-and-ms64-executed", "ms62-target-composed"),
        ("checks-disposition", "migrated-and-ms64-executed", "ms63-target-composed"),
        ("testrunner-disposition", "migrated-and-ms64-executed", "ms63-target-composed"),
        ("creditscore-disposition", "migrated-and-ms64-executed", "ms64-target"),
        ("chatbot-disposition", "migrated-and-ms64-executed", "ms64-target"),
        ("whole-application-equivalence", "not-qualified", "integrated-dual-run-required"),
        ("production-deployment", "not-qualified", "operational-gate-required"),
    ]
    return seal({
        "schema_version": "1.0",
        "ledger_type": "lightyear-cloudbank-edge-ai-compatibility",
        "release": RELEASE,
        "entries": [
            {"capability": capability, "classification": classification, "evidence": evidence}
            for capability, classification, evidence in rows
        ],
        "remaining_service_workcells_eligible": True,
        "eight_service_target_eligible": True,
        "real_credit_decision_equivalent": False,
        "model_quality_qualified": False,
        "whole_application_equivalent": False,
        "production_ready": False,
    })


def acceptance_contract(project_root: Path) -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-edge-ai-acceptance",
        "release": RELEASE,
        "bindings": {
            "source_contract_sha256": source_contract()["content_sha256"],
            "edge_contract_sha256": edge_contract()["content_sha256"],
            "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
            "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
        },
        "required_receipts": [MS63_RECEIPT_TYPE, MS57_RECEIPT_TYPE],
        "required_scenarios": SCENARIO_IDS,
        "required_contract_sha256": CONTRACT_SHA256,
        "required_tests": REQUIRED_TESTS,
        "required_workcells": required_workcells(),
        "required_packaging": {"executable_jars": 8, "oracle_runtime_libraries": 0,
                               "microtx_runtime_libraries": 0},
        "eligible_claim": {
            "remaining_service_workcells_complete": True,
            "eight_service_target_assembled": True,
            "real_credit_decision_equivalent": False,
            "model_quality_qualified": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        },
    })


def readiness_receipt(project_root: Path) -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-cloudbank-edge-ai-readiness",
        "release": RELEASE,
        "bindings": {
            **acceptance_contract(project_root)["bindings"],
            "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
        },
        "gate_status": "ready-for-signed-ms63-ms57-edge-ai-run",
        "remaining_service_workcells_complete": False,
        "eight_service_target_assembled": False,
        "real_credit_decision_equivalent": False,
        "model_quality_qualified": False,
        "whole_application_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    })


def build_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "source-contract.json": source_contract(),
        "edge-contract.json": edge_contract(),
        "execution-plan.json": execution_plan(project_root),
        "compatibility-ledger.json": compatibility_ledger(),
        "acceptance-contract.json": acceptance_contract(project_root),
        "readiness.receipt.json": readiness_receipt(project_root),
    }


def write_artifacts(project_root: Path) -> None:
    for name, payload in build_artifacts(project_root).items():
        write_json(project_root / OUTPUT_ROOT / name, payload)


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    for name, expected in build_artifacts(project_root).items():
        try:
            actual = json.loads((project_root / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-edge-ai-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-edge-ai-artifact-drift:{name}")
    for claim in (
        "remaining_service_workcells_complete", "eight_service_target_assembled",
        "real_credit_decision_equivalent", "model_quality_qualified",
        "whole_application_equivalent", "migration_complete", "production_ready",
    ):
        if readiness_receipt(project_root).get(claim) is not False:
            errors.append("cloudbank-edge-ai-readiness-overclaims")
    if len(SCENARIO_IDS) != 28 or len(set(SCENARIO_IDS)) != 28:
        errors.append("cloudbank-edge-ai-scenarios-invalid")
    return sorted(set(errors))


def validate_edge_source(source_root: Path) -> list[str]:
    errors = validate_checks_source(source_root)
    root = source_root / PINNED_SUBTREE
    for path, expected in sorted(SOURCE_FILES.items()):
        candidate = root / path
        if not candidate.is_file():
            errors.append(f"cloudbank-edge-ai-source-missing:{path}")
        elif _sha256(candidate) != expected:
            errors.append(f"cloudbank-edge-ai-source-drift:{path}")
    return sorted(set(errors))


def _pin_runtime_dependencies(root_pom: Path) -> None:
    text = root_pom.read_text(encoding="utf-8")
    marker = "    </properties>"
    if text.count(marker) != 1:
        raise ValueError("cloudbank-edge-ai-runtime-dependency-pom-drift")
    # The pinned source already declares its Spring AI BOM property.
    source_versions = {"spring-ai.version": "1.0.5"}
    overrides = "        <!-- Reviewed MS67 runtime security updates for the generated target. -->\n"
    for name, version in sorted(RUNTIME_DEPENDENCY_VERSIONS.items()):
        replacement = f"<{name}>{version}</{name}>"
        if name in source_versions:
            expected = f"<{name}>{source_versions[name]}</{name}>"
            if text.count(f"<{name}>") != 1 or text.count(expected) != 1:
                raise ValueError("cloudbank-edge-ai-runtime-dependency-pom-drift")
            text = text.replace(expected, replacement, 1)
        elif f"<{name}>" in text:
            raise ValueError("cloudbank-edge-ai-runtime-dependency-pom-drift")
        else:
            overrides += f"        {replacement}\n"
    write_text(root_pom, text.replace(marker, overrides + marker, 1))


def materialize_target(project_root: Path, source_root: Path, output: Path) -> Path:
    workspace = materialize_ms63_target(project_root, source_root, output)
    _pin_runtime_dependencies(workspace / "pom.xml")
    for target, (template, _) in CUSTOMER_PATCHES.items():
        destination = workspace / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_root / CUSTOMER_PATCH_ROOT / template, destination)
    for target, template in PATCHES.items():
        destination = workspace / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_root / PATCH_ROOT / template, destination)
    return workspace


def _package_inventory(workspace: Path) -> dict[str, int]:
    modules = ["azn-server", "customer", "account", "transfer", "checks", "testrunner",
               "creditscore", "chatbot"]
    jars = [workspace / name / "target" / f"{name}-0.0.1-SNAPSHOT.jar" for name in modules]
    if not all(path.is_file() and zipfile.is_zipfile(path) for path in jars):
        return {"executable_jars": 0, "oracle_runtime_libraries": -1,
                "microtx_runtime_libraries": -1}
    oracle = microtx = 0
    for jar in jars:
        with zipfile.ZipFile(jar) as archive:
            names = [name.lower() for name in archive.namelist() if "boot-inf/lib/" in name.lower()]
        oracle += sum(any(marker in name for marker in
                          ("ojdbc", "oracle-spring", "oraclepki", "osdt_", "ucp-", "aqapi"))
                      for name in names)
        microtx += sum(any(marker in name for marker in ("microtx", "tmm-")) for name in names)
    return {"executable_jars": 8, "oracle_runtime_libraries": oracle,
            "microtx_runtime_libraries": microtx}


def _workcell_results(workspace: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for spec in WORKCELL_TEST_SPECS:
        report = workspace / str(spec["report"])
        totals = {"tests": -1, "failures": -1, "errors": -1, "skipped": -1}
        if report.is_file():
            root = ET.parse(report).getroot()
            totals = {name: int(root.attrib.get(name, "-1")) for name in totals}
        results.append({
            "service": spec["service"],
            "disposition": spec["disposition"],
            "migration_milestone": spec["migration_milestone"],
            "generated": True,
            "executed": totals == {
                "tests": spec["tests"], "failures": 0, "errors": 0, "skipped": 0,
            },
            **totals,
        })
    return results


def _test_totals(workcells: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    if any(item[name] < 0 for item in workcells for name in totals):
        return {name: -1 for name in totals}
    for name in totals:
        totals[name] = sum(int(item[name]) for item in workcells)
    return totals


def _native_lane(
    workspace: Path,
    run: Callable[..., subprocess.CompletedProcess[str]],
    progress: Callable[[str], None],
) -> dict[str, Any]:
    modules = "azn-server,customer,account,transfer,checks,testrunner,creditscore,chatbot"
    common = ["-Djkube.skip=true", "-Ddependency-check.skip=true"]
    progress("Packaging the isolated eight-service target")
    package = run(["mvn", "-pl", modules, "-am", "-DskipTests", *common, "package"],
                  cwd=workspace, env=os.environ.copy(), text=True, capture_output=True, timeout=1200)
    packaging = _package_inventory(workspace)
    progress("Executing target workcells and Kubernetes probe authorization tests")
    test_classes = ",".join(str(spec["test_class"]) for spec in WORKCELL_TEST_SPECS)
    tests = run([
        "mvn", "-pl", "account,transfer,azn-server,checks,testrunner,creditscore,chatbot", "-am",
        f"-Dtest={test_classes}",
        "-Dsurefire.failIfNoSpecifiedTests=false", *common, "test",
    ], cwd=workspace, env=os.environ.copy(), text=True, capture_output=True, timeout=1200)
    workcells = _workcell_results(workspace)
    totals = _test_totals(workcells)
    required_packaging = {"executable_jars": 8, "oracle_runtime_libraries": 0,
                          "microtx_runtime_libraries": 0}
    required_tests = REQUIRED_TESTS
    passed = package.returncode == 0 and tests.returncode == 0 and packaging == required_packaging \
        and totals == required_tests and workcells == required_workcells()
    scenarios = [{"id": identifier, "status": "passed" if passed else "failed"}
                 for identifier in SCENARIO_IDS]
    return {
        "lane": "native-cloudbank-eight-service-edge-ai",
        "status": "passed" if passed else "failed",
        "reason": None if passed else "package-or-test-gate-failed",
        "contract_sha256": CONTRACT_SHA256,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "tests": totals,
        "workcells": workcells,
        "packaging": packaging,
        "package_exit_code": package.returncode,
        "test_exit_code": tests.returncode,
        "package_stdout_sha256": hashlib.sha256(package.stdout.encode()).hexdigest(),
        "package_stderr_sha256": hashlib.sha256(package.stderr.encode()).hexdigest(),
        "test_stdout_sha256": hashlib.sha256(tests.stdout.encode()).hexdigest(),
        "test_stderr_sha256": hashlib.sha256(tests.stderr.encode()).hexdigest(),
        "external_credit_bureau_called": False,
        "external_model_called": False,
        "synthetic_data_only": True,
        "raw_output_persisted": False,
    }


def execute_edge_ai(
    project_root: Path,
    source_root: Path,
    ms63_receipt: Mapping[str, Any],
    ms57_receipt: Mapping[str, Any],
    output_root: Path,
    key: str,
    signer: str,
    run_id: str | None = None,
    *,
    lane_runner: Callable[[Path], dict[str, Any]] | None = None,
    progress: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    errors = validate_edge_source(source_root)
    errors.extend(validate_ms63_receipt(dict(ms63_receipt), key, project_root))
    errors.extend(validate_ms57_receipt(ms57_receipt, key, project_root))
    if errors or ms63_receipt.get("receipt_type") != MS63_RECEIPT_TYPE \
            or ms57_receipt.get("receipt_type") != MS57_RECEIPT_TYPE:
        raise ValueError("cloudbank-edge-ai-signed-ms63-ms57-receipts-required")
    image_id = str(ms63_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(image_id) or ms57_receipt.get("postgresql_image_id_sha256") != image_id:
        raise ValueError("cloudbank-edge-ai-postgresql-image-chain-invalid")
    output_root.mkdir(parents=True, exist_ok=True)
    workspace = materialize_target(project_root, source_root, output_root / "workspace")
    lane = lane_runner(workspace) if lane_runner else _native_lane(workspace, subprocess.run, progress)
    required_packaging = {"executable_jars": 8, "oracle_runtime_libraries": 0,
                          "microtx_runtime_libraries": 0}
    required_tests = REQUIRED_TESTS
    accepted = lane.get("status") == "passed" \
        and lane.get("contract_sha256") == CONTRACT_SHA256 \
        and lane.get("scenario_count") == len(SCENARIO_IDS) \
        and [item.get("id") for item in lane.get("scenarios", [])] == SCENARIO_IDS \
        and all(item.get("status") == "passed" for item in lane.get("scenarios", [])) \
        and lane.get("packaging") == required_packaging and lane.get("tests") == required_tests \
        and lane.get("workcells") == required_workcells() \
        and lane.get("external_credit_bureau_called") is False \
        and lane.get("external_model_called") is False \
        and lane.get("synthetic_data_only") is True and lane.get("raw_output_persisted") is False
    if not accepted:
        write_json(output_root / FAILURE_NAME, {
            "schema_version": "1.0", "status": "failed", "reason": "acceptance-failed",
            "lane_status": lane.get("status"), "scenario_count": lane.get("scenario_count", 0),
            "tests": lane.get("tests"), "workcells": lane.get("workcells"),
            "packaging": lane.get("packaging"),
            "raw_output_persisted": False,
        })
        raise ValueError("cloudbank-edge-ai-acceptance-failed")
    receipt = sign({
        "schema_version": "1.0", "receipt_type": RECEIPT_TYPE, "release": RELEASE,
        "run_id": run_id or f"cloudbank-edge-ai-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
        "source_ms63_receipt_sha256": ms63_receipt["content_sha256"],
        "source_ms57_receipt_sha256": ms57_receipt["content_sha256"],
        "postgresql_image_id_sha256": image_id,
        "bindings": readiness_receipt(project_root)["bindings"],
        "edge_ai_lane": lane,
        "status": "passed-edge-ai-application-boundary",
        "remaining_service_workcells_complete": True,
        "eight_service_target_assembled": True,
        "real_credit_decision_equivalent": False,
        "model_quality_qualified": False,
        "whole_application_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    }, key, signer)
    write_json(output_root / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(
    receipt: Mapping[str, Any], key: str, project_root: Path
) -> list[str]:
    errors: list[str] = []
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-edge-ai-receipt-identity-invalid")
    if receipt.get("status") != "passed-edge-ai-application-boundary":
        errors.append("cloudbank-edge-ai-receipt-status-invalid")
    if content_hash(receipt) != receipt.get("content_sha256"):
        errors.append("cloudbank-edge-ai-receipt-content-hash-invalid")
    if not key or not verify_signature(receipt, key):
        errors.append("cloudbank-edge-ai-receipt-signature-invalid")
    lane = receipt.get("edge_ai_lane") or {}
    required_packaging = {"executable_jars": 8, "oracle_runtime_libraries": 0,
                          "microtx_runtime_libraries": 0}
    required_tests = REQUIRED_TESTS
    if lane.get("status") != "passed" or lane.get("contract_sha256") != CONTRACT_SHA256 \
            or lane.get("scenario_count") != len(SCENARIO_IDS) \
            or [item.get("id") for item in lane.get("scenarios", [])] != SCENARIO_IDS \
            or any(item.get("status") != "passed" for item in lane.get("scenarios", [])) \
            or lane.get("packaging") != required_packaging or lane.get("tests") != required_tests \
            or lane.get("workcells") != required_workcells() \
            or lane.get("external_credit_bureau_called") is not False \
            or lane.get("external_model_called") is not False \
            or lane.get("synthetic_data_only") is not True \
            or lane.get("raw_output_persisted") is not False:
        errors.append("cloudbank-edge-ai-receipt-lane-invalid")
    if receipt.get("bindings") != readiness_receipt(project_root)["bindings"]:
        errors.append("cloudbank-edge-ai-receipt-binding-invalid")
    for name in ("source_ms63_receipt_sha256", "source_ms57_receipt_sha256",
                 "postgresql_image_id_sha256"):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-edge-ai-receipt-{name}-invalid")
    expected = {
        "remaining_service_workcells_complete": True,
        "eight_service_target_assembled": True,
        "real_credit_decision_equivalent": False,
        "model_quality_qualified": False,
        "whole_application_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    }
    if any(receipt.get(name) is not value for name, value in expected.items()):
        errors.append("cloudbank-edge-ai-receipt-claims-invalid")
    if validate_artifacts(project_root):
        errors.append("cloudbank-edge-ai-repository-artifacts-invalid")
    return sorted(set(errors))
