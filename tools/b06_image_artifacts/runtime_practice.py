"""Non-evidence rehearsal runner. Explicit --run only after operator Docker approval.

No Tower request/decision, campaign authority, database, native pair or model.
Only an ephemeral in-memory test key exercises the mandatory replay verifier.
"""
import hashlib,json,subprocess,time,uuid
from pathlib import Path
from .controller import IMAGE
from .runtime_capture import digest_file,atomic_json

WORKER={'runtime_worker.py','runtime_capture.py','bundle_content.py','runtime_inventory.py','application_identity.py','transient_sources.py','tycho_runtime.py','resolved_runtime.py','archive.py','RuntimeClosureAgent.java'}
EXTRA={'B06RuntimeCatalogTest.java','B06RuntimeCatalogAgent.java','ms94_b06_observed_worker.py'}
def prepare(repository,output):
 repository=Path(repository).resolve();output=Path(output).resolve()
 if output.exists() or not output.is_relative_to(repository/'work'):raise ValueError('fresh-repository-work-directory-required')
 source=output/'source';source.mkdir(parents=True)
 for name in sorted(WORKER|EXTRA):
  original=repository/'tools'/(name if name in EXTRA else 'b06_image_artifacts/'+name)
  (source/name).write_bytes(original.read_bytes())
 for original in (repository/'src/lightyear_evidence').rglob('*.py'):
  target=source/original.relative_to(repository/'src');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
 # Bind all prospective host Python inputs, not private work files or archives.
 files={p.relative_to(repository).as_posix():digest_file(p) for folder in ('src','tools') for p in (repository/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.java')}
 plan=dict(schema='b06-runtime-practice/1',claim='NON-EVIDENCE PRACTICE; not qualification or Tower authority',repository=str(repository),output=str(output),image=IMAGE,
  source_sha256={p.relative_to(source).as_posix():digest_file(p) for p in source.rglob('*') if p.is_file()},host_files_sha256=files,model_calls=0,native_pairs=0,database_containers=0,network='none',maximum_runtime_seconds=2700,cleanup_reserve_seconds=600,run_authorized=False)
 atomic_json(output/'practice-plan.json',plan)
 return plan

def replay(results):
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
 from cryptography.hazmat.primitives import serialization
 from lightyear_workflow.campaign_engine import Signer
 from .runtime_producer import produce,h
 from .runtime_closure import assemble
 from .transient_sources import copies_at
 from .application_identity import copies_at as app_copies
 # Never import/open a production authority; private test key is memory only.
 signer=Signer.__new__(Signer);signer.key=Ed25519PrivateKey.generate();signer.public=signer.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
 raw=(results/'worker-observation.json').read_bytes();obs=json.loads(raw)
 config=(results/'effective-config.ini').read_bytes();props=(results/'effective-surefire.properties').read_bytes();fork=(results/'fork-command.json').read_bytes();inventory=json.loads((results/'measured-inventory.json').read_bytes())
 java=next(r for r in inventory['artifacts'] if r['path']==obs['java_home']+'/bin/java')
 expected=dict(probe_sha256='0'*64,image=IMAGE,java_sha256=java['sha256'],plan_sha256='0'*64,tower_decision_sha256='0'*64,measured_command_sha256=h((results/'measured-command.json').read_bytes()),closure_command_sha256=h((results/'command.json').read_bytes()),fork_command_sha256=h(fork))
 receipt=signer.sign(dict(schema='b06-runtime-launch-receipt/6',passed=True,cleanup_passed=True,bindings=expected,outputs={'observation':h(raw),'config.ini':h(config),'surefire.properties':h(props),'inventory':h(json.dumps(inventory,sort_keys=True).encode()),'fork-command':h(fork)}))
 tc=copies_at(obs,results);ac=app_copies(obs,results)
 resolution=produce(raw,config,props,inventory,receipt,signer.public,expected,fork_command=fork,transient_copies=tc,application_copies=ac)
 closure=assemble(inventory,resolution,launch_key=signer.public,expected_launch=expected,transient_copies=tc,application_copies=ac)
 return dict(replayed=True,native_admission=False,maximum_classes=closure['maximum_classes'],claim='In-memory test-signature check only; no production or Tower signing authority used')

def run(plan_path,*,snapshot=None,output=None):
 plan_path=Path(plan_path).resolve();original_plan=json.loads(plan_path.read_bytes());frozen=original_plan.get('schema') in ('b06-runtime-closure-plan/2','b06-runtime-closure-plan/3')
 if frozen:
  if snapshot is None or output is None:raise ValueError('frozen-snapshot-and-fresh-output-required')
  from .runtime_launch import validate
  repo=Path(snapshot).resolve()
  if Path.cwd().resolve()!=repo or not Path(__file__).resolve().is_relative_to(repo):raise ValueError('frozen-practice-cwd-imports-required')
  validate(repo,original_plan);root=Path(output).resolve()
  if root.exists() or root.is_relative_to(repo):raise ValueError('fresh-output-outside-snapshot-required')
  root.mkdir(parents=True);source=repo
  plan=dict(repository=str(repo),output=str(root),image=original_plan['image'],host_files_sha256=original_plan['files_sha256'])
 else:
  plan=original_plan;root=plan_path.parent;repo=Path(plan['repository']);source=root/'source'
 if root!=Path(plan['output']) or (not frozen and not root.is_relative_to(repo/'work')) or plan['image']!=IMAGE:raise ValueError('practice-plan-location-or-image')
 def verify():
  for name,sha in plan['host_files_sha256'].items():
   if digest_file(repo/name)!=sha:raise ValueError('practice-host-changed:'+name)
  if frozen:
   validate(repo,original_plan)
  elif {p.relative_to(source).as_posix():digest_file(p) for p in source.rglob('*') if p.is_file()}!=plan['source_sha256']:raise ValueError('practice-source-changed')
 verify()
 claim=root/'once.claim'
 with claim.open('x') as f:f.write('practice only; no automatic retry')
 out=root/'results';out.mkdir();name='b06-runtime-practice-'+uuid.uuid4().hex[:12];label='lightyear.b06.practice='+name
 started=time.monotonic();deadline=started+3300;created=False;clean=False;failure=None;result=None;commands=[]
 def docker(*args,timeout=60):
  remaining=deadline-time.monotonic()
  if remaining<=0:raise TimeoutError('practice-hard-deadline')
  commands.append(list(args));r=subprocess.run(['docker',*map(str,args)],capture_output=True,timeout=min(timeout,remaining))
  if r.returncode:raise RuntimeError('practice-docker-'+args[0]+': '+r.stderr.decode(errors='replace'))
  return r.stdout+r.stderr if args[0] in ('start','logs') else r.stdout
 try:
  if docker('ps','-q').strip():raise ValueError('active-container-overlap')
  item=json.loads(docker('image','inspect',IMAGE))[0]
  if item['Id']!=IMAGE or item.get('Config',{}).get('Volumes'):raise ValueError('practice-image')
  created=True
  docker('create','--name',name,'--label',label,'--network','none','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','8g','--cpus','2','--pids-limit','256','--mount','type=bind,src='+str(source)+',dst=/source,readonly','--mount','type=bind,src='+str(out)+',dst=/results','--entrypoint','python3',IMAGE,'-B','/source/runtime_worker.py')
  try:
   raw=docker('start','--attach',name,timeout=2700);(root/'stdout').write_bytes(raw)
  except BaseException:
   # Read logs before owned cleanup, retaining worker diagnostics even on failure.
   (root/'container.log').write_bytes(docker('logs',name));raise
 except BaseException as e:failure=type(e).__name__+': '+str(e)
 finally:
  try:
   if created:
    ids=docker('ps','-a','-q','--filter','label='+label).decode().split()
    if len(ids)>1:raise ValueError('practice-ownership-ambiguous')
    for identity in ids:
     item=json.loads(docker('container','inspect',identity))[0]
     if item['Name']!='/'+name or item['Image']!=IMAGE or item['Config']['Labels'].get('lightyear.b06.practice')!=name:raise ValueError('practice-ownership-mismatch')
     docker('rm','--force',identity)
    for args in (('ps','-a','-q'),('network','ls','-q'),('volume','ls','-q')):
     if docker(*args,'--filter','label='+label).strip():raise ValueError('practice-cleanup-incomplete')
   clean=True;verify()
   if failure is None:
    result=replay(out)
    if frozen:
     from .frozen_runtime import six_checks
     acceptance=six_checks(out,original_plan,repo,clean);atomic_json(root/'six-checks.json',acceptance)
     result['six_checks_passed']=acceptance['passed']
     if not acceptance['passed']:failure='frozen-practice-six-checks-not-satisfied'
  except BaseException as e:failure=(failure or '')+'; finalization: '+str(e)
  report=dict(schema='b06-practice-report/1',claim='NON-EVIDENCE; never qualification',passed=failure is None,cleanup_passed=clean,failure=failure,replay=result,elapsed_seconds=time.monotonic()-started,commands=commands,model_calls=0,native_pairs=0)
  if frozen:report.update(source_commit=original_plan['source_commit'],snapshot_sha256=original_plan['snapshot_sha256'],plan_sha256=original_plan['content_sha256'])
  atomic_json(root/'practice-report.json',report)
 return report

def main():
 import argparse
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
 a=sub.add_parser('prepare');a.add_argument('--repository',required=True);a.add_argument('--output',required=True)
 a=sub.add_parser('run');a.add_argument('--plan',required=True);a.add_argument('--snapshot');a.add_argument('--output');a.add_argument('--run',action='store_true',required=True,help='Only after explicit operator approval for this Docker practice')
 args=p.parse_args()
 if args.action=='prepare':value=prepare(args.repository,args.output);print(json.dumps({k:value[k] for k in ('output','image','run_authorized')}))
 else:
  result=run(args.plan,snapshot=args.snapshot,output=args.output);print(json.dumps(result));raise SystemExit(0 if result['passed'] else 1)
if __name__=='__main__':main()
