from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from lightyear_common.io import write_json

from .cloudbank_customer_postgres import POSTGRES_IMAGE
from .cloudbank_dark_factory import (
    _container_connectivity_args,
    _container_endpoint,
    _inspect_image,
    _wait_postgres,
)
from .cloudbank_native_wave import (
    _free_port,
    _psql,
    _request,
    _seed,
    _state,
    _stop_service,
    _wait_health,
    materialize_target as materialize_ms60_target,
)
from .cloudbank_oracle_equivalence import (
    RECEIPT_TYPE as MS61_RECEIPT_TYPE,
    validate_execution_receipt as validate_ms61_receipt,
)
from .cloudbank_transaction_wave import validate_source
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.62.0"
OUTPUT_ROOT = Path("factory/cloudbank/production-oauth")
PATCH_ROOT = OUTPUT_ROOT / "patches"
RECEIPT_TYPE = "lightyear-cloudbank-production-oauth-execution"
RECEIPT_NAME = "cloudbank-production-oauth.receipt.json"
FAILURE_NAME = "cloudbank-production-oauth.failure.json"
DIAGNOSTIC_MARKER = "CLOUDBANK_PRODUCTION_OAUTH_ACCEPTANCE_DIAGNOSTIC="
AUTHORIZATION_DATABASE = "cloudbank_azn"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SCENARIO_IDS = [
    "authorization-server-discovery-and-jwks",
    "invalid-client-rejected",
    "scope-escalation-rejected",
    "caller-token-claims-bound",
    "service-token-claims-bound",
    "missing-bearer-rejected",
    "insufficient-scope-rejected",
    "tampered-token-rejected",
    "cross-audience-token-rejected",
    "owner-authorization-before-mutation",
    "authenticated-transfer-conserves-value",
    "persistent-key-restart-continuity",
]
CONTRACT_SHA256 = hashlib.sha256(";".join(SCENARIO_IDS).encode()).hexdigest()
SAFE_FAILURE_REASONS = {
    "package-gate-failed",
    "postgresql-start-failed",
    "runtime-gate-failed:azn-server-exited-before-health",
    "runtime-gate-failed:azn-server-health-timeout",
    "runtime-gate-failed:account-exited-before-health",
    "runtime-gate-failed:account-health-timeout",
    "runtime-gate-failed:transfer-exited-before-health",
    "runtime-gate-failed:transfer-health-timeout",
    "runtime-gate-failed:postgresql-query-failed",
    "runtime-gate-failed:rsa-key-generation-failed",
    "runtime-gate-failed:required-token-issuance-failed",
    "runtime-gate-failed:authorization-database-create-failed",
}
SAFE_EXCEPTION_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,199}$")
SAFE_SERVICE_START_CATEGORIES = {
    "bean-creation-failed",
    "configuration-placeholder-missing",
    "database-migration-failed",
    "port-bind-failed",
    "resource-exhausted",
    "unclassified",
}
SAFE_SERVICE_START_COMPONENTS = {
    "datasource",
    "entity-manager",
    "jpa-repository",
    "liquibase",
    "oauth-jwt-decoder",
    "oauth-security-filter-chain",
    "request-logging-filter",
    "transaction-core",
    "unclassified",
}
SAFE_SERVICE_START_CAUSES = {
    "ambiguous-bean",
    "bean-definition-conflict",
    "database-authentication-failed",
    "database-concurrency-failed",
    "database-connection-failed",
    "database-constraint-violation",
    "database-object-conflict",
    "database-object-missing",
    "database-permission-denied",
    "database-resource-exhausted",
    "database-statement-failed",
    "illegal-argument",
    "illegal-state",
    "missing-bean",
    "resource-load-failed",
    "schema-validation-failed",
    "sql-syntax-invalid",
    "unclassified",
    "unsatisfied-dependency",
}
POSTGRES_SQLSTATE_CAUSES = {
    "08001": "database-connection-failed",
    "08003": "database-connection-failed",
    "08004": "database-connection-failed",
    "08006": "database-connection-failed",
    "08007": "database-connection-failed",
    "08P01": "database-connection-failed",
    "23502": "database-constraint-violation",
    "23503": "database-constraint-violation",
    "23505": "database-constraint-violation",
    "23514": "database-constraint-violation",
    "28P01": "database-authentication-failed",
    "3D000": "database-object-missing",
    "3F000": "database-object-missing",
    "40001": "database-concurrency-failed",
    "40P01": "database-concurrency-failed",
    "42501": "database-permission-denied",
    "42601": "sql-syntax-invalid",
    "42701": "database-object-conflict",
    "42703": "database-object-missing",
    "42P01": "database-object-missing",
    "42P06": "database-object-conflict",
    "42P07": "database-object-conflict",
    "53300": "database-resource-exhausted",
    "55006": "database-concurrency-failed",
    "55P03": "database-concurrency-failed",
    "57014": "database-concurrency-failed",
}
POSTGRES_SQLSTATE_PATTERN = re.compile(
    rb"(?:sql\s*state|sqlstate)\s*(?:\[|:|=)?\s*([0-9A-Z]{5})",
    re.IGNORECASE,
)
PATCHES = {
    "azn-server/pom.xml": "azn-pom.xml",
    "azn-server/src/main/resources/application.yaml": "azn-application.yaml",
    "azn-server/src/main/resources/db/changelog/controller.yaml": "azn-controller.yaml",
    "azn-server/src/main/resources/db/changelog/table.sql": "azn-table.sql",
    (
        "azn-server/src/main/java/oracle/obaas/aznserver/securityconfig/"
        "ProductionAudienceTokenCustomizer.java"
    ): "ProductionAudienceTokenCustomizer.java",
    (
        "account/src/main/java/com/example/accounts/config/"
        "AccountOAuthSecurityConfiguration.java"
    ): "AccountOAuthSecurityConfiguration.java",
    (
        "account/src/main/java/com/example/accounts/controller/"
        "TransactionCoreController.java"
    ): "TransactionCoreOAuthController.java",
    "account/src/main/resources/application.yaml": "account-application.yaml",
    (
        "transfer/src/main/java/com/example/transfer/config/"
        "TransferOAuthSecurityConfiguration.java"
    ): "TransferOAuthSecurityConfiguration.java",
    "transfer/src/main/java/com/example/transfer/TransferService.java": "TransferOAuthService.java",
    (
        "transfer/src/test/java/com/example/transfer/TransferServiceTests.java"
    ): "TransferOAuthServiceTests.java",
    "transfer/src/main/resources/application.yaml": "transfer-application.yaml",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changed_paths() -> list[str]:
    return sorted(PATCHES)


def security_contract() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-production-oauth-boundary",
            "release": RELEASE,
            "protocol": "oauth2-oidc-jwt",
            "authorization_server": "native-cloudbank-azn-server-on-postgresql",
            "grant_types_exercised": ["client_credentials"],
            "browser_flow_policy": "authorization-code-requires-pkce-configured-not-exercised",
            "token_validation": {
                "signature": "rsa-3072-jwks",
                "issuer": "exact-runtime-issuer",
                "audiences": ["cloudbank-transfer", "cloudbank-account"],
                "scopes": ["cloudbank.transfer", "cloudbank.internal"],
                "lifetime": "exp-nbf-iat-default-validation",
            },
            "caller_identity": "jwt-subject-preserved-to-account-authorization",
            "service_identity": "client-credentials-token-no-static-shared-header",
            "signing_key": "operator-ephemeral-files-persistent-across-process-restart",
            "secrets": "runtime-environment-only-not-receipted",
            "transport": "loopback-http-test-boundary-production-tls-required-separately",
            "required_scenarios": SCENARIO_IDS,
        }
    )


