from pathlib import Path
import importlib.util,json,subprocess,hashlib,concurrent.futures,time
from lightyear_calibration.native_effects import compare_observations
from lightyear_common.io import normalize_logical_source
from lightyear_calibration.contracts import seal
spec=importlib.util.spec_from_file_location('snap','work/native-snapshots.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=m.r;src=Path('work/idempiere-upstream');out=r/'native-migrations';s=m.s
before={'oracle':json.loads((out/'case-011/oracle-observation-retry/state.json').read_text()),'postgresql':json.loads((out/'case-011/postgresql/state.json').read_text())}
op=json.loads((r/'oracle-pending.json').read_text());pp=json.loads((r/'postgresql-pending.json').read_text());oids={p['pair_id'] for p in op}
pairs=sorted([p for p in pp if p['pair_id'] in oids and 'processes_post_migration' not in p['postgresql']['path']],key=lambda p:p['postgresql']['path'])
assert len(pairs)==20
plan=json.loads((out/'execution-plan.json').read_text());assert plan['pairs']==pairs
for lane,c in s['containers'].items():
 info=json.loads(subprocess.check_output(['docker','inspect',c['id']],text=True))[0]
 assert info['Config']['Labels']['lightyear.run']==s['run_id']
def execute(lane,pair,case):
 raw=(src/pair[lane]['path']).read_bytes();assert hashlib.sha256(normalize_logical_source(raw)).hexdigest()==pair[lane]['logical_sha256']
 name=s['containers'][lane]['name'];target='/tmp/ly-pair-'+case.name+'.sql'
 subprocess.run(['docker','cp',str(src/pair[lane]['path']),name+':'+target],check=True,capture_output=True)
 if lane=='oracle':
  wrapper="whenever oserror exit failure\nwhenever sqlerror exit failure rollback\nset define off\nset sqlblanklines on\nset linesize 32767\nset pagesize 0\nconnect adempiere/"+s['password']+"@FREEPDB1\nalter session set time_zone='UTC';\nselect json_object('current_schema' value sys_context('USERENV','CURRENT_SCHEMA'), 'time_zone' value sessiontimezone, 'numeric_characters' value (select value from nls_session_parameters where parameter='NLS_NUMERIC_CHARACTERS')) from dual;\n@"+target+"\ncommit;\nexit success\n"
  cmd=['docker','exec','-i','-e','NLS_LANG=.AL32UTF8',name,'sqlplus','-s','/nolog']
 else:
  wrapper="\\set ON_ERROR_STOP on\nSET TIME ZONE 'UTC';\nSELECT json_build_object('current_schema', current_schema(), 'search_path',current_setting('search_path'),'time_zone',current_setting('TimeZone'),'standard_conforming_strings',current_setting('standard_conforming_strings'));\n\\i "+target+'\n'
  cmd=['docker','exec','-i',name,'psql','-X','-U','adempiere','-d','idempiere']
 start=time.monotonic();p=subprocess.run(cmd,input=wrapper.encode(),capture_output=True,timeout=180)
 log=(p.stdout+p.stderr).decode(errors='replace').replace(s['password'],'[redacted]');(case/(lane+'-execution.log')).write_text(log,encoding='utf-8')
 result={'returncode':p.returncode,'source_path':pair[lane]['path'],'source_sha256':pair[lane]['logical_sha256'],'native_client':'sqlplus' if lane=='oracle' else 'psql','duration_seconds':round(time.monotonic()-start,3),'log_sha256':hashlib.sha256(log.encode()).hexdigest()}
 return result
results=json.loads((out/'progress.json').read_text());assert len(results)==11
for ordinal,pair in enumerate(pairs[11:],12):
 case=out/f'case-{ordinal:03}';case.mkdir(exist_ok=False)
 with (case/'dispatch.json').open('x') as f:json.dump({'pair_id':pair['pair_id'],'plan_sha256':plan['content_sha256'],'status':'dispatched-do-not-retry'},f)
 with concurrent.futures.ThreadPoolExecutor() as pool:
  fs={lane:pool.submit(execute,lane,pair,case) for lane in before};execution={k:f.result() for k,f in fs.items()}
 (case/'execution.json').write_text(json.dumps(execution,indent=2))
 time.sleep(2)  # Let Oracle's DDL timestamp boundary settle before a read-only snapshot.
 with concurrent.futures.ThreadPoolExecutor() as pool:
  fs={lane:pool.submit(m.snapshot,lane,case/lane) for lane in before};after={k:f.result() for k,f in fs.items()}
 comparison=compare_observations(before,after,execution)
 (case/'comparison.json').write_text(json.dumps(comparison,indent=2))
 row={'ordinal':ordinal,'pair_id':pair['pair_id'],'script':Path(pair['postgresql']['path']).name,'comparison_sha256':comparison['content_sha256'],'status':comparison['status'],'row_effects_match':comparison['row_effects_match'],'non_registration_row_effects_match':comparison['non_registration_row_effects_match'],'changed_tables':{k:list(v['tables']) for k,v in comparison['deltas'].items()},'returncodes':{k:v['returncode'] for k,v in execution.items()}}
 results.append(row);(out/'progress.json').write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True)
 before=after
 if any(e['returncode'] for e in execution.values()):break
(out/'run-result.json').write_text(json.dumps(seal({'plan_sha256':plan['content_sha256'],'planned_pairs':len(pairs),'attempted_pairs':len(results),'cases':results,'remaining_pairs':len(pairs)-len(results),'application_equivalence':False,'native_execution':True}),indent=2))
