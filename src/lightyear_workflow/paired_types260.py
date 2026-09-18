"""Thirteen-family bounded datatype contract; historical 100 SQL is unchanged."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from lightyear_control_tower.decisions import digest
from . import paired_number, paired_types as previous

CAMPAIGN = 'oracle26ai-alloydb-types260'
NAME = 'Oracle 26ai → AlloyDB · 260 datatype pairs'
FAMILIES = previous.FAMILIES + ('binary-float', 'binary-double', 'nchar', 'raw',
                               'timestamp-tz', 'timestamp-ltz', 'interval-ym', 'interval-ds')
EXECUTION_FAMILIES = ('interval-ym', 'interval-ds') + FAMILIES[:-2]
# The initial native attempt completed 220 pairs before an interval compile
# error. Its exact failed SQL remains reviewable; do not rewrite its binding.
RETIRED_PLAN = '8af0836221c81282924e995d1980d1fa8faa836d4ca97fe49c10521710747ed0'
ARTIFACTS = Path('data-modernization/oracle-paired-types260')
PROFILE = Path('work/campaigns') / CAMPAIGN / 'profile.json'
MARKER = previous.MARKER

# Independent expected values. No expected value is used to render native SQL.
EXPECTED = {
    'binary-float': dict(canonical='3FC00000', boundary='00800000', session_value='1', comparison=1, overflow_code=-1722),
    'binary-double': dict(canonical='3FF8000000000000', boundary='0010000000000000', session_value='1', comparison=1, overflow_code=-1722),
    'nchar': dict(canonical='CEA92020', boundary='CEA9CEA9CEA9', session_value='3', comparison=1, overflow_code=-12899),
    'raw': dict(canonical='00017FFF', boundary='FFFF', session_value='4', comparison=1, overflow_code=-1465),
    'timestamp-tz': dict(canonical='2026-09-01T12:00:00.123456', boundary='2027-01-01T00:30:00.000000', session_value='2026-09-01T17:30:00.123456', comparison=1, overflow_code=-1861),
    'timestamp-ltz': dict(canonical='2026-09-01T12:00:00.123456', boundary='2027-01-01T00:30:00.000000', session_value='2026-09-01T17:30:00.123456', comparison=1, overflow_code=-1861),
    'interval-ym': dict(canonical='14', boundary='1201', session_value='-14', comparison=1, overflow_code=-1867),
    'interval-ds': dict(canonical='93784', boundary='1', session_value='-93784', comparison=1, overflow_code=-1867),
}
DIAGNOSTICS = {
    'binary-float': (-1722, '22P02', 'invalid-floating-input'),
    'binary-double': (-1722, '22P02', 'invalid-floating-input'),
    'nchar': (-12899, '22001', 'character-length-overflow'),
    'raw': (-1465, '22023', 'invalid-hex-input'),
    'timestamp-tz': (-1861, '22007', 'invalid-datetime-format'),
    'timestamp-ltz': (-1861, '22007', 'invalid-datetime-format'),
    'interval-ym': (-1867, '22007', 'invalid-interval-input'),
    'interval-ds': (-1867, '22007', 'invalid-interval-input'),
}


def cases(root):
    corpus = json.loads((root / 'data-modernization/oracle-core-sql-coverage/core-sql-corpus.json').read_text(encoding='utf-8'))
    selected = [c for topic in FAMILIES for c in corpus['results'] if c['domain_id'] == 'types' and c['topic'] == topic]
    if len(selected) != 260 or len({c['id'] for c in selected}) != 260:
        raise ValueError('Types260 catalog scope changed')
    for topic in FAMILIES:
        family = [c for c in selected if c['topic'] == topic]
        if len(family) != 20 or len({c['behavior_id'] for c in family}) != 5:
            raise ValueError('Each family requires five behaviours and twenty cases')
    return selected


def probes(case):
    if case['topic'] in previous.FAMILIES:
        return previous.probes(case)
    focus = {'canonical semantics': ('canonical',), 'null and absence semantics': ('null_value',),
             'boundary and overflow semantics': ('boundary',),
             'session, ordering, and version semantics': ('session_value', 'comparison'),
             'failure and diagnostic semantics': ('overflow_code', 'recovery')}
    dimension = {'canonical': (), 'null-boundary': ('null_value',),
                 'session-version': ('session_value', 'comparison'), 'failure-recovery': ('overflow_code', 'recovery')}
    return tuple(sorted(set(focus[case['focus']] + dimension[case['dimension']])))


def expected(case, lane):
    if case['topic'] in previous.FAMILIES:
        return previous.expected(case, lane)
    values = {**EXPECTED[case['topic']], 'null_value': None, 'recovery': EXPECTED[case['topic']]['canonical']}
    if lane == 'alloydb':
        values['overflow_code'] = DIAGNOSTICS[case['topic']][1]
    return {p: values[p] for p in probes(case)}


def _expressions(topic, lane):
    """SQL expressions, deliberately independent of EXPECTED."""
    ora = lane == 'oracle'
    if topic in ('binary-float', 'binary-double'):
        single = topic == 'binary-float'
        typ = ('BINARY_FLOAT' if single else 'BINARY_DOUBLE') if ora else ('real' if single else 'double precision')
        encode = (lambda value: f'RAWTOHEX(UTL_RAW.CAST_FROM_{typ}(CAST({value} AS {typ}), UTL_RAW.BIG_ENDIAN))') if ora else (lambda value: f"upper(encode({'float4send' if single else 'float8send'}(CAST({value} AS {typ})), 'hex'))")
        nan = typ + '_NAN' if ora else f"CAST('NaN' AS {typ})"
        infinity = typ + '_INFINITY' if ora else f"CAST('Infinity' AS {typ})"
        return dict(canonical=encode('1.5'), null_value=encode('NULL'),
                    boundary=encode("'1.1754943508222875e-38'" if single else "'2.2250738585072014e-308'"),
                    session_value=f"CASE WHEN CAST('-0' AS {typ}) = CAST('0' AS {typ}) THEN '1' ELSE '0' END",
                    comparison=f'CASE WHEN {nan} = {nan} AND {nan} > {infinity} THEN 1 ELSE 0 END',
                    bad=f"TO_{typ}('not-a-number')" if ora else f"CAST('not-a-number' AS {typ})")
    if topic == 'raw':
        raw = (lambda value: f"HEXTORAW('{value}')") if ora else (lambda value: f"decode('{value}', 'hex')")
        enc = (lambda value: f'RAWTOHEX({value})') if ora else (lambda value: f"upper(encode({value}, 'hex'))")
        return dict(canonical=enc(raw('00017FFF')), null_value=enc('NULL'), boundary=enc(raw('FFFF')),
                    session_value=f"TO_CHAR(UTL_RAW.LENGTH({raw('00017FFF')}), 'FM9990')" if ora else f"octet_length({raw('00017FFF')})::text",
                    comparison=f"CASE WHEN {raw('00ff')} = {raw('00FF')} THEN 1 ELSE 0 END", bad=enc(raw('GG')))
    if topic in ('interval-ym', 'interval-ds'):
        ym = topic == 'interval-ym'
        value = ("INTERVAL '1-2' YEAR TO MONTH" if ym else "INTERVAL '1 02:03:04' DAY TO SECOND") if ora else ("INTERVAL '1 year 2 months'" if ym else "INTERVAL '1 day 2 hours 3 minutes 4 seconds'")
        def total(v):
            return f'(EXTRACT(YEAR FROM {v}) * 12 + EXTRACT(MONTH FROM {v}))' if ym else f'(EXTRACT(DAY FROM {v}) * 86400 + EXTRACT(HOUR FROM {v}) * 3600 + EXTRACT(MINUTE FROM {v}) * 60 + EXTRACT(SECOND FROM {v}))'
        fmt = (lambda v: f"TO_CHAR({v}, 'FM9999999990')")
        microsecond = "INTERVAL '0.000001' SECOND" if ora else "INTERVAL '0.000001 second'"
        boundary = total("INTERVAL '100-1' YEAR(3) TO MONTH" if ora else "INTERVAL '100 years 1 month'") if ym else f'EXTRACT(SECOND FROM {microsecond}) * 1000000'
        null = 'CAST(NULL AS INTERVAL YEAR TO MONTH)' if ym and ora else 'CAST(NULL AS INTERVAL DAY TO SECOND)' if ora else 'NULL::interval'
        negative = ("INTERVAL '-1-2' YEAR TO MONTH" if ym else "INTERVAL '-1 02:03:04' DAY TO SECOND") if ora else f'(-{value})'
        invalid = "TO_YMINTERVAL('invalid')" if ym else "TO_DSINTERVAL('invalid')"
        return dict(canonical=fmt(total(value)), null_value=fmt(total(null)), boundary=fmt(boundary), session_value=fmt(total(negative)),
                    comparison=f'CASE WHEN {value} > {negative if ora else "-" + value} THEN 1 ELSE 0 END',
                    bad=f'TO_CHAR({invalid})' if ora else "'invalid'::interval")
    raise ValueError('No expression contract for family')


def _body(case, lane, table):
    topic, ora = case['topic'], lane == 'oracle'
    if topic == 'nchar':
        # Adapt the already observed column-assignment contract; compare UTF-8
        # bytes so client output encodings cannot silently replace Unicode.
        body = previous._string_body('char', lane, table)
        if ora:
            body = body.replace('CHAR(3 CHAR)', 'NCHAR(3)').replace(' AS CHAR(3)', ' AS NCHAR(3)')
            body = body.replace("'ABCD'", "UNISTR('\\03A9\\03A9\\03A9\\03A9')").replace("'ABC'", "UNISTR('\\03A9\\03A9\\03A9')").replace("'A  '", "UNISTR('\\03A9  ')").replace("'A'", "UNISTR('\\03A9')")
            body += "\n  SELECT TO_CHAR(v_length, 'FM9990') INTO v_session_value FROM dual;"
            for p in ('canonical', 'boundary', 'recovery'):
                body += f"\n  SELECT RAWTOHEX(UTL_I18N.STRING_TO_RAW(v_{p}, 'AL32UTF8')) INTO v_{p} FROM dual;"
        else:
            body = body.replace("'ABCD'", "U&'\\03A9\\03A9\\03A9\\03A9'").replace("'ABC'", "U&'\\03A9\\03A9\\03A9'").replace("'A  '", "U&'\\03A9  '").replace("'A'", "U&'\\03A9'")
            body = body.replace("octet_length(U&'\\03A9'::char(3))", "length(rpad((U&'\\03A9'::char(3))::text, 3, ' '))")
            body += '\n v_session_value := v_length::text;'
            for p in ('canonical', 'boundary', 'recovery'):
                body += f"\n v_{p} := upper(encode(convert_to(v_{p}, 'UTF8'), 'hex'));"
        return body
    if topic in ('timestamp-tz', 'timestamp-ltz'):
        fmt = 'YYYY-MM-DD"T"HH24:MI:SS.' + ('FF6' if ora else 'US')
        if ora:
            local = 'LOCAL ' if topic == 'timestamp-ltz' else ''
            shown = 'v_zoned' if local else '(v_zoned AT LOCAL)'
            return f""" EXECUTE IMMEDIATE 'ALTER SESSION SET TIME_ZONE = ''+00:00''';
 SELECT CAST(TO_TIMESTAMP_TZ('2026-09-01 17:30:00.123456 +05:30', 'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM') AS TIMESTAMP WITH {local}TIME ZONE) INTO v_zoned FROM dual;
 SELECT TO_CHAR(SYS_EXTRACT_UTC(v_zoned), '{fmt}'), TO_CHAR(CAST(NULL AS TIMESTAMP), '{fmt}'),
 TO_CHAR(SYS_EXTRACT_UTC(TO_TIMESTAMP_TZ('2026-12-31 23:30:00 -01:00', 'YYYY-MM-DD HH24:MI:SS TZH:TZM')), '{fmt}'),
 CASE WHEN v_zoned = TO_TIMESTAMP_TZ('2026-09-01 12:00:00.123456 +00:00', 'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM') THEN 1 ELSE 0 END
 INTO v_canonical, v_null_value, v_boundary, v_comparison FROM dual;
 BEGIN
 SELECT TO_CHAR(TO_TIMESTAMP_TZ('2026x09x01 12:00:00 +00:00', 'FXYYYY-MM-DD HH24:MI:SS TZH:TZM'), '{fmt}') INTO v_sink FROM dual;
 EXCEPTION WHEN OTHERS THEN v_overflow_code := SQLCODE;
 END;
 SELECT TO_CHAR(SYS_EXTRACT_UTC(v_zoned), '{fmt}') INTO v_recovery FROM dual;
 EXECUTE IMMEDIATE 'ALTER SESSION SET TIME_ZONE = ''+05:30''';
 SELECT TO_CHAR({shown}, '{fmt}') INTO v_session_value FROM dual;"""
        return f""" v_zoned := TIMESTAMPTZ '2026-09-01 17:30:00.123456 +05:30';
 SELECT to_char(v_zoned AT TIME ZONE 'UTC', '{fmt}'), to_char(NULL::timestamptz, '{fmt}'),
 to_char(TIMESTAMPTZ '2026-12-31 23:30:00 -01:00' AT TIME ZONE 'UTC', '{fmt}'),
 CASE WHEN v_zoned = TIMESTAMPTZ '2026-09-01 12:00:00.123456 +00:00' THEN 1 ELSE 0 END
 INTO v_canonical, v_null_value, v_boundary, v_comparison;
 BEGIN
 v_sink := ('2026x09x01 12:00:00 +00:00'::timestamptz)::text;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 v_recovery := to_char(v_zoned AT TIME ZONE 'UTC', '{fmt}');
 SET LOCAL TIME ZONE INTERVAL '+05:30' HOUR TO MINUTE;
 v_session_value := to_char(v_zoned, '{fmt}');"""
    expr = _expressions(topic, lane)
    fields = ('canonical', 'null_value', 'boundary', 'session_value', 'comparison')
    select = ', '.join(expr[p] for p in fields)
    into = ', '.join('v_' + p for p in fields)
    if ora:
        return f""" SELECT {select} INTO {into} FROM dual;
 BEGIN
 SELECT {expr['bad']} INTO v_sink FROM dual;
 EXCEPTION WHEN OTHERS THEN v_overflow_code := SQLCODE;
 END;
 SELECT {expr['canonical']} INTO v_recovery FROM dual;"""
    return f""" SELECT {select} INTO {into};
 BEGIN
 v_sink := ({expr['bad']})::text;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT {expr['canonical']} INTO v_recovery;"""


def render(case, lane):
    if lane not in ('oracle', 'alloydb') or case['topic'] not in FAMILIES:
        raise ValueError('Unknown native lane/family')
    if case['topic'] in previous.FAMILIES:
        return previous.render(case, lane)
    if not re.fullmatch(r'ORA-TYPE-[0-9]{3}-CASE-0[1-4]', case['id']):
        raise ValueError('Unsafe catalog identifier')
    body = _body(case, lane, 'LY_' + case['id'].replace('-', '_'))
    names = ('canonical', 'null_value', 'boundary', 'recovery', 'session_value', 'sink')
    if lane == 'oracle':
        declarations = '\n'.join(f' v_{p} VARCHAR2(128);' for p in names)
        fields = ', '.join(f"'{p}' VALUE v_{p}" for p in probes(case))
        zone = 'LOCAL ' if case['topic'] == 'timestamp-ltz' else ''
        return f"""-- Synthetic bounded catalog case {case['id']}; Oracle 26ai.
