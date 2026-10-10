"""Bounded build-once practice. Preparation and replay are Docker-free.

No Tower or production authority access. Run requires a separate explicit window.
"""
import datetime as dt,json,shutil,subprocess,time,uuid
from pathlib import Path
from .build_once import require,seal,verify,digest,canonical,verify_consumer,TEST_ROOT,CLASS_PATH
from .controller import IMAGE
from .runtime_capture import atomic_json,digest_file
from .runtime_practice import WORKER,EXTRA,replay
from .warning_baseline import check
from .frozen_runtime import bundle_census

BASELINE='docs/calibration/idempiere-ms94/stage-b-06/preparation/runtime-fidelity-r9/warning-baseline.json'

def prepare(repo,commit,snapshot,plan_path):
 repo=Path(repo).resolve();root=Path(snapshot).resolve();target=Path(plan_path).resolve()
 require(not root.exists() and not target.exists(),'fresh-build-once-freeze-required')
 def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],timeout=60)
 require(git('rev-parse',commit).decode().strip()==commit,'full-commit-required')
 names=git('ls-tree','-r','--name-only',commit).decode().splitlines()
 selected={n:n for n in names if n.startswith(('tools/','src/')) and n.endswith(('.py','.java'))}
 selected.update({n.removeprefix('src/'):n for n in names if n.startswith('src/lightyear_evidence/') and n.endswith('.py')})
 for n in WORKER|EXTRA:selected[n]='tools/'+n if n in EXTRA else 'tools/b06_image_artifacts/'+n
 selected['warning-baseline.json']=BASELINE
 require(all(n in names for n in selected.values()),'committed-freeze-input-required')
 root.mkdir(parents=True);hashes={}
 for dest,source in sorted(selected.items()):
  raw=git('cat-file','blob',commit+':'+source);p=root/dest;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);hashes[dest]=digest_file(p)
 plan=seal(dict(schema='b06-build-once-practice-plan/1',source_commit=commit,image=IMAGE,files_sha256=hashes,public_files=selected,
  snapshot_sha256=digest(hashes),public_ref='refs/heads/codex/b06-closure-lifecycle-r8',public_plan_path=target.relative_to(repo).as_posix(),maximum_runtime_seconds=2700,cleanup_reserve_seconds=600,container_limits_seconds=[1500,600,600],
  containers=['builder','consumer-1','consumer-2'],retries=0,network='none',model_calls=0,native_pairs=0,database_containers=0,
  historical_content_required=False,native_admission=False,run_authorized=False,window=None,
  derived_image=None,derived_image_retained=True,review='operator review; not independent attestation'))
 target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(canonical(plan));return plan

def validate(root,plan):
 root=Path(root).resolve();verify(plan)
 require(plan['schema']=='b06-build-once-practice-plan/1' and plan['image']==IMAGE,'build-once-plan-schema')
 require(plan['maximum_runtime_seconds']==2700 and plan['cleanup_reserve_seconds']==600 and plan['container_limits_seconds']==[1500,600,600],'build-once-limits')
 require(plan['retries']==plan['model_calls']==plan['native_pairs']==plan['database_containers']==0 and plan['network']=='none' and plan['native_admission'] is False,'build-once-scope')
 require(digest(plan['files_sha256'])==plan['snapshot_sha256'],'build-once-snapshot-hash')
 require({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}==set(plan['files_sha256']),'build-once-snapshot-file-set')
 for n,h in plan['files_sha256'].items():
  p=root/n;require(p.resolve().is_relative_to(root) and not p.is_symlink() and digest_file(p)==h,'build-once-frozen-bytes:'+n)
 return root

def utc(value):
 d=dt.datetime.fromisoformat(value.replace('Z','+00:00'));require(d.utcoffset()==dt.timedelta(0),'UTC-window-required');return d

def window(start,end,now=None):
 start=utc(start);end=utc(end);now=now or dt.datetime.now(dt.timezone.utc)
 require(start<=now and now+dt.timedelta(seconds=3300)<=end and end-start<=dt.timedelta(hours=1),'insufficient-approved-build-once-window')
 return (end-now).total_seconds()