def execution_plan(project_root: Path) -> dict[str, Any]:
    patches = [
        {
            "path": target,
            "template": f"patches/{template}",
            "template_sha256": _sha256(project_root / PATCH_ROOT / template),
            "operation": "replace-or-create-in-isolated-target",
        }
        for target, template in sorted(PATCHES.items())
    ]
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-production-oauth",
            "release": RELEASE,
            "requires": ["signed-ms61-receipt", "same-evidence-key"],
            "base_target": "ms60-generated-postgresql-account-transfer",
            "services": ["azn-server", "account", "transfer"],
            "patches": patches,
            "stages": [
                "validate-ms61-and-content-addressed-security-contract",
                "materialize-isolated-postgresql-security-target",
                "generate-runtime-rsa-3072-keypair",
                "package-zero-oracle-zero-microtx-three-service-target",
                "start-loopback-postgresql-and-authorization-server",
                "issue-scoped-caller-and-service-client-credentials-tokens",
                "exercise-negative-and-positive-resource-server-boundaries",
                "restart-all-services-and-revalidate-pre-restart-caller-token",
                "sign-bounded-production-oauth-application-receipt",
            ],
            "scenario_ids": SCENARIO_IDS,
            "source_checkout_mutated": False,
            "production_data": False,
            "external_tls_termination": False,
            "secret_manager_integration": False,
            "whole_application": False,
        }
    )


def compatibility_ledger() -> dict[str, Any]:
    entries = [
        ("oauth2-client-credentials", "native-qualified", "live-token-endpoint"),
        ("oidc-discovery-and-jwks", "native-qualified", "live-metadata-and-jwks"),
        ("jwt-signature-issuer-lifetime", "native-qualified", "resource-server-validation"),
        ("jwt-audience-isolation", "native-qualified", "cross-audience-rejection"),
        ("jwt-scope-authorization", "native-qualified", "negative-and-positive-paths"),
        ("caller-subject-ownership", "native-qualified", "authorization-before-mutation"),
        ("service-to-service-oauth", "native-qualified", "client-credentials-provider"),
        ("persistent-signing-key-restart", "native-qualified", "old-token-new-process"),
        ("authorization-code-pkce", "configured-not-executed", "browser-flow-later"),
        ("external-tls-termination", "not-qualified", "deployment-readiness-wave"),
        ("managed-secret-store-and-rotation", "not-qualified", "deployment-readiness-wave"),
        ("external-enterprise-idp-federation", "not-qualified", "customer-policy-decision"),
        ("checks-aq-jms", "not-qualified", "ms63"),
        ("remaining-services", "not-qualified", "ms64"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "ledger_type": "lightyear-cloudbank-production-oauth-compatibility",
            "release": RELEASE,
            "entries": [
                {"capability": name, "classification": classification, "evidence": evidence}
                for name, classification, evidence in entries
            ],
            "production_oauth_application_profile_eligible": True,
            "production_oauth_operational_deployment_qualified": False,
            "whole_application_equivalent": False,
            "production_ready": False,
        }
    )


def acceptance_contract(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-production-oauth-acceptance",
            "release": RELEASE,
            "bindings": {
                "security_contract_sha256": security_contract()["content_sha256"],
                "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            },
            "required_receipt": MS61_RECEIPT_TYPE,
            "required_services": ["azn-server", "account", "transfer"],
            "required_service_starts": {"azn-server": 2, "account": 2, "transfer": 2},
            "required_scenarios": SCENARIO_IDS,
            "required_contract_sha256": CONTRACT_SHA256,
            "required_packaging": {
                "executable_jars": 3,
                "oracle_runtime_libraries": 0,
                "microtx_runtime_libraries": 0,
            },
            "required_runtime_boundaries": {
                "database_port": "ephemeral-loopback-only",
                "service_ports": "ephemeral-loopback-only",
                "raw_logs_persisted": False,
                "credentials_persisted": False,
                "synthetic_data_only": True,
            },
            "eligible_claim": {
                "production_oauth_application_profile_qualified": True,
                "production_oauth_operational_deployment_qualified": False,
                "checks_messaging_qualified": False,
                "whole_application_equivalent": False,
                "production_ready": False,
            },
        }
    )


def readiness_receipt(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-production-oauth-readiness",
            "release": RELEASE,
            "bindings": {
                "security_contract_sha256": security_contract()["content_sha256"],
                "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
                "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
            },
            "gate_status": "ready-for-signed-ms61-and-native-oauth-run",
            "production_oauth_application_profile_qualified": False,
            "production_oauth_operational_deployment_qualified": False,
            "native_messaging_observed": False,
            "remaining_service_workcells_complete": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "security-contract.json": security_contract(),
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
            errors.append(f"cloudbank-production-oauth-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-production-oauth-artifact-drift:{name}")
    readiness = readiness_receipt(project_root)
    claims = (
        "production_oauth_application_profile_qualified",
        "production_oauth_operational_deployment_qualified",
        "native_messaging_observed",
        "remaining_service_workcells_complete",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(readiness.get(name) is not False for name in claims):
        errors.append("cloudbank-production-oauth-readiness-overclaims")
    if len(SCENARIO_IDS) != 12 or len(set(SCENARIO_IDS)) != 12:
        errors.append("cloudbank-production-oauth-scenarios-invalid")
    return sorted(set(errors))


def materialize_target(project_root: Path, source_root: Path, output: Path) -> Path:
    workspace = materialize_ms60_target(project_root, source_root, output)
    for target, template in PATCHES.items():
        destination = workspace / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_root / PATCH_ROOT / template, destination)
    return workspace


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True, capture_output=True, **kwargs)


