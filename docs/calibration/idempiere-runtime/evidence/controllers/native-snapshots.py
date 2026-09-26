from pathlib import Path
import json,oracledb,psycopg,concurrent.futures,time
from lightyear_calibration.native_effects import capture_rows
r=Path('work/native-run-20260925');s=json.loads((r/'private.json').read_text())
oracledb.defaults.fetch_decimals=True

def connect(lane):
 if lane=='oracle':
  c=oracledb.connect(user='adempiere',password=s['password'],dsn='127.0.0.1:'+str(s['containers'][lane]['port'])+'/FREEPDB1');c.call_timeout=120000;return c
 return psycopg.connect(host='127.0.0.1',port=s['containers'][lane]['port'],dbname='idempiere',user='adempiere',password=s['password'],autocommit=True)
def snapshot(lane,path):
 start=time.monotonic()
 with connect(lane) as c:
  with c.cursor() as q:q.execute('SET TRANSACTION READ ONLY' if lane=='oracle' else 'BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
  result=capture_rows(c,lane,path);c.rollback()
 print(json.dumps({'lane':lane,'snapshot':str(path),'tables':len(result['tables']),'rows':sum(t['rows'] for t in result['tables'].values()),'elapsed_seconds':round(time.monotonic()-start,1)}),flush=True)
 return result
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor() as p:
  fs=[p.submit(snapshot,lane,r/'native-migrations'/'entry'/lane) for lane in ('oracle','postgresql')]
  results=[f.result() for f in fs]
