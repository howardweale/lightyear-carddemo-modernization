from pathlib import Path
import importlib.util,json,subprocess,hashlib,re
from lightyear_calibration.native_catalog import query
from lightyear_calibration.contracts import seal
r=Path('work/native-run-20260925');s=json.loads((r/'private.json').read_text())
spec=importlib.util.spec_from_file_location('snapshots','work/native-snapshots.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
queries={
 'oracle':{
  'invalid_objects':"SELECT object_name,object_type,status FROM user_objects WHERE status<>'VALID'",
  'errors':'SELECT name,type,line,position,text FROM user_errors',
  'disabled_constraints':"SELECT table_name,constraint_name,status FROM user_constraints WHERE status<>'ENABLED'",
  'disabled_triggers':"SELECT trigger_name,status FROM user_triggers WHERE status<>'ENABLED'",
  'register':"SELECT name,filename,status,isapply FROM ad_migrationscript",
 },
 'postgresql':{
  'invalid_indexes':"SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='adempiere' AND (NOT i.indisvalid OR NOT i.indisready)",
  'unvalidated_constraints':"SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='adempiere' AND NOT convalidated",
  'disabled_triggers':"SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='adempiere' AND t.tgenabled='D'",
  'register':"SELECT name,filename,status,isapply FROM adempiere.ad_migrationscript",
 }}
result={}
plan=json.loads((r/'native-migrations/execution-plan.json').read_text())
for lane,checks in queries.items():
 with m.connect(lane) as c:
  values={k:query(c,sql) for k,sql in checks.items()}
  registry=values.pop('register')
  applied={str(v['filename']).replace('\\','/').split('/')[-1] for v in registry if v['status']=='CO' and v['isapply']=='Y'}
  values['executed_scripts_registered']={p['pair_id']:Path(p[lane]['path']).name in applied for p in plan['pairs']}
  values['query_sha256']={k:hashlib.sha256(v.encode()).hexdigest() for k,v in checks.items()}
  result[lane]=values
logs=[]
for path in sorted((r/'native-migrations').glob('case-*/*-execution.log')):
 text=path.read_text(encoding='utf-8');assert s['password'] not in text
 logs.append({'path':path.relative_to(r).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'error_or_warning_lines':[line for line in text.splitlines() if re.search(r'ORA-|SP2-|\bERROR\b|\bWARNING\b',line,re.I)]})
result=seal({'artifact_type':'lightyear-native-migration-final-checks','checks':result,'client_logs':logs,'scope':'native database validity and registration checks after 20 pairs; not application validation'})
(r/'native-migrations/final-checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'checks':result['checks'],'logs_checked':len(logs),'error_logs':sum(bool(v['error_or_warning_lines']) for v in logs)}))
