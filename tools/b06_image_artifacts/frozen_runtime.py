"""Commit-byte common executable/plan for practice and later evidence authority.

Preparation only. A window is authorization data; never patch the common plan.
No Docker or Tower calls in prepare().
"""
import hashlib,json,subprocess
from pathlib import Path
from lightyear_calibration.contracts import seal,digest,canonical,verify
from .controller import IMAGE

def prepare(repository,commit,snapshot,public,baseline,historical,tower_key,java_sha256,*,plan_id="b06-runtime-fidelity-r9",historical_required=False):
 import re
 if not re.fullmatch(r"b06-runtime-fidelity-r[1-9][0-9]*",plan_id):raise ValueError("invalid-runtime-plan-id")
 repo=Path(repository).resolve();snapshot=Path(snapshot).resolve();public=Path(public).resolve()
 if snapshot.exists() or public.exists():raise ValueError('fresh-freeze-paths-required')
 def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],timeout=60)
 if git('rev-parse',commit).decode().strip()!=commit:raise ValueError('full-commit-required')
 names=git('ls-tree','-r','--name-only',commit).decode().splitlines()
 selected={n:n for n in names if n.startswith(('src/','tools/')) and n.endswith(('.py','.java'))}
 from .runtime_launch import REQUIRED
 from .runtime_practice import WORKER,EXTRA
 for n in REQUIRED|WORKER|EXTRA:
  selected[n]='tools/'+n if n in EXTRA else 'tools/b06_image_artifacts/'+n
 if type(historical_required) is not bool:raise ValueError('historical-policy-boolean-required')
 if not historical_required and historical is not None:raise ValueError('unexpected-historical-input')
 assets=[('warning-baseline.json',baseline)]
 if historical_required:assets.append(('historical-content.json',historical))
 for name,source in assets:
  if source not in names:raise ValueError('committed-acceptance-input-required')
  selected[name]=source
 snapshot.mkdir(parents=True);public.mkdir(parents=True);hashes={}
 for dest,source in sorted(selected.items()):
  raw=git('cat-file','blob',commit+':'+source);p=snapshot/dest;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);hashes[dest]=hashlib.sha256(raw).hexdigest()
 from .runtime_worker import launch_arguments
 measured,_=launch_arguments()
 # Guard this preparation import against the selected committed input.
 if Path('tools/ms94_b06_observed_worker.py').read_bytes()!=git('cat-file','blob',commit+':tools/ms94_b06_observed_worker.py'):raise ValueError('preparer-measured-worker-differs')
 from .runtime_launch import HISTORY_AMENDMENT
 policy=dict(historical_content_sha256=hashes['historical-content.json']) if historical_required else dict(historical_content_required=False,historical_content_amendment=HISTORY_AMENDMENT)
 plan=seal(dict(schema='b06-runtime-closure-plan/2' if historical_required else 'b06-runtime-closure-plan/3',id=plan_id,source_commit=commit,image=IMAGE,
  files_sha256=hashes,snapshot_sha256=digest(hashes),public_files=selected,
  public_ref='refs/heads/codex/b06-closure-lifecycle-r8',public_plan_path=public.relative_to(repo).as_posix()+'/plan.json',
  warning_baseline_sha256=hashes['warning-baseline.json'],**policy,
  model_calls=0,native_pairs=0,database_containers=0,retries=0,network='none',maximum_runtime_seconds=2700,cleanup_reserve_seconds=600,
  java_sha256=java_sha256,tower_public_key_sha256=hashlib.sha256(Path(tower_key).read_bytes()).hexdigest(),
  measured_maven_arguments=measured,window=None,window_in_authorization=True,requires_exact_tower_decision=True,
  requires_practice_six_checks=True,run_authorized=False,review='operator review; not independent attestation'))
 (public/'plan.json').write_bytes(canonical(plan));return plan

def bundle_census(observation):
 """The system bundle has a sentinel location, not a file URL."""
 from .tycho_runtime import path
 counts={'system':0,'/root/.m2':0,'/application':0,'/tmp':0,'other':0}
 for b in observation['bundles']:
  if b['id']==0:
   counts['system']+=1
   continue
  p=path(b['location'],path(observation['install_area']))
  key=next((n for n in ('/root/.m2','/application','/tmp') if p.startswith(n+'/')),'other')
  counts[key]+=1
 return counts


