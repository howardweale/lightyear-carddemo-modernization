"""MS91: versioned rule/ledger register and datatype-bound exact decimals.

Historical judges stay immutable. This register is frozen before generation;
its selectors are materialized against verified native column declarations.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from .contracts import digest, require, seal, verify

VERSION = 'idempiere-declared-purchasing-comparison-v4-ms94'
NUMERIC = 'typed-exact-decimal-no-exponent-v3'
STAMP = 'idempiere-oracle-date-seconds-v1'
DECIMAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)\Z')


def decimal_value(value):
    if isinstance(value, dict):
        require(set(value) == {'decimal'}, 'Unsupported numeric observation wrapper')
        value = value['decimal']
    if type(value) is int:
        value = str(value)
    require(isinstance(value, str) and len(value) <= 256 and DECIMAL.fullmatch(value),
            'Numeric observation must use finite plain decimal notation; exponents refused')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid numeric observation') from exc
    require(result.is_finite(), 'Nonfinite numeric observation')
    return result


def exact_decimal(left, right):
    try:
        return decimal_value(left) == decimal_value(right)
    except ValueError:
        return False


def inventory_columns(inventory):
    verify(inventory)
    require(inventory['artifact_type'] == 'lightyear-native-datatype-mapping-review', 'Wrong datatype inventory')
    records = inventory['columns']
    require(len(records) == inventory['common_column_count'], 'Incomplete datatype inventory')
    columns = {(r['table'], r['column']): r for r in records}
    require(len(columns) == len(records), 'Duplicate datatype column')
    return columns


def numeric_columns(inventory):
    return sorted([list(key) for key, row in inventory_columns(inventory).items()
                   if row['native_declarations']['oracle']['data_type'] == 'NUMBER'
                   and row['native_declarations']['postgresql']['data_type'] in ('numeric', 'decimal')])


def radius(columns, inventory, witnesses=()):
    unique = sorted(set(tuple(x) for x in columns))
    return {'state': 'measured', 'inventory_sha256': inventory['content_sha256'],
            'column_count': len(unique), 'table_count': len({t for t, _ in unique}),
            'columns': [list(x) for x in unique], 'column_set_sha256': digest(unique),
            'retained_witness_count': len(witnesses), 'retained_witness_sha256': digest(list(witnesses)),
            'scope': 'Potential column admission scope; not a prediction of affected runtime rows'}


def make_register(inventory, timestamp_decision, definitions, ledger, *, owner, effective_date, review_date):
    """Materialize selectors; an empty or unmeasured scope cannot be signed."""
    columns = inventory_columns(inventory)
    require(owner and date.fromisoformat(effective_date) < date.fromisoformat(review_date), 'Missing owner/date')
    entries = []
    definitions = [{'id': NUMERIC, 'predicate': 'verified-numeric-column-exact-decimal',
                    'columns': numeric_columns(inventory)},
                   {'id': STAMP, 'predicate': 'owned-oracle-date-whole-second',
                    'columns': [['m_inout', 'shipdate']],
                    'decision_sha256': timestamp_decision['content_sha256']}, *definitions]
    ids = [d['id'] for d in definitions]
    require(len(ids) == len(set(ids)), 'Duplicate rule definition')
    require(all(w['rule'] in ids for w in ledger), 'Ledger has an unregistered rule')
    for definition in definitions:
        selected = definition['columns']
        require(selected and all(tuple(x) in columns for x in selected), 'Empty or invalid rule column scope')
        witnesses = [w for w in ledger if w['rule'] == definition['id']]
        entry = {**definition, 'owner': owner, 'effective_date': effective_date, 'review_date': review_date,
                 'blast_radius': radius(selected, inventory, witnesses)}
        if entry['id'] == STAMP:
            entry.update(owner=timestamp_decision['owner'], effective_date=timestamp_decision['effective_date'],
                         review_date=timestamp_decision['review_date'])
        entries.append(entry)
    return seal({'artifact_type': 'lightyear-comparison-rule-register', 'version': VERSION,
                 'inventory_sha256': inventory['content_sha256'], 'entries': entries,
                 'accepted_difference_ledger': ledger,
                 'metadata_entries': [{'id':'declared-lane-identity','owner':owner,
                     'effective_date':effective_date,'review_date':review_date,
                     'predicate':'oracle-and-postgresql-lane-names',
                     'blast_radius':{'state':'measured','fields':['database'],'field_count':1,
                                     'scope':'Trace metadata only; no database columns admitted'}}],
                 'timestamp_decision': timestamp_decision,
                 'meaning': 'Rule definitions, measured scopes, owners, review dates and retained witnesses in one register'})


def validate_register(register, inventory, assessed_on):
    verify(register)
    require(register['version'] == VERSION and register['inventory_sha256'] == inventory['content_sha256'],
            'Register inventory/version differs')
    columns = inventory_columns(inventory)
    entries = {r['id']: r for r in register['entries']}
    require(len(entries) == len(register['entries']) and NUMERIC in entries and STAMP in entries,
            'Missing or duplicate rules')
    require(entries[NUMERIC]['columns'] == numeric_columns(inventory), 'Numeric rule is not the complete typed inventory')
    require(entries[NUMERIC]['predicate'] == 'verified-numeric-column-exact-decimal', 'Wrong numeric predicate')
    require(entries[STAMP]['columns'] == [['m_inout', 'shipdate']], 'Timestamp scope changed')
    decision = register['timestamp_decision']
    verify({k:v for k,v in decision.items() if k != 'signature'})
    require(decision['id'] == STAMP and decision['decision'] == 'accept-second-level-precision'
            and decision['scope']['columns'] == ['adempiere.m_inout.shipdate']
            and decision['scope']['oracle_datatype'] == 'DATE'
            and decision['scope']['application_source_commit'] == '731515dcdd5278b843db33b9d3109d155b881951',
            'Timestamp decision changed')
    require(entries[STAMP]['decision_sha256'] == decision['content_sha256']
            and all(entries[STAMP][k] == decision[k] for k in ('owner','effective_date','review_date')),
            'Timestamp ownership/decision binding differs')
    for rule in entries.values():
        require(isinstance(rule['owner'], str) and rule['owner'].strip(), 'Rule has no accountable owner')
        require(date.fromisoformat(rule['effective_date']) <= assessed_on < date.fromisoformat(rule['review_date']),
                'Rule is not current: ' + rule['id'])
        require(rule['columns'] and all(tuple(x) in columns for x in rule['columns']), 'Invalid rule scope')
        witnesses = [w for w in register['accepted_difference_ledger'] if w['rule'] == rule['id']]
        require(rule['blast_radius'] == radius(rule['columns'], inventory, witnesses), 'Unmeasured or altered blast radius')
        require(all([w['table'], w['column']] in rule['columns'] for w in witnesses), 'Ledger witness escaped rule scope')
    require(all(w['rule'] in entries for w in register['accepted_difference_ledger']), 'Unregistered ledger entry')
    metadata = register['metadata_entries']
    require(len(metadata)==1 and metadata[0]['id']=='declared-lane-identity'
            and metadata[0]['predicate']=='oracle-and-postgresql-lane-names'
            and metadata[0]['owner'].strip()
            and date.fromisoformat(metadata[0]['effective_date']) <= assessed_on < date.fromisoformat(metadata[0]['review_date'])
            and metadata[0]['blast_radius']=={'state':'measured','fields':['database'],'field_count':1,
                'scope':'Trace metadata only; no database columns admitted'}, 'Invalid metadata admission')
    return entries


def typed_numeric_observation(observation, inventory, snapshots, folders):
    """Require catalog type AND independently captured row provenance, never a field-name heuristic."""
    from .native_reconciliation import rows, keyed, observed_primary_key
    key = (observation['table'], observation['column'])
    column = inventory_columns(inventory).get(key)
    require(column is not None and list(key) in numeric_columns(inventory), 'Observation is not from a numeric column')
    for lane in ('oracle', 'postgresql'):
        source = snapshots[lane]
        verify(source)
        require(source['lane'] == lane and source['evidence_class'] == 'native-database-observation', 'Non-native numeric source')
        require(observation['state_sha256'][lane] == source['content_sha256'], 'Numeric observation state differs')
        native = [r for r in source['structure']['columns']
                  if r['table_name'].lower() == key[0] and r['column_name'].lower() == key[1]]
        require(len(native) == 1 and native[0]['data_type'].lower() == column['native_declarations'][lane]['data_type'].lower(),
                'Numeric declaration changed since frozen inventory')
        records = keyed(rows(folders[lane], source['tables'][key[0]]), observed_primary_key(source, key[0]))
        require(observation['key'] in records and records[observation['key']][key[1]] == observation[lane],
                'Numeric observation differs from independently captured row')
    return exact_decimal(observation['oracle'], observation['postgresql'])
