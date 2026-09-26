"""Narrow, witnessed native comparison rules; raw observations remain unchanged.

Admission is for logical data under this explicit policy, never full application
or structural equivalence. A prior admitted difference can only be carried
forward while its exact two observed values remain unchanged.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
import gzip
import hashlib
import json
from pathlib import Path
import uuid

from .contracts import canonical, digest, read_json, require, seal, verify

POLICY = {
    'version': 'idempiere-native-reconciliation-v1',
    'uuid_columns': {'ad_migrationscript': 'ad_migrationscript_uu', 'ad_treenodemm': 'ad_treenodemm_uu'},
    'runtime_clock_columns': {'ad_migrationscript': ['created', 'updated'], 'ad_treenodemm': ['created', 'updated']},
    'utc_type_projection': {'ad_scheduler': ['datenextrun']},
    'engine_only_tables': {'oracle': ['create$java$lob$table', 'java$class$md5$table'], 'postgresql': ['t_alter_column']},
    'scope': 'logical base-table data under explicit rules; no schema or application equivalence claim',
}

HISTORY_BASE_POLICY = {**POLICY, 'version': 'idempiere-native-reconciliation-v2-history31',
                  'existing_updated_columns': ['ad_treenodemm'],
                  'engine_only_tables': {**POLICY['engine_only_tables'], 'postgresql': ['dual', 't_alter_column']}}

HISTORY_V3_POLICY = {**HISTORY_BASE_POLICY, 'version': 'idempiere-native-reconciliation-v3-history31',
                  'existing_updated_columns': ['ad_treenodemm', 'ad_field'],
                  'runtime_clock_columns': {**POLICY['runtime_clock_columns'], 'ad_field': ['updated']}}

HISTORY_V4_POLICY = {**HISTORY_V3_POLICY, 'version': 'idempiere-native-reconciliation-v4-history31',
                  'uuid_columns': {**POLICY['uuid_columns'], 'ad_message_trl': 'ad_message_trl_uu'},
                  'runtime_clock_columns': {**HISTORY_V3_POLICY['runtime_clock_columns'], 'ad_message_trl': ['created', 'updated']}}

HISTORY_V5_POLICY = {**HISTORY_V4_POLICY, 'version': 'idempiere-native-reconciliation-v5-history31',
                  'uuid_columns': {**HISTORY_V4_POLICY['uuid_columns'], **{t: t+'_uu' for t in
                      ('ad_column_trl','ad_element_trl','ad_field_trl','ad_menu_trl','ad_tab_trl','ad_table_trl','ad_window_trl')}}}

HISTORY_V6_POLICY = {**HISTORY_V5_POLICY, 'version': 'idempiere-native-reconciliation-v6-history31',
                  'uuid_columns': {**HISTORY_V5_POLICY['uuid_columns'], 'c_charge_acct': 'c_charge_acct_uu'},
                  'runtime_clock_columns': {**HISTORY_V5_POLICY['runtime_clock_columns'], 'c_charge_acct': ['created']},
                  'exact_native_decimal_values': True, 'witnessed_registration_reapplications': True}

HISTORY_ACCOUNT_CLOCK_TABLES = ('c_bankaccount_acct','c_bp_customer_acct','c_bp_group_acct','c_bp_vendor_acct',
    'c_cashbook_acct','c_project_acct','c_tax_acct','m_product_acct','m_product_category_acct','m_warehouse_acct',
    'ad_treebar','ad_treenodepr')
HISTORY_V7_POLICY = {**HISTORY_V6_POLICY, 'version': 'idempiere-native-reconciliation-v7-history31',
    'runtime_clock_columns': {**HISTORY_V6_POLICY['runtime_clock_columns'],
        **{t:['created','updated'] for t in HISTORY_ACCOUNT_CLOCK_TABLES}, 'c_charge_acct':['created','updated']},
    'existing_updated_columns': [*HISTORY_V6_POLICY['existing_updated_columns'], 'c_charge_acct']}
HISTORY_V8_POLICY = {**HISTORY_V7_POLICY, 'version': 'idempiere-native-reconciliation-v8-history31',
    'runtime_clock_columns': {**HISTORY_V7_POLICY['runtime_clock_columns'], 'ad_column':['updated']},
    'existing_updated_columns': [*HISTORY_V7_POLICY['existing_updated_columns'], 'ad_column']}
HISTORY_V9_POLICY = {**HISTORY_V8_POLICY, 'version':'idempiere-native-reconciliation-v9-history31',
    'uuid_columns':{**HISTORY_V8_POLICY['uuid_columns'], **{t:t+'_uu' for t in ('ad_treenodebp','c_bp_customer_acct','c_bp_vendor_acct')}},
    'runtime_clock_columns':{**HISTORY_V8_POLICY['runtime_clock_columns'], 'ad_treenodebp':['created','updated']}}
HISTORY_V10_POLICY = {**HISTORY_V9_POLICY, 'version':'idempiere-native-reconciliation-v10-history31',
    'runtime_clock_columns':{**HISTORY_V9_POLICY['runtime_clock_columns'],'ad_printformatitem':['updated']},
    'existing_updated_columns':[*HISTORY_V9_POLICY['existing_updated_columns'],'ad_printformatitem']}
HISTORY_POLICY = {**HISTORY_V10_POLICY,'version':'idempiere-native-reconciliation-v11-history31','allow_constant_dual_view':True,'paired_registration_names':True}





# Upstream translation/role maintenance creates these metadata rows and updates
# the two named terminology tables. Business values and all other fields remain
# exact. Each exception still needs native execution-window / UUID validation.
MAINTENANCE_TABLES = ('ad_column_trl', 'ad_element_trl', 'ad_field_trl', 'ad_message_trl',
    'ad_ref_list_trl', 'ad_menu_trl', 'ad_tab_trl', 'ad_table_trl', 'ad_window_trl',
    'ad_process_para_trl', 'ad_process_trl', 'ad_reference_trl', 'r_mailtext_trl',
    'c_currency_trl', 'ad_window_access', 'ad_process_access')
MAINTENANCE_POLICY = {**POLICY, 'version': 'idempiere-native-reconciliation-v1-maintenance',
    'uuid_columns': {**POLICY['uuid_columns'], **{t:t+'_uu' for t in MAINTENANCE_TABLES}},
    'runtime_clock_columns': {**POLICY['runtime_clock_columns'], **{t:['created','updated'] for t in MAINTENANCE_TABLES}, 'ad_field':['updated']},
    'existing_updated_columns': ['ad_field', 'ad_field_trl']}


def state(folder, lane):
    value = read_json(Path(folder) / 'state.json'); verify(value)
    require(value['lane'] == lane and value['evidence_class'] == 'native-database-observation', 'Wrong native state lane/class')
    return value


def rows(folder, entry):
    path = (Path(folder) / entry['raw_file']).resolve()
    require(path.is_relative_to(Path(folder).resolve()), 'Row file escapes snapshot')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == entry['raw_file_sha256'], 'Raw rows changed')
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        result = [json.loads(line) for line in handle]
    require(len(result) == entry['rows'], 'Row count mismatch')
    require(dict(Counter(digest(row) for row in result)) == entry['row_multiset'], 'Row multiset mismatch')
    return result


def keyed(records, columns):
    require(bool(columns), 'No observed primary key for differing table')
    require(all(all(k in row and row[k] is not None for k in columns) for row in records), 'Incomplete primary key')
    result = {canonical([row[k] for k in columns]).decode(): row for row in records}
    require(len(result) == len(records), 'Duplicate primary key')
    return result


def observed_primary_key(snapshot, table):
    """Read a conservative key from the captured native catalog, or refuse."""
    structure = snapshot['structure']
    constraints = [c for c in structure.get('constraints', []) if c['table_name'].lower() == table]
    if snapshot['lane'] == 'postgresql':
        definitions = [c['definition'] for c in constraints if c.get('definition', '').startswith('PRIMARY KEY (')]
        if len(definitions) != 1:return None
        match = re.fullmatch(r'PRIMARY KEY \(([a-z0-9_, ]+)\)', definitions[0])
        return [v.strip() for v in match[1].split(',')] if match else None
    primary = [c for c in constraints if c.get('constraint_type') == 'P']
    if len(primary) != 1:return None
    columns = sorted([c for c in structure.get('index_columns', [])
                      if c['table_name'].lower() == table and c['index_name'] == primary[0]['constraint_name']],
                     key=lambda c:c['column_position'])
    return [c['column_name'].lower() for c in columns] or None


def utc(value):
    require(isinstance(value, str), 'Timestamp must be a native observed string')
    result = datetime.fromisoformat(value)
    return (result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc))


def valid_uuid(value):
    try:
        parsed = uuid.UUID(value)
        return str(parsed) == value.lower() and parsed.int != 0
    except (ValueError, TypeError, AttributeError):
        return False


def exact_decimal(left, right):
    if not all(isinstance(v, dict) and set(v) == {'decimal'} and isinstance(v['decimal'], str) for v in (left, right)):
        return False
    try:
        a, b = Decimal(left['decimal']), Decimal(right['decimal'])
        return a.is_finite() and b.is_finite() and a == b
    except InvalidOperation:
        return False


def reapplication_rule(column, left, right, old_rows, proof):
    """Validate lane-specific audit effects; never rewrite a registration ledger."""
    if column not in {'description', 'updated'} or set(old_rows) != {'oracle', 'postgresql'}:
        return False
    verify(proof)
    name = proof['script']
    require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+\.sql', name)), 'Invalid audit script name')
    require(set(proof['calls']) == set(old_rows), 'Both audit lanes required')
    require(proof['native_function_contract'] == 'coalesce-description-space-append-reapplied-and-update-clock', 'Unknown registration contract')
    statement = "SELECT register_migration_script('"+name+"') FROM dual"
    expected_hash = hashlib.sha256(statement.encode()).hexdigest()
    require(all(row.get('name') == name and row.get('status') == 'CO' and row.get('isapply') == 'Y' for row in old_rows.values()), 'Reapplication requires an applied prior registration')
    if not any(proof['calls'].values()):
        return False
    for lane, value in [('oracle', left), ('postgresql', right)]:
        calls = proof['calls'][lane]
        if not calls:
            if value != old_rows[lane].get(column):return False
            continue
        require(len({c['started_at'] for c in calls}) == len(calls), 'Duplicate registration call witness')
        require(all(c['statement_sha256'] == expected_hash and c['function_return'] == name+' was already applied' for c in calls), 'Wrong registration call witness')
        if column == 'description':
            old = old_rows[lane].get(column)
            expected = (old if old is not None else ' ') + ' reapplied' * len(calls)
            if value != expected:return False
        else:
            last = max(calls, key=lambda c: utc(c['started_at']))
            start = utc(last['started_at'])
            if lane == 'oracle':start = start.replace(microsecond=0)
            if not start <= utc(value) <= utc(last['finished_at']):return False
    return True


def field_rule(table, column, left, right, row_left, row_right, *, script, windows,
               new_row, unique_uuid=False, utc_column_verified=False, policy=POLICY, script_names=None):
    """Return a named rule, or None. Unknown differences never become passes."""
    if column in POLICY['utc_type_projection'].get(table, []) and utc_column_verified:
        if (left is not None and right is not None and datetime.fromisoformat(left).tzinfo is not None
                and datetime.fromisoformat(right).tzinfo is not None and utc(left) == utc(right)):
            return 'native-timestamptz-same-instant'
    if not new_row and not (column == 'updated' and table in policy.get('existing_updated_columns', [])):
        return None
    if (table == 'ad_migrationscript' and column in {'name','filename'} and script_names
            and policy.get('paired_registration_names') and set(script_names)=={'oracle','postgresql'}):
        if (all(isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_.-]+\.sql',v) for v in script_names.values())
                and script == script_names['oracle']
                and all(row.get('name')==script_names[lane] and row.get('filename')==lane+'/'+script_names[lane]
                        and row.get('status')=='CO' and row.get('isapply')=='Y'
                        for lane,row in [('oracle',row_left),('postgresql',row_right)])):
            expected={lane:(name if column=='name' else lane+'/'+name) for lane,name in script_names.items()}
            if left==expected['oracle'] and right==expected['postgresql']:
                return 'paired-executed-registration-name-or-path'
    if table == 'ad_migrationscript' and column == 'filename' and script:
        if (row_left.get('name') == row_right.get('name') == script and
                all(r.get('status') == 'CO' and r.get('isapply') == 'Y' for r in (row_left, row_right)) and
                left == 'oracle/' + script and right == 'postgresql/' + script):
            return 'engine-registration-path'
    if new_row and policy['uuid_columns'].get(table) == column and unique_uuid and valid_uuid(left) and valid_uuid(right):
        return 'fresh-unique-generated-UUID'
    if column in policy['runtime_clock_columns'].get(table, []) and windows:
        if all((utc(windows[lane]['started_at']).replace(microsecond=0) if lane == 'oracle' else utc(windows[lane]['started_at'])) <= utc(value) <= utc(windows[lane]['finished_at'])
               for lane, value in [('oracle', left), ('postgresql', right)]):
            return 'timestamp-within-recorded-native-execution'
    return None


def reconcile(folders, primary_keys, *, before=None, prior=None, script=None, windows=None, utc_columns=(), policy=POLICY, executions=None, reapplications=None):
    require(policy in (POLICY, HISTORY_POLICY, MAINTENANCE_POLICY), 'Unknown reconciliation policy')
    require(set(folders) == {'oracle', 'postgresql'}, 'Both lanes required')
    require(before is None or set(before) == set(folders), 'Both before lanes required')
    if executions is not None:
        require(all(set(v) == set(folders) and all(e['returncode'] == 0 for e in v.values()) for v in executions.values()), 'Unsuccessful batch execution')
    snapshots = {lane: state(folder, lane) for lane, folder in folders.items()}
    previous = {}
    if prior:
        verify(prior)
        accepted_prior_policies = {digest(policy)}
        if policy == HISTORY_POLICY:
            accepted_prior_policies.update({digest(HISTORY_BASE_POLICY), digest(HISTORY_V3_POLICY), digest(HISTORY_V4_POLICY), digest(HISTORY_V5_POLICY), digest(HISTORY_V6_POLICY), digest(HISTORY_V7_POLICY), digest(HISTORY_V8_POLICY), digest(HISTORY_V9_POLICY), digest(HISTORY_V10_POLICY)})
        if policy == MAINTENANCE_POLICY:
            accepted_prior_policies.add(digest(POLICY))  # Fixed, explicit extension of the prior rules.
        require(prior['admitted'] and prior['policy_sha256'] in accepted_prior_policies, 'Unadmitted or changed prior policy')
        require(before is not None, 'Prior witnesses require bound before states')
        require(prior['state_sha256'] == {lane: state(folder, lane)['content_sha256'] for lane, folder in before.items()}, 'Prior checkpoint differs from before states')
        previous = {(v['table'], v['key'], v['column']): v for v in prior['allowed_differences']}
    a, b = snapshots['oracle'], snapshots['postgresql']
    require(a.get('row_query_contract') == b.get('row_query_contract'), 'Mixed row observation contracts')
    common = set(a['tables']) & set(b['tables'])
    blocked = []; allowed = []; exact = 0
    dual_views=[v for v in b['structure'].get('views',[]) if v.get('viewname')=='dual']
    constant_dual_view=bool(policy.get('allow_constant_dual_view') and 'dual' not in b['tables']
        and len(dual_views)==1 and re.fullmatch(r"SELECT 'X'::character varying AS dummy;",dual_views[0]['definition'].strip()))
    for lane, other in [('oracle', 'postgresql'), ('postgresql', 'oracle')]:
        extra = set(snapshots[lane]['tables']) - set(snapshots[other]['tables'])
        expected_extra=set(policy['engine_only_tables'][lane])
        if lane=='postgresql' and constant_dual_view:expected_extra.discard('dual')
        if extra != expected_extra:
            blocked.append({'reason': 'unexpected-engine-only-tables', 'lane': lane, 'tables': sorted(extra)})
    if b['tables'].get('t_alter_column', {}).get('rows') != 0:
        blocked.append({'reason': 'PostgreSQL-DDL-helper-not-empty'})
    if 'dual' in policy['engine_only_tables']['postgresql'] and not constant_dual_view:
        if b['tables'].get('dual', {}).get('row_multiset') != {digest({'dummy':'X'}): 1}:
            blocked.append({'reason': 'PostgreSQL-DUAL-helper-must-match-native-Oracle-DUAL'})
    old_states = {lane: state(folder, lane) for lane, folder in before.items()} if before else {}
    require(all(value.get('row_query_contract') == snapshots[lane].get('row_query_contract') for lane, value in old_states.items()), 'Changed row observation contract')
    column_sets = {}
    column_types = {}
    for lane, value in snapshots.items():
        column_sets[lane] = defaultdict(set)
        column_types[lane] = {}
        for column in value['structure']['columns']:
            column_sets[lane][column['table_name'].lower()].add(column['column_name'].lower())
            column_types[lane][(column['table_name'].lower(), column['column_name'].lower())] = column.get('data_type', '').lower()
    for table in sorted(common):
        if column_sets['oracle'][table] != column_sets['postgresql'][table]:
            blocked.append({'table': table, 'reason': 'column-set-difference'}); continue
        if a['tables'][table]['row_multiset'] == b['tables'][table]['row_multiset']:
            exact += 1; continue
        require(primary_keys['oracle'].get(table) == primary_keys['postgresql'].get(table), 'Primary keys differ')
        key_columns = primary_keys['oracle'].get(table)
        records = {lane: rows(folder, snapshots[lane]['tables'][table]) for lane, folder in folders.items()}
        maps = {lane: keyed(value, key_columns) for lane, value in records.items()}
        old_maps = {lane: keyed(rows(before[lane], value['tables'][table]), key_columns) if table in value['tables'] else {}
                    for lane, value in old_states.items()}
        if set(maps['oracle']) != set(maps['postgresql']):
            blocked.append({'table': table, 'reason': 'different-row-keys'}); continue
        for key, left_row in maps['oracle'].items():
            right_row = maps['postgresql'][key]
            if set(left_row) != set(right_row):
                blocked.append({'table': table, 'key': key, 'reason': 'different-row-columns'}); continue
            for column, left in left_row.items():
                right = right_row[column]
                if canonical(left) == canonical(right): continue
                witness = {'table': table, 'key': key, 'column': column, 'oracle': left, 'postgresql': right}
                prev = previous.get((table, key, column))
                if not prev and prior and all(key in old_maps.get(lane, {}) for lane in folders):
                    old_keys = {lane:observed_primary_key(value, table) for lane,value in old_states.items()}
                    old_key_columns = old_keys.get('oracle')
                    if (old_key_columns and old_key_columns == old_keys.get('postgresql')
                            and set(old_key_columns) <= set(key_columns)):
                        old_key_values = {lane:canonical([old_maps[lane][key][c] for c in old_key_columns]).decode() for lane in folders}
                        if old_key_values['oracle'] == old_key_values['postgresql']:
                            old_key = old_key_values['oracle']
                            candidate = previous.get((table, old_key, column))
                            if candidate and all(canonical(candidate[lane]) == canonical(old_maps[lane][key][column]) for lane in folders):
                                prev = {**candidate, 'key':key, 'previous_key':old_key,
                                        'previous_checkpoint_sha256':prior['content_sha256'],
                                        'previous_primary_key_columns':old_key_columns}
                if prev and canonical(prev['oracle']) == canonical(left) and canonical(prev['postgresql']) == canonical(right):
                    allowed.append(prev); continue
                if (policy.get('exact_native_decimal_values') and column_types['oracle'].get((table,column)) == 'number'
                        and column_types['postgresql'].get((table,column)) in {'numeric','decimal'} and exact_decimal(left,right)):
                    allowed.append({**witness,'rule':'exact-native-decimal-value','native_types':{'oracle':'NUMBER','postgresql':column_types['postgresql'][(table,column)]}});continue
                if table == 'ad_migrationscript' and policy.get('witnessed_registration_reapplications') and reapplications:
                    proof = reapplications.get(left_row.get('name'))
                    if proof:
                        require(left_row.get('name') == right_row.get('name') == proof['script'], 'Audit names differ')
                        require(proof['before_state_sha256'] == {lane:v['content_sha256'] for lane,v in old_states.items()}, 'Audit proof differs from before states')
                        old_rows = {lane:values[key] for lane,values in old_maps.items() if key in values}
                        if reapplication_rule(column,left,right,old_rows,proof):
                            allowed.append({**witness,'rule':'native-registration-reapplication-audit','audit_proof':proof});continue
                new_row = bool(old_maps) and all(key not in value for value in old_maps.values())
                unique = all(sum(row.get(column) == val for row in records[lane]) == 1
                             and all(row.get(column) != val for row in old_maps.get(lane, {}).values())
                             for lane, val in [('oracle', left), ('postgresql', right)])
                field_script, field_windows = script, windows
                script_names=None
                if table == 'ad_migrationscript' and executions is not None:
                    field_script = left_row.get('name')
                    field_windows = executions.get(field_script)
                    if field_windows and all('source_path' in v for v in field_windows.values()):
                        script_names={lane:Path(v['source_path']).name for lane,v in field_windows.items()}
                    if field_windows is None:
                        blocked.append({**witness, 'reason': 'registration-not-bound-to-executed-script'}); continue
                rule = field_rule(table, column, left, right, left_row, right_row, script=field_script,
                                  windows=field_windows, new_row=new_row, unique_uuid=unique,
                                  utc_column_verified=((table, column) in utc_columns or
                                      (a.get('row_query_contract')=='all-columns-v2-preserve-native-timezone-offsets'
                                       and bool(re.fullmatch(r'timestamp(?:\(\d+\))? with time zone',column_types['oracle'].get((table,column),'')))
                                       and column_types['postgresql'].get((table,column))=='timestamp with time zone')),
                                  policy=policy, script_names=script_names)
                if rule: allowed.append({**witness, 'rule': rule, 'script': field_script, 'execution_windows': field_windows})
                else: blocked.append({**witness, 'reason': 'unapproved-or-invalid-field-difference'})
    return seal({'artifact_type': 'lightyear-native-logical-checkpoint', 'policy_sha256': digest(policy),
                 'state_sha256': {lane: value['content_sha256'] for lane, value in snapshots.items()},
                 'common_table_count': len(common), 'exact_table_count': exact,
                 'allowed_differences': allowed, 'unresolved_differences': blocked, 'admitted': not blocked,
                 'scope': policy['scope'], 'application_equivalence': False, 'schema_equivalence': False})
