"""Native lane operations executed inside the private, offline runner container."""
from __future__ import annotations
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .contracts import canonical, require, seal, verify
from .native_catalog import query, capture
from .native_effects import capture_rows
from .schema_constraint_probes import run_lane


def connect(lane,password):
    if lane=='oracle':
        import oracledb
        oracledb.defaults.fetch_decimals=True
        c=oracledb.connect(user='adempiere',password=password,dsn='oracle:1521/FREEPDB1')
        c.call_timeout=180000
        with c.cursor() as cur:cur.execute("alter session set time_zone='UTC'")
        return c
    import psycopg
    c=psycopg.connect(host='postgresql',port=5432,user='adempiere',password=password,dbname='idempiere',autocommit=True)
    c.execute('SET search_path TO adempiere,pg_catalog');c.execute("SET TIME ZONE 'UTC'")
    return c


def observe(lane,password,folder):
    with connect(lane,password) as c:
        with c.cursor() as cursor:cursor.execute('SET TRANSACTION READ ONLY' if lane=='oracle' else 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        result=capture_rows(c,lane,folder);c.rollback();return result


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(canonical(value))


def prepare(spec):
    lane=spec['lane'];password=spec['password'];out=Path(spec['output']);inputs=Path('/output/inputs')
    out.mkdir(parents=True,exist_ok=True)
    before=observe(lane,password,out/'before')
    expected=json.loads((inputs/(lane+'-entry-multisets.json')).read_bytes())
    require({t:v['row_multiset'] for t,v in before['tables'].items()} == expected, 'entry-state-mismatch')
    repairs=json.loads((inputs/(lane+'-repairs.json')).read_bytes());verify(repairs)
    with connect(lane,password) as c:
        with c.cursor() as cursor:
            for change in repairs['changes']:cursor.execute(change['sql'])
        c.commit()
    # Oracle DATE-resolution DDL timestamps can otherwise make an immediate
    # read-only snapshot fail ORA-01466. The original MS85/MS86 capture waited
    # across this boundary as well; no migration is reexecuted.
    if lane=='oracle':time.sleep(2)
    after=observe(lane,password,out/'after')
    require({t:v['row_multiset'] for t,v in after['tables'].items()} == expected, 'Schema repair changed starting rows')
    with connect(lane,password) as c:
        checkpoint=json.loads((inputs/'checkpoint.json').read_bytes());verify(checkpoint)
        cat=capture(c,lane,{'ms84_checkpoint_sha256':checkpoint['content_sha256'],'state_sha256':after['content_sha256']})
        version=query(c,"SELECT version_full value FROM product_component_version WHERE product LIKE 'Oracle%'" if lane=='oracle' else "SELECT current_setting('server_version') value")[0]['value']
        require(version.startswith(spec['expected_version']), 'Native database version differs')
        probes=run_lane(c,lane,isolated_test_copy=True,catalog_sha256=cat['content_sha256'])
    write(out/'catalog.json',cat);write(out/'probes.json',probes)
    # Probe assertions must leave the entire database unchanged, not only their
    # selected rows. Capture again before the application is permitted to run.
    entry=observe(lane,password,out/'entry')
    require({t:v['row_multiset'] for t,v in entry['tables'].items()} == expected, 'Constraint probes changed starting rows')
    result=seal({'lane':lane,'version':version,'before_sha256':before['content_sha256'],
                 'after_sha256':after['content_sha256'],'entry_sha256':entry['content_sha256'],
                 'repair_sha256':repairs['content_sha256'],'catalog_sha256':cat['content_sha256'],
                 'probe_sha256':probes['content_sha256'],'row_multisets_equal_checkpoint':True})
    write(out/'entry.json',result);return result


def clock(lane,password):
    sql="SELECT to_char(systimestamp AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.FF6TZH:TZM') value FROM dual" if lane=='oracle' else 'SELECT clock_timestamp()::text value'
    with connect(lane,password) as c:return {'value':query(c,sql)[0]['value'],'sql':sql}


def execute(spec):
    lane=spec['lane'];password=spec['password'];out=Path(spec['output']);out.mkdir(parents=True,exist_ok=False)
    harness=Path(spec['harness']).read_bytes()
    require(hashlib.sha256(harness).hexdigest()==spec['harness_sha256'],'Harness differs from approved plan')
    test=spec['test'];require(test in ('LightyearBoundaryTest','LightyearOperationsTest','LightyearPartialInvoiceTest'),'Unknown native test')
    target=Path('/application/org.idempiere.test/src/org/idempiere/test')/(test+'.java')
    target.write_bytes(harness);(out/'harness.java').write_bytes(harness)
    props=Path('/secrets/application.properties')
    name='FREEPDB1' if lane=='oracle' else 'idempiere';port=1521 if lane=='oracle' else 5432
    conn=f'CConnection[name=Lightyear isolated,type={"Oracle" if lane=="oracle" else "PostgreSQL"},DBhost={lane},DBport={port},DBname={name},UID=adempiere,PWD={password}]'
    props.write_text('Connection='+conn+'\nTraceLevel=WARNING\nTraceFile=N\nToday=2026-09-26\n',encoding='ascii');props.chmod(0o600)
    with connect(lane,password) as c:
        native_name=query(c,"SELECT LOWER(SYS_CONTEXT('USERENV','CURRENT_USER') || '.' || SYS_CONTEXT('USERENV','DB_NAME') || '.' || SYS_CONTEXT('USERENV','DB_DOMAIN')) value FROM dual")[0]['value'] if lane=='oracle' else None
    facts={'native_database_instance':native_name,'expected_database_address':
           'jdbc:oracle:thin:@//oracle:1521/freepdb1' if lane=='oracle' else
           'jdbc:postgresql://postgresql:5432/idempiere?encoding=unicode&applicationname=idempiere&stringtype=unspecified&tcpkeepalive=true'}
    before=clock(lane,password);started=time.monotonic();raw=Path('/secrets/maven.log')
    args=['mvn','-o','-B','verify','-DskipTests=false','-Dtest='+test,'-DfailIfNoTests=false',
          '-DmaterializeProduct=none','-DassembleRepository=none',
          f'-Dp1=-DPropertyFile={props} -Dlightyear.output={out/"journey.xml"} -Duser.timezone=UTC -Djunit.jupiter.execution.parallel.enabled=false']
    try:
        with raw.open('wb') as stream:
            process=subprocess.run(args,cwd='/application',stdout=stream,stderr=subprocess.STDOUT,timeout=spec['timeout_seconds'])
        code=process.returncode
    except subprocess.TimeoutExpired:
        code=124
    finally:
        props.unlink(missing_ok=True)
    log=raw.read_text(errors='replace').replace(password,'[redacted]');raw.unlink()
    (out/'maven.log').write_text(log,encoding='utf-8')
    result=seal({'lane':lane,'runtime_facts':facts,'exit_code':code,'elapsed_seconds':round(time.monotonic()-started,1),
                 'native_clock_before':before,'native_clock_after':clock(lane,password),
                 'harness_sha256':spec['harness_sha256'],'application_source_commit':spec['source_commit'],
                 'journey_output_exists':(out/'journey.xml').exists(),'offline_maven':True})
    write(out/'execution.json',result)
    return result


def main():
    spec=json.load(sys.stdin);password=spec['password']
    try:
        command=sys.argv[1]
        if command=='prepare':result=prepare(spec)
        elif command=='execute':result=execute(spec)
        elif command=='capture':result=observe(spec['lane'],password,Path(spec['output']));result={'content_sha256':result['content_sha256']}
        elif command=='probe':
            with connect(spec['lane'],password) as c:result={'connected':True}
        else:raise ValueError('Unknown worker command')
        print(json.dumps(result,ensure_ascii=True))
    except Exception as exc:
        import traceback
        print(json.dumps({'error_type':type(exc).__name__,'error':str(exc).replace(password,'[redacted]'),
                          'traceback':traceback.format_exc().replace(password,'[redacted]')}))
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