def _package_inventory(workspace: Path) -> dict[str, int]:
    jars = [
        workspace / "azn-server/target/azn-server-0.0.1-SNAPSHOT.jar",
        workspace / "account/target/account-0.0.1-SNAPSHOT.jar",
        workspace / "transfer/target/transfer-0.0.1-SNAPSHOT.jar",
    ]
    if not all(path.is_file() for path in jars):
        return {
            "executable_jars": 0,
            "oracle_runtime_libraries": -1,
            "microtx_runtime_libraries": -1,
        }
    oracle = 0
    microtx = 0
    for jar in jars:
        with zipfile.ZipFile(jar) as archive:
            names = [name.lower() for name in archive.namelist() if "boot-inf/lib/" in name.lower()]
        oracle += sum(
            any(marker in name for marker in ("ojdbc", "oracle-spring", "ucp-"))
            for name in names
        )
        microtx += sum(any(marker in name for marker in ("microtx", "tmm-")) for name in names)
    return {
        "executable_jars": 3,
        "oracle_runtime_libraries": oracle,
        "microtx_runtime_libraries": microtx,
    }


def _form_request(
    url: str,
    form: Mapping[str, str],
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    timeout: float = 10,
) -> tuple[int, bytes]:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if client_id is not None and client_secret is not None:
        raw = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {raw}"
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(65536)
    except urllib.error.HTTPError as error:
        return int(error.code), error.read(65536)


def _issue_token(
    port: int, client_id: str, client_secret: str, scope: str
) -> tuple[int, dict[str, Any]]:
    status, body = _form_request(
        f"http://127.0.0.1:{port}/oauth2/token",
        {"grant_type": "client_credentials", "scope": scope},
        client_id=client_id,
        client_secret=client_secret,
    )
    try:
        payload = json.loads(body.decode()) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    return status, payload


def _jwt_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _bearer_transfer(
    port: int,
    token: str | None,
    command_id: str,
    source: int,
    target: int,
    amount: int,
) -> tuple[int, dict[str, Any]]:
    query = urllib.parse.urlencode(
        {"fromAccount": source, "toAccount": target, "amount": amount}
    )
    headers = {"Idempotency-Key": command_id}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    status, body = _request(
        f"http://127.0.0.1:{port}/transfer?{query}",
        headers=headers,
        method="POST",
    )
    try:
        payload = json.loads(body.decode()) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    return status, payload


def _direct_account(port: int, token: str) -> int:
    query = urllib.parse.urlencode({"fromAccount": 1, "toAccount": 2, "amount": 1})
    status, _ = _request(
        f"http://127.0.0.1:{port}/api/v1/transfers?{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "cross-audience",
            "X-CloudBank-Actor": "cust-source",
        },
        method="POST",
    )
    return status


def _generate_keys(
    key_root: Path, run: Callable[..., subprocess.CompletedProcess[str]]
) -> tuple[Path, Path, str]:
    private_key = key_root / "private.pem"
    public_key = key_root / "public.pem"
    generated = run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:3072",
            "-out",
            str(private_key),
        ],
        timeout=120,
    )
    exported = run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        timeout=30,
    )
    if generated.returncode or exported.returncode:
        raise RuntimeError("rsa-key-generation-failed")
    private_key.chmod(0o600)
    return private_key, public_key, _sha256(public_key)


