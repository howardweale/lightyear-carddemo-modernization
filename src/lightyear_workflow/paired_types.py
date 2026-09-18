"""Reviewed five-family SQL contract. Expectations never enter observed output."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from lightyear_control_tower.decisions import digest
from lightyear_data import oracle_number_native as number
from . import paired_number

CAMPAIGN = 'oracle26ai-alloydb-core100'
NAME = 'Oracle 26ai → AlloyDB · 100 datatype pairs'
FAMILIES = ('number', 'char', 'varchar2', 'date', 'timestamp')
ARTIFACTS = Path('data-modernization/oracle-paired-core100')
PROFILE = Path('work/campaigns') / CAMPAIGN / 'profile.json'
MARKER = 'LY_TYPES_OBSERVATION='

# Deliberately independent of both SQL programs and the bounded-model outputs.
EXPECTED = {
    'char': {'canonical': 'A  ', 'null_value': None, 'length': 3, 'boundary': 'ABC',
             'overflow_code': -12899, 'recovery': 'A  ', 'comparison': 1},
    'varchar2': {'canonical': None, 'null_value': None, 'length': 2, 'boundary': 'ABC',
                 'overflow_code': -12899, 'recovery': None, 'comparison': 0},
    'date': {'canonical': '2024-03-01T00:00:00', 'null_value': None,
             'boundary': '2024-03-01T00:00:00', 'time_value': '2024-02-29T23:59:59',
             'overflow_code': -1861, 'recovery': '2024-03-01T00:00:00',
             'format_a': '01/03/2024', 'format_b': '2024-03-01'},
    'timestamp': {'canonical': '2026-09-01T12:00:00.123456', 'null_value': None,
                  'boundary': '2026-09-01T12:00:00.123', 'time_value': '2026-09-02T00:00:00.000001',
                  'overflow_code': -1861, 'recovery': '2026-09-01T12:00:00.123456',
                  'format_a': '01/09/2026 12:00:00.123456', 'format_b': '2026-09-01T12:00:00.123456'},
}
DIAGNOSTICS = {'char': (-12899, '22001', 'character-length-overflow'),
               'varchar2': (-12899, '22001', 'character-length-overflow'),
               'date': (-1861, '22007', 'invalid-datetime-format'),
               'timestamp': (-1861, '22007', 'invalid-datetime-format')}


def cases(root: Path) -> list[dict]:
    corpus = json.loads((root / 'data-modernization/oracle-core-sql-coverage/core-sql-corpus.json').read_text(encoding='utf-8'))
    selected = [c for topic in FAMILIES for c in corpus['results'] if c['domain_id'] == 'types' and c['topic'] == topic]
    if len(selected) != 100 or len({c['id'] for c in selected}) != 100:
        raise ValueError('Core100 catalog scope changed')
    for topic in FAMILIES:
        family = [c for c in selected if c['topic'] == topic]
        if len(family) != 20 or len({c['behavior_id'] for c in family}) != 5:
            raise ValueError('Each family requires five behaviours and twenty cases')
    return selected


def probes(case):
    topic = case['topic']
    if topic == 'number':
        return number.probes(case)
    focus = {
        'canonical semantics': ('canonical',),
        'null and absence semantics': ('null_value', 'canonical') if topic == 'varchar2' else ('null_value',),
        'boundary and overflow semantics': ('length', 'boundary', 'overflow_code') if topic in ('char', 'varchar2') else ('boundary', 'time_value'),
        'session, ordering, and version semantics': ('comparison',) if topic in ('char', 'varchar2') else ('format_a', 'format_b'),
        'failure and diagnostic semantics': ('overflow_code', 'recovery'),
    }
    dimension = {'canonical': (), 'null-boundary': ('null_value',),
                 'session-version': focus['session, ordering, and version semantics'],
                 'failure-recovery': ('overflow_code', 'recovery')}
    return tuple(sorted(set(focus[case['focus']] + dimension[case['dimension']])))


def expected(case, lane):
    if case['topic'] == 'number':
        result = {p: number.EXPECTED[p] for p in probes(case)}
        if lane == 'alloydb' and 'overflow_code' in result:
            result['overflow_code'] = '22003'
        return result
    result = {p: EXPECTED[case['topic']][p] for p in probes(case)}
    if lane == 'alloydb' and 'overflow_code' in result:
        result['overflow_code'] = DIAGNOSTICS[case['topic']][1]
    return result


def _string_body(topic, lane, table):
    char = topic == 'char'
    if lane == 'oracle':
        typ = 'CHAR(3 CHAR)' if char else 'VARCHAR2(3 CHAR)'
        canonical = "CAST('A' AS CHAR(3))" if char else "CAST('' AS VARCHAR2(3))"
        length = "LENGTH(CAST('A' AS CHAR(3)))" if char else "LENGTH(CAST('A ' AS VARCHAR2(3)))"
        left, right = ("CAST('A' AS CHAR(3))", "CAST('A  ' AS CHAR(3))") if char else ("CAST('A' AS VARCHAR2(3))", "CAST('A ' AS VARCHAR2(3))")
        return f"""  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_COMP=BINARY';
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_SORT=BINARY';
  SELECT {canonical}, CAST(NULL AS {typ}), {length},
         CASE WHEN {left} = {right} THEN 1 ELSE 0 END
    INTO v_canonical, v_null_value, v_length, v_comparison FROM dual;
  EXECUTE IMMEDIATE 'CREATE TABLE {table} (v {typ})';
  BEGIN
    EXECUTE IMMEDIATE 'INSERT INTO {table} VALUES (:1)' USING 'ABC';
    EXECUTE IMMEDIATE 'SELECT v FROM {table}' INTO v_boundary;
    BEGIN
      EXECUTE IMMEDIATE 'INSERT INTO {table} VALUES (:1)' USING 'ABCD';
    EXCEPTION WHEN OTHERS THEN v_overflow_code := SQLCODE;
    END;
    SELECT {canonical} INTO v_recovery FROM dual;
  EXCEPTION WHEN OTHERS THEN
    EXECUTE IMMEDIATE 'DROP TABLE {table} PURGE'; RAISE;
  END;
  EXECUTE IMMEDIATE 'DROP TABLE {table} PURGE';"""
    typ = 'char(3)' if char else 'varchar(3)'
    canonical = "rpad(('A'::char(3))::text, 3, ' ')" if char else "nullif(''::varchar(3), '')"
    length = "octet_length('A'::char(3))" if char else "length('A '::varchar(3))"
    comparison = "'A'::char(3) = 'A  '::char(3)" if char else "('A'::varchar(3) COLLATE \"C\") = 'A '::varchar(3)"
    return f""" SELECT {canonical}, NULL::{typ}, {length}, CASE WHEN {comparison} THEN 1 ELSE 0 END
 INTO v_canonical, v_null_value, v_length, v_comparison;
 CREATE TEMP TABLE {table} (v {typ}) ON COMMIT DROP;
 INSERT INTO pg_temp.{table} VALUES ('ABC');
 SELECT v INTO v_boundary FROM pg_temp.{table};
 BEGIN
   INSERT INTO pg_temp.{table} VALUES ('ABCD');
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT {canonical} INTO v_recovery;"""


def _datetime_body(topic, lane):
    date = topic == 'date'
    fmt = 'YYYY-MM-DD"T"HH24:MI:SS' + ('' if date else '.FF6' if lane == 'oracle' else '.US')
    value = "DATE '2024-02-29' + 1" if date and lane == 'oracle' else "TIMESTAMP '2024-02-29 00:00:00' + INTERVAL '1 day'" if date else "TIMESTAMP '2026-09-01 12:00:00.123456'"
    boundary = value if date else "CAST(TIMESTAMP '2026-09-01 12:00:00.123456' AS TIMESTAMP(3))"
    boundary_fmt = fmt if date else 'YYYY-MM-DD"T"HH24:MI:SS.' + ('FF3' if lane == 'oracle' else 'MS')
    time_value = "TO_DATE('2024-02-29 23:59:59','YYYY-MM-DD HH24:MI:SS')" if date and lane == 'oracle' else "TIMESTAMP '2024-02-29 23:59:59'" if date else "TIMESTAMP '2026-09-01 23:59:59.999999' + INTERVAL '0.000002' SECOND" if lane == 'oracle' else "TIMESTAMP '2026-09-01 23:59:59.999999' + INTERVAL '0.000002 second'"
    a = 'DD/MM/YYYY' + ('' if date else ' HH24:MI:SS.' + ('FF6' if lane == 'oracle' else 'US'))
    b = 'YYYY-MM-DD' if date else fmt
    if lane == 'oracle':
        typ = 'DATE' if date else 'TIMESTAMP'
        bad = "TO_DATE('2024x03x01','FXYYYY-MM-DD')" if date else "TO_TIMESTAMP('2026x09x01 12:00:00.123456','FXYYYY-MM-DD HH24:MI:SS.FF6')"
        setting = 'NLS_DATE_FORMAT' if date else 'NLS_TIMESTAMP_FORMAT'
        return f"""  SELECT TO_CHAR({value}, '{fmt}'), TO_CHAR(CAST(NULL AS {typ}), '{fmt}'),
         TO_CHAR({boundary}, '{boundary_fmt}'), TO_CHAR({time_value}, '{fmt}')
    INTO v_canonical, v_null_value, v_boundary, v_time_value FROM dual;
  BEGIN
    SELECT TO_CHAR({bad}, '{fmt}') INTO v_sink FROM dual;
  EXCEPTION WHEN OTHERS THEN v_overflow_code := SQLCODE;
  END;
  SELECT TO_CHAR({value}, '{fmt}') INTO v_recovery FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET {setting} = ''{a}''';
  SELECT TO_CHAR({value}) INTO v_format_a FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET {setting} = ''{b}''';
  SELECT TO_CHAR({value}) INTO v_format_b FROM dual;"""
    bad = "'2024x03x01'::timestamp" if date else "'2026x09x01 12:00:00.123456'::timestamp"
    return f""" SELECT to_char({value}, '{fmt}'), to_char(NULL::timestamp, '{fmt}'),
        to_char({boundary}, '{boundary_fmt}'), to_char({time_value}, '{fmt}')
 INTO v_canonical, v_null_value, v_boundary, v_time_value;
 BEGIN
   SELECT to_char({bad}, '{fmt}') INTO v_sink;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT to_char({value}, '{fmt}'), to_char({value}, '{a}'), to_char({value}, '{b}')
 INTO v_recovery, v_format_a, v_format_b;"""


def render(case, lane):
    if lane not in ('oracle', 'alloydb') or case['topic'] not in FAMILIES:
        raise ValueError('Unknown native lane/family')
    if case['topic'] == 'number':
        return number.render_case(case, '26ai') if lane == 'oracle' else paired_number.postgres_case(case)
    # Names are generated solely from the validated catalog identifier.
    import re
    if not re.fullmatch(r'ORA-TYPE-[0-9]{3}-CASE-0[1-4]', case['id']):
        raise ValueError('Unsafe catalog identifier')
    table = 'LY_' + case['id'].replace('-', '_')
    body = _string_body(case['topic'], lane, table) if case['topic'] in ('char', 'varchar2') else _datetime_body(case['topic'], lane)
    names = ('canonical', 'null_value', 'boundary', 'recovery', 'time_value', 'format_a', 'format_b', 'sink')
    if lane == 'oracle':
        fields = ', '.join(f"'{p}' VALUE v_{p}" for p in probes(case))
        declarations = '\n'.join(f'  v_{p} VARCHAR2(128);' for p in names)
        return f"""-- Synthetic catalog case {case['id']}; source Oracle 26ai.
