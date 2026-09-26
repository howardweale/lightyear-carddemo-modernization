import json,pathlib,oracledb,hashlib
from lightyear_calibration.native_catalog import capture,project_capture
r=pathlib.Path('work/native-run-20260925');s=json.loads((r/'private.json').read_text())
with oracledb.connect(user='adempiere',password=s['password'],dsn='127.0.0.1:'+str(s['containers']['oracle']['port'])+'/FREEPDB1') as c:
 c.call_timeout=60000
 with c.cursor() as q:q.execute('SET TRANSACTION READ ONLY')
 v=capture(c,'oracle',{'seed_sha256':'a98f32665e1926b858e8dcc10f2c535dde8a5441f9792b2b26a3124ce333234b','image':s['images']['oracle'],'import_log_sha256':hashlib.sha256((r/'oracle-import.log').read_bytes()).hexdigest(),'import_returncode':5,'accepted_import_errors':['ORA-31684 USER ADEMPIERE already exists (pre-created by bootstrap)'],'post_import_log_sha256':hashlib.sha256((r/'oracle-after-import.log').read_bytes()).hexdigest(),'post_import_returncode':0})
 (r/'oracle-catalog.json').write_text(json.dumps(v,indent=2),encoding='utf-8')
 p=project_capture(v)
 print(json.dumps({'objects':len(p['tables']),'columns':sum(len(t['columns']) for t in p['tables'].values()),'session':p['session'],'catalog_sha256':v['content_sha256'],'version':v['results']['version']['rows']}))
 c.rollback()