def _create_authorization_database(
    container: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    """Create the isolated Authorization Server database inside PostgreSQL."""
    created = run(
        [
            "docker",
            "exec",
            container,
            "createdb",
            "-U",
            "postgres",
            AUTHORIZATION_DATABASE,
        ],
        timeout=30,
    )
    if created.returncode:
        raise RuntimeError("authorization-database-create-failed")


def _isolated_postgres_jdbc_urls(host: str, port: int) -> dict[str, str]:
    """Keep authorization metadata separate from the Account transaction database."""
    root = f"jdbc:postgresql://{host}:{port}"
    return {
        "authorization": f"{root}/{AUTHORIZATION_DATABASE}",
        "account": f"{root}/cloudbank",
    }


def _oauth_user_bootstrap_environment() -> dict[str, str]:
    """Disable browser-user seeding in the client-credentials qualification lane."""
    return {"AZN_BOOTSTRAP_USERS_ENABLED": "false"}


def _claim_contains(value: Any, expected: str) -> bool:
    """Accept the JSON string and array representations used for JWT claims."""
    if isinstance(value, str):
        return expected in value.split()
    if isinstance(value, (list, tuple, set)):
        return expected in value
    return False


def _classify_service_start_failure(raw_log: bytes, exit_code: int | None) -> str:
    """Reduce a private service log to one safe, allowlisted failure category."""
    if exit_code in {134, 137} or b"OutOfMemoryError" in raw_log:
        return "resource-exhausted"
    if b"Address already in use" in raw_log or (
        b"Port " in raw_log and b"was already in use" in raw_log
    ):
        return "port-bind-failed"
    if b"Could not resolve placeholder" in raw_log:
        return "configuration-placeholder-missing"
    if any(
        marker in raw_log
        for marker in (
            b"LiquibaseException",
            b"MigrationFailedException",
            b"Validation Failed",
        )
    ):
        return "database-migration-failed"
    if b"BeanCreationException" in raw_log:
        return "bean-creation-failed"
    return "unclassified"


def _classify_service_start_component(raw_log: bytes) -> str:
    """Map private Spring bean names to a stable, non-sensitive component category."""
    markers = (
        ((b"accountOAuthSecurityFilterChain", b"transferOAuthSecurityFilterChain",
          b"springSecurityFilterChain", b"webSecurityConfiguration"),
         "oauth-security-filter-chain"),
        ((b"accountJwtDecoder", b"transferJwtDecoder", b"jwtDecoder"),
         "oauth-jwt-decoder"),
        ((b"liquibase", b"SpringLiquibase"), "liquibase"),
        ((b"entityManagerFactory", b"jpaSharedEM"), "entity-manager"),
        ((b"dataSource", b"hikariPoolDataSourceMetadataProvider"), "datasource"),
        ((b"accountRepository", b"journalRepository", b"transferCommandRepository"),
         "jpa-repository"),
        ((b"transactionCoreController", b"transactionCoreService"), "transaction-core"),
        ((b"logFilter",), "request-logging-filter"),
    )
    for candidates, category in markers:
        if any(candidate in raw_log for candidate in candidates):
            return category
    return "unclassified"


def _postgres_sqlstate(raw_log: bytes) -> str | None:
    """Return only a recognized PostgreSQL SQLSTATE from a private service log."""
    for match in POSTGRES_SQLSTATE_PATTERN.finditer(raw_log):
        value = match.group(1).decode("ascii").upper()
        if value in POSTGRES_SQLSTATE_CAUSES:
            return value
    return None


def _classify_service_start_cause(raw_log: bytes) -> str:
    """Reduce nested startup exceptions to one allowlisted root-cause category."""
    sqlstate = _postgres_sqlstate(raw_log)
    if sqlstate is not None:
        return POSTGRES_SQLSTATE_CAUSES[sqlstate]
    markers = (
        ((b"BeanDefinitionOverrideException",), "bean-definition-conflict"),
        ((b"NoUniqueBeanDefinitionException",), "ambiguous-bean"),
        ((b"NoSuchBeanDefinitionException", b"No qualifying bean of type"), "missing-bean"),
        (
            (b"password authentication failed", b"no pg_hba.conf entry"),
            "database-authentication-failed",
        ),
        (
            (b"Connection refused", b"connection attempt failed", b"JDBCConnectionException"),
            "database-connection-failed",
        ),
        ((b"permission denied", b"must be owner of"), "database-permission-denied"),
        ((b"already exists",), "database-object-conflict"),
        ((b"does not exist", b"undefined table"), "database-object-missing"),
        (
            (
                b"duplicate key value",
                b"violates not-null constraint",
                b"violates foreign key constraint",
                b"violates check constraint",
                b"violates unique constraint",
            ),
            "database-constraint-violation",
        ),
        ((b"syntax error at or near",), "sql-syntax-invalid"),
        (
            (b"too many clients", b"remaining connection slots are reserved"),
            "database-resource-exhausted",
        ),
        (
            (b"deadlock detected", b"could not obtain lock"),
            "database-concurrency-failed",
        ),
        ((b"SchemaManagementException", b"Schema-validation"), "schema-validation-failed"),
        ((b"FileNotFoundException", b"class path resource"), "resource-load-failed"),
        ((b"PSQLException",), "database-statement-failed"),
        ((b"IllegalArgumentException",), "illegal-argument"),
        ((b"IllegalStateException",), "illegal-state"),
        ((b"UnsatisfiedDependencyException",), "unsatisfied-dependency"),
    )
    for candidates, category in markers:
        if any(candidate in raw_log for candidate in candidates):
            return category
    return "unclassified"


class _OAuthServiceStartFailure(RuntimeError):
    """Carries only bounded evidence from a failed OAuth service start."""

    def __init__(
        self,
        service: str,
        reason: str,
        exit_code: int | None,
        log_sha256: str,
        category: str,
        component: str,
        cause: str,
        database_sqlstate: str | None,
    ) -> None:
        super().__init__(reason)
        self.service = service
        self.exit_code = exit_code
        self.log_sha256 = log_sha256
        self.category = category
        self.component = component
        self.cause = cause
        self.database_sqlstate = database_sqlstate


def _start_oauth_service(
    service: str,
    jar: Path,
    port: int,
    env: Mapping[str, str],
    pause: Callable[[float], None],
) -> tuple[subprocess.Popen[bytes], Any]:
    """Start a service while retaining hashed, classified evidence on failure."""
    log = tempfile.TemporaryFile()
    process = subprocess.Popen(
        ["java", "-jar", str(jar)],
        cwd=jar.parent,
        env=dict(env),
        stdout=log,
        stderr=log,
    )
    try:
        _wait_health(service, port, process, pause)
    except Exception as exception:
        exit_code = process.poll()
        log.flush()
        log.seek(0)
        raw_log = log.read()
        log_sha256 = hashlib.sha256(raw_log).hexdigest()
        category = _classify_service_start_failure(raw_log, exit_code)
        component = _classify_service_start_component(raw_log)
        cause = _classify_service_start_cause(raw_log)
        database_sqlstate = _postgres_sqlstate(raw_log)
        _stop_service(process, log)
        reason = str(exception)
        raise _OAuthServiceStartFailure(
            service,
            reason,
            exit_code,
            log_sha256,
            category,
            component,
            cause,
            database_sqlstate,
        ) from None
    return process, log


def _native_oauth_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    pause: Callable[[float], None],
    progress: Callable[[str], None],
) -> dict[str, Any]:
    _inspect_image(POSTGRES_IMAGE, image_id, run)
    progress("Packaging Authorization, Account, and Transfer with the production OAuth profile")
    build = run(
        ["mvn", "-pl", "azn-server,account,transfer", "-am", "-DskipTests", "package"],
        cwd=workspace,
        env=os.environ.copy(),
        timeout=1200,
    )
    packaging = _package_inventory(workspace)
    required_packaging = {
        "executable_jars": 3,
        "oracle_runtime_libraries": 0,
        "microtx_runtime_libraries": 0,
    }
    if build.returncode or packaging != required_packaging:
        return {
            "lane": "native-production-oauth-account-transfer",
            "status": "failed",
            "reason": "package-gate-failed",
            "maven_exit_code": build.returncode,
            "packaging": packaging,
            "maven_stdout_sha256": hashlib.sha256(build.stdout.encode()).hexdigest(),
            "maven_stderr_sha256": hashlib.sha256(build.stderr.encode()).hexdigest(),
            "raw_output_persisted": False,
        }

    name = "lightyear-cb-ms62-pg-" + uuid.uuid4().hex[:10]
    database_password = "Ly" + secrets.token_hex(12) + "A1"
    source_secret = secrets.token_urlsafe(24)
    service_secret = secrets.token_urlsafe(24)
    read_secret = secrets.token_urlsafe(24)
    attacker_secret = secrets.token_urlsafe(24)
    azn_port, account_port, transfer_port = _free_port(), _free_port(), _free_port()
    azn_process: subprocess.Popen[bytes] | None = None
    account_process: subprocess.Popen[bytes] | None = None
    transfer_process: subprocess.Popen[bytes] | None = None
    azn_log = account_log = transfer_log = None
    log_hashes: dict[str, list[str]] = {"azn-server": [], "account": [], "transfer": []}
    service_starts = {"azn-server": 0, "account": 0, "transfer": 0}
    service_exit_codes: dict[str, int | None] = {
        "azn-server": None,
        "account": None,
        "transfer": None,
    }
    service_start_failure_categories: dict[str, str | None] = {
        "azn-server": None,
        "account": None,
        "transfer": None,
    }
    service_start_failure_components: dict[str, str | None] = {
        "azn-server": None,
        "account": None,
        "transfer": None,
    }
    service_start_failure_causes: dict[str, str | None] = {
        "azn-server": None,
        "account": None,
        "transfer": None,
    }
    service_start_database_sqlstates: dict[str, str | None] = {
        "azn-server": None,
        "account": None,
        "transfer": None,
    }
    scenarios: list[dict[str, Any]] = []
    failure_reason: str | None = None
    public_key_sha256: str | None = None
    jwks_sha256: str | None = None
    started = run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            *_container_connectivity_args(5432), "--read-only", "--user", "70:70",
            "--pids-limit", "128", "--memory", "768m", "--cpus", "1.0",
            "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=384m,uid=70,gid=70",
            "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=70,gid=70",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m,uid=70,gid=70",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "-e", f"POSTGRES_PASSWORD={database_password}", "-e", "POSTGRES_DB=cloudbank",
            f"sha256:{image_id}",
        ],
        timeout=120,
    )
    if started.returncode:
        return {
            "lane": "native-production-oauth-account-transfer",
            "status": "failed",
            "reason": "postgresql-start-failed",
            "packaging": packaging,
            "raw_output_persisted": False,
        }

    def record(identifier: str, passed: bool, **evidence: Any) -> None:
        scenarios.append(
            {"id": identifier, "status": "passed" if passed else "failed", **evidence}
        )

    try:
        _wait_postgres(name, run, pause)
        _create_authorization_database(name, run)
        database_host, database_port = _container_endpoint(name, 5432, run)
        jdbc_urls = _isolated_postgres_jdbc_urls(database_host, database_port)
        with tempfile.TemporaryDirectory(prefix="lightyear-ms62-keys-") as key_dir:
            private_key, public_key, public_key_sha256 = _generate_keys(Path(key_dir), run)
            issuer = f"http://127.0.0.1:{azn_port}"
            jwk_uri = f"{issuer}/oauth2/jwks"
            token_uri = f"{issuer}/oauth2/token"
            common = {
                **os.environ,
                "SPRING_PROFILES_ACTIVE": "cloudbank-oauth",
                "SERVER_ADDRESS": "127.0.0.1",
                "EUREKA_CLIENT_ENABLED": "false",
                "SPRING_CLOUD_DISCOVERY_ENABLED": "false",
                "SPRING_CLOUD_CONFIG_ENABLED": "false",
                "CLOUDBANK_SECURITY_ISSUER_URI": issuer,
                "CLOUDBANK_SECURITY_JWK_SET_URI": jwk_uri,
            }
            azn_env = {
                **common,
                **_oauth_user_bootstrap_environment(),
                "SERVER_PORT": str(azn_port),
                "SPRING_DATASOURCE_URL": jdbc_urls["authorization"],
                "SPRING_DATASOURCE_USERNAME": "postgres",
                "SPRING_DATASOURCE_PASSWORD": database_password,
                "LIQUIBASE_DATASOURCE_URL": jdbc_urls["authorization"],
                "LIQUIBASE_DATASOURCE_USERNAME": "postgres",
                "LIQUIBASE_DATASOURCE_PASSWORD": database_password,
                "AZN_AUTHORIZATION_SERVER_ISSUER": issuer,
                "AZN_AUTHORIZATION_SERVER_SIGNING_KEY_PRIVATE_KEY_PATH": str(private_key),
                "AZN_AUTHORIZATION_SERVER_SIGNING_KEY_PUBLIC_KEY_PATH": str(public_key),
                "AZN_AUTHORIZATION_SERVER_SIGNING_KEY_KEY_ID": "cloudbank-ms62",
                "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_ID": "cust-source",
                "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SECRET": source_secret,
                "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SCOPES": "cloudbank.transfer",
                "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_ID": "cloudbank-transfer-service",
                "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SECRET": service_secret,
                "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SCOPES": "cloudbank.internal",
                "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_ID": "scope-denied",
                "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_SECRET": read_secret,
                "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_SCOPES": "cloudbank.read",
                "AZN_AUTHORIZATION_SERVER_ADMIN_CLIENT_ID": "cust-attacker",
                "AZN_AUTHORIZATION_SERVER_ADMIN_CLIENT_SECRET": attacker_secret,
                "AZN_AUTHORIZATION_SERVER_ADMIN_CLIENT_SCOPES": "cloudbank.transfer",
            }
            account_env = {
                **common,
                "SERVER_PORT": str(account_port),
                "SPRING_DATASOURCE_URL": jdbc_urls["account"],
                "SPRING_DATASOURCE_USERNAME": "postgres",
                "SPRING_DATASOURCE_PASSWORD": database_password,
                "LIQUIBASE_DATASOURCE_URL": jdbc_urls["account"],
                "LIQUIBASE_DATASOURCE_USERNAME": "postgres",
                "LIQUIBASE_DATASOURCE_PASSWORD": database_password,
            }
            transfer_env = {
                **common,
                "SERVER_PORT": str(transfer_port),
                "ACCOUNT_TRANSACTION_URL": (
                    f"http://127.0.0.1:{account_port}/api/v1/transfers"
                ),
                "CLOUDBANK_SECURITY_SERVICE_TOKEN_URI": token_uri,
                "CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_ID": "cloudbank-transfer-service",
                "CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_SECRET": service_secret,
            }
            jars = {
                "azn-server": workspace / "azn-server/target/azn-server-0.0.1-SNAPSHOT.jar",
                "account": workspace / "account/target/account-0.0.1-SNAPSHOT.jar",
                "transfer": workspace / "transfer/target/transfer-0.0.1-SNAPSHOT.jar",
            }

            progress("Starting PostgreSQL and the persistent-key CloudBank authorization server")
            azn_process, azn_log = _start_oauth_service(
                "azn-server", jars["azn-server"], azn_port, azn_env, pause
            )
            service_starts["azn-server"] += 1
            metadata_status, metadata_body = _request(
                f"{issuer}/.well-known/oauth-authorization-server"
            )
            jwks_status, jwks_body = _request(jwk_uri)
            metadata = json.loads(metadata_body.decode())
            jwks = json.loads(jwks_body.decode())
            jwks_sha256 = hashlib.sha256(jwks_body).hexdigest()
            keys = jwks.get("keys", [])
            record(
                "authorization-server-discovery-and-jwks",
                metadata_status == 200
                and jwks_status == 200
                and metadata.get("issuer") == issuer
                and metadata.get("token_endpoint") == token_uri
                and any(key.get("kid") == "cloudbank-ms62" for key in keys),
                metadata_status=metadata_status,
                jwks_status=jwks_status,
                key_count=len(keys),
            )

            invalid_status, _ = _issue_token(
                azn_port, "cust-source", "incorrect-client-secret", "cloudbank.transfer"
            )
            record("invalid-client-rejected", invalid_status == 401, http_status=invalid_status)
            escalation_status, _ = _issue_token(
                azn_port, "cust-source", source_secret, "cloudbank.admin"
            )
            record(
                "scope-escalation-rejected",
                escalation_status == 400,
                http_status=escalation_status,
            )

            source_status, source_payload = _issue_token(
                azn_port, "cust-source", source_secret, "cloudbank.transfer"
            )
            service_status, service_payload = _issue_token(
                azn_port,
                "cloudbank-transfer-service",
                service_secret,
                "cloudbank.internal",
            )
            read_status, read_payload = _issue_token(
                azn_port, "scope-denied", read_secret, "cloudbank.read"
            )
            attacker_status, attacker_payload = _issue_token(
                azn_port, "cust-attacker", attacker_secret, "cloudbank.transfer"
            )
            source_token = str(source_payload.get("access_token", ""))
            service_token = str(service_payload.get("access_token", ""))
            read_token = str(read_payload.get("access_token", ""))
            attacker_token = str(attacker_payload.get("access_token", ""))
            source_claims = _jwt_claims(source_token)
            service_claims = _jwt_claims(service_token)
            now = int(time.time())
            record(
                "caller-token-claims-bound",
                source_status == 200
                and source_claims.get("sub") == "cust-source"
                and source_claims.get("iss") == issuer
                and _claim_contains(source_claims.get("aud"), "cloudbank-transfer")
                and _claim_contains(source_claims.get("scope"), "cloudbank.transfer")
                and int(source_claims.get("exp", 0)) > now,
                http_status=source_status,
                subject="cust-source",
                audience="cloudbank-transfer",
                scope="cloudbank.transfer",
            )
            record(
                "service-token-claims-bound",
                service_status == 200
                and service_claims.get("sub") == "cloudbank-transfer-service"
                and service_claims.get("iss") == issuer
                and _claim_contains(service_claims.get("aud"), "cloudbank-account")
                and _claim_contains(service_claims.get("scope"), "cloudbank.internal"),
                http_status=service_status,
                subject="cloudbank-transfer-service",
                audience="cloudbank-account",
                scope="cloudbank.internal",
            )
            if not all(
                (
                    source_status == 200,
                    service_status == 200,
                    read_status == 200,
                    attacker_status == 200,
                    source_token,
                    service_token,
                    read_token,
                    attacker_token,
                )
            ):
                raise RuntimeError("required-token-issuance-failed")

            progress("Starting OAuth resource servers and exercising denial boundaries")
            account_process, account_log = _start_oauth_service(
                "account", jars["account"], account_port, account_env, pause
            )
            service_starts["account"] += 1
            transfer_process, transfer_log = _start_oauth_service(
                "transfer", jars["transfer"], transfer_port, transfer_env, pause
            )
            service_starts["transfer"] += 1
            _seed(name, run)
            initial = _state(name, run)

            status, _ = _bearer_transfer(transfer_port, None, "missing", 1, 2, 1)
            record("missing-bearer-rejected", status == 401, http_status=status)
            status, _ = _bearer_transfer(
                transfer_port, read_token, "scope-denied", 1, 2, 1
            )
            record(
                "insufficient-scope-rejected",
                status == 403 and _state(name, run) == initial,
                http_status=status,
            )
            tampered = source_token[:-1] + ("A" if source_token[-1:] != "A" else "B")
            status, _ = _bearer_transfer(
                transfer_port, tampered, "tampered", 1, 2, 1
            )
            record(
                "tampered-token-rejected",
                status == 401 and _state(name, run) == initial,
                http_status=status,
            )
            account_status = _direct_account(account_port, source_token)
            record(
                "cross-audience-token-rejected",
                account_status == 401 and _state(name, run) == initial,
                http_status=account_status,
            )
            status, _ = _bearer_transfer(
                transfer_port, attacker_token, "wrong-owner", 1, 2, 10
            )
            record(
                "owner-authorization-before-mutation",
                status == 400 and _state(name, run) == initial,
                http_status=status,
            )
            status, body = _bearer_transfer(
                transfer_port, source_token, "oauth-success", 1, 2, 125
            )
            successful = _state(name, run)
            expected_success = {
                "balance_1": 875,
                "balance_2": 375,
                "balance_3": 5,
                "journal_count": 2,
                "command_count": 1,
                "journal_net": 0,
            }
            record(
                "authenticated-transfer-conserves-value",
                status == 200 and body.get("accepted") is True and successful == expected_success,
                http_status=status,
                database_state=successful,
            )

            progress("Restarting Authorization, Account, and Transfer with the same signing key")
            for service, process, log in (
                ("transfer", transfer_process, transfer_log),
                ("account", account_process, account_log),
                ("azn-server", azn_process, azn_log),
            ):
                digest = _stop_service(process, log)
                if digest:
                    log_hashes[service].append(digest)
            azn_process = account_process = transfer_process = None
            azn_log = account_log = transfer_log = None
            azn_process, azn_log = _start_oauth_service(
                "azn-server", jars["azn-server"], azn_port, azn_env, pause
            )
            service_starts["azn-server"] += 1
            account_process, account_log = _start_oauth_service(
                "account", jars["account"], account_port, account_env, pause
            )
            service_starts["account"] += 1
            transfer_process, transfer_log = _start_oauth_service(
                "transfer", jars["transfer"], transfer_port, transfer_env, pause
            )
            service_starts["transfer"] += 1
            _, restarted_jwks = _request(jwk_uri)
            status, body = _bearer_transfer(
                transfer_port, source_token, "after-auth-restart", 1, 2, 25
            )
            after_restart = _state(name, run)
            expected_restart = {
                "balance_1": 850,
                "balance_2": 400,
                "balance_3": 5,
                "journal_count": 4,
                "command_count": 2,
                "journal_net": 0,
            }
            record(
                "persistent-key-restart-continuity",
                hashlib.sha256(restarted_jwks).hexdigest() == jwks_sha256
                and status == 200
                and body.get("accepted") is True
                and after_restart == expected_restart,
                jwks_stable=True,
                pre_restart_caller_credential_accepted=status == 200,
                database_state=after_restart,
            )
    except Exception as exception:
        if isinstance(exception, _OAuthServiceStartFailure):
            log_hashes[exception.service].append(exception.log_sha256)
            service_exit_codes[exception.service] = exception.exit_code
            service_start_failure_categories[exception.service] = exception.category
            service_start_failure_components[exception.service] = exception.component
            service_start_failure_causes[exception.service] = exception.cause
            service_start_database_sqlstates[exception.service] = (
                exception.database_sqlstate
            )
        safe_reason = str(exception)
        allowed = {
            "azn-server-exited-before-health",
            "azn-server-health-timeout",
            "account-exited-before-health",
            "account-health-timeout",
            "transfer-exited-before-health",
            "transfer-health-timeout",
            "postgresql-query-failed",
            "rsa-key-generation-failed",
            "required-token-issuance-failed",
            "authorization-database-create-failed",
        }
        if safe_reason not in allowed:
            safe_reason = type(exception).__name__
        failure_reason = f"runtime-gate-failed:{safe_reason}"
    finally:
        for service, process, log in (
            ("transfer", transfer_process, transfer_log),
            ("account", account_process, account_log),
            ("azn-server", azn_process, azn_log),
        ):
            digest = _stop_service(process, log)
            if digest:
                log_hashes[service].append(digest)
        database_password = source_secret = service_secret = read_secret = attacker_secret = ""
        run(["docker", "rm", "-f", name], timeout=30)

    passed = (
        failure_reason is None
        and [item["id"] for item in scenarios] == SCENARIO_IDS
        and all(item["status"] == "passed" for item in scenarios)
        and service_starts == {"azn-server": 2, "account": 2, "transfer": 2}
    )
    return {
        "lane": "native-production-oauth-account-transfer",
        "status": "passed" if passed else "failed",
        "reason": failure_reason,
        "database_image_id_sha256": image_id,
        "contract_sha256": CONTRACT_SHA256 if passed else None,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "service_starts": service_starts,
        "service_log_sha256": log_hashes,
        "service_exit_codes": service_exit_codes,
        "service_start_failure_categories": service_start_failure_categories,
        "service_start_failure_components": service_start_failure_components,
        "service_start_failure_causes": service_start_failure_causes,
        "service_start_database_sqlstates": service_start_database_sqlstates,
        "public_signing_key_sha256": public_key_sha256,
        "jwks_sha256": jwks_sha256,
        "packaging": packaging,
        "maven_exit_code": build.returncode,
        "maven_stdout_sha256": hashlib.sha256(build.stdout.encode()).hexdigest(),
        "maven_stderr_sha256": hashlib.sha256(build.stderr.encode()).hexdigest(),
        "ports": "ephemeral-loopback-only",
        "synthetic_data_only": True,
        "credentials_persisted": False,
        "raw_output_persisted": False,
    }


