from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from lightyear_data.cloudbank_oracle_equivalence import RECEIPT_TYPE as MS61_RECEIPT_TYPE
from lightyear_data.cloudbank_production_oauth import (
    CONTRACT_SHA256,
    DIAGNOSTIC_MARKER,
    OUTPUT_ROOT,
    RECEIPT_TYPE,
    SCENARIO_IDS,
    _account_schema_relation_presence,
    _claim_contains,
    _classify_service_start_cause,
    _classify_service_start_component,
    _classify_service_start_failure,
    _classify_service_start_stage,
    _create_authorization_database,
    _isolated_postgres_jdbc_urls,
    _oauth_account_environment,
    _oauth_transfer_environment,
    _oauth_user_bootstrap_environment,
    _postgres_relation,
    _postgres_sqlstate,
    _start_oauth_service,
    build_artifacts,
    changed_paths,
    compatibility_ledger,
    execute_production_oauth,
    execution_plan,
    materialize_target,
    production_oauth_failure_diagnostic,
    readiness_receipt,
    security_contract,
    validate_artifacts,
    validate_execution_receipt,
)
from tools import cloudbank_production_oauth as production_oauth_tool


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "cloudbank-upstream"
KEY = "unit-test-cloudbank-production-oauth-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


def ms61_receipt() -> dict[str, object]:
    return {
        "receipt_type": MS61_RECEIPT_TYPE,
        "content_sha256": HEX_A,
        "postgresql_image_id_sha256": HEX_B,
    }


def passed_lane() -> dict[str, object]:
    return {
        "lane": "native-production-oauth-account-transfer",
        "status": "passed",
        "reason": None,
        "database_image_id_sha256": HEX_B,
        "contract_sha256": CONTRACT_SHA256,
        "scenario_count": len(SCENARIO_IDS),
        "scenarios": [
            {"id": identifier, "status": "passed"} for identifier in SCENARIO_IDS
        ],
        "service_starts": {"azn-server": 2, "account": 2, "transfer": 2},
        "service_log_sha256": {"azn-server": [HEX_A], "account": [HEX_A], "transfer": [HEX_A]},
        "public_signing_key_sha256": HEX_A,
        "jwks_sha256": HEX_B,
        "packaging": {
            "executable_jars": 3,
            "oracle_runtime_libraries": 0,
            "microtx_runtime_libraries": 0,
        },
        "maven_exit_code": 0,
        "maven_stdout_sha256": HEX_A,
        "maven_stderr_sha256": HEX_B,
        "ports": "ephemeral-loopback-only",
        "synthetic_data_only": True,
        "credentials_persisted": False,
        "raw_output_persisted": False,
    }


class CloudBankProductionOAuthTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        readiness = readiness_receipt(ROOT)
        self.assertFalse(readiness["production_oauth_application_profile_qualified"])
        self.assertFalse(readiness["whole_application_equivalent"])
        self.assertFalse(readiness["production_ready"])

    def test_security_contract_is_real_oauth_not_static_token_authentication(self) -> None:
        contract = security_contract()
        self.assertEqual("oauth2-oidc-jwt", contract["protocol"])
        self.assertEqual(["client_credentials"], contract["grant_types_exercised"])
        self.assertEqual(SCENARIO_IDS, contract["required_scenarios"])
        validation = contract["token_validation"]
        self.assertEqual("rsa-3072-jwks", validation["signature"])
        self.assertIn("cloudbank-account", validation["audiences"])
        self.assertIn("cloudbank.internal", validation["scopes"])

    def test_plan_binds_three_services_and_all_templates(self) -> None:
        plan = execution_plan(ROOT)
        self.assertEqual(["azn-server", "account", "transfer"], plan["services"])
        self.assertEqual(changed_paths(), sorted(item["path"] for item in plan["patches"]))
        self.assertEqual(12, len(plan["patches"]))
        self.assertFalse(plan["external_tls_termination"])
        self.assertFalse(plan["secret_manager_integration"])

    def test_ledger_separates_application_oauth_from_deployment_readiness(self) -> None:
        ledger = compatibility_ledger()
        entries = {item["capability"]: item for item in ledger["entries"]}
        self.assertEqual("native-qualified", entries["jwt-audience-isolation"]["classification"])
        self.assertEqual("native-qualified", entries["service-to-service-oauth"]["classification"])
        self.assertEqual("not-qualified", entries["external-tls-termination"]["classification"])
        self.assertTrue(ledger["production_oauth_application_profile_eligible"])
        self.assertFalse(ledger["production_oauth_operational_deployment_qualified"])

    def test_templates_have_no_embedded_credentials_or_static_internal_header(self) -> None:
        patches = ROOT / OUTPUT_ROOT / "patches"
        transfer = (patches / "TransferOAuthService.java").read_text(encoding="utf-8")
        self.assertNotIn("X-CloudBank-Internal-Token", transfer)
        self.assertIn("CloudBankServiceTokenProvider", transfer)
        self.assertIn("getAuthorizationHeader", transfer)
        self.assertNotIn("httpBasic", (patches / "TransferOAuthSecurityConfiguration.java").read_text())
        application = (patches / "azn-application.yaml").read_text(encoding="utf-8")
        self.assertIn("AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SECRET", application)
        self.assertNotIn("password123", application)
        self.assertIn("private-key-path", application)

    def test_client_credentials_lane_disables_browser_user_bootstrap(self) -> None:
        environment = _oauth_user_bootstrap_environment()
        self.assertEqual({"AZN_BOOTSTRAP_USERS_ENABLED": "false"}, environment)
        self.assertFalse(any(name.endswith("PASSWORD") for name in environment))

    def test_authorization_and_account_use_isolated_databases(self) -> None:
        urls = _isolated_postgres_jdbc_urls("127.0.0.1", 54321)
        self.assertEqual(
            "jdbc:postgresql://127.0.0.1:54321/cloudbank_azn",
            urls["authorization"],
        )
        self.assertEqual(
            "jdbc:postgresql://127.0.0.1:54321/cloudbank",
            urls["account"],
        )
        self.assertNotEqual(urls["authorization"], urls["account"])

    def test_oauth_account_runtime_overrides_imported_oracle_dialect(self) -> None:
        environment = _oauth_account_environment(
            {
                "SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT": (
                    "org.hibernate.dialect.OracleDialect"
                ),
                "SAFE_PARENT_VALUE": "retained",
            },
            54321,
            "jdbc:postgresql://127.0.0.1:5432/cloudbank",
            "synthetic-password",
        )
        self.assertEqual(
            "org.hibernate.dialect.PostgreSQLDialect",
            environment["SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT"],
        )
        self.assertEqual("retained", environment["SAFE_PARENT_VALUE"])
        self.assertEqual("54321", environment["SERVER_PORT"])
        self.assertEqual(
            environment["SPRING_DATASOURCE_URL"],
            environment["LIQUIBASE_DATASOURCE_URL"],
        )

    def test_oauth_transfer_runtime_enables_its_own_service_identity(self) -> None:
        common = {
            "CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED": "false",
            "CLOUDBANK_SECURITY_SERVICE_TOKEN_SCOPE": "cloudbank.transfer",
            "SAFE_PARENT_VALUE": "retained",
        }
        environment = _oauth_transfer_environment(
            common, 54321, 54322, "http://127.0.0.1:54323/oauth2/token", "synthetic-secret"
        )
        self.assertEqual("true", environment["CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED"])
        self.assertEqual("false", common["CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED"])
        self.assertEqual("retained", environment["SAFE_PARENT_VALUE"])
        self.assertEqual("54321", environment["SERVER_PORT"])
        self.assertEqual(
            "http://127.0.0.1:54322/api/v1/transfers", environment["ACCOUNT_TRANSACTION_URL"]
        )
        self.assertEqual(
            "cloudbank-transfer-service", environment["CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_ID"]
        )
        self.assertEqual(
            "cloudbank.internal", environment["CLOUDBANK_SECURITY_SERVICE_TOKEN_SCOPE"]
        )
        self.assertEqual(
            "http://127.0.0.1:54323/oauth2/token", environment["CLOUDBANK_SECURITY_SERVICE_TOKEN_URI"]
        )
        self.assertEqual(
            "synthetic-secret", environment["CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_SECRET"]
        )

    def test_authorization_database_creation_is_fail_closed(self) -> None:
        run = Mock()
        run.return_value.returncode = 0
        _create_authorization_database("postgres-container", run)
        run.assert_called_once_with(
            [
                "docker",
                "exec",
                "postgres-container",
                "createdb",
                "-U",
                "postgres",
                "cloudbank_azn",
            ],
            timeout=30,
        )

        run.return_value.returncode = 1
        with self.assertRaisesRegex(
            RuntimeError, "authorization-database-create-failed"
        ):
            _create_authorization_database("postgres-container", run)

    def test_claim_membership_accepts_string_and_array_jwt_encodings(self) -> None:
        self.assertTrue(_claim_contains("cloudbank.read cloudbank.transfer", "cloudbank.transfer"))
        self.assertTrue(_claim_contains(["cloudbank.internal"], "cloudbank.internal"))
        self.assertTrue(_claim_contains(["cloudbank-account"], "cloudbank-account"))
        self.assertFalse(_claim_contains("cloudbank.read", "cloudbank.transfer"))
        self.assertFalse(_claim_contains({"scope": "cloudbank.transfer"}, "cloudbank.transfer"))

    def test_failed_service_start_retains_only_bounded_evidence(self) -> None:
        raw_log = (
            b"secret=never-emit\nBeanCreationException: Error creating bean with name "
            b"'accountJwtDecoder'\nCaused by: java.lang.IllegalArgumentException\n"
        )
        process = Mock()
        process.poll.return_value = 1
        log = io.BytesIO(raw_log)
        with patch(
            "lightyear_data.cloudbank_production_oauth.subprocess.Popen",
            return_value=process,
        ), patch(
            "lightyear_data.cloudbank_production_oauth.tempfile.TemporaryFile",
            return_value=log,
        ), patch(
            "lightyear_data.cloudbank_production_oauth._wait_health",
            side_effect=RuntimeError("account-exited-before-health"),
        ):
            with self.assertRaisesRegex(RuntimeError, "account-exited-before-health") as raised:
                _start_oauth_service(
                    "account", ROOT / "account.jar", 12345, {}, lambda _: None
                )
        exception = raised.exception
        self.assertEqual("account", exception.service)
        self.assertEqual(1, exception.exit_code)
        self.assertEqual(hashlib.sha256(raw_log).hexdigest(), exception.log_sha256)
        self.assertEqual("bean-creation-failed", exception.category)
        self.assertEqual("oauth-jwt-decoder", exception.component)
        self.assertEqual("illegal-argument", exception.cause)
        self.assertIsNone(exception.database_sqlstate)
        self.assertIsNone(exception.database_relation)
        self.assertEqual("oauth-security-initialization", exception.stage)
        self.assertNotIn("never-emit", str(exception))

    def test_start_failure_categories_are_allowlisted(self) -> None:
        self.assertEqual(
            "configuration-placeholder-missing",
            _classify_service_start_failure(b"Could not resolve placeholder 'secret'", 1),
        )
        self.assertEqual(
            "database-migration-failed",
            _classify_service_start_failure(b"LiquibaseException: password=hidden", 1),
        )
        self.assertEqual("resource-exhausted", _classify_service_start_failure(b"", 137))
        self.assertEqual("unclassified", _classify_service_start_failure(b"private", 1))

    def test_start_failure_component_and_cause_categories_are_allowlisted(self) -> None:
        self.assertEqual(
            "oauth-security-filter-chain",
            _classify_service_start_component(
                b"Error creating bean with name 'accountOAuthSecurityFilterChain'"
            ),
        )
        self.assertEqual(
            "entity-manager",
            _classify_service_start_component(b"Error creating bean 'entityManagerFactory'"),
        )
        self.assertEqual(
            "schema-validation-failed",
            _classify_service_start_cause(
                b"SchemaManagementException: Schema-validation: missing table"
            ),
        )
        self.assertEqual(
            "unsatisfied-dependency",
            _classify_service_start_cause(b"UnsatisfiedDependencyException: secret=hidden"),
        )
        self.assertEqual(
            "database-object-conflict",
            _classify_service_start_cause(
                b"PSQLException: relation already exists; SQL State  : 42P07"
            ),
        )
        self.assertEqual(
            "database-statement-failed",
            _classify_service_start_cause(b"PSQLException: secret=hidden"),
        )
        self.assertEqual(
            "database-permission-denied",
            _classify_service_start_cause(b"ERROR: permission denied for schema user_repo"),
        )
        self.assertEqual(
            "database-connection-failed",
            _classify_service_start_cause(b"Connection refused"),
        )
        self.assertEqual(
            "42P07",
            _postgres_sqlstate(b"SQLSTATE[42p07]: secret=hidden"),
        )
        self.assertIsNone(_postgres_sqlstate(b"SQL State: ABCDE secret=hidden"))
        self.assertEqual(
            "accounts",
            _postgres_relation(
                b'PSQLException: ERROR: relation "accounts" does not exist\n'
                b"SQL State  : 42P01"
            ),
        )
        self.assertEqual(
            "authorization-users",
            _postgres_relation(
                b'ERROR: relation "user_repo"."users" does not exist\n'
                b"SQLSTATE[42P01]"
            ),
        )
        self.assertIsNone(
            _postgres_relation(
                b'ERROR: relation "secret_customer_table" does not exist\n'
                b"SQL State: 42P01"
            )
        )
        self.assertIsNone(
            _postgres_relation(
                b'NOTICE: table "transfer_commands" does not exist, skipping\n'
                b"SQL State: 42P01"
            )
        )
        self.assertEqual(
            "journal",
            _postgres_relation(
                b'NOTICE: table "transfer_commands" does not exist, skipping\n'
                b'PSQLException: ERROR: relation "journal" does not exist\n'
                b"SQL State: 42P01"
            ),
        )
        self.assertIsNone(
            _postgres_relation(
                b'ERROR: relation "accounts" does not exist\nSQL State: 23505'
            )
        )
        self.assertEqual(
            "account-seed-migration",
            _classify_service_start_stage(
                "account",
                b"Migration failed for changeset db/changelog/data.sql::"
                b"postgresql-transaction-core-data-1::account",
            ),
        )
        self.assertEqual(
            "jpa-schema-validation",
            _classify_service_start_stage(
                "account", b"SchemaManagementException: Schema-validation"
            ),
        )
        self.assertEqual(
            "unclassified",
            _classify_service_start_stage("account", b"secret=hidden"),
        )
        self.assertEqual("unclassified", _classify_service_start_component(b"secret"))
        self.assertEqual("unclassified", _classify_service_start_cause(b"secret"))

    def test_account_schema_relation_presence_is_strictly_bounded(self) -> None:
        supplied = {
            "accounts": True,
            "journal": False,
            "transfer-commands": True,
            "liquibase-history": True,
            "liquibase-lock": "secret=should-not-leak",
            "secret-table": True,
        }
        with patch(
            "lightyear_data.cloudbank_production_oauth._psql",
            return_value=json.dumps(supplied),
        ) as psql:
            presence = _account_schema_relation_presence(
                "postgres-container", lambda *_args, **_kwargs: Mock()
            )
        self.assertEqual(
            {
                "accounts": True,
                "journal": False,
                "transfer-commands": True,
                "liquibase-history": True,
                "liquibase-lock": None,
            },
            presence,
        )
        query = psql.call_args.args[1]
        self.assertIn("to_regclass('public.transfer_commands')", query)
        self.assertNotIn("secret", query)

    @unittest.skipUnless(SOURCE.is_dir(), "pinned CloudBank source is unavailable")
    def test_materialization_preserves_source_and_creates_oauth_target(self) -> None:
        source_head = (SOURCE / ".git/HEAD").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            workspace = materialize_target(ROOT, SOURCE, Path(directory) / "workspace")
            for relative in changed_paths():
                self.assertTrue((workspace / relative).is_file(), relative)
            azn_pom = (workspace / "azn-server/pom.xml").read_text(encoding="utf-8")
            self.assertIn("postgresql", azn_pom)
            self.assertNotIn("oracle-spring-boot", azn_pom)
            for test_dependency in (
                "spring-security-test",
                "spring-boot-testcontainers",
                "junit-jupiter",
                "oracle-free",
            ):
                self.assertIn(test_dependency, azn_pom)
        self.assertEqual(source_head, (SOURCE / ".git/HEAD").read_bytes())

    @patch(
        "lightyear_data.cloudbank_production_oauth.validate_ms61_receipt",
        return_value=[],
    )
    @patch("lightyear_data.cloudbank_production_oauth.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_production_oauth.materialize_target")
    def test_execution_closes_only_application_oauth_boundary(
        self, materialize: object, _source: object, _ms61: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            receipt = execute_production_oauth(
                ROOT,
                ROOT,
                ms61_receipt(),
                output,
                KEY,
                "unit-test",
                "ms62-unit-run",
                lane_runner=lambda _workspace, _image: passed_lane(),
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["production_oauth_application_profile_qualified"])
            self.assertTrue(receipt["service_to_service_client_credentials_observed"])
            self.assertFalse(receipt["production_oauth_operational_deployment_qualified"])
            self.assertFalse(receipt["external_tls_termination_observed"])
            self.assertFalse(receipt["native_messaging_observed"])
            self.assertFalse(receipt["production_ready"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-production-oauth-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-production-oauth-receipt-claims-invalid", errors)

    @patch(
        "lightyear_data.cloudbank_production_oauth.validate_ms61_receipt",
        return_value=[],
    )
    @patch("lightyear_data.cloudbank_production_oauth.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_production_oauth.materialize_target")
    def test_failed_lane_writes_safe_aggregate_diagnostics(
        self, materialize: object, _source: object, _ms61: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            failed = passed_lane()
            failed["status"] = "failed"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_production_oauth(
                    ROOT,
                    ROOT,
                    ms61_receipt(),
                    output,
                    KEY,
                    "unit-test",
                    "ms62-failed-run",
                    lane_runner=lambda _workspace, _image: failed,
                )
            diagnostic = output / "cloudbank-production-oauth.failure.json"
            text = diagnostic.read_text(encoding="utf-8")
            self.assertNotIn("client-secret", text)
            self.assertNotIn("access_token", text)
            self.assertNotIn("raw_stdout", text)

    def test_failure_diagnostic_emits_only_bounded_classifications(self) -> None:
        failed = passed_lane()
        failed.update(
            {
                "status": "failed",
                "reason": "runtime-gate-failed:azn-server-health-timeout",
                "scenario_count": 3,
                "scenarios": [
                    {
                        "id": "authorization-server-discovery-and-jwks",
                        "status": "failed",
                        "access_token": "should-not-leak",
                    },
                    {
                        "id": "password=should-not-leak",
                        "status": "failed",
                    },
                ],
                "service_starts": {
                    "azn-server": 1,
                    "account": 0,
                    "transfer": 0,
                    "password": "should-not-leak",
                },
                "service_log_sha256": {
                    "azn-server": [HEX_A, "secret=should-not-leak"],
                    "account": [],
                    "transfer": [],
                    "password": ["should-not-leak"],
                },
                "service_exit_codes": {
                    "azn-server": 1,
                    "account": 100_000,
                    "transfer": None,
                    "password": 1,
                },
                "service_start_failure_categories": {
                    "azn-server": "bean-creation-failed",
                    "account": "secret=should-not-leak",
                    "transfer": None,
                    "password": "configuration-placeholder-missing",
                },
                "service_start_failure_components": {
                    "azn-server": "oauth-jwt-decoder",
                    "account": "secret=should-not-leak",
                    "transfer": None,
                    "password": "datasource",
                },
                "service_start_failure_causes": {
                    "azn-server": "database-object-conflict",
                    "account": "secret=should-not-leak",
                    "transfer": None,
                    "password": "missing-bean",
                },
                "service_start_database_sqlstates": {
                    "azn-server": "42P07",
                    "account": "ABCDE",
                    "transfer": None,
                    "password": "28P01",
                },
                "service_start_database_relations": {
                    "azn-server": "accounts",
                    "account": "secret=should-not-leak",
                    "transfer": None,
                    "password": "journal",
                },
                "service_start_failure_stages": {
                    "azn-server": "account-seed-migration",
                    "account": "secret=should-not-leak",
                    "transfer": None,
                    "password": "application-context",
                },
                "account_schema_relation_presence": {
                    "accounts": True,
                    "journal": False,
                    "transfer-commands": "secret=should-not-leak",
                    "liquibase-history": True,
                    "liquibase-lock": None,
                    "password": True,
                },
                "packaging": {
                    "executable_jars": 3,
                    "oracle_runtime_libraries": 0,
                    "microtx_runtime_libraries": 0,
                    "secret": "should-not-leak",
                },
                "raw_stdout": "access_token=should-not-leak",
                "private_key": "should-not-leak",
            }
        )
        diagnostic = production_oauth_failure_diagnostic(
            {"lane": failed, "secret": "should-not-leak"}, HEX_B
        )
        self.assertEqual(
            "runtime-gate-failed:azn-server-health-timeout",
            diagnostic["reason"],
        )
        self.assertEqual(
            [{"id": SCENARIO_IDS[0], "status": "failed"}],
            diagnostic["scenario_statuses"],
        )
        self.assertEqual([SCENARIO_IDS[0]], diagnostic["failed_scenarios"])
        self.assertEqual(
            {"azn-server": 1, "account": 0, "transfer": 0},
            diagnostic["service_starts"],
        )
        self.assertEqual(
            {"azn-server": 1, "account": 0, "transfer": 0},
            diagnostic["service_log_counts"],
        )
        self.assertEqual(
            {"azn-server": 1, "account": None, "transfer": None},
            diagnostic["service_exit_codes"],
        )
        self.assertEqual(
            {
                "azn-server": "bean-creation-failed",
                "account": None,
                "transfer": None,
            },
            diagnostic["service_start_failure_categories"],
        )
        self.assertEqual(
            {
                "azn-server": "oauth-jwt-decoder",
                "account": None,
                "transfer": None,
            },
            diagnostic["service_start_failure_components"],
        )
        self.assertEqual(
            {
                "azn-server": "database-object-conflict",
                "account": None,
                "transfer": None,
            },
            diagnostic["service_start_failure_causes"],
        )
        self.assertEqual(
            {"azn-server": "42P07", "account": None, "transfer": None},
            diagnostic["service_start_database_sqlstates"],
        )
        self.assertEqual(
            {"azn-server": "accounts", "account": None, "transfer": None},
            diagnostic["service_start_database_relations"],
        )
        self.assertEqual(
            {
                "azn-server": "account-seed-migration",
                "account": None,
                "transfer": None,
            },
            diagnostic["service_start_failure_stages"],
        )
        self.assertEqual(
            {
                "accounts": True,
                "journal": False,
                "transfer-commands": None,
                "liquibase-history": True,
                "liquibase-lock": None,
            },
            diagnostic["account_schema_relation_presence"],
        )
        self.assertTrue(diagnostic["public_signing_key_created"])
        self.assertTrue(diagnostic["jwks_observed"])
        self.assertFalse(diagnostic["credentials_persisted"])
        self.assertFalse(diagnostic["private_key_persisted"])
        self.assertFalse(diagnostic["raw_output_persisted"])
        rendered = json.dumps(diagnostic, sort_keys=True)
        self.assertNotIn("should-not-leak", rendered)
        self.assertNotIn("access_token", rendered)

    def test_failure_diagnostic_rejects_unbounded_values(self) -> None:
        diagnostic = production_oauth_failure_diagnostic(
            {
                "lane": {
                    "lane": "secret=should-not-leak",
                    "status": ["failed", "secret=should-not-leak"],
                    "reason": "runtime-gate-failed:secret=should-not-leak",
                    "maven_exit_code": 100_000,
                    "scenario_count": -2,
                    "scenarios": [
                        {"id": SCENARIO_IDS[0], "status": ["failed"]}
                    ],
                }
            },
            HEX_B,
        )
        self.assertFalse(diagnostic["lane_match"])
        self.assertEqual("invalid", diagnostic["status"])
        self.assertEqual("invalid", diagnostic["reason"])
        self.assertIsNone(diagnostic["maven_exit_code"])
        self.assertIsNone(diagnostic["scenario_count"])
        self.assertEqual([], diagnostic["scenario_statuses"])
        self.assertNotIn("should-not-leak", json.dumps(diagnostic, sort_keys=True))

    def test_run_cli_emits_bounded_failure_diagnostic_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt_path = root / "ms61.json"
            receipt_path.write_text(json.dumps(ms61_receipt()), encoding="utf-8")
            failed = passed_lane()
            failed.update(
                {
                    "status": "failed",
                    "reason": "runtime-gate-failed:azn-server-health-timeout",
                    "service_starts": {
                        "azn-server": 1,
                        "account": 0,
                        "transfer": 0,
                    },
                    "scenarios": [],
                    "scenario_count": 0,
                    "raw_stdout": "client_secret=should-not-leak",
                }
            )
            (root / "cloudbank-production-oauth.failure.json").write_text(
                json.dumps({"lane": failed}), encoding="utf-8"
            )
            stdout = io.StringIO()
            with patch.object(
                production_oauth_tool,
                "execute_production_oauth",
                side_effect=ValueError("cloudbank-production-oauth-acceptance-failed"),
            ), redirect_stdout(stdout):
                exit_code = production_oauth_tool.main(
                    [
                        "run",
                        "--source-root",
                        str(root),
                        "--ms61-receipt",
                        str(receipt_path),
                        "--output-root",
                        str(root),
                        "--signer",
                        "unit-test",
                    ]
                )
            rendered = stdout.getvalue()
            self.assertEqual(1, exit_code)
            marker_lines = [
                line for line in rendered.splitlines() if line.startswith(DIAGNOSTIC_MARKER)
            ]
            self.assertEqual(1, len(marker_lines))
            diagnostic = json.loads(marker_lines[0].removeprefix(DIAGNOSTIC_MARKER))
            self.assertEqual(
                "runtime-gate-failed:azn-server-health-timeout",
                diagnostic["reason"],
            )
            self.assertNotIn("should-not-leak", rendered)
            self.assertNotIn("client_secret", rendered)

    def test_launchers_exist(self) -> None:
        for relative in (
            "cloudbank-production-oauth.sh",
            "cloudbank-production-oauth.ps1",
            "tools/cloudbank_production_oauth.py",
            "reference-estates/cloudbank/schema/production-oauth-readiness.schema.json",
            "reference-estates/cloudbank/schema/production-oauth-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        powershell = (ROOT / "cloudbank-production-oauth.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-FactoryDarkPython", powershell)
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertIn("cloudbank-production-oauth.sh materialize", workflow)
        self.assertIn("mvn -pl azn-server,account,transfer", workflow)
        tool = (ROOT / "tools/cloudbank_production_oauth.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("DIAGNOSTIC_MARKER", tool)
        self.assertTrue(DIAGNOSTIC_MARKER.endswith("="))


if __name__ == "__main__":
    unittest.main()