def inspect_owned(item,name,image,owner):
 require(item['Name']=='/'+name and item['Image']==image and item['Config']['Labels'].get('lightyear.b06.build-once')==owner,'build-once-container-ownership')


def checks(out,snapshot,manifest=None,variant=None):
 out=Path(out);obs=json.loads((out/'worker-observation.json').read_bytes())
 require(bundle_census(obs)=={'system':1,'/root/.m2':203,'/application':44,'/tmp':102,'other':0},'build-once-census')
 require(not list(out.rglob('*error*.json')),'build-once-error-file')
 warning=check((out/('runtime.log' if variant else 'maven.log')).read_bytes(),json.loads((Path(snapshot)/'warning-baseline.json').read_bytes()))
 require(warning['passed'],'build-once-new-warning:'+str(warning['new']))
 result=dict(replay=replay(out),warnings=warning)
 if variant:result['layer_binding']=verify_consumer(manifest,out,variant)
 return result


def audit(root,plan,snapshot):
 """Replay actual output only. Does not reconstruct missing records or run Docker."""
 root=Path(root);validate(snapshot,plan)
 m=json.loads((root/'builder/layer-manifest.json').read_bytes());verify(m)
 result={'builder':checks(root/'builder',snapshot)}
 for v in ('1','2'):result['consumer-'+v]=checks(root/('consumer-'+v),snapshot,m,v)
 require(m['variants']['1']['class']!=m['variants']['2']['class'],'practice-class-variation-required')
 return result


