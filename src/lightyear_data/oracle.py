from __future__ import annotations

from typing import Any

from .contracts import SCHEMA_VERSION, seal
from .postgres import TargetAdapter, _source_type, sql_literal


class OracleAdapter(TargetAdapter):
    """Oracle 26ai Free projection of the target-neutral AUTHFRDS model."""

    adapter_id = "factorydark-oracle"
    adapter_version = "1.0"
    dialect = "oracle-26ai-free"
    default_image = "oracle/database:23.26.1-free"

    @staticmethod
    def target_type(column: dict[str, Any]) -> str:
        source = column["source_type"]
        if source == "CHAR":
            return f"CHAR({column['length']} CHAR)"
        if source == "VARCHAR":
            return f"VARCHAR2({column['length']} CHAR)"
        if source == "DECIMAL":
            return f"NUMBER({column['precision']},{column['scale'] or 0})"
        return {
            "SMALLINT": "NUMBER(5,0)",
            "INTEGER": "NUMBER(10,0)",
            "DATE": "DATE",
            "TIMESTAMP": "TIMESTAMP(6)",
        }[source]

    def mapping(self, model: dict[str, Any]) -> dict[str, Any]:
        return seal({
            "schema_version": SCHEMA_VERSION,
            "mapping_type": "target-adapter-mapping",
            "source_dialect": "db2-zos",
            "target_dialect": self.dialect,
            "source_table": f"{model['schema']}.{model['name']}",
            "target_table": f"CARDDEMO.{model['name']}",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "columns": [
                {
                    "source": column["name"],
                    "target": column["name"],
                    "source_type": _source_type(column),
                    "target_type": self.target_type(column),
                    "nullable": column["nullable"],
                    "transformation": "identity-with-encoding-normalization",
                }
                for column in model["columns"]
            ],
            "known_gaps": [
                {
                    "id": "oracle-empty-string-is-null",
                    "severity": "requires-data-profile",
                    "statement": "Oracle treats zero-length character values as NULL; live source profiling must prove this is safe.",
                },
                {
                    "id": "live-db2-catalog-not-observed",
                    "severity": "blocking-production",
                    "statement": "The Db2 catalog and live authorization workload have not yet been captured on z/OS.",
                },
            ],
        })

    def schema_sql(self, model: dict[str, Any]) -> str:
        definitions = []
        for column in model["columns"]:
            nullability = "" if column["nullable"] else " NOT NULL"
            definitions.append(f"  {column['name']} {self.target_type(column)}{nullability}")
        for constraint in model["constraints"]:
            if constraint["kind"] == "primary_key":
                names = ", ".join(constraint["columns"])
                definitions.append(f"  CONSTRAINT PK_AUTHFRDS PRIMARY KEY ({names})")
        statements = [
            "BEGIN EXECUTE IMMEDIATE 'DROP USER CARDDEMO CASCADE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1918 THEN RAISE; END IF; END;\n/",
            "CREATE USER CARDDEMO NO AUTHENTICATION;",
            """DECLARE
  FD_DEFAULT_TABLESPACE VARCHAR2(128);
BEGIN
  SELECT PROPERTY_VALUE INTO FD_DEFAULT_TABLESPACE
  FROM DATABASE_PROPERTIES
  WHERE PROPERTY_NAME='DEFAULT_PERMANENT_TABLESPACE';
  EXECUTE IMMEDIATE 'ALTER USER CARDDEMO QUOTA UNLIMITED ON ' ||
    DBMS_ASSERT.ENQUOTE_NAME(FD_DEFAULT_TABLESPACE, FALSE);
END;
/""",
            "CREATE TABLE CARDDEMO.AUTHFRDS (\n" + ",\n".join(definitions) + "\n);",
        ]
        for index in model["indexes"]:
            unique = "UNIQUE " if index["unique"] else ""
            columns = ", ".join(f"{item['name']} {item['order']}" for item in index["columns"])
            statements.append(f"CREATE {unique}INDEX CARDDEMO.{index['name']} ON CARDDEMO.AUTHFRDS ({columns});")
        return "\n\n".join(statements) + "\n"

    def fixture_sql(self, fixtures: dict[str, Any], model: dict[str, Any]) -> str:
        columns = [column["name"] for column in model["columns"]]
        rows = fixtures.get("rows", [])
        if not rows:
            raise ValueError("Fixture catalog contains no rows")
        statements = []
        for row in rows:
            if set(row) != set(columns):
                raise ValueError("Fixture row does not exactly match the canonical column set")
            values = []
            for column in model["columns"]:
                value = row[column["name"]]
                if value is not None and column["source_type"] == "TIMESTAMP":
                    values.append(f"TO_TIMESTAMP({sql_literal(value)}, 'YYYY-MM-DD\"T\"HH24:MI:SS.FF6')")
                elif value is not None and column["source_type"] == "DATE":
                    values.append(f"TO_DATE({sql_literal(value)}, 'YYYY-MM-DD')")
                else:
                    values.append(sql_literal(value))
            statements.append(
                f"INSERT INTO CARDDEMO.AUTHFRDS ({', '.join(columns)}) VALUES ({', '.join(values)});"
            )
        statements.append("COMMIT;")
        return "\n".join(statements) + "\n"

    def catalog_expectation(self, model: dict[str, Any]) -> dict[str, Any]:
        columns = []
        for column in model["columns"]:
            source = column["source_type"]
            columns.append({
                "name": column["name"],
                "ordinal": column["ordinal"],
                "data_type": {
                    "CHAR": "CHAR", "VARCHAR": "VARCHAR2", "DECIMAL": "NUMBER",
                    "SMALLINT": "NUMBER", "INTEGER": "NUMBER", "DATE": "DATE",
                    "TIMESTAMP": "TIMESTAMP(6)",
                }[source],
                "length": column.get("length"),
                "precision": column.get("precision") if source == "DECIMAL" else (
                    5 if source == "SMALLINT" else 10 if source == "INTEGER" else None
                ),
                "scale": (column.get("scale") or 0) if source == "DECIMAL" else (
                    0 if source in {"SMALLINT", "INTEGER"} else 6 if source == "TIMESTAMP" else None
                ),
                "nullable": column["nullable"],
            })
        return {
            "columns": columns,
            "primary_key": {"name": "PK_AUTHFRDS", "columns": model["constraints"][0]["columns"]},
            "indexes": [
                {
                    "name": index["name"], "unique": index["unique"],
                    "columns": index["columns"],
                }
                for index in model["indexes"]
            ],
        }