DECLARE
{declarations}
 v_zoned TIMESTAMP WITH {zone}TIME ZONE;
 v_length NUMBER; v_comparison NUMBER; v_overflow_code NUMBER := 0; v_json VARCHAR2(4000);
BEGIN
{body}
 SELECT JSON_OBJECT('case_id' VALUE '{case['id']}', 'observations' VALUE
 JSON_OBJECT({fields} NULL ON NULL) RETURNING VARCHAR2(4000)) INTO v_json FROM dual;
 DBMS_OUTPUT.PUT_LINE('{MARKER}' || v_json);
END;
/
"""
    declarations = '\n'.join(f' v_{p} text;' for p in names)
    fields = ', '.join(f"'{p}', v_{p}" for p in probes(case))
    return f"""-- Synthetic bounded catalog case {case['id']}; AlloyDB PostgreSQL.
BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL TIME ZONE 'UTC';
SET LOCAL DateStyle = 'ISO, YMD';
DO $pilot$
DECLARE
{declarations}
 v_zoned timestamptz;
 v_length integer; v_comparison integer; v_overflow_code text := '00000';
BEGIN
{body}
 RAISE NOTICE '{MARKER}%', json_build_object('case_id', '{case['id']}', 'observations', json_build_object({fields}));
END $pilot$;
ROLLBACK;
"""


def parse(output, case, lane):
    if case['topic'] in previous.FAMILIES:
        return previous.parse(output, case, lane)
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
    if case['topic'] in previous.FAMILIES:
        return previous.compare(case, source, target)
    a, b = expected(case, 'oracle'), expected(case, 'alloydb')
    exact = lambda observed, wanted: observed == wanted and all(type(observed[k]) is type(wanted[k]) for k in wanted)
    differences = []
    for p in probes(case):
        equal = type(source.get(p)) is type(target.get(p)) and source.get(p) == target.get(p)
        if p == 'overflow_code':
            equal = type(source.get(p)) is int and source[p] == DIAGNOSTICS[case['topic']][0] and target.get(p) == DIAGNOSTICS[case['topic']][1]
        if not equal:
            differences.append(dict(probe=p, oracle=source.get(p), alloydb=target.get(p)))
    source_ok, target_ok = exact(source, a), exact(target, b)
    return dict(case_id=case['id'], source_expectations_met=source_ok, target_expectations_met=target_ok,
                equivalent=source_ok and target_ok and not differences, differences=differences,
                diagnostic_mapping=list(DIAGNOSTICS[case['topic']]) if 'overflow_code' in probes(case) else None)


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
                raise ValueError('Types260 SQL binding drift: ' + case['id'])


def bound_render(root, case, lane, authorized_plan):
    """Only the exact retired signed plan can use the archived interval SQL."""
    if (authorized_plan['plan_sha256'] == RETIRED_PLAN and lane == 'oracle'
            and case['topic'] in ('interval-ym', 'interval-ds')):
        path = root / ARTIFACTS / 'retired-v1/oracle' / (case['id'] + '.sql')
        if path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError('Invalid retired SQL contract')
        return path.read_text(encoding='utf-8')
    return render(case, lane)


def plan(root):
    verify(root)
    # Reuse the operational policy, never the historical scope or profile.
    config = paired_number.profile(root, PROFILE)
    sources = ['lightyear_workflow/' + name for name in ('paired_types260.py', 'paired_types.py', 'paired_number.py', 'campaign_engine.py', 'campaign_gcp.py', 'campaign_journals.py')]
    sources.append('lightyear_data/oracle_number_native.py')
    body = dict(campaign_id=CAMPAIGN, name=NAME, project=paired_number.PROJECT, region=paired_number.REGION,
                profile=config, contract_revision=2, journal_layout='family-v1', families=list(EXECUTION_FAMILIES),
                implementation={name: hashlib.sha256((root / 'src' / name).read_bytes()).hexdigest() for name in sources},
                cases=[dict(id=c['id'], behavior_id=c['behavior_id'], family=c['topic'],
                            catalog_expectation_sha256=digest(c['expected']),
                            probe_contract_sha256=digest({lane: expected(c, lane) for lane in ('oracle', 'alloydb')}),
                            **{lane + '_sql_sha256': hashlib.sha256(render(c, lane).encode()).hexdigest() for lane in ('oracle', 'alloydb')}) for c in cases(root)],
                alloydb_cluster='cloudbank-ms71-alloydb', alloydb_instance='primary',
                resource_policy='One owned ephemeral runner; resume only stopped AlloyDB primary. Delete owned runner/firewall/disk and restore AlloyDB STOPPED.',
                data_policy='Synthetic data only; disposable Oracle tables and session-local PostgreSQL temporary tables. Target transactions roll back; no application data or permanent target objects.',
                identity_policy='Pinned Oracle 26ai image/FREEPDB1 and fresh fixed-resource PostgreSQL 16 AlloyDB endpoint. Unknown metadata remains unknown.',
                comparison_policy='100 prior probes unchanged. New probes compare exact float bits, UTF-8 character bytes, RAW hex, UTC instants/session display, signed interval units and explicitly mapped invalid-input diagnostics. No comparator tolerance, trimming or null rewriting.',
                cost_policy='Estimated incremental budget; 60-minute active runtime guard, not a billing cap. Cleanup may take additional time. Existing storage charges continue.',
                interruption_policy='Signed per-family journals/checkpoints. No automatic SQL replay; retain failures and clean resources before another launch.',
                qualification='260 bounded pairs / 13 datatype families / 65 behaviours, Oracle 26ai only. 100 regression plus 160 new cases, deduplicated. No exhaustive datatype, DST/region retention, Oracle 19c, application or additional platform qualification.')
    return {**body, 'plan_sha256': digest(body)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('materialize', 'verify'))
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    (materialize if args.command == 'materialize' else verify)(args.root.resolve())
    print('260 case pairs: SQL ' + args.command + ' complete; no database executed')
