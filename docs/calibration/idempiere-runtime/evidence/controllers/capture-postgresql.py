import json,pathlib,psycopg,hashlib
from lightyear_calibration.native_catalog import capture,project_capture
r=pathlib.Path('work/native-run-20260925');s=json.loads((r/'private.json').read_text())
with psycopg.connect(host='127.0.0.1',port=s['containers']['postgresql']['port'],dbname='idempiere',user='adempiere',password=s['password'],autocommit=True) as c:
 c.execute('ALTER ROLE adempiere SET search_path TO adempiere, pg_catalog')
 c.execute('SET search_path TO adempiere, pg_catalog')
 c.execute('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
 v=capture(c,'postgresql',{'seed_sha256':'f6e5f409791c9eb576caf3c36e0bf9747d59d261ff9bdd743e55fcb125b21b9c','image':s['images']['postgresql'],'import_log_sha256':hashlib.sha256((r/'postgresql-import.log').read_bytes()).hexdigest(),'import_returncode':0})
 (r/'postgresql-catalog.json').write_text(json.dumps(v,indent=2),encoding='utf-8')
 p=project_capture(v)
 print(json.dumps({'tables':len(p['tables']),'columns':sum(len(t['columns']) for t in p['tables'].values()),'session':p['session'],'catalog_sha256':v['content_sha256']}))
 c.rollback()
