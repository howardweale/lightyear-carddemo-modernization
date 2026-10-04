"""Trusted, read-only document probes while the application JVM is suspended.

Input arrives from the host observer broker, never a candidate output file.
Results and SQL remain private. There is no signing authority in this process.
"""
from datetime import datetime, timezone
import json
import sys
from .contracts import require, seal, canonical, digest
from .journey_worker import connect
from .native_catalog import query

TABLES = {318: 'c_invoice', 319: 'm_inout', 321: 'm_inventory', 323: 'm_movement',
          335: 'c_payment', 259: 'c_order', 735: 'c_allocationhdr',
          472: 'm_matchinv', 473: 'm_matchpo'}


def queries_for(lane, key):
    require(lane in ('oracle', 'postgresql'), 'Unknown posting probe lane')
    require(isinstance(key, list) and len(key) == 2 and all(type(i) is int for i in key),
            'Invalid document key')
    table_id, identity = key
    require(table_id in TABLES and 0 < identity < 2**31, 'Unsupported posting document')
    table = TABLES[table_id]
    # Identifiers are from the closed code map; values are validated integers.
    return {
        'document': f'SELECT {table}_id record_id, ad_client_id, ad_org_id, processed, processing, posted, isactive FROM adempiere.{table} WHERE {table}_id={identity}',
        'facts': f'SELECT fact_acct_id, ad_table_id, record_id, c_acctschema_id, c_period_id, account_id, amtacctdr, amtacctcr FROM adempiere.fact_acct WHERE ad_table_id={table_id} AND record_id={identity}',
        'clock': 'SELECT SYSTIMESTAMP value FROM dual' if lane == 'oracle' else 'SELECT clock_timestamp() value',
        'health': 'SELECT 1 value FROM dual' if lane == 'oracle' else 'SELECT 1 value',
    }


def capture(spec):
    lane = spec['lane']
    key = spec['document']
    queries = queries_for(lane, key)
    started = datetime.now(timezone.utc).isoformat()
    with connect(lane, spec['password']) as connection:
        if lane == 'oracle':
            connection.call_timeout = 5000
            with connection.cursor() as cursor: cursor.execute('SET TRANSACTION READ ONLY')
        else:
            connection.execute("SET statement_timeout='5s'")
            connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        try:
            results = {name: {'sql': sql, 'rows': query(connection, sql)} for name, sql in queries.items()}
        finally:
            connection.rollback()
    return seal({'artifact_type': 'ms94-b06-posting-native-readback/1', 'lane': lane,
                 'document': key, 'event_sequence': spec['event_sequence'],
                 'query_set_sha256': digest(queries), 'results': results,
                 'real_started_utc': started, 'real_finished_utc': datetime.now(timezone.utc).isoformat(),
                 'read_only': True, 'application_vm_suspended': True})


if __name__ == '__main__':
    print(canonical(capture(json.load(sys.stdin))).decode(), flush=True)