DECLARE
{declarations}
  v_length NUMBER; v_comparison NUMBER; v_overflow_code NUMBER := 0; v_json VARCHAR2(4000);
BEGIN
{body}
  SELECT JSON_OBJECT('case_id' VALUE '{case['id']}', 'observations' VALUE
    JSON_OBJECT({fields} NULL ON NULL) RETURNING VARCHAR2(4000)) INTO v_json FROM dual;
  DBMS_OUTPUT.PUT_LINE('{MARKER}' || v_json);
END;
/
"""
    fields = ', '.join(f"'{p}', v_{p}" for p in probes(case))
    declarations = '\n'.join(f' v_{p} text;' for p in names)
    return f"""-- Synthetic catalog case {case['id']}; target AlloyDB PostgreSQL.
BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL TIME ZONE 'UTC';
SET LOCAL DateStyle = 'ISO, YMD';
DO $pilot$
DECLARE
{declarations}
 v_length integer; v_comparison integer; v_overflow_code text := '00000';
BEGIN
{body}
 RAISE NOTICE '{MARKER}%', json_build_object('case_id', '{case['id']}', 'observations', json_build_object({fields}));
END $pilot$;
ROLLBACK;
"""


def parse(output, case, lane):
    if case['topic'] == 'number':
        return paired_number.parse_observation(output, case, lane)
    values = [line.split(MARKER, 1)[1].strip() for line in output.splitlines() if MARKER in line]
    if len(values) != 1:
        raise ValueError('A case requires exactly one native observation')
    from .policy import _unique_object
    value = json.loads(values[0], object_pairs_hook=_unique_object)
    if value.get('case_id') != case['id'] or set(value.get('observations', {})) != set(probes(case)):
        raise ValueError('Observation differs from bound catalog probes')
    if any(v is not None and (type(v) not in (str, int) or len(str(v)) > 128) for v in value['observations'].values()):
        raise ValueError('Unexpected native observation type or length')
    return value['observations']


def compare(case, source, target):
    if case['topic'] == 'number':
        return paired_number.compare(case, source, target)
    source_ok, target_ok = source == expected(case, 'oracle'), target == expected(case, 'alloydb')
    differences = []
    for probe in probes(case):
        equal = source.get(probe) == target.get(probe)
        if probe == 'overflow_code':
            code, sqlstate, _ = DIAGNOSTICS[case['topic']]
            equal = type(source.get(probe)) is int and source[probe] == code and target.get(probe) == sqlstate
        if not equal:
            differences.append({'probe': probe, 'oracle': source.get(probe), 'alloydb': target.get(probe)})
    return {'case_id': case['id'], 'source_expectations_met': source_ok, 'target_expectations_met': target_ok,
            'equivalent': source_ok and target_ok and not differences, 'differences': differences,
            'diagnostic_mapping': list(DIAGNOSTICS[case['topic']]) if 'overflow_code' in probes(case) else None}


def materialize(root):
    for case in cases(root):
        for lane in ('oracle', 'alloydb'):
            path = root / ARTIFACTS / 'cases' / lane / (case['id'] + '.sql')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render(case, lane), encoding='utf-8', newline='\n')


def verify(root):
    for case in cases(root):
        for lane in ('oracle', 'alloydb'):
            path = root / ARTIFACTS / 'cases' / lane / (case['id'] + '.sql')
            if path.read_bytes() != render(case, lane).encode():
                raise ValueError('Core100 SQL binding drift: ' + case['id'])


def plan(root):
    verify(root)
    config = paired_number.profile(root, PROFILE)
    selected = cases(root)
    sources = ['lightyear_workflow/' + name for name in ('paired_types.py', 'paired_number.py', 'campaign_engine.py', 'campaign_gcp.py', 'campaign_journals.py')]
    sources.append('lightyear_data/oracle_number_native.py')
    body = {'campaign_id': CAMPAIGN, 'name': NAME, 'project': paired_number.PROJECT, 'region': paired_number.REGION,
            'profile': config, 'journal_layout': 'family-v1', 'families': list(FAMILIES),
            'implementation': {name: hashlib.sha256((root / 'src' / name).read_bytes()).hexdigest() for name in sources},
            'cases': [{'id': c['id'], 'behavior_id': c['behavior_id'], 'family': c['topic'],
                       'catalog_expectation_sha256': digest(c['expected']),
                       'probe_contract_sha256': digest({'oracle': expected(c, 'oracle'), 'alloydb': expected(c, 'alloydb')}),
                       'oracle_sql_sha256': hashlib.sha256(render(c, 'oracle').encode()).hexdigest(),
                       'alloydb_sql_sha256': hashlib.sha256(render(c, 'alloydb').encode()).hexdigest()} for c in selected],
            'alloydb_cluster': 'cloudbank-ms71-alloydb', 'alloydb_instance': 'primary',
            'resource_policy': 'One owned ephemeral runner; resume only the stopped AlloyDB primary. Delete owned runner/firewall/disk and restore AlloyDB STOPPED.',
            'data_policy': 'Synthetic data only. CHAR/VARCHAR2 use disposable tables in the isolated Oracle container and session-local pg_temp tables on AlloyDB; target transactions roll back. No application data or permanent target objects.',
            'identity_policy': 'Pinned Oracle 26ai image/PDB; fresh fixed-resource AlloyDB endpoint and PostgreSQL 16 identity. Unknown metadata remains unknown.',
            'comparison_policy': 'Exact typed values and nulls. Only reviewed -1438/22003, -12899/22001 and -1861/22007 diagnostic mappings. Explicit target empty-string normalization, padding and date/time rendering are part of the SQL, never comparator rewrites.',
            'cost_policy': 'Estimated incremental budget; runtime guard, not a guaranteed billing cap. Existing storage charges continue.',
            'interruption_policy': 'No automatic SQL replay. Signed per-family journals/checkpoints; failed observations retained. Cleanup before another launch.',
            'qualification': '100 bounded datatype pairs, five families/25 behaviours, Oracle 26ai only. No Oracle 19c, application or platform qualification.'}
    return {**body, 'plan_sha256': digest(body)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('materialize', 'verify'))
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    (materialize if args.command == 'materialize' else verify)(args.root.resolve())
    print('100 case pairs: SQL ' + args.command + ' complete; no database executed')
