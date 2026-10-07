"""Read-only DB-API capture and deterministic replay primitives.

No connection is opened here. Live callers must admit their VM and owned database
before supplying a connection. Unit-test connections are not native evidence.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import math
from uuid import UUID

from lightyear_data.contracts import content_hash, seal
from .comparison import table_delta


class CaptureIncomplete(ValueError):
    pass


def scalar(value):
    """Lossless JSON transport tags. Do not silently coerce floats or trim text."""
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CaptureIncomplete("nonfinite-decimal")
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CaptureIncomplete("nonfinite-float")
        return {"type": "binary-float", "value": value.hex()}
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"type": "time", "value": value.isoformat()}
    if isinstance(value, UUID):
        return {"type": "uuid", "value": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"type": "binary", "value": base64.b64encode(bytes(value)).decode("ascii")}
    raise CaptureIncomplete("unsupported-driver-value-type")


def identifier(name, engine):
    if not isinstance(name, str) or not name or "\x00" in name:
        raise CaptureIncomplete("invalid-identifier")
    if engine == "sqlserver":
        return "[" + name.replace("]", "]]") + "]"
    if engine == "postgresql":
        return '"' + name.replace('"', '""') + '"'
    raise CaptureIncomplete("unsupported-capture-engine")


TABLES = {
    "sqlserver": """SELECT s.name,t.name FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
WHERE t.is_ms_shipped=0 ORDER BY s.name,t.name""",
    "postgresql": """SELECT n.nspname,c.relname FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','p') AND NOT c.relispartition
AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
ORDER BY n.nspname,c.relname""",
}
COLUMNS = {
    "sqlserver": """SELECT c.name,ty.name,c.max_length,c.precision,c.scale,c.is_nullable
FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
JOIN sys.tables t ON t.object_id=c.object_id
JOIN sys.schemas s ON s.schema_id=t.schema_id
WHERE s.name=? AND t.name=? ORDER BY c.column_id""",
    "postgresql": """SELECT a.attname,format_type(a.atttypid,a.atttypmod),
a.attnotnull,a.attgenerated FROM pg_attribute a
JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped
ORDER BY a.attnum""",
}
KEYS = {
    "sqlserver": """SELECT c.name FROM sys.indexes i
JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
JOIN sys.tables t ON t.object_id=i.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id
WHERE s.name=? AND t.name=? AND i.is_primary_key=1 ORDER BY ic.key_ordinal""",
    "postgresql": """SELECT a.attname FROM pg_index i
JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum,ord) ON true
JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
WHERE n.nspname=%s AND c.relname=%s AND i.indisprimary ORDER BY k.ord""",
}
IDENTITIES = """SELECT s.name,t.name,c.name,CONVERT(varchar(100),c.last_value),
CONVERT(varchar(100),c.seed_value),CONVERT(varchar(100),c.increment_value)
FROM sys.identity_columns c JOIN sys.tables t ON t.object_id=c.object_id
JOIN sys.schemas s ON s.schema_id=t.schema_id ORDER BY s.name,t.name,c.name"""
SEQUENCES = """SELECT n.nspname,c.relname FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S'
AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
ORDER BY n.nspname,c.relname"""
SEQUENCE_OWNER = """SELECT sn.nspname,tab.relname,a.attname,s.seqstart,s.seqincrement
FROM pg_class seq JOIN pg_namespace n ON n.oid=seq.relnamespace
JOIN pg_sequence s ON s.seqrelid=seq.oid
LEFT JOIN pg_depend d ON d.objid=seq.oid AND d.classid='pg_class'::regclass AND d.deptype IN ('a','i')
LEFT JOIN pg_class tab ON tab.oid=d.refobjid
LEFT JOIN pg_namespace sn ON sn.oid=tab.relnamespace
LEFT JOIN pg_attribute a ON a.attrelid=tab.oid AND a.attnum=d.refobjsubid
WHERE n.nspname=%s AND seq.relname=%s"""


def query(connection, sql, parameters=(), *, maximum_rows=1000000):
    """A partial/truncated read is never a complete state capture."""
    cursor = connection.cursor()
    try:
        if parameters:
            cursor.execute(sql, parameters)
        else:
            # Passing an empty tuple enables pyformat interpolation in native
            # drivers; literal LIKE '%' clauses must stay literal SQL.
            cursor.execute(sql)
        rows = cursor.fetchmany(maximum_rows + 1)
        if len(rows) > maximum_rows:
            raise CaptureIncomplete("capture-row-limit")
        # Drivers may return fewer than requested rows even before EOF.
        rows = list(rows)
        while True:
            batch = cursor.fetchmany(min(4096, maximum_rows - len(rows) + 1))
            if not batch:
                break
            rows.extend(batch)
            if len(rows) > maximum_rows:
                raise CaptureIncomplete("capture-row-limit")
        return [list(row) for row in rows]
    finally:
        cursor.close()


def capture_state(connection, engine, *, maximum_rows=1000000):
    """Enumerate every ordinary user table, including trigger targets.

    PostgreSQL partition roots include their partition rows exactly once.
    Raw column/type metadata is retained; cross-engine mapping is separate.
    """
    if engine not in TABLES:
        raise CaptureIncomplete("unsupported-capture-engine")
    if type(maximum_rows) is not int or maximum_rows < 1:
        raise CaptureIncomplete("capture-row-limit")
    inventory = query(connection, TABLES[engine], maximum_rows=maximum_rows)
    if len({tuple(x) for x in inventory}) != len(inventory):
        raise CaptureIncomplete("duplicate-table-inventory")
    tables = {}
    for schema, table in inventory:
        key = json_key((schema, table))
        qualified = identifier(schema, engine) + "." + identifier(table, engine)
        columns = query(connection, COLUMNS[engine], (schema, table), maximum_rows=maximum_rows)
        names = [c[0] for c in columns]
        if not names or len(set(names)) != len(names):
            raise CaptureIncomplete("invalid-table-columns")
        primary_key = [r[0] for r in query(connection, KEYS[engine], (schema, table))]
        if not set(primary_key) <= set(names):
            raise CaptureIncomplete("invalid-primary-key")
        projection = ",".join(identifier(n, engine) for n in names)
        rows = query(connection, "SELECT " + projection + " FROM " + qualified,
                     maximum_rows=maximum_rows)
        if any(len(r) != len(names) for r in rows):
            raise CaptureIncomplete("capture-row-width")
        tables[key] = {
            "schema": schema, "table": table,
            "columns": [[scalar(v) for v in row] for row in columns],
            "primary_key": primary_key,
            "rows": [dict(zip(names, [scalar(v) for v in row])) for row in rows],
        }
    identities = {}
    if engine == "sqlserver":
        for schema, table, column, current, seed, increment in query(connection, IDENTITIES):
            identities[json_key((schema, table, column))] = {
                "last_value": current,"seed":seed,"increment":increment}
    else:
        for schema, sequence in query(connection, SEQUENCES):
            qualified = identifier(schema, engine) + "." + identifier(sequence, engine)
            rows = query(connection, "SELECT last_value,is_called FROM " + qualified)
            if len(rows) != 1 or len(rows[0]) != 2:
                raise CaptureIncomplete("sequence-state-missing")
            identities[json_key((schema, sequence))] = {
                "last_value": scalar(rows[0][0]), "is_called": scalar(rows[0][1]),
            }
            metadata=query(connection,SEQUENCE_OWNER,(schema,sequence))
            if len(metadata)!=1:raise CaptureIncomplete('sequence-owner-ambiguous')
            owner_schema,owner_table,owner_column,seed,increment=metadata[0]
            identities[json_key((schema,sequence))].update(
                owner=[owner_schema,owner_table,owner_column],seed=seed,increment=increment)
    if inventory != query(connection, TABLES[engine], maximum_rows=maximum_rows):
        raise CaptureIncomplete("table-inventory-changed-during-capture")
    return seal({
        "schema": "tsql-state-capture/1", "engine": engine,
        "table_inventory": sorted(tables), "tables": tables,
        "identity_sequence_state": identities, "all_user_tables_captured": True,
        "mapping_applied": False,
    })


def json_key(parts):
    import json
    return json.dumps(list(parts), ensure_ascii=True, separators=(",", ":"))


def state_changes(before, after):
    """Recompute same-engine effects from complete before/after captures.

    Cross-engine table, column, type and sequence mappings are still mandatory.
    """
    for state in (before, after):
        if (state.get("schema") != "tsql-state-capture/1"
                or state.get("content_sha256") != content_hash(state)
                or state.get("all_user_tables_captured") is not True
                or set(state.get("table_inventory", [])) != set(state.get("tables", {}))):
            raise CaptureIncomplete("invalid-state-capture")
    if before["engine"] != after["engine"]:
        raise CaptureIncomplete("state-engine-changed")
    names = sorted(set(before["tables"]) | set(after["tables"]))
    effects = {}
    for name in names:
        old, new = before["tables"].get(name), after["tables"].get(name)
        if old is None or new is None or old["columns"] != new["columns"] or old["primary_key"] != new["primary_key"]:
            effects[name] = {"kind": "schema-change", "before": old, "after": new}
        else:
            effects[name] = table_delta(old["rows"], new["rows"], tuple(old["primary_key"]))
    return {
        "all_user_tables_captured": True, "table_inventory": names, "tables": effects,
        "identity_sequence_state": {
            "before": before["identity_sequence_state"],
            "after": after["identity_sequence_state"],
        },
    }
