"""Source-bound native schema assessment with explicit unresolved obligations.

Catalog equality is one layer of evidence. Dialect-specific types, executable
objects and privileges cannot acquire a behavioral equivalence claim from names
or current row equality. This module deliberately reports that remaining work.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import json
import re

from .contracts import canonical, digest, require, seal
from .native_catalog import project_capture, read_capture

LANES = ('oracle', 'postgresql')


def identifier(value, lane):
    require(isinstance(value, str), 'Missing native identifier')
    pattern = r'[A-Z][A-Z0-9_$#]*' if lane == 'oracle' else r'[a-z_][a-z_0-9$]*'
    require(re.fullmatch(pattern, value) is not None, 'Quoted or ambiguous identifier requires an explicit mapping')
    return value.lower()


def keyed(rows, key):
    result = {}
    for row in rows:
        name = key(row)
        require(name not in result, 'Duplicate native object identity')
        result[name] = row
    return result


def rows(capture):
    project_capture(capture)  # Verify seal, collector/query identity and completeness.
    native = {name: item['rows'] for name, item in capture['results'].items()}
    require(len(native['identity']) == 1 and native['tables'], 'Missing identity or empty imported schema')
    return native


def relation_map(native, lane):
    if lane == 'oracle':
        return keyed(native['tables'], lambda x: identifier(x['table_name'], lane))
    return keyed((x for x in native['tables'] if x['table_type'] == 'BASE TABLE'),
                 lambda x: identifier(x['table_name'], lane))


def column_map(native, lane, tables):
    selected = [x for x in native['columns'] if identifier(x['table_name'], lane) in tables
                and x.get('hidden_column') != 'YES']
    return keyed(selected, lambda x: (identifier(x['table_name'], lane), identifier(x['column_name'], lane)))


def declaration(row, lane):
    """Compare bounded declared domains; broader value semantics stay obligations."""
    typ = row['data_type']
    if lane == 'oracle':
        if typ == 'NUMBER':
            return ('decimal', row.get('data_precision'), row.get('data_scale'))
        if typ in ('VARCHAR2', 'CHAR'):
            return ('varying-text' if typ == 'VARCHAR2' else 'fixed-text',
                    row.get('char_length'), row.get('char_used'))
        if typ == 'DATE':
            return ('local-timestamp', 0)
        if typ == 'TIMESTAMP(6) WITH TIME ZONE':
            return ('offset-timestamp', 6)
    else:
        if typ == 'numeric':
            return ('decimal', row.get('numeric_precision'), row.get('numeric_scale'))
        if typ in ('character varying', 'character'):
            return ('varying-text' if typ == 'character varying' else 'fixed-text',
                    row.get('character_maximum_length'), 'C')
        if typ == 'timestamp without time zone':
            return ('local-timestamp', row.get('datetime_precision'))
        if typ == 'timestamp with time zone':
            return ('offset-timestamp', row.get('datetime_precision'))
    return ('native-type', lane, typ)


def column_contract(row, lane):
    oracle = lane == 'oracle'
    return {
        'declaration': declaration(row, lane),
        'nullable': row['nullable'] == 'Y' if oracle else row['is_nullable'] == 'YES',
        'native_default': row.get('data_default') if oracle else row.get('column_default'),
        'generated': row.get('virtual_column') == 'YES' if oracle else row.get('is_generated') == 'ALWAYS',
        'identity': row.get('identity_column') == 'YES' if oracle else row.get('is_identity') == 'YES',
        'collation': row.get('collation') if oracle else row.get('collation_name'),
    }


def foreign_keys(native, lane):
    """Resolve ordered columns and targets, independent of constraint names."""
    result = defaultdict(list)
    if lane == 'oracle':
        constraints = keyed(native['constraints'], lambda x: x['constraint_name'])
        columns = defaultdict(list)
        for row in native['constraint_columns']:
            columns[row['constraint_name']].append(row)
        def names(name):
            ordered = sorted(columns[name], key=lambda x: x['position'])
            require(ordered and [x['position'] for x in ordered] == list(range(1, len(ordered)+1)),
                    'Incomplete or duplicate constraint-column positions')
            return tuple(identifier(x['column_name'], lane) for x in ordered)
        for c in constraints.values():
            if c['constraint_type'] != 'R':
                continue
            require(c.get('r_owner') == native['identity'][0]['current_schema'],
                    'External foreign-key target requires capture of its owner')
            require(c['r_constraint_name'] in constraints, 'Foreign-key target was not captured')
            target = constraints[c['r_constraint_name']]
            require(target['constraint_type'] in ('P', 'U'), 'Foreign-key target is not a captured key')
            local, remote = names(c['constraint_name']), names(target['constraint_name'])
            require(len(local) == len(remote), 'Foreign-key column arity mismatch')
            key = (identifier(c['table_name'], lane), local, identifier(target['table_name'], lane), remote)
            contract = {'delete': c['delete_rule'], 'update': 'NO ACTION', 'match': 'SIMPLE',
                        'deferrable': c['deferrable'] == 'DEFERRABLE',
                        'initially_deferred': c['deferred'] == 'DEFERRED',
                        'enabled': c['status'] == 'ENABLED', 'validated': c['validated'] == 'VALIDATED'}
            result[key].append({'name': c['constraint_name'], 'contract': contract, 'raw_sha256': digest(c)})
    else:
        objects = keyed(native['objects'], lambda x: x['oid'])
        attributes = keyed(native['attributes'], lambda x: (x['attrelid'], x['attnum']))
        actions = {'a': 'NO ACTION', 'r': 'RESTRICT', 'c': 'CASCADE', 'n': 'SET NULL', 'd': 'SET DEFAULT'}
        def names(oid, numbers):
            require(oid in objects and numbers, 'Foreign-key relation/columns were not captured')
            require(len(numbers) == len(set(numbers)), 'Repeated foreign-key column')
            values = []
            for n in numbers:
                require((oid, n) in attributes and not attributes[oid, n]['attisdropped'], 'Foreign-key column was not captured')
                values.append(identifier(attributes[oid, n]['attname'], lane))
            return tuple(values)
        for c in native['constraints']:
            if c['contype'] != 'f':
                continue
            local, remote = names(c['conrelid'], c['conkey']), names(c['confrelid'], c['confkey'])
            require(len(local) == len(remote), 'Foreign-key column arity mismatch')
            key = (identifier(objects[c['conrelid']]['relname'], lane), local,
                   identifier(objects[c['confrelid']]['relname'], lane), remote)
            require(c['confdeltype'] in actions and c['confupdtype'] in actions, 'Unknown referential action')
            contract = {'delete': actions[c['confdeltype']], 'update': actions[c['confupdtype']],
                        'match': {'s': 'SIMPLE', 'f': 'FULL', 'p': 'PARTIAL'}[c['confmatchtype']],
                        'deferrable': c['condeferrable'], 'initially_deferred': c['condeferred'],
                        'enabled': None, 'validated': c['convalidated']}
            # Internal RI trigger state determines enforcement, not just the FK row.
            triggers = [t for t in native['triggers'] if t['tgconstraint'] == c['oid'] and t['tgisinternal']]
            contract['enabled'] = len(triggers) == 4 and all(t['tgenabled'] in ('O', 'A') for t in triggers)
            result[key].append({'name': c['conname'], 'contract': contract, 'raw_sha256': digest(c)})
    return dict(result)


def compare_foreign_keys(left, right):
    records = []
    for key in sorted(left.keys() | right.keys()):
        a, b = left.get(key, []), right.get(key, [])
        status = 'missing-oracle' if not a else 'missing-postgresql' if not b else 'catalog-contract-match'
        if a and b:
            if len(a) != 1 or len(b) != 1:
                status = 'duplicate-relationship-review'
            elif a[0]['contract'] != b[0]['contract']:
                status = 'enforcement-difference'
            elif not a[0]['contract']['enabled'] or not a[0]['contract']['validated']:
                status = 'unenforced-or-unvalidated'
        records.append({'identity': key, 'status': status, 'oracle': a, 'postgresql': b})
    return records


def key_declarations(native, lane):
    """Compare key column sets; preserve index order and native enforcement facts.

    Column order does not change tuple uniqueness, but can change index access.
    This is a declaration inventory, never a proof of equivalent null semantics.
    """
    result = defaultdict(list)
    columns = defaultdict(list)
    if lane == 'oracle':
        for row in native['constraint_columns']:
            columns[row['constraint_name']].append(row)
    else:
        attributes = keyed(native['attributes'], lambda x: (x['attrelid'], x['attnum']))
    for constraint in native['constraints']:
        kind = constraint.get('constraint_type') if lane == 'oracle' else constraint['contype'].upper()
        if kind not in ('P', 'U'):
            continue
        if lane == 'oracle':
            selected = sorted(columns[constraint['constraint_name']], key=lambda x: x['position'])
            require(selected and [x['position'] for x in selected] == list(range(1, len(selected)+1)), 'Incomplete key columns')
            names = [identifier(x['column_name'], lane) for x in selected]
            name = constraint['constraint_name']
        else:
            require(constraint['conkey'], 'Missing key columns')
            selected = []
            for number in constraint['conkey']:
                require((constraint['conrelid'], number) in attributes, 'Missing key attribute')
                attribute = attributes[constraint['conrelid'], number]
                require(not attribute['attisdropped'], 'Dropped key attribute')
                selected.append(attribute)
            names = [identifier(x['attname'], lane) for x in selected]
            name = constraint['conname']
        require(len(names) == len(set(names)), 'Repeated key column')
        identity = (identifier(constraint['table_name'], lane), kind, tuple(sorted(names)))
        result[identity].append({'name': name, 'column_order': names, 'native_definition': constraint})
    return dict(result)


def compare_keys(left, right):
    records = []
    for identity in sorted(left.keys() | right.keys()):
        a, b = left.get(identity, []), right.get(identity, [])
        status = 'missing-oracle' if not a else 'missing-postgresql' if not b else 'column-set-match'
        if a and b and (len(a) != 1 or len(b) != 1):
            status = 'duplicate-key-review'
        records.append({'identity': identity, 'status': status, 'oracle': a, 'postgresql': b,
                        'column_order_matches': bool(len(a) == len(b) == 1 and a[0]['column_order'] == b[0]['column_order'])})
    return records


def assess(captures):
    require(set(captures) == set(LANES), 'Both native schema captures are required')
    for lane in LANES:
        require(captures[lane]['lane'] == lane, 'Mislabeled schema lane')
    native = {lane: rows(captures[lane]) for lane in LANES}
    require(all(captures[lane].get('import_binding') for lane in LANES), 'Missing baseline lineage')
    bindings = [captures[lane]['import_binding'].get('ms84_checkpoint_sha256') for lane in LANES]
    require(bindings[0] and bindings[0] == bindings[1], 'Schema captures must reference the same MS84 checkpoint')
    tables = {lane: relation_map(native[lane], lane) for lane in LANES}
    columns = {lane: column_map(native[lane], lane, tables[lane]) for lane in LANES}
    common_tables = tables['oracle'].keys() & tables['postgresql'].keys()
    common = {key for key in columns['oracle'].keys() & columns['postgresql'].keys() if key[0] in common_tables}
    column_records = []
    for key in sorted(common):
        a, b = (column_contract(columns[lane][key], lane) for lane in LANES)
        differences = [field for field in a if canonical(a[field]) != canonical(b[field])]
        column_records.append({'table': key[0], 'column': key[1],
                               'status': 'declared-property-difference' if differences else 'catalog-contract-match',
                               'different_properties': differences, 'oracle': a, 'postgresql': b})
    fks = compare_foreign_keys(*(foreign_keys(native[lane], lane) for lane in LANES))
    keys = compare_keys(*(key_declarations(native[lane], lane) for lane in LANES))
    # Every captured category is accounted for. Future evidence may discharge
    # these obligations, but this report never infers their behavior from rows.
    obligations = [
        {'dimension': 'datatype-behavior', 'status': 'native-probes-required',
         'reason': 'Empty text, character lengths, rounding, timestamp precision, UUID, JSON and LOB representations need explicit domains and native boundary probes.'},
        {'dimension': 'defaults', 'status': 'native-probes-required',
         'reason': 'Oracle SYSDATE, PostgreSQL now() and statement_timestamp() have different clock and transaction semantics.'},
        {'dimension': 'primary-unique-check-constraints', 'status': 'definition-and-negative-probes-required',
         'native_counts': {lane: dict(Counter(x['constraint_type' if lane == 'oracle' else 'contype'] for x in native[lane]['constraints'])) for lane in LANES}},
    ]
    for dimension, category in [('indexes', 'indexes'), ('views', 'views'), ('routines', 'routines'),
                                ('triggers', 'triggers'), ('privileges', 'privileges'), ('row-policies', 'policies'),
                                ('sequences', 'sequences')]:
        counts = {lane: len(native[lane][category]) for lane in LANES}
        obligations.append({'dimension': dimension, 'status': 'definition-and-behavior-review-required',
                            'capture_row_counts': counts, 'raw_definition_sha256': {lane: digest(native[lane][category]) for lane in LANES}})
    missing_columns = {lane: [list(k) for k in sorted(columns[lane].keys() - columns[other].keys()) if k[0] in common_tables]
                       for lane, other in [('oracle','postgresql'),('postgresql','oracle')]}
    count = {'common_base_tables': len(common_tables), 'common_base_columns': len(common),
             'nullable_differences': sum('nullable' in x['different_properties'] for x in column_records),
             'column_declaration_differences': sum('declaration' in x['different_properties'] for x in column_records),
             'default_definition_differences': sum('native_default' in x['different_properties'] for x in column_records),
             'foreign_key_relationships': len(fks),
             'foreign_key_catalog_matches': sum(x['status'] == 'catalog-contract-match' for x in fks),
             'foreign_key_missing_relationships': sum(x['status'].startswith('missing-') for x in fks),
             'foreign_key_enforcement_differences': sum(x['status'] == 'enforcement-difference' for x in fks),
             'primary_key_column_set_matches': sum(x['identity'][1] == 'P' and x['status'] == 'column-set-match' for x in keys),
             'unique_key_column_set_matches': sum(x['identity'][1] == 'U' and x['status'] == 'column-set-match' for x in keys),
             'key_column_order_differences': sum(x['status'] == 'column-set-match' and not x['column_order_matches'] for x in keys),
             'unresolved_dimensions': len(obligations)}
    statement = (f"{count['common_base_tables']} common base tables assessed; "
                 f"{count['foreign_key_missing_relationships']} one-sided foreign-key relationships and "
                 f"{count['nullable_differences']} nullability differences. "
                 'Schema and application equivalence remain unproven.')
    return seal({'schema_version': '1.0', 'artifact_type': 'lightyear-native-schema-assessment',
                 'status': 'schema-review-required', 'coverage_statement': statement, 'counts': count,
                 'evidence_class': 'native-catalog-observation', 'independently_attested': False,
                 'schema_equivalence': False, 'application_equivalence': False, 'platform_qualification': False,
                 'baseline_checkpoint_sha256': bindings[0],
                 'catalog_sha256': {lane: captures[lane]['content_sha256'] for lane in LANES},
                 'engine_only_tables': {lane: sorted(tables[lane].keys() - tables[other].keys())
                                        for lane, other in [('oracle','postgresql'),('postgresql','oracle')]},
                 'engine_only_tables_disposition': 'explicit-scope-and-behavior-review-required',
                 'missing_common_table_columns': missing_columns,
                 'columns': column_records, 'foreign_keys': fks, 'key_declarations': keys,
                 'remaining_obligations': obligations})


def markdown(report):
    lines = ['# Native schema assessment', '', report['coverage_statement'], '',
             'Catalog matches describe declared properties only. Native behavioral probes and explicit domain rules remain required.', '',
             '| Measurement | Count |', '|---|---:|']
    lines += [f'| {k.replace("_", " ")} | {v} |' for k, v in report['counts'].items()]
    lines += ['', '## Foreign-key findings', '', '| Relationship | Finding |', '|---|---|']
    for item in report['foreign_keys']:
        if item['status'] != 'catalog-contract-match':
            table, columns, target, remote = item['identity']
            lines.append(f'| {table} ({", ".join(columns)}) references {target} ({", ".join(remote)}) | {item["status"]} |')
    lines += ['', '## Nullability findings', '', '| Column | Oracle nullable | PostgreSQL nullable |', '|---|---|---|']
    lines += [f'| {x["table"]}.{x["column"]} | {x["oracle"]["nullable"]} | {x["postgresql"]["nullable"]} |'
              for x in report['columns'] if 'nullable' in x['different_properties']]
    lines += ['', '## Remaining schema obligations', '']
    lines += [f'- {x["dimension"]}: {x["status"]}.' for x in report['remaining_obligations']]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oracle-catalog', required=True, type=Path)
    parser.add_argument('--postgresql-catalog', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    report = assess({'oracle': read_capture(args.oracle_catalog), 'postgresql': read_capture(args.postgresql_catalog)})
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'assessment.json').write_bytes(canonical(report))
    (args.output/'README.md').write_text(markdown(report), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'counts': report['counts']}))
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
