import importlib.util,json,pathlib
from lightyear_calibration.native_effects import compare_observations
spec=importlib.util.spec_from_file_location('snap','work/native-snapshots.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=m.r/'native-migrations';case=out/'case-011'
execution=json.loads((case/'execution.json').read_text());print('recorded execution returncodes',{k:v['returncode'] for k,v in execution.items()},flush=True)
assert all(v['returncode']==0 for v in execution.values())
a=m.snapshot('oracle',case/'oracle-observation-retry')
before={lane:json.loads((out/'case-010'/lane/'state.json').read_text()) for lane in ('oracle','postgresql')}
after={'oracle':a,'postgresql':json.loads((case/'postgresql/state.json').read_text())}
c=compare_observations(before,after,execution);(case/'comparison.json').write_text(json.dumps(c,indent=2))
progress=json.loads((out/'progress.json').read_text());pair=json.loads((out/'execution-plan.json').read_text())['pairs'][10]
row={'ordinal':11,'pair_id':pair['pair_id'],'script':pathlib.Path(pair['postgresql']['path']).name,'comparison_sha256':c['content_sha256'],'status':c['status'],'row_effects_match':c['row_effects_match'],'non_registration_row_effects_match':c['non_registration_row_effects_match'],'changed_tables':{k:list(v['tables']) for k,v in c['deltas'].items()},'returncodes':{k:v['returncode'] for k,v in execution.items()},'observation_retry':'Oracle read-only capture retried after ORA-01466; no migration replay'}
assert len(progress)==10;progress.append(row);(out/'progress.json').write_text(json.dumps(progress,indent=2));print(json.dumps(row))
