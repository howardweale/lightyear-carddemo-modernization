"""Read-only native boundary probes for the observed Oracle/PostgreSQL schema.

These probes expose differences, not a full datatype proof. Known rejections
are comparable only through named error classes; arbitrary failures never pass.
"""
from datetime import datetime, timezone
import time

from .contracts import canonical, digest, require, seal, verify
from .native_catalog import capture, query
from .schema_equivalence import rows


def definitions():
    cases=[]
    def add(name, family, oracle, postgresql):
        cases.append({'id':name,'family':family,'sql':{'oracle':'SELECT '+oracle+' value FROM dual',
                                                    'postgresql':'SELECT '+postgresql+' AS value'}})
    for name,value in [('zero','0'),('maximum','9999999999'),('minimum','-9999999999'),
                       ('round-positive','1.5'),('round-negative','-1.5'),
                       ('overflow-positive','10000000000'),('overflow-negative','-10000000000')]:
        add('number10-'+name,'number10',f'CAST({value} AS NUMBER(10,0))',f'CAST({value} AS numeric(10,0))')
    huge='12345678901234567890123456789012345678901234567890'
    add('unbounded-number-50-digits','unbounded-number',f'CAST({huge} AS NUMBER)',f'CAST({huge} AS numeric)')
    for name,value in [('empty',''),('plain','ABC'),('unicode','é')]:
        add('varchar-'+name,'varchar',f"CAST('{value}' AS VARCHAR2(10 CHAR))",f"CAST('{value}' AS varchar(10))")
    for name,value in [('ascii','Y'),('unicode','é')]:
        add('char1-'+name,'char-byte',f"CAST('{value}' AS CHAR(1 BYTE))",f"CAST('{value}' AS char(1))")
    for name,value in [('seconds','2026-09-26 12:34:56'),('fraction','2026-09-26 12:34:56.123456')]:
        add('timestamp-'+name,'timestamp',
            f"TO_CHAR(CAST(TIMESTAMP '{value}' AS DATE),'YYYY-MM-DD HH24:MI:SS')",
            f"to_char(TIMESTAMP '{value}','YYYY-MM-DD HH24:MI:SS') || CASE WHEN EXTRACT(MICROSECONDS FROM TIMESTAMP '{value}')::bigint % 1000000 = 0 THEN '' ELSE '.' || to_char(TIMESTAMP '{value}','US') END")
    for name,value in [('valid','550e8400-e29b-41d4-a716-446655440000'),('invalid','not-a-uuid')]:
        add('uuid-'+name,'uuid',f"CAST('{value}' AS VARCHAR2(36 CHAR))",f"CAST(CAST('{value}' AS uuid) AS text)")
    for name,value in [('valid','{"a":1}'),('invalid','not-json')]:
        add('json-'+name,'json',f"TO_CLOB('{value}')",f"CAST(CAST('{value}' AS json) AS text)")
    add('jsonb-duplicate-key','jsonb',"TO_CLOB('{\"a\":1,\"a\":2}')", "CAST(CAST('{\"a\":1,\"a\":2}' AS jsonb) AS text)")
    return cases


ERROR_CLASSES = {'oracle': {1438:'numeric-overflow',12899:'character-overflow',25137:'character-overflow'},
                 'postgresql': {'22003':'numeric-overflow','22001':'character-overflow','22P02':'invalid-typed-input'}}


def outcome(connection, lane, sql):
    if lane=='postgresql':
        with connection.cursor() as c:c.execute('SAVEPOINT lightyear_schema_probe')
    try:
        result=query(connection,sql)
        require(len(result)==1 and set(result[0])=={'value'},'Probe returned an unexpected shape')
        return {'status':'observed-value','value':result[0]['value']}
    except Exception as exc:
        code=getattr(exc.args[0],'code',None) if lane=='oracle' and exc.args else getattr(exc,'sqlstate',None)
        kind=ERROR_CLASSES[lane].get(code)
        return {'status':'observed-rejection' if kind else 'probe-error','native_code':code,
                'error_class':kind,'exception_type':type(exc).__name__}
    finally:
        if lane=='postgresql':
            with connection.cursor() as c:
                c.execute('ROLLBACK TO SAVEPOINT lightyear_schema_probe')
                c.execute('RELEASE SAVEPOINT lightyear_schema_probe')


def compare_outcomes(left,right):
    if 'probe-error' in (left['status'],right['status']):return 'inconclusive'
    if left['status']==right['status']=='observed-value':
        return 'observed-match' if canonical(left['value'])==canonical(right['value']) else 'observed-difference'
    if left['status']==right['status']=='observed-rejection' and left['error_class']==right['error_class']:
        return 'observed-matching-rejection'
    return 'observed-difference'