def _diagnostic_int(value: Any, minimum: int = 0, maximum: int = 10_000) -> int | None:
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    ):
        return value
    return None


def _safe_failure_reason(value: Any) -> str:
    if isinstance(value, str) and value in SAFE_FAILURE_REASONS:
        return value
    prefix = "runtime-gate-failed:"
    if isinstance(value, str) and value.startswith(prefix):
        exception_type = value.removeprefix(prefix)
        if SAFE_EXCEPTION_TYPE.fullmatch(exception_type):
            return prefix + exception_type
    return "invalid"


def production_oauth_failure_diagnostic(
    report: Mapping[str, Any], expected_image_id: str
) -> dict[str, Any]:
    """Return an allowlisted failure summary safe to emit in shared build logs."""
    report = report if isinstance(report, Mapping) else {}
    supplied_lane = report.get("lane")
    lane = supplied_lane if isinstance(supplied_lane, Mapping) else {}

    supplied_scenarios = lane.get("scenarios", [])
    scenario_statuses: dict[str, str] = {}
    if isinstance(supplied_scenarios, list):
        for item in supplied_scenarios:
            if not isinstance(item, Mapping):
                continue
            identifier = item.get("id")
            status = item.get("status")
            if (
                isinstance(identifier, str)
                and identifier in SCENARIO_IDS
                and isinstance(status, str)
                and status in {"passed", "failed"}
            ):
                scenario_statuses[str(identifier)] = str(status)

    supplied_starts = lane.get("service_starts", {})
    service_starts = {
        service: _diagnostic_int(
            supplied_starts.get(service) if isinstance(supplied_starts, Mapping) else None
        )
        for service in ("azn-server", "account", "transfer")
    }
    supplied_packaging = lane.get("packaging", {})
    packaging = {
        field: _diagnostic_int(
            supplied_packaging.get(field)
            if isinstance(supplied_packaging, Mapping)
            else None
        )
        for field in (
            "executable_jars",
            "oracle_runtime_libraries",
            "microtx_runtime_libraries",
        )
    }
    supplied_log_hashes = lane.get("service_log_sha256", {})
    service_log_counts = {}
    for service in ("azn-server", "account", "transfer"):
        values = (
            supplied_log_hashes.get(service, [])
            if isinstance(supplied_log_hashes, Mapping)
            else []
        )
        service_log_counts[service] = (
            sum(1 for value in values if isinstance(value, str) and HEX_64.fullmatch(value))
            if isinstance(values, list)
            else 0
        )
    supplied_exit_codes = lane.get("service_exit_codes", {})
    service_exit_codes = {
        service: _diagnostic_int(
            supplied_exit_codes.get(service)
            if isinstance(supplied_exit_codes, Mapping)
            else None,
            -255,
            255,
        )
        for service in ("azn-server", "account", "transfer")
    }
    supplied_categories = lane.get("service_start_failure_categories", {})
    service_start_failure_categories = {}
    for service in ("azn-server", "account", "transfer"):
        value = (
            supplied_categories.get(service)
            if isinstance(supplied_categories, Mapping)
            else None
        )
        service_start_failure_categories[service] = (
            value if isinstance(value, str) and value in SAFE_SERVICE_START_CATEGORIES else None
        )
    supplied_components = lane.get("service_start_failure_components", {})
    service_start_failure_components = {}
    for service in ("azn-server", "account", "transfer"):
        value = (
            supplied_components.get(service)
            if isinstance(supplied_components, Mapping)
            else None
        )
        service_start_failure_components[service] = (
            value if isinstance(value, str) and value in SAFE_SERVICE_START_COMPONENTS else None
        )
    supplied_causes = lane.get("service_start_failure_causes", {})
    service_start_failure_causes = {}
    for service in ("azn-server", "account", "transfer"):
        value = (
            supplied_causes.get(service)
            if isinstance(supplied_causes, Mapping)
            else None
        )
        service_start_failure_causes[service] = (
            value if isinstance(value, str) and value in SAFE_SERVICE_START_CAUSES else None
        )
    supplied_sqlstates = lane.get("service_start_database_sqlstates", {})
    service_start_database_sqlstates = {}
    for service in ("azn-server", "account", "transfer"):
        value = (
            supplied_sqlstates.get(service)
            if isinstance(supplied_sqlstates, Mapping)
            else None
        )
        service_start_database_sqlstates[service] = (
            value if isinstance(value, str) and value in POSTGRES_SQLSTATE_CAUSES else None
        )

    return {
        "lane_match": lane.get("lane") == "native-production-oauth-account-transfer",
        "status": lane.get("status")
        if isinstance(lane.get("status"), str)
        and lane.get("status") in {"passed", "failed"}
        else "invalid",
        "reason": _safe_failure_reason(lane.get("reason")),
        "database_image_match": lane.get("database_image_id_sha256") == expected_image_id,
        "maven_exit_code": _diagnostic_int(lane.get("maven_exit_code"), -1, 255),
        "packaging": packaging,
        "scenario_count": _diagnostic_int(lane.get("scenario_count")),
        "scenario_statuses": [
            {"id": identifier, "status": scenario_statuses[identifier]}
            for identifier in SCENARIO_IDS
            if identifier in scenario_statuses
        ],
        "failed_scenarios": [
            identifier
            for identifier in SCENARIO_IDS
            if scenario_statuses.get(identifier) == "failed"
        ],
        "service_starts": service_starts,
        "service_log_counts": service_log_counts,
        "service_exit_codes": service_exit_codes,
        "service_start_failure_categories": service_start_failure_categories,
        "service_start_failure_components": service_start_failure_components,
        "service_start_failure_causes": service_start_failure_causes,
        "service_start_database_sqlstates": service_start_database_sqlstates,
        "public_signing_key_created": bool(
            HEX_64.fullmatch(str(lane.get("public_signing_key_sha256", "")))
        ),
        "jwks_observed": bool(HEX_64.fullmatch(str(lane.get("jwks_sha256", "")))),
        "credentials_persisted": False,
        "private_key_persisted": False,
        "raw_output_persisted": False,
    }


