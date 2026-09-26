"""Inventory native column mappings without promoting declarations into behavior.

Every common base-table column is retained. Matching precision or length is a
declared parameter match, never a proof of acceptance, rounding or application
equivalence. Missing metadata remains unknown rather than becoming zero.
"""
from collections import Counter
from pathlib import Path
import argparse

from .contracts import canonical, require, seal
from .native_catalog import read_capture
from .schema_equivalence import rows, relation_map, column_map


FIELDS = {
    'oracle': ('data_type', 'data_precision', 'data_scale', 'data_length',
               'char_length', 'char_used', 'character_set_name', 'collation'),
    'postgresql': ('data_type', 'udt_name', 'numeric_precision', 'numeric_scale',
                   'numeric_precision_radix', 'datetime_precision',
                   'character_maximum_length', 'character_octet_length', 'collation_name'),
}


def classify(oracle, postgresql):
    """Return review obligations; do not infer target safety from a type name."""
    a, b = oracle['data_type'], postgresql['data_type']
    checks, relation = [], 'requires-explicit-mapping'
    family = a + ' -> ' + b
    if (a, b) == ('NUMBER', 'numeric'):
        source = (oracle.get('data_precision'), oracle.get('data_scale'))
        target = (postgresql.get('numeric_precision'), postgresql.get('numeric_scale'))
        if None in source or None in target:
            relation = 'unbounded-or-partially-declared-numeric'
            checks.append('significant-digit-and-exponent-boundaries')
        elif source == target:
            relation = 'matching-declared-precision-and-scale'
        else:
            relation = 'different-declared-precision-or-scale'
            checks.append('integer-digit-and-scale-capacity')
        checks += ['positive-and-negative-rounding-ties', 'overflow-rejection',
                   'application-currency-price-and-tax-rounding', 'nonfinite-input-rejection']
    elif a in ('CHAR', 'VARCHAR2') and b in ('character', 'character varying'):
        size = oracle.get('char_length')
        target = postgresql.get('character_maximum_length')
        unit = oracle.get('char_used')
        relation = ('matching-declared-character-length' if unit == 'C' and
                    size is not None and size == target else 'different-or-unknown-length-contract')
        checks += ['unicode-round-trip', 'empty-string-and-null', 'length-boundary',
                   'collation-and-comparison']
        if unit == 'B': checks.append('multibyte-byte-capacity')
        if a == 'CHAR' or b == 'character': checks.append('fixed-width-padding-and-trailing-spaces')
        if (a == 'CHAR') != (b == 'character'): checks.append('fixed-versus-varying-text')
    elif a == 'DATE' and b == 'timestamp without time zone':
        relation = 'different-declared-fractional-second-capacity'
        checks += ['fractional-second-write-and-readback', 'date-range', 'application-time-normalization']
    elif a.startswith('TIMESTAMP') and b.startswith('timestamp'):
        relation = 'timestamp-mapping-needs-explicit-precision-and-zone-check'
        checks += ['fractional-second-write-and-readback', 'timezone-offset-and-instant', 'date-range']
    elif a == 'VARCHAR2' and b == 'uuid':
        relation = 'text-to-validated-uuid-domain'
        checks += ['valid-uuid-round-trip', 'invalid-uuid-rejection', 'uuid-case-rendering', 'empty-string-and-null']
    elif a == 'CLOB' and b in ('json', 'jsonb'):
        relation = 'text-to-json-domain'
        checks += ['actual-column-json-constraints', 'invalid-json-rejection', 'duplicate-json-keys',
                   'json-number-precision', 'json-null-versus-sql-null', 'json-text-rendering']
    elif a == 'CLOB' and b == 'text':
        relation = 'large-text-mapping'
        checks += ['large-unicode-round-trip', 'empty-lob-versus-null', 'large-value-capacity']
    elif a == 'BLOB' and b in ('bytea', 'oid'):
        relation = 'binary-value-mapping' if b == 'bytea' else 'binary-to-large-object-reference'
        checks += ['binary-byte-round-trip', 'empty-binary-versus-null', 'large-value-capacity']
        if b == 'oid': checks += ['large-object-dereference', 'large-object-ownership-and-lifecycle']
    else:
        checks += ['unclassified-native-domain']
    return {'mapping': family, 'declared_relation': relation,
            'required_behavior_checks': checks, 'behavior_verified': False}


def assess(captures):
    require(set(captures) == {'oracle', 'postgresql'}, 'Both native catalogs are required')
    maps = {}
    for lane, capture in captures.items():
        require(capture['lane'] == lane, 'Catalog lane mismatch')
        native = rows(capture)
        maps[lane] = column_map(native, lane, relation_map(native, lane))
    common = maps['oracle'].keys() & maps['postgresql'].keys()
    require(common, 'No common base-table columns')
    records = []
    for table, column in sorted(common):
        raw = {lane: {k: maps[lane][table, column].get(k) for k in FIELDS[lane]} for lane in maps}
        records.append({'table': table, 'column': column, 'native_declarations': raw,
                        **classify(raw['oracle'], raw['postgresql'])})
    return seal({'artifact_type': 'lightyear-native-datatype-mapping-review',
                 'status': 'datatype-behavior-review-required',
                 'catalog_sha256': {lane: c['content_sha256'] for lane, c in captures.items()},
                 'common_column_count': len(records), 'columns': records,
                 'mapping_counts': dict(sorted(Counter(x['mapping'] for x in records).items())),
                 'declared_relation_counts': dict(sorted(Counter(x['declared_relation'] for x in records).items())),
                 'required_check_column_counts': dict(sorted(Counter(y for x in records for y in x['required_behavior_checks']).items())),
                 'one_sided_columns': {lane: [{'table': t, 'column': c} for t, c in sorted(maps[lane].keys()-common)] for lane in maps},
                 'behavior_verified_column_count': 0, 'schema_equivalence': False,
                 'application_equivalence': False, 'platform_qualification': False,
                 'scope': 'Native declarations and review obligations; observed journey results are separate evidence'})


def markdown(report):
    lines = ['# Native datatype mapping review', '',
             f"Common base-table columns: **{report['common_column_count']:,}**. "
             'This inventory does not prove datatype behavior.', '',
             '| Oracle to PostgreSQL mapping | Columns |', '|---|---:|']
    lines += [f'| {name} | {count:,} |' for name, count in report['mapping_counts'].items()]
    lines += ['', '## Required behavioral checks', '', '| Check | Columns requiring review |', '|---|---:|']
    lines += [f'| {name} | {count:,} |' for name, count in report['required_check_column_counts'].items()]
    lines += ['', 'Counts overlap: a column can require several checks. Matching declared',
              'length or precision does not prove identical accepted inputs, rounding,',
              'collation, table constraints or application behavior. Missing metadata is',
              'retained as null. Every native declaration and one-sided column is retained',
              'in the JSON report. Full schema and platform qualification remain false.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for lane in ('oracle', 'postgresql'):
        parser.add_argument('--'+lane+'-catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    result = assess({lane: read_capture(getattr(args, lane+'_catalog')) for lane in ('oracle', 'postgresql')})
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'mappings.json').write_bytes(canonical(result))
    (args.output/'mappings.md').write_text(markdown(result), encoding='utf-8', newline='\n')
    print(result['status'])
    return 3


if __name__ == '__main__': raise SystemExit(main())
