from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from .contracts import SCHEMA_VERSION, seal


class TargetAdapter(ABC):
    adapter_id: str
    adapter_version: str
    dialect: str
    default_image: str

    @abstractmethod
    def mapping(self, model: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def schema_sql(self, model: dict[str, Any]) -> str: ...

    @abstractmethod
    def fixture_sql(self, fixtures: dict[str, Any], model: dict[str, Any]) -> str: ...

    @abstractmethod
    def catalog_expectation(self, model: dict[str, Any]) -> dict[str, Any]: ...


class PostgreSQLAdapter(TargetAdapter):
    adapter_id = "factorydark-postgresql"
    adapter_version = "1.0"
    dialect = "postgresql-16"
    default_image = "postgres:16-alpine"

    @staticmethod
    def target_type(column: dict[str, Any]) -> str:
        source = column["source_type"]
        if source == "CHAR":
            return f"CHAR({column['length']})"
        if source == "VARCHAR":
            return f"VARCHAR({column['length']})"
        if source == "DECIMAL":
            return f"NUMERIC({column['precision']},{column['scale'] or 0})"
        return {"SMALLINT": "SMALLINT", "INTEGER": "INTEGER", "DATE": "DATE", "TIMESTAMP": "TIMESTAMP(6)"}[source]

    def mapping(self, model: dict[str, Any]) -> dict[str, Any]:
        return seal({
            "schema_version": SCHEMA_VERSION, "mapping_type": "target-adapter-mapping",
            "source_dialect": "db2-zos", "target_dialect": self.dialect,
            "source_table": f"{model['schema']}.{model['name']}",
            "target_table": f"carddemo.{model['name'].lower()}",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "columns": [
                {
                    "source": column["name"], "target": column["name"].lower(),
                    "source_type": _source_type(column), "target_type": self.target_type(column),
                    "nullable": column["nullable"], "transformation": "identity-with-encoding-normalization",
                }
                for column in model["columns"]
            ],
            "known_gaps": [
                {
                    "id": "live-db2-catalog-not-observed", "severity": "blocking-production",
                    "statement": "The Db2 catalog and live authorization workload have not yet been captured on z/OS."
                }
            ],
        })

    def fixture_sql(self, fixtures: dict[str, Any], model: dict[str, Any]) -> str:
        return fixture_sql(fixtures, model)

    def catalog_expectation(self, model: dict[str, Any]) -> dict[str, Any]:
        return {
            "columns": [
                {
                    "name": column["name"].lower(),
                    "ordinal": column["ordinal"],
                    "data_type": _postgres_catalog_type(column),
                    "length": column.get("length"),
                    "precision": column.get("precision") if column["source_type"] == "DECIMAL" else (
                        16 if column["source_type"] == "SMALLINT" else 32 if column["source_type"] == "INTEGER" else None
                    ),
                    "scale": column.get("scale") if column.get("scale") is not None else (
                        0 if column["source_type"] in {"DECIMAL", "SMALLINT", "INTEGER"} else None
                    ),
                    "nullable": column["nullable"],
                }
                for column in model["columns"]
            ],
            "primary_key": {
                "name": "pk_authfrds",
                "columns": [name.lower() for name in model["constraints"][0]["columns"]],
            },
            "indexes": [
                {
                    "name": index["name"].lower(),
                    "unique": index["unique"],
                    "columns": [
                        {"name": item["name"].lower(), "order": item["order"]}
                        for item in index["columns"]
                    ],
                }
                for index in model["indexes"]
            ],
        }

    def schema_sql(self, model: dict[str, Any]) -> str:
        definitions = []
        for column in model["columns"]:
            nullability = "" if column["nullable"] else " NOT NULL"
            definitions.append(f'  "{column["name"].lower()}" {self.target_type(column)}{nullability}')
        for constraint in model["constraints"]:
            if constraint["kind"] == "primary_key":
                columns = ", ".join(f'"{name.lower()}"' for name in constraint["columns"])
                definitions.append(f'  CONSTRAINT "{constraint["id"].replace(":", "_").lower()}" PRIMARY KEY ({columns})')
        statements = [
            "CREATE SCHEMA IF NOT EXISTS carddemo;",
            "DROP TABLE IF EXISTS carddemo.authfrds;",
            "CREATE TABLE carddemo.authfrds (\n" + ",\n".join(definitions) + "\n);",
        ]
        for index in model["indexes"]:
            unique = "UNIQUE " if index["unique"] else ""
            columns = ", ".join(f'"{item["name"].lower()}" {item["order"]}' for item in index["columns"])
            statements.append(f'CREATE {unique}INDEX "{index["name"].lower()}" ON carddemo.authfrds ({columns});')
        return "\n\n".join(statements) + "\n"


def _source_type(column: dict[str, Any]) -> str:
    source = column["source_type"]
    if source in {"CHAR", "VARCHAR"}:
        return f"{source}({column['length']})"
    if source == "DECIMAL":
        return f"DECIMAL({column['precision']},{column['scale'] or 0})"
    return source


def _postgres_catalog_type(column: dict[str, Any]) -> str:
    return {
        "CHAR": "character",
        "VARCHAR": "character varying",
        "DECIMAL": "numeric",
        "SMALLINT": "smallint",
        "INTEGER": "integer",
        "DATE": "date",
        "TIMESTAMP": "timestamp without time zone",
    }[column["source_type"]]


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("'", "''")
    return "'" + text + "'"


def fixture_sql(fixtures: dict[str, Any], model: dict[str, Any]) -> str:
    columns = [column["name"] for column in model["columns"]]
    rows = fixtures.get("rows", [])
    if not rows:
        raise ValueError("Fixture catalog contains no rows")
    statements = []
    names = ", ".join(f'"{name.lower()}"' for name in columns)
    for row in rows:
        if set(row) != set(columns):
            raise ValueError("Fixture row does not exactly match the canonical column set")
        values = ", ".join(sql_literal(row[name]) for name in columns)
        statements.append(f"INSERT INTO carddemo.authfrds ({names}) VALUES ({values});")
    return "\n".join(statements) + "\n"
