"""Full public reconciliation both storage key modes; decimal restriction retained."""
import argparse,json
from pathlib import Path
from lightyear_mainframe.legacy_twin import build,run,receipt,new_output,PUBLIC_SCENARIOS
from lightyear_mainframe.scenario_generation import manifest
from tools.check_factory_review import attempt


def check(output):
 output=new_output(output);rows=[]
 for mode in ('ascii','cp037'):build(output/mode,cp037_keys=mode=='cp037')
 for case in PUBLIC_SCENARIOS:
  actual={}
  for mode in ('ascii','cp037'):
   r=run(output/mode,case,output/(mode+'-'+case));actual[mode]={k:r[k] for k in ('returncode','outputs','invariants')}
  rows.append(dict(scenario=case,kind='public',matched=actual['ascii']==actual['cp037'],actual=actual))
 for spec in manifest():
  case=spec['id'];actual={mode:attempt(output/mode,case,output/(mode+'-'+case)) for mode in ('ascii','cp037')}
  # Admission-refusal paths differ by output directory; compare refusal type only.
  matched=actual['ascii']==actual['cp037'] if actual['ascii']['status']=='executed' else all(x['status']=='execution-refusal' and x.get('error_type')=='RuntimeError' and 'rc=66;' in x.get('detail','') for x in actual.values())
  rows.append(dict(scenario=case,kind='generated',matched=matched,actual=actual))
 receipt(output/'cp037-reconciliation.json',phase='cp037-full-twin-reconciliation',cases=rows,matched=sum(r['matched'] for r in rows),count=len(rows),decimal_key_restriction_retained=True,model_calls=0)
 if not all(r['matched'] for r in rows):raise AssertionError('cp037 reconciliation differs; preserve results')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('output',type=Path);check(p.parse_args().output)