def validate_outcome(value, lane):
    require(isinstance(value, dict), 'Missing probe outcome')
    status = value.get('status')
    require(status in ('observed-value', 'observed-rejection', 'probe-error'), 'Unknown probe outcome')
    if status == 'observed-value':
        require('value' in value, 'Missing observed value')
    elif status == 'observed-rejection':
        kind = ERROR_CLASSES[lane].get(value.get('native_code'))
        require(kind is not None and kind == value.get('error_class'), 'Unrecognized rejection cannot count as a match')


def run_lane(connection,lane,baseline_binding):
    require(lane in ('oracle','postgresql'),'Unknown probe lane')
    with connection.cursor() as c:
        c.execute('SET TRANSACTION READ ONLY' if lane=='oracle' else 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
    observed=capture(connection,lane,baseline_binding)
    records=[]
    for case in definitions():
        records.append({'case_id':case['id'],'family':case['family'],'sql_sha256':digest(case['sql'][lane]),
                        'outcome':outcome(connection,lane,case['sql'][lane])})
    clock_sql=("SELECT TO_CHAR(SYSDATE,'YYYY-MM-DD HH24:MI:SS') value FROM dual" if lane=='oracle'
               else "SELECT to_char(now(),'YYYY-MM-DD HH24:MI:SS.US') value")
    first=query(connection,clock_sql)[0]['value'];time.sleep(1.3);second=query(connection,clock_sql)[0]['value']
    connection.rollback()
    result=seal({'artifact_type':'lightyear-native-schema-probe-lane','lane':lane,
        'evidence_class':'native-database-observation','independently_attested':False,
        'observed_at':datetime.now(timezone.utc).isoformat(),'catalog_sha256':observed['content_sha256'],
        'plan_sha256':digest(definitions()),'cases':records,
        'clock_observation':{'sql':clock_sql,'before':first,'after':second,'changed_within_one_transaction':first!=second},
        'schema_equivalence':False,'application_equivalence':False})
    return observed,result


def compare_lanes(lanes, catalogs):
    require(set(lanes)=={'oracle','postgresql'},'Both native probe lanes required')
    require(set(catalogs)==set(lanes), 'Both probe-session catalogs required')
    planned=definitions();expected={x['id']:x for x in planned};observations={}
    bindings = []
    for lane,receipt in lanes.items():
        verify(receipt)
        require(receipt.get('artifact_type')=='lightyear-native-schema-probe-lane', 'Wrong probe artifact')
        require(receipt['lane']==lane and receipt['evidence_class']=='native-database-observation','Mislabeled or non-native probe evidence')
        catalog = catalogs[lane]
        rows(catalog)
        require(catalog['lane']==lane and receipt['catalog_sha256']==catalog['content_sha256'], 'Probe catalog binding mismatch')
        bindings.append(catalog.get('import_binding', {}).get('ms84_checkpoint_sha256'))
        require(receipt['plan_sha256']==digest(planned),'Probe plan mismatch')
        require(len(receipt['cases'])==len(expected),'Incomplete probe cases')
        records={}
        for case in receipt['cases']:
            name=case['case_id'];require(name in expected and name not in records,'Unknown or repeated probe case')
            require(case['sql_sha256']==digest(expected[name]['sql'][lane]),'Probe SQL mismatch')
            require(case['family']==expected[name]['family'], 'Probe family mismatch')
            validate_outcome(case['outcome'], lane)
            records[name]=case['outcome']
        observations[lane]=records
    require(bindings[0] and bindings[0]==bindings[1], 'Probe lanes have different baseline lineage')
    cases=[{'case_id':name,'status':compare_outcomes(observations['oracle'][name],observations['postgresql'][name]),
            'oracle':observations['oracle'][name],'postgresql':observations['postgresql'][name]} for name in expected]
    return seal({'artifact_type':'lightyear-native-schema-boundary-comparison','cases':cases,
                 'counts':{status:sum(x['status']==status for x in cases) for status in
                           ('observed-match','observed-matching-rejection','observed-difference','inconclusive')},
                 'paired_cases':len(cases),'lane_receipt_sha256':{k:v['content_sha256'] for k,v in lanes.items()},
                 'catalog_sha256':{k:v['content_sha256'] for k,v in catalogs.items()},
                 'baseline_checkpoint_sha256':bindings[0],
                 'evidence_class':'native-database-observation','independently_attested':False,
                 'clock_observations':{k:v['clock_observation'] for k,v in lanes.items()},
                 'schema_equivalence':False,'application_equivalence':False,
                 'scope':'Observed boundary cases only; no unrestricted datatype, schema or application equivalence claim'})
