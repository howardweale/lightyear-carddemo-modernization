"""Prospective Tower envelope for unchanged build-once consumer bytes.

This module prepares requests and verifies admission only; it never runs Docker.
A native evidence driver must verify this envelope before any external command.
"""
import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
from lightyear_calibration.contracts import canonical,digest,seal,verify
from lightyear_control_tower.verification import verify_decision
from .build_once_practice import validate,audit

KIND='campaign-authorization'
SCOPE='ms94-b06'
KEY='65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240'

def check(ok,why):
 if not ok:raise ValueError(why)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def utc(s):
 d=datetime.fromisoformat(s.replace('Z','+00:00'));check(d.utcoffset() is not None and d.utcoffset().total_seconds()==0,'UTC-required');return d

def accepted_practice(root,common,directory):
 """Replay actual outputs and retain exact hashes; never fabricate signatures."""
 root=validate(root,common);out=Path(directory);report=json.loads((out/'practice-report.json').read_bytes())
 check(report.get('passed') is True and report.get('cleanup_passed') is True and report.get('failure') is None,'passed-practice-required')
 check(report.get('source_commit')==common['source_commit'] and report.get('snapshot_sha256')==common['snapshot_sha256'] and report.get('plan_sha256')==common['content_sha256'],'practice-binding')
 check(report.get('native_pairs')==report.get('model_calls')==0 and report.get('native_admission') is False,'practice-scope')
 replayed=audit(out,common,root);check(replayed==report['checks'],'practice-replay-differs')
 built=json.loads((out/'built-image.json').read_bytes());manifest=json.loads((out/'builder/layer-manifest.json').read_bytes());verify(manifest)
 check(built['image']==report['derived_image'] and built['manifest_sha256']==manifest['content_sha256'],'practice-image-manifest-binding')
 check(re.fullmatch(r'sha256:[a-f0-9]{64}',built['image']) is not None,'derived-image-required')
 check(manifest['variants']['1']['class']!=manifest['variants']['2']['class'],'distinct-practice-variants')
 outputs={}
 for stage in ('builder','consumer-1','consumer-2'):
  outputs[stage]={name:sha(out/stage/name) for name in ('worker-observation.json','measured-inventory.json','effective-config.ini','effective-surefire.properties','fork-command.json','runtime-catalogue.tsv')}
 return seal(dict(schema='b06-build-once-accepted-practice/1',source_commit=common['source_commit'],snapshot_sha256=common['snapshot_sha256'],common_plan_sha256=common['content_sha256'],
  report_sha256=sha(out/'practice-report.json'),manifest_sha256=manifest['content_sha256'],manifest_file_sha256=sha(out/'builder/layer-manifest.json'),image=built['image'],
  elapsed_seconds=report['elapsed_seconds'],replayed=list(replayed),outputs_sha256=outputs,model_calls=0,native_pairs=0,native_admission=False,
  historical_content_required=False,production_signatures=False,review='operator review; not independent attestation'))

def prospective(common,practice):
 """Concrete handoff, not executable admission or authority to rebuild the layer."""
 verify(common);verify(practice)
 check(practice['snapshot_sha256']==common['snapshot_sha256'] and practice['common_plan_sha256']==common['content_sha256'] and practice['source_commit']==common['source_commit'],'common-plan-binding')
 check(practice['native_admission'] is False and practice['native_pairs']==practice['model_calls']==0,'practice-scope')
 return seal(dict(schema='b06-built-runtime-handoff/1',common_plan=common['content_sha256'],practice=practice['content_sha256'],snapshot_sha256=common['snapshot_sha256'],
  source_commit=common['source_commit'],image=practice['image'],manifest_sha256=practice['manifest_sha256'],practice_report_sha256=practice['report_sha256'],
  next_stage='direct-consumer-evidence-and-native-JDI-integration',builder_runs=0,consumer_variants=['1','2'],model_calls=0,native_pairs=0,databases=0,
  maximum_seconds=1800,cleanup_reserve_seconds=600,tower_public_key_sha256=KEY,window=None,public_commit=None,
  executable=False,driver_sha256=None,native_admission=False,
  blockers=['public hash-bound Tower-gated direct-consumer driver','fresh approved Docker window and exact Tower decision','native direct-launch integration with external JDI and per-slot candidate classes','five-path provenance census','J1/J2/J3 qualification and final preflight']))

def request(plan,commit):
 verify(plan);check(plan.get('schema')=='b06-built-runtime-handoff/1','handoff-schema')
 check(plan.get('executable') is True and re.fullmatch('[a-f0-9]{64}',plan.get('driver_sha256') or ''),'evidence-driver-not-ready')
 check(re.fullmatch('[a-f0-9]{40}',commit) is not None and plan.get('public_commit') in (None,commit),'evidence-public-commit')
 check(plan['builder_runs']==plan['model_calls']==plan['native_pairs']==plan['databases']==0 and plan['consumer_variants']==['1','2'],'evidence-consumers-only')
 w=plan['window'];check(isinstance(w,dict) and set(w)=={'not_before_utc','latest_start_utc','deadline_utc'},'fresh-evidence-window-required')
 check(utc(w['not_before_utc'])<=utc(w['latest_start_utc']) and (utc(w['deadline_utc'])-utc(w['latest_start_utc'])).total_seconds()>=plan['maximum_seconds']+plan['cleanup_reserve_seconds'],'evidence-window-reserve')
 artifacts=dict(campaign='b06-built-runtime-evidence-r1',plan=plan,snapshot=plan['snapshot_sha256'],window=w,public_commit=commit,
  declaration=dict(models=0,native_pairs=0,rebuild=False,native_admission=False),limits=dict(seconds=plan['maximum_seconds'],cleanup=plan['cleanup_reserve_seconds'],retries=0))
 bound={k:digest(v) for k,v in artifacts.items()}
 value=dict(schema='tower-request/1',scope=SCOPE,kind=KIND,bound=bound,evidence={k:'evidence/b06/built-runtime/'+v+'.json' for k,v in bound.items()},proposed_by='b06-build-once-handoff',workload='b06-built-runtime-evidence-r1',summary='Two read-only no-database consumers of the retained built image, no rebuild, no model calls, no native pairs. Exact worker and layer binding. Not five-path qualification or measurement. Operator review; not independent attestation.')
 value['id']='b06-built-runtime-'+digest(value)
 return value,{**bound,'request':digest(value)},artifacts

def authorize(plan,commit,reader,campaign_public,now=None):
 now=now or datetime.now(timezone.utc);_,bound,_=request(plan,commit)
 check(reader is not None and reader.key!=campaign_public and hashlib.sha256(reader.key).hexdigest()==plan['tower_public_key_sha256'],'distinct-tower-authority')
 check(utc(plan['window']['not_before_utc'])<=now<=utc(plan['window']['latest_start_utc']),'evidence-start-window')
 proof=reader.get(KIND,bound,now);check(proof is not None,'exact-tower-decision-required')
 journal=proof['journal'];check(abs((now-utc(journal['exported_at'])).total_seconds())<60,'fresh-tower-history-required')
 verify_decision(proof,reader.key,KIND,bound,scope=SCOPE,outcomes={'authorized'},expected_head=journal['journal_head_sha256'],now=now)
 return proof