def run(plan_path,snapshot,output,start,end,public_commit):
 plan=json.loads(Path(plan_path).read_bytes());repo=validate(snapshot,plan)
 require(Path.cwd().resolve()==repo and Path(__file__).resolve().is_relative_to(repo),'frozen-build-once-cwd-imports-required')
 # Same existing public-byte verifier, no network requests to model services.
 from .runtime_launch import publication
 publication(repo,repo,plan,public_commit)
 remaining=window(start,end);root=Path(output).resolve()
 require(not root.exists() and not root.is_relative_to(repo),'fresh-output-outside-freeze')
 root.mkdir(parents=True);atomic_json(root/'started.json',dict(plan_sha256=plan['content_sha256'],public_commit=public_commit,window=[start,end],utc=dt.datetime.now(dt.timezone.utc).isoformat()))
 owner='b06-build-once-'+uuid.uuid4().hex[:12];label='lightyear.b06.build-once='+owner
 deadline=time.monotonic()+remaining;work_deadline=min(deadline-600,time.monotonic()+2700)
 created={};commands=[];failure=None;clean=False;derived=None;results=None;t0=time.monotonic()
 def docker(*args,timeout=60,work=False):
  seconds=(work_deadline if work else deadline)-time.monotonic();require(seconds>0,'build-once-hard-deadline')
  command=list(map(str,args));commands.append(command)
  atomic_json(root/('command-%04d.json'%len(commands)),dict(argv=command,at_utc=dt.datetime.now(dt.timezone.utc).isoformat()))
  r=subprocess.run(['docker',*command],capture_output=True,timeout=min(timeout,seconds))
  require(r.returncode==0,'build-once-docker-'+command[0]+': '+r.stderr.decode(errors='replace'))
  return r.stdout+r.stderr if command[0] in ('logs','start') else r.stdout
 def stage(name,image,args,seconds,mounts=(),readonly=False):
  out=root/name;out.mkdir();cn=owner+'-'+name;created[cn]=image
  command=['create','--name',cn,'--label',label,'--network','none','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','8g','--cpus','2','--pids-limit','256',
    '--mount','type=bind,src='+str(repo)+',dst=/source,readonly','--mount','type=bind,src='+str(out)+',dst=/results',
    '--env','PYTHONPATH=/source:/source/tools/b06_image_artifacts','--env','PYTHONDONTWRITEBYTECODE=1']
  if readonly:command+=['--read-only']
  for src,dest,ro in mounts:command+=['--mount','type=bind,src='+str(src)+',dst='+dest+(',readonly' if ro else '')]
  command+=['--entrypoint','python3',image,'-B','-m','tools.b06_image_artifacts.build_once_worker',*args]
  docker(*command,work=True)
  try:(root/(name+'.stdout')).write_bytes(docker('start','--attach',cn,timeout=seconds,work=True))
  finally:(root/(name+'.container.log')).write_bytes(docker('logs',cn))
  item=json.loads(docker('container','inspect',cn))[0];inspect_owned(item,cn,image,owner)
  require(not item['State']['Running'] and item['State']['ExitCode']==0,'build-once-worker-failed:'+name)
  return cn,out
 try:
  require(not docker('ps','-q').strip(),'active-container-overlap')
  item=json.loads(docker('image','inspect',IMAGE))[0];require(item['Id']==IMAGE and not item.get('Config',{}).get('Volumes'),'pinned-image-or-anonymous-volumes')
  cn,builder=stage('builder',IMAGE,['build'],1500)
  checks(builder,repo);manifest=json.loads((builder/'layer-manifest.json').read_bytes());verify(manifest)
  # Commit one exited owned builder, never a user's container; retain layer for review.
  inspect_owned(json.loads(docker('container','inspect',cn))[0],cn,IMAGE,owner)
  derived=docker('commit','--change','LABEL lightyear.b06.build-once='+owner,cn,'lightyear/b06-build-once:'+owner,timeout=120,work=True).decode().strip()
  item=json.loads(docker('image','inspect',derived))[0]
  require(item['Id']==derived and item['Config']['Labels'].get('lightyear.b06.build-once')==owner and not item['Config'].get('Volumes'),'derived-image-binding')
  atomic_json(root/'built-image.json',dict(image=derived,manifest_sha256=manifest['content_sha256'],owner=owner,retained=True))
  for v in ('1','2'):
   mount=root/('mutable-'+v);mount.mkdir();shutil.copytree(builder/'configuration-seed',mount/'configuration')
   (mount/'data').mkdir();(mount/'reports').mkdir()
   mounts=[(mount/'configuration',manifest['config_path'],False),(mount/'data',manifest['data_path'],False),
    (mount/'reports',TEST_ROOT+'/target/surefire-reports',False),(builder/('variant-'+v+'.class'),CLASS_PATH,True)]
   _,out=stage('consumer-'+v,derived,['consume','--variant',v],600,mounts,True)
   checks(out,repo,manifest,v)
  results=audit(root,plan,repo)
 except BaseException as error:failure=type(error).__name__+': '+str(error)
 finally:
  try:
   for cn,image in created.items():
    ids=docker('ps','-a','-q','--filter','name=^/'+cn+'$').decode().split();require(len(ids)<=1,'ambiguous-owned-container')
    for identity in ids:
     inspect_owned(json.loads(docker('container','inspect',identity))[0],cn,image,owner);docker('rm','--force',identity)
   for args in (('ps','-a','-q'),('network','ls','-q'),('volume','ls','-q')):require(not docker(*args,'--filter','label='+label).strip(),'owned-cleanup-incomplete')
   validate(repo,plan);clean=True
  except BaseException as error:failure=(failure or '')+'; cleanup: '+str(error)
  report=dict(schema='b06-build-once-practice-report/1',passed=failure is None and clean,cleanup_passed=clean,failure=failure,elapsed_seconds=time.monotonic()-t0,
    source_commit=plan['source_commit'],snapshot_sha256=plan['snapshot_sha256'],plan_sha256=plan['content_sha256'],derived_image=derived,checks=results,model_calls=0,native_pairs=0,native_admission=False,commands=commands)
  atomic_json(root/'practice-report.json',report)
 return report


def main():
 import argparse
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='action',required=True)
 a=s.add_parser('prepare')
 for name in ('repo','commit','snapshot','plan'):a.add_argument('--'+name,required=True)
 a=s.add_parser('run')
 for name in ('plan','snapshot','output','start','end','public-commit'):a.add_argument('--'+name,required=True)
 a.add_argument('--run',action='store_true',required=True)
 a=p.parse_args()
 if a.action=='prepare':value=prepare(a.repo,a.commit,a.snapshot,a.plan)
 else:value=run(a.plan,a.snapshot,a.output,a.start,a.end,a.public_commit)
 print(json.dumps(value));raise SystemExit(0 if a.action=='prepare' or value['passed'] else 1)
if __name__=='__main__':main()