def execute_production_oauth(
    project_root: Path,
    source_root: Path,
    ms61_receipt: Mapping[str, Any],
    output_root: Path,
    key: str,
    signer: str,
    run_id: str | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
    progress: Callable[[str], None] = lambda _: None,
    lane_runner: Callable[[Path, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    progress("Validating MS #62 artifacts, pinned source, and signed MS #61 receipt")
    errors = validate_artifacts(project_root)
    errors.extend(validate_source(source_root))
    errors.extend(validate_ms61_receipt(ms61_receipt, key, project_root))
    if ms61_receipt.get("receipt_type") != MS61_RECEIPT_TYPE:
        errors.append("cloudbank-production-oauth-ms61-receipt-required")
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    image_id = str(ms61_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(image_id):
        raise ValueError("cloudbank-production-oauth-image-identity-invalid")
    run_name = run_id or f"cloudbank-production-oauth-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    run_root = output_root / "runs" / run_name
    progress("Materializing the isolated PostgreSQL Authorization/Account/Transfer target")
    workspace = materialize_target(project_root, source_root, run_root / "workspace")
    lane = (
        lane_runner(workspace, image_id)
        if lane_runner is not None
        else _native_oauth_lane(workspace, image_id, run, pause, progress)
    )
    if lane["status"] != "passed":
        output_root.mkdir(parents=True, exist_ok=True)
        write_json(
            output_root / FAILURE_NAME,
            {
                "schema_version": "1.0",
                "release": RELEASE,
                "run_id": run_name,
                "status": "failed",
                "lane": lane,
            },
        )
        raise ValueError("cloudbank-production-oauth-acceptance-failed")
    progress("All native OAuth gates passed; signing the bounded MS #62 receipt")
    receipt = sign(
        {
            "schema_version": "1.0",
            "receipt_type": RECEIPT_TYPE,
            "release": RELEASE,
            "run_id": run_name,
            "source_ms61_receipt_sha256": ms61_receipt["content_sha256"],
            "postgresql_image_id_sha256": image_id,
            "security_contract_sha256": security_contract()["content_sha256"],
            "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
            "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
            "changed_paths": changed_paths(),
            "oauth_lane": lane,
            "status": "passed-production-oauth-application-boundary",
            "native_authorization_server_observed": True,
            "jwt_resource_servers_observed": True,
            "service_to_service_client_credentials_observed": True,
            "persistent_signing_key_restart_observed": True,
            "production_oauth_application_profile_qualified": True,
            "production_oauth_operational_deployment_qualified": False,
            "authorization_code_flow_observed": False,
            "external_tls_termination_observed": False,
            "managed_secret_rotation_observed": False,
            "external_idp_federation_observed": False,
            "native_messaging_observed": False,
            "remaining_service_workcells_complete": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
            "security": {
                "source_checkout_mutated": False,
                "synthetic_data_only": True,
                "credentials_persisted": False,
                "private_key_persisted": False,
                "raw_service_logs_persisted": False,
                "ports": "ephemeral-loopback-only",
                "application_protocol": "oauth2-oidc-jwt",
                "transport_boundary": "loopback-http-production-tls-required-separately",
                "human_promotion_authorized": False,
            },
        },
        key,
        signer,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(
    receipt: Mapping[str, Any], key: str, project_root: Path
) -> list[str]:
    errors: list[str] = []
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-production-oauth-receipt-identity-invalid")
    if receipt.get("status") != "passed-production-oauth-application-boundary":
        errors.append("cloudbank-production-oauth-receipt-status-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("cloudbank-production-oauth-receipt-content-hash-invalid")
    if not key or not verify_signature(dict(receipt), key):
        errors.append("cloudbank-production-oauth-receipt-signature-invalid")
    expected = {
        "security_contract_sha256": security_contract()["content_sha256"],
        "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
        "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
        "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
        "changed_paths": changed_paths(),
    }
    if any(receipt.get(name) != value for name, value in expected.items()):
        errors.append("cloudbank-production-oauth-receipt-binding-invalid")
    for name in ("source_ms61_receipt_sha256", "postgresql_image_id_sha256"):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-production-oauth-receipt-hash-invalid:{name}")
    lane = receipt.get("oauth_lane", {})
    required_packaging = {
        "executable_jars": 3,
        "oracle_runtime_libraries": 0,
        "microtx_runtime_libraries": 0,
    }
    if not isinstance(lane, Mapping):
        errors.append("cloudbank-production-oauth-receipt-lane-invalid")
    else:
        scenarios = lane.get("scenarios", [])
        lane_invalid = any(
            (
                lane.get("status") != "passed",
                lane.get("contract_sha256") != CONTRACT_SHA256,
                lane.get("scenario_count") != len(SCENARIO_IDS),
                not isinstance(scenarios, list),
                [item.get("id") for item in scenarios] != SCENARIO_IDS
                if isinstance(scenarios, list) else True,
                any(item.get("status") != "passed" for item in scenarios)
                if isinstance(scenarios, list) else True,
                lane.get("service_starts") != {"azn-server": 2, "account": 2, "transfer": 2},
                lane.get("packaging") != required_packaging,
                lane.get("ports") != "ephemeral-loopback-only",
                lane.get("synthetic_data_only") is not True,
                lane.get("credentials_persisted") is not False,
                lane.get("raw_output_persisted") is not False,
                not HEX_64.fullmatch(str(lane.get("public_signing_key_sha256", ""))),
                not HEX_64.fullmatch(str(lane.get("jwks_sha256", ""))),
            )
        )
        if lane_invalid:
            errors.append("cloudbank-production-oauth-receipt-lane-invalid")
    required_true = (
        "native_authorization_server_observed",
        "jwt_resource_servers_observed",
        "service_to_service_client_credentials_observed",
        "persistent_signing_key_restart_observed",
        "production_oauth_application_profile_qualified",
    )
    required_false = (
        "production_oauth_operational_deployment_qualified",
        "authorization_code_flow_observed",
        "external_tls_termination_observed",
        "managed_secret_rotation_observed",
        "external_idp_federation_observed",
        "native_messaging_observed",
        "remaining_service_workcells_complete",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(receipt.get(name) is not True for name in required_true) or any(
        receipt.get(name) is not False for name in required_false
    ):
        errors.append("cloudbank-production-oauth-receipt-claims-invalid")
    security = receipt.get("security", {})
    if security != {
        "source_checkout_mutated": False,
        "synthetic_data_only": True,
        "credentials_persisted": False,
        "private_key_persisted": False,
        "raw_service_logs_persisted": False,
        "ports": "ephemeral-loopback-only",
        "application_protocol": "oauth2-oidc-jwt",
        "transport_boundary": "loopback-http-production-tls-required-separately",
        "human_promotion_authorized": False,
    }:
        errors.append("cloudbank-production-oauth-receipt-security-invalid")
    errors.extend(validate_artifacts(project_root))
    return sorted(set(errors))