def application_review(results,plan,snapshot,observation):
 """Keep legacy history checks; /3 verifies current captures without old inputs."""
 from .runtime_launch import historical_policy
 from .application_identity import records,copies_at
 from .content_comparison import identity,compare
 out=Path(results);root=Path(snapshot);obs=observation
 if not historical_policy(plan):
  current=records(obs,copies_at(obs,out))
  return dict(passed=len(current)==44,basis='current-capture-validation',comparisons=[],
              captures=[dict(symbolic_name=r['identity']['symbolic_name'],entries=len(r['identity']['entries']),content_sha256=r['content_sha256'],archive_sha256=r['archive_sha256']) for r in current])
 hist=json.loads((root/'historical-content.json').read_bytes());comparisons=[]
 for b in obs['bundles']:
  if not b.get('application_copy'):continue
  c=b['application_copy'];now=identity(out/'runtime-application'/f"{b['id']}.jar",'jar' if c['kind']=='jar' else 'folder-archive')
  for run,old in hist['runs'].items():
   previous=old.get(b['symbolic_name']);comparisons.append(dict(run=run,symbolic_name=b['symbolic_name'],**(compare(previous,now) if previous else dict(passed=False,reason='historical-content-not-retained'))))
 return dict(passed=len(comparisons)==88 and all(r['passed'] for r in comparisons),basis='historical-r4-r5b-comparison',comparisons=comparisons,captures=[])


def six_checks(results,plan,snapshot,cleanup):
 from .tycho_runtime import path,read
 from .transient_sources import classify,copies_at,catalogue
 from .content_comparison import identity,compare
 from .warning_baseline import check
 out=Path(results);root=Path(snapshot);obs=json.loads((out/'worker-observation.json').read_bytes())
 counts=bundle_census(obs)
 sources=classify(obs,copies_at(obs,out),catalogue((out/'runtime-catalogue.tsv').read_bytes()))
 app=application_review(out,plan,root,obs);comparisons=app['comparisons']
 parsed=read((out/'effective-config.ini').read_bytes(),(out/'effective-surefire.properties').read_bytes(),obs,obs['fork_command'])
 inv=json.loads((out/'measured-inventory.json').read_bytes());launcher=parsed['boot_classpath'][0]
 tycho=any(r['path']==launcher and len(r['sha256'])==64 for r in inv['artifacts'])
 warnings=check((out/'maven.log').read_bytes(),json.loads((root/'warning-baseline.json').read_bytes()))
 errors=[p.name for p in out.rglob('*error*.json')]
 verify(plan);unchanged=all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in plan['files_sha256'].items())
 checks=dict(census=counts=={'system':1,'/root/.m2':203,'/application':44,'/tmp':102,'other':0},source_only=len(sources)==counts['/tmp']==102,
  application_content=app['passed'],tycho=tycho,
  warning_baseline=warnings['passed'] and not errors,frozen_bytes=unchanged,cleanup=cleanup)
 details=dict(application_content_basis=app['basis'],application_captures=app['captures']) if plan['schema']=='b06-runtime-closure-plan/3' else {}
 return dict(schema='b06-frozen-practice-checks/2' if details else 'b06-frozen-practice-checks/1',passed=all(checks.values()),checks=checks,census=counts,source_only_qualified=len(sources),
  comparisons=comparisons,**details,warnings=warnings,error_files=errors,source_commit=plan['source_commit'],snapshot_sha256=plan['snapshot_sha256'],plan_sha256=plan['content_sha256'])


def verify_practice(snapshot,plan,directory):
 """Recompute acceptance before request and again before any evidence Docker."""
 if directory is None:raise ValueError('frozen-practice-directory-required')
 root=Path(directory);report=json.loads((root/'practice-report.json').read_bytes())
 if not report.get('passed') or not report.get('cleanup_passed'):raise ValueError('successful-frozen-practice-required')
 for key,expected in [('source_commit',plan['source_commit']),('snapshot_sha256',plan['snapshot_sha256']),('plan_sha256',plan['content_sha256'])]:
  if report.get(key)!=expected:raise ValueError('practice-report-binding')
 checks=six_checks(root/'results',plan,snapshot,True)
 if not checks['passed'] or checks!=json.loads((root/'six-checks.json').read_bytes()):raise ValueError('practice-six-checks-not-satisfied')
 from .runtime_practice import replay
 if not replay(root/'results')['replayed']:raise ValueError('practice-replay-failed')
 return checks

def write_request(repository,snapshot,plan,public_commit,practice_directory,window):
 """Explicit call only after Howard's practice approval and all six checks pass."""
 from .runtime_launch import validate,publication,request
 from lightyear_control_tower.status_export import atomic_new
 root=validate(snapshot,plan);publication(repository,root,plan,public_commit)
 checks=verify_practice(root,plan,practice_directory)
 value,bindings,artifacts=request(plan,public_commit,window=window,practice=checks)
 for name,artifact in artifacts.items():atomic_new(Path(repository)/value['evidence'][name],artifact)
 atomic_new(Path(repository)/'work/control-tower/requests/ms94-b06'/(value['id']+'.json'),value)
 return value['id'],bindings
