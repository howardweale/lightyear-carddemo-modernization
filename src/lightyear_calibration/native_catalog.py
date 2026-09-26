"""Native schema observations and a conservative projection for the static gate.

This captures metadata, not migration effects or an independent attestation.
Every query must succeed; a permission error is never an empty catalog.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import gzip
from pathlib import Path

from .contracts import canonical, digest, require, seal, verify


def read_capture(path):
    """Raw catalogs can exceed the small report limit; still bound decompression."""
    path = Path(path)
    opener = gzip.open if path.suffix == '.gz' else open
    maximum = 256 * 1024 * 1024
    with opener(path, 'rb') as handle:
        data = handle.read(maximum + 1)
    require(len(data) <= maximum, 'Catalog exceeds 256 MiB')
    def pairs(items):
        result = {}
        for k,v in items:
            require(k not in result, 'Duplicate catalog key')
            result[k] = v
        return result
    def invalid(value):
        raise ValueError('Nonfinite catalog value')
    result = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    verify(result)
    return result

ORACLE_QUERIES = {
    'identity': "SELECT sys_context('USERENV','DB_NAME') db_name, sys_context('USERENV','CON_NAME') container_name, sys_context('USERENV','SESSION_USER') session_user, sys_context('USERENV','CURRENT_SCHEMA') current_schema, sessiontimezone time_zone FROM dual",
    'version': "SELECT banner_full FROM v$version",
    'nls_session': "SELECT parameter,value FROM nls_session_parameters",
    'nls_database': "SELECT parameter,value FROM nls_database_parameters",
    'objects': "SELECT object_name,object_type,status FROM user_objects",
    'tables': "SELECT * FROM user_tables",
    'columns': "SELECT * FROM user_tab_cols",
    'constraints': "SELECT * FROM user_constraints",
    'constraint_columns': "SELECT * FROM user_cons_columns",
    'triggers': "SELECT * FROM user_triggers",
    'indexes': "SELECT * FROM user_indexes",
    'index_columns': "SELECT * FROM user_ind_columns",
    'index_expressions': "SELECT * FROM user_ind_expressions",
    'views': "SELECT * FROM user_views",
    'materialized_views': "SELECT * FROM user_mviews",
    'materialized_view_logs': "SELECT * FROM user_mview_logs",
    'routines': "SELECT * FROM user_source",
    'sequences': "SELECT * FROM user_sequences",
    'synonyms': "SELECT * FROM user_synonyms",
    'dependencies': "SELECT * FROM user_dependencies",
    'policies': "SELECT * FROM all_policies WHERE object_owner=sys_context('USERENV','CURRENT_SCHEMA')",
    'privileges': "SELECT * FROM user_tab_privs",
    'role_privileges': "SELECT * FROM user_role_privs",
    'system_privileges': "SELECT * FROM user_sys_privs",
    'errors': "SELECT * FROM user_errors",
    'migration_register': "SELECT name,filename,status,isapply FROM ad_migrationscript",
}

PG_QUERIES = {
    'identity': "SELECT current_database() db_name,current_user session_user,current_schema() current_schema,current_schemas(true) effective_search_path",
    'version': "SELECT version() version",
    'settings': "SELECT name,setting,unit,source FROM pg_settings",
    'database': "SELECT datname,encoding,datcollate,datctype FROM pg_database WHERE datname=current_database()",
    'objects': "SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='adempiere'",
    'tables': "SELECT * FROM information_schema.tables WHERE table_schema='adempiere'",
    'columns': "SELECT * FROM information_schema.columns WHERE table_schema='adempiere'",
    'attributes': "SELECT a.* FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='adempiere'",
    'constraints': "SELECT con.*, c.relname table_name, pg_get_constraintdef(con.oid) definition FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace LEFT JOIN pg_class c ON c.oid=con.conrelid WHERE n.nspname='adempiere'",
    'triggers': "SELECT t.*,c.relname table_name,pg_get_triggerdef(t.oid) definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='adempiere'",
    'indexes': "SELECT * FROM pg_indexes WHERE schemaname='adempiere'",
    'views': "SELECT * FROM pg_views WHERE schemaname='adempiere'",
    'materialized_views': "SELECT * FROM pg_matviews WHERE schemaname='adempiere'",
    'routines': "SELECT p.*,pg_get_functiondef(p.oid) definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='adempiere' AND p.prokind<>'a'",
    'sequences': "SELECT * FROM pg_sequences WHERE schemaname='adempiere'",
    'types': "SELECT t.* FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='adempiere'",
    'dependencies': "SELECT d.* FROM pg_depend d WHERE (d.classid='pg_class'::regclass AND d.objid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='adempiere')) OR (d.refclassid='pg_class'::regclass AND d.refobjid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='adempiere'))",
    'policies': "SELECT * FROM pg_policies WHERE schemaname='adempiere'",
    'rules': "SELECT * FROM pg_rules WHERE schemaname='adempiere'",
    'privileges': "SELECT * FROM information_schema.table_privileges WHERE table_schema='adempiere'",
    'migration_register': "SELECT name,filename,status,isapply FROM adempiere.ad_migrationscript",
}


def json_value(value):
    if hasattr(value, 'read'):
        value = value.read()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else {'decimal': str(value)}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'hex': bytes(value).hex()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_value(v) for k,v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def query(connection, sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        names = [d[0].lower() for d in cursor.description]
        require(len(names) == len(set(names)), 'Duplicate query column')
        rows = []
        while batch := cursor.fetchmany(1000):
            rows.extend(dict(zip(names, map(json_value, row))) for row in batch)
            require(len(rows) <= 1000000, 'Catalog query exceeded row bound')
        return sorted(rows, key=canonical)


def capture(connection, lane, import_binding):
    require(lane in ('oracle','postgresql'), 'Unknown catalog lane')
    queries = ORACLE_QUERIES if lane == 'oracle' else PG_QUERIES
    results = {name: {'sql_sha256': hashlib.sha256(sql.encode()).hexdigest(),
                      'rows': query(connection, sql)} for name,sql in queries.items()}
    identity = results['identity']['rows']
    require(len(identity) == 1 and identity[0]['current_schema'].lower() == 'adempiere', 'Wrong capture schema')
    if lane == 'oracle':
        require(identity[0]['session_user'] == identity[0]['current_schema'], 'Oracle USER catalogs require schema owner session')
    require(results['tables']['rows'], 'Empty schema is not an imported estate')
    return seal({'schema_version':'1.0','artifact_type':'lightyear-native-schema-capture',
                 'lane':lane,'observed_at':datetime.now(timezone.utc).isoformat(),
                 'evidence_class':'native-catalog-observation','independently_attested':False,
                 'import_binding':import_binding,'query_set_sha256':digest(queries),
                 'results':results,'query_errors':[], 'migration_execution_claim':False})


def project_capture(snapshot):
    verify(snapshot)
    lane = snapshot['lane']
    require(lane in ('oracle','postgresql'), 'Unknown catalog lane')
    require(snapshot['evidence_class']=='native-catalog-observation', 'Not a native catalog observation')
    queries = ORACLE_QUERIES if lane == 'oracle' else PG_QUERIES
    require(snapshot['query_set_sha256'] == digest(queries), 'Catalog collector changed')
    require(not snapshot['query_errors'] and set(snapshot['results']) == set(queries), 'Incomplete catalog capture')
    for key,sql in queries.items():
        require(snapshot['results'][key]['sql_sha256'] == hashlib.sha256(sql.encode()).hexdigest(), 'Catalog query mismatch')
    r = {k:v['rows'] for k,v in snapshot['results'].items()}
    identity = r['identity'][0]
    schema = identity['current_schema']
    tables = {}
    table_rows = [(row, 'base-table' if lane=='oracle' or row['table_type']=='BASE TABLE' else 'view') for row in r['tables']]
    if lane=='oracle':
        table_rows += [({'table_name':row['view_name']}, 'view') for row in r['views']]
    for row,kind in table_rows:
        name = row['table_name']
        # Preserve quoted/case-sensitive names as unsupported to avoid aliases.
        if not re.fullmatch(r'[A-Z][A-Z0-9_$#]*' if lane=='oracle' else r'[a-z_][a-z_0-9]*', name):
            continue
        key = name.lower() if lane == 'oracle' and name.upper() == name else name
        require(key not in tables, 'Colliding catalog names')
        tables[key] = {'kind':kind,
                       'complete':True,'columns':{},'triggers':[], 'constraints':[], 'row_policies':[], 'rewrite_rules':[]}
    for row in r['columns']:
        name = row['table_name'].lower() if lane == 'oracle' else row['table_name']
        if name not in tables:
            continue
        col = row['column_name'].lower() if lane == 'oracle' else row['column_name']
        if lane=='oracle' and row['column_name'] != row['column_name'].upper() or lane=='postgresql' and row['column_name'] != col.lower():
            tables[name]['complete'] = False
        precision = row.get('data_precision') if lane == 'oracle' else row.get('numeric_precision')
        scale = row.get('data_scale') if lane == 'oracle' else row.get('numeric_scale')
        numeric = row['data_type'] == ('NUMBER' if lane == 'oracle' else 'numeric')
        domain = None
        if numeric and type(precision) is int and type(scale) is int and 1<=precision<=38 and 0<=scale<=precision:
            domain = {'canonical_type':'exact-decimal','precision':precision,'scale':scale}
        tables[name]['columns'][col] = {'type':domain,'nullable':row['nullable']=='Y' if lane=='oracle' else row['is_nullable']=='YES'}
        if row.get('virtual_column')=='YES' or row.get('identity_column')=='YES' or row.get('is_generated')=='ALWAYS' or row.get('is_identity')=='YES':
            tables[name]['constraints'].append({'generated_or_identity_column':col})
    for raw, dest, table_field in [('triggers','triggers','table_name'), ('constraints','constraints','table_name'),
                                  ('policies','row_policies','object_name' if lane=='oracle' else 'tablename')]:
        for row in r[raw]:
            key = row.get(table_field)
            key = key.lower() if key and lane=='oracle' else key
            if key in tables:
                # The bounded gate only needs absence/presence here. Keep full
                # definitions in the immutable raw capture instead of duplicating
                # large bodies into every case that references the same table.
                tables[key][dest].append({'capture_row_sha256':digest(row)})
    if lane == 'postgresql':
        for row in r['rules']:
            if row['tablename'] in tables: tables[row['tablename']]['rewrite_rules'].append({'capture_row_sha256':digest(row)})
        # RLS enabled with no policies still blocks DML; empty policy list does
        # not mean absence of security behavior.
        for row in r['objects']:
            if row['relname'] in tables and (row['relrowsecurity'] or row['relforcerowsecurity']):
                tables[row['relname']]['row_policies'].append({'rls_enabled':True})
        settings = {row['name']:row['setting'] for row in r['settings']}
        session = {'current_schema':schema,'search_path':[x.strip().strip('"') for x in settings['search_path'].split(',')],
                   'numeric_characters':None,'standard_conforming_strings':settings['standard_conforming_strings']=='on',
                   'time_zone':settings['TimeZone']}
    else:
        for row in r['materialized_view_logs']:
            if row['master'].lower() in tables: tables[row['master'].lower()]['rewrite_rules'].append({'capture_row_sha256':digest(row)})
        settings = {row['parameter']:row['value'] for row in r['nls_session']}
        session = {'current_schema':schema,'search_path':None,'numeric_characters':settings['NLS_NUMERIC_CHARACTERS'],
                   'standard_conforming_strings':None,'time_zone':identity['time_zone']}
    return {'session':session,'tables':tables}


def context_from_captures(template, snapshots):
    """Apply one observed baseline conditionally, never assert historical entry states."""
    require(set(snapshots)=={'oracle','postgresql'}, 'Both native catalogs required')
    context = deepcopy(template)
    facts = {lane:project_capture(snapshot) for lane,snapshot in snapshots.items()}
    context['evidence'] = {'mode':'captured-catalog','references':[
        {'path':lane+'-catalog.json','sha256':snapshot['content_sha256']} for lane,snapshot in sorted(snapshots.items())]}
    for case in context['cases'].values():
        for lane,entry in case['lanes'].items():
            entry['session'] = deepcopy(facts[lane]['session'])
            # Missing objects remain incomplete template entries. Capture full
            # columns for present objects; omitted defaults cannot be inferred.
            for table in list(entry['tables']):
                if table in facts[lane]['tables']:
                    entry['tables'][table] = deepcopy(facts[lane]['tables'][table])
    return context
