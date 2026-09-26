"""Rollback-only checks on the six journey tables in an isolated test database.

This exercises database constraints, not iDempiere business logic. A successful
client statement alone cannot count as a successful rejection test.
"""
from datetime import datetime, timezone

from .contracts import digest, require, seal
from .native_catalog import query

TABLES = (
    ('c_bpartner', 'name', 'c_bp_group_id', 'c_bp_group'),
    ('m_product', 'name', 'c_uom_id', 'c_uom'),
    ('c_order', 'documentno', 'c_bpartner_id', 'c_bpartner'),
    ('m_inout', 'documentno', 'c_bpartner_id', 'c_bpartner'),
    ('c_invoice', 'documentno', 'c_bpartner_id', 'c_bpartner'),
    ('c_payment', 'documentno', 'c_currency_id', 'c_currency'),
)
ERRORS = {
    'oracle': {1: 'unique', 1407: 'not-null', 2290: 'check', 2291: 'foreign-key'},
    'postgresql': {'23505': 'unique', '23502': 'not-null', '23514': 'check', '23503': 'foreign-key'},
}


def run_update(connection, lane, sql, expected):
    with connection.cursor() as cursor:
        cursor.execute('SAVEPOINT ly_constraint_probe')
    affected = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            affected = cursor.rowcount
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        status = 'observed-acceptance' if affected == 1 else 'probe-error'
        value = {'status': status, 'affected_rows': affected}
    except Exception as exc:
        code = getattr(exc.args[0], 'code', None) if lane == 'oracle' and exc.args else getattr(exc, 'sqlstate', None)
        error_class = ERRORS[lane].get(code)
        value = {'status': 'observed-rejection' if error_class else 'probe-error',
                 'native_code': code, 'error_class': error_class, 'exception_type': type(exc).__name__}
    finally:
        with connection.cursor() as cursor:
            cursor.execute('ROLLBACK TO ' + ('SAVEPOINT ' if lane == 'postgresql' else '') + 'ly_constraint_probe')
            if lane == 'postgresql': cursor.execute('RELEASE SAVEPOINT ly_constraint_probe')
    passed = (expected == 'accept' and value['status'] == 'observed-acceptance' or
              expected != 'accept' and value['status'] == 'observed-rejection' and value['error_class'] == expected)
    return {'sql': sql, 'sql_sha256': digest(sql), 'expected': expected,
            'outcome': value, 'expectation_met': passed}


def run_lane(connection, lane, *, isolated_test_copy, catalog_sha256):
    require(isolated_test_copy is True, 'Constraint probes require an isolated test copy')
    require(lane in ERRORS, 'Unknown native lane')
    records = []
    try:
        if lane == 'postgresql':
            with connection.cursor() as c: c.execute('BEGIN')
        for table, required, fk, parent in TABLES:
            pk = table + '_id'
            selected = query(connection, f'SELECT {pk} AS id FROM {table} ORDER BY {pk} FETCH FIRST 2 ROWS ONLY')
            if len(selected) < 2:
                records.append({'table': table, 'status': 'not-executed', 'reason': 'Two existing rows required'})
                continue
            first, second = (x['id'] for x in selected)
            require(type(first) is int and type(second) is int and first != second, 'Unexpected primary-key values')
            missing = -2147483647
            require(query(connection, f'SELECT COUNT(*) AS n FROM {parent} WHERE {fk}={missing}')[0]['n'] == 0,
                    'Negative foreign-key control must be absent')
            before = query(connection, f'SELECT * FROM {table} WHERE {pk}={first}')
            cases = [('positive-control', 'isactive=isactive', 'accept'),
                     ('required-column', required+'=NULL', 'not-null'),
                     ('primary-key', pk+'='+str(second), 'unique'),
                     ('foreign-key', fk+'='+str(missing), 'foreign-key'),
                     ('yn-check', "isactive='X'", 'check')]
            for name, assignment, expected in cases:
                result = run_update(connection, lane, f'UPDATE {table} SET {assignment} WHERE {pk}={first}', expected)
                after = query(connection, f'SELECT * FROM {table} WHERE {pk}={first}')
                require(before == after, 'Rollback did not restore the tested row')
                records.append({'table': table, 'case_id': table+'/'+name, 'row_id': first,
                                'before_row_sha256': digest(before), 'after_row_sha256': digest(after), **result})
    finally:
        connection.rollback()
    complete = len(records) == len(TABLES)*5 and all(x.get('expectation_met') for x in records)
    return seal({'artifact_type': 'lightyear-native-schema-constraint-probes', 'lane': lane,
                 'evidence_class': 'native-database-observation', 'independently_attested': False,
                 'observed_at': datetime.now(timezone.utc).isoformat(), 'catalog_sha256': catalog_sha256,
                 'status': 'passed-bounded-constraint-probes' if complete else 'constraint-review-required',
                 'cases': records, 'expected_cases': len(TABLES)*5,
                 'expectations_met': sum(x.get('expectation_met', False) for x in records),
                 'transaction_rolled_back': True, 'schema_equivalence': False, 'application_equivalence': False})
