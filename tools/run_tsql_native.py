#!/usr/bin/env python3
"""Dedicated Linux VM only: public-corpus paired execution and signed evidence.

Never uses a shared database, Docker prune, global stop, or an outer rollback.
The run-local evidence key is an experimental recorder, NOT a Tower authority
or independent attestation. Its private bytes remain outside the evidence tree.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import sys
import time
import traceback

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_data.tsql_procedures.native import NativeEngine, utc
from lightyear_data.tsql_procedures.native_evidence import write, sha, sign, compare, seal_pair, replay_pair
from lightyear_data.tsql_procedures.native_evidence import compare_v2
from lightyear_data.tsql_procedures.policy import profile,policy_register
from lightyear_data.tsql_procedures.m0 import expand, accept

SQL_IMAGE='mcr.microsoft.com/mssql/server@sha256:4402d880dd4c34bfa7d8705e56a86cd6c88da80a1f6bbbe741f999e76264a090'
PG_IMAGE='postgres@sha256:0ea6700a3b4f0ae6ce746519073558aed4d88a79d8d07622a9a644946c7319c4'


def docker(*args,timeout=180,check=True):
    result=subprocess.run(['sudo','-n','docker',*args],capture_output=True,text=True,timeout=timeout)
    if check and result.returncode: raise RuntimeError('Docker '+args[0]+': '+result.stderr[-4000:])
    return result


def asset(root, descriptor):
    path=(root/descriptor['path']).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('asset-escape')
    raw=path.read_bytes()
    if sha(raw)!=descriptor['sha256']: raise ValueError('asset-hash:'+str(path))
    return raw.decode('utf-8')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ids',nargs='*')
    p.add_argument('--variants',nargs='+',choices=['correct','wrong'],default=['correct','wrong'])
    p.add_argument('--expected-host',default='ly-tsql-m0')
    p.add_argument('--coverage-bridge',type=Path)
    p.add_argument('--coverage-revision',type=int,choices=(1,2),default=1)
    p.add_argument('--coverage-schema',action='append',dest='coverage_schemas')
    p.add_argument('--semantic-bridge',type=Path,required=True)
    p.add_argument('--pg-image',default=PG_IMAGE)
    p.add_argument('--coverage-controls-evidence',type=Path)
    p.add_argument('--coverage-controls-report-sha256')
    p.add_argument('--coverage-controls-key-sha256')
    args=p.parse_args()
    if args.coverage_revision==1 and args.coverage_schemas not in (None,['dbo']):
        raise ValueError('coverage-v1-schema-fixed')
    if platform.system()!='Linux' or platform.machine()!='x86_64' or platform.node()!=args.expected_host:
        raise SystemExit('Refusing: dedicated approved x86_64 Linux VM required')
    if importlib.metadata.version('python-tds')!='1.16.1': raise SystemExit('TDS driver not pinned')
    args.output.mkdir(parents=True,exist_ok=False)
    root=args.root.resolve(); out=args.output.resolve()
    manifest_path=root/'data-modernization/tsql-procedures/corpus.json'
    corpus=json.loads(manifest_path.read_bytes())
    items=[v for v in corpus['procedures'] if not args.ids or v['id'] in args.ids]
    if args.ids and {v['id'] for v in items}!=set(args.ids): raise ValueError('unknown-id')
    items=expand(items)
    from lightyear_data.tsql_procedures.inventory import parse
    from lightyear_data.tsql_procedures.semantics import contract
    from lightyear_data.tsql_procedures.comparison_v5 import compare as compare_v5
    from copy import deepcopy
    cases=[]
    for item in items:
        syntax=parse(asset(root,item['assets']['source']),('dotnet',str(args.semantic_bridge)),allow_sqlglot=False)
        if syntax['status']!='parsed':raise ValueError('native-source-syntax-required')
        semantic=contract(syntax)
        if len(semantic['procedures'])!=1:raise ValueError('native-single-procedure-contract')
        for case in item['cases']:
            one=deepcopy(item);one['cases']=[case];one['source_syntax']=syntax['ast']
            one['procedure_contract']=semantic['procedures'][0]
            if len(item['cases'])>1:one['scenario']+=':'+case['id']
            cases.append(one)
    items=cases
    # Verify EVERY selected byte before any container or SQL action.
    for item in items:
        for a in item['assets'].values(): asset(root,a)
    qualification=None
    if args.coverage_controls_evidence:
        from lightyear_data.tsql_procedures.coverage_qualification import qualify
        from lightyear_data.tsql_procedures import coverage as coverage_module
        if args.coverage_revision==2:
            from lightyear_data.tsql_procedures import coverage_v2 as coverage_module
        qualification=qualify(args.coverage_controls_evidence,args.coverage_controls_report_sha256,args.coverage_controls_key_sha256)
        if qualification['schema']!='tsql-coverage-qualification/'+str(args.coverage_revision):raise ValueError('coverage-qualification-revision')
        if args.coverage_revision==2 and qualification['coverage_schemas']!=(args.coverage_schemas or ['dbo']):raise ValueError('coverage-qualification-schemas')
        if (not args.coverage_bridge or qualification['bridge_sha256']!=sha(args.coverage_bridge.read_bytes())
                or qualification['collector_sha256']!=sha(Path(coverage_module.__file__).read_bytes())
                or qualification['images']!={'sqlserver':SQL_IMAGE,'postgresql':args.pg_image}):
            raise ValueError('coverage-qualification-runtime-binding')
        shutil.copytree(args.coverage_controls_evidence,out/'coverage-control-evidence')
        write(out/'coverage-qualification.json',qualification)
    owner='lytsql_'+secrets.token_hex(6)
    secret_dir=out.parent/(out.name+'-private')
    secret_dir.mkdir(mode=0o700,exist_ok=False)
    key=Ed25519PrivateKey.generate()
    (secret_dir/'evidence.key').write_bytes(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()))
    os.chmod(secret_dir/'evidence.key',0o600)
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    (out/'evidence-public-key.bin').write_bytes(public)
    plan={'schema':'tsql-native-run-plan/1','owner':owner,'created_utc':utc(),
          'host':platform.node(),'architecture':platform.machine(),'corpus_sha256':sha(manifest_path.read_bytes()),
          'images':{'sqlserver':SQL_IMAGE,'postgresql':args.pg_image},
          'coverage_bridge_sha256':sha(args.coverage_bridge.read_bytes()) if args.coverage_bridge else None,
          'coverage_revision':args.coverage_revision,'coverage_schemas':args.coverage_schemas or ['dbo'],
          'semantic_bridge_sha256':sha(args.semantic_bridge.read_bytes()),'comparison_revision':5,
          'sqlserver_profile':{'collation':'Latin1_General_100_CI_AS','compatibility_level':160},
          'ids':[v['id'] for v in items],'variants':args.variants,
          'pairs':sum(v['cases'][0]['repeated_runs']*len(args.variants) for v in items),
          'code_sha256':{f.relative_to(root).as_posix():sha(f.read_bytes()) for f in sorted((root/'src/lightyear_data').rglob('*.py'))},
          'runner_sha256':sha(Path(__file__).read_bytes()),
          'evidence_key_sha256':sha(public),'signer_role':'run-local experimental recorder; operator review, not independent attestation',
          'model_calls':0,'coverage_required':True,'coverage_collector_qualified':False,
          'no_equivalence_certificate':True}
    plan['coverage_collector_qualified']=qualification is not None
    plan['coverage_qualification_sha256']=sha((out/'coverage-qualification.json').read_bytes()) if qualification else None
    write(out/'plan.json',sign(plan,key))
    (out/'corpus.json').write_bytes(manifest_path.read_bytes())
    write(out/'policy-register.json',policy_register(corpus))
    resources=[]; records=[]; started=utc(); tick=time.monotonic(); fatal=None; cleanup=[]
    password='Ly!'+secrets.token_urlsafe(28)+'9a'
    sql_env=secret_dir/'sql.env'; pg_env=secret_dir/'pg.env'
    sql_env.write_text('ACCEPT_EULA=Y\nMSSQL_PID=Developer\nMSSQL_SA_PASSWORD='+password+'\nMSSQL_MEMORY_LIMIT_MB=4096\n')
    pg_env.write_text('POSTGRES_PASSWORD='+password+'\n')
    for f in (sql_env,pg_env): os.chmod(f,0o600)
    try:
        label='lightyear.tsql.owner='+owner
        network=owner+'-net'
        docker('network','create','--internal','--label',label,network)
        resources.append(('network',network))
        images={}
        for engine,image,port,env,mount in [('sqlserver',SQL_IMAGE,1433,sql_env,'/var/opt/mssql'),('postgresql',args.pg_image,5432,pg_env,'/var/lib/postgresql/data')]:
            image_info=json.loads(docker('image','inspect',image).stdout)[0]
            if image!=image_info['Id'] and image not in image_info['RepoDigests']: raise ValueError('image-digest-not-present')
            images[engine]={k:image_info[k] for k in ('Id','RepoDigests','Architecture','Os')}
            volume=owner+'-'+engine+'-data'; name=owner+'-'+engine
            docker('volume','create','--label',label,volume); resources.append(('volume',volume))
            docker('run','-d','--name',name,'--label',label,'--network',network,
                   '--memory',('6g' if engine=='sqlserver' else '2g'),'--cpus','2',
                   '--env-file',str(env),'--mount',f'type=volume,src={volume},dst={mount}',image)
            resources.append(('container',name))
        import pytds,psycopg
        addresses={}
        for engine,port in [('sqlserver',1433),('postgresql',5432)]:
            inspection=json.loads(docker('inspect',owner+'-'+engine).stdout)[0]
            addresses[engine]=inspection['NetworkSettings']['Networks'][network]['IPAddress']
            if not addresses[engine] or inspection['NetworkSettings']['Ports'].get(str(port)+'/tcp'):
                raise ValueError('database-network-exposure')
        def sql_conn(db):
            return closing(pytds.connect(addresses['sqlserver'],port=1433,user='sa',password=password,database=db or 'master',autocommit=True,timeout=90,login_timeout=5))
        def pg_conn(db):
            return closing(psycopg.connect(host=addresses['postgresql'],port=5432,user='postgres',password=password,dbname=db or 'postgres',autocommit=True,connect_timeout=5))
        for connect in (sql_conn,pg_conn):
            deadline=time.monotonic()+240
            while True:
                try:
                    with connect(None): pass
                    break
                except Exception:
                    if time.monotonic()>deadline: raise RuntimeError('database-readiness-timeout')
                    time.sleep(3)
        engines={'source':NativeEngine('sqlserver',sql_conn,owner,args.coverage_bridge,plan['sqlserver_profile'],
                                      args.coverage_revision,args.coverage_schemas or ('dbo',)),
                 'target':NativeEngine('postgresql',pg_conn,owner,args.coverage_bridge,
                                      coverage_revision=args.coverage_revision,
                                      coverage_schemas=args.coverage_schemas or ('dbo',))}
        write(out/'ready.json',sign({'schema':'tsql-native-ready/1','at_utc':utc(),'images':images,
              'ports_bind':'unpublished; host access to dedicated internal bridge only','versions':{n:importlib.metadata.version(n) for n in ('python-tds','psycopg','cryptography')},'model_calls':0},key))
        print(json.dumps({'event':'ready','owner':owner,'planned_pairs':plan['pairs'],'at_utc':utc()}),flush=True)
        index=0
        for item in items:
            for variant in args.variants:
                for repeat in range(item['cases'][0]['repeated_runs']):
                    index+=1
                    pair=out/f'pair-{index:03d}-{item["id"]}-{variant}-{repeat+1}'
                    pair.mkdir()
                    record={'index':index,'id':item['id'],'variant':variant,'repeat':repeat+1,
                            'scenario':item.get('scenario','primary'),'trap_family':item['trap_family'],'started_utc':utc()}
                    baselines={}; resets={}; lanes={}; phase='provision'
                    try:
                        for lane,engine in engines.items():
                            setup='source-setup' if lane=='source' else ('target-setup' if variant=='correct' else 'wrong-setup')
                            procedure='source' if lane=='source' else variant
                            baselines[lane]=engine.provision(f'b{index:03d}',asset(root,item['assets'][setup]),asset(root,item['assets'][procedure]))
                            phase='reset-'+lane
                            resets[lane]=engine.reset(baselines[lane],f'r{index:03d}')
                            phase='call-'+lane
                            lanes[lane]=engine.call(resets[lane],item,
                                lambda kind,value,lane=lane:write(out/f'capture-{index:03d}-{lane}-{kind}.json',value))
                            lanes[lane]['baseline']=baselines[lane]
                            write(pair/(lane+'.json'),lanes[lane])
                            phase='provision'
                        phase='compare'
                        comparison=compare_v5(lanes['source'],lanes['target'],profile(item),qualification)
                        write(pair/'comparison.json',comparison)
                        envelope=seal_pair(pair,dict(record,assets=item['assets'],images=plan['images'],plan_sha256=sha((out/'plan.json').read_bytes())),key)
                        replay=replay_pair(pair,public,envelope['content_sha256'])
                        write(out/f'replay-{index:03d}.json',sign(replay,key))
                        record.update(status=comparison['observed_status'],verdict=comparison['verdict'],
                                      manifest_sha256=envelope['content_sha256'],replay_verified=True,
                                      differences=[d['observable'] for d in comparison['differences']])
                    except Exception as ex:
                        record.update(status='failed',phase=phase,error_type=type(ex).__name__,error=str(ex))
                        write(pair/'failure.json',sign(dict(record,traceback=traceback.format_exc()),key))
                    finally:
                        dropped=[]
                        for engine in engines.values():
                            for db in sorted(engine.owned): dropped.append(engine.drop(db))
                        record['database_cleanup']=dropped
                    record['ended_utc']=utc(); records.append(record)
                    write(out/f'progress-{index:03d}.json',sign(record,key))
                    print(json.dumps(record),flush=True)
                    if record['status']=='failed':
                        raise RuntimeError('native-pair-failed-preserved:'+str(index))
    except Exception as ex:
        fatal={'type':type(ex).__name__,'message':str(ex),'traceback':traceback.format_exc()}
    finally:
        for kind,name in reversed(resources):
            if kind=='container':
                logs=docker('logs',name,check=False)
                (out/(name+'.log')).write_text(logs.stdout+logs.stderr)
            inspect=docker(kind,'inspect',name,check=False)
            if inspect.returncode:
                cleanup.append({'kind':kind,'name':name,'status':'inspect-failed','error':inspect.stderr}); continue
            obj=json.loads(inspect.stdout)[0]
            labels=obj.get('Config',{}).get('Labels',{}) if kind=='container' else obj.get('Labels',{})
            if labels.get('lightyear.tsql.owner')!=owner:
                cleanup.append({'kind':kind,'name':name,'status':'owner-mismatch'}); continue
            remove=docker(kind,'rm',*(['-f'] if kind=='container' else []),name,check=False)
            # Successful list response is required; inspect failure alone is not absence proof.
            if kind=='container': listing=docker('ps','-a','--filter','label=lightyear.tsql.owner='+owner,'--format','{{.Names}}',check=False)
            else: listing=docker(kind,'ls','--filter','label=lightyear.tsql.owner='+owner,'--format','{{.Name}}',check=False)
            cleanup.append({'kind':kind,'name':name,'remove_exit':remove.returncode,
                            'status':'absent' if remove.returncode==0 and listing.returncode==0 and name not in listing.stdout.splitlines() else 'cleanup-failed'})
        report={'schema':'tsql-native-run-report/1','owner':owner,'started_utc':started,'ended_utc':utc(),
                'elapsed_seconds':time.monotonic()-tick,'planned_pairs':plan['pairs'],'records':records,
                'counts':dict(Counter(r['status'] for r in records)),'fatal':fatal,'cleanup':cleanup,
                'cleanup_passed':len(cleanup)==len(resources) and all(r['status']=='absent' for r in cleanup),
                'model_calls':0,'qualification_passed':False,
                'claim':('Native public-fixture comparison; seven-control coverage qualification bound; '
                         if qualification and len(qualification.get('controls',[]))==7 else
                         'Native public-fixture comparison; see plan for coverage qualification; ')
                        +'operator review, not independent attestation'}
        if not fatal and report['cleanup_passed'] and qualification and not args.ids and args.variants==['correct','wrong']:
            try:
                from lightyear_data.tsql_procedures.m0_v2 import accept as accept_v2
                acceptance=accept_v2(out,corpus,plan,records,public)
                acceptance['native_elapsed_seconds']=report['elapsed_seconds']
                acceptance['pairs_per_minute']=len(records)/(report['elapsed_seconds']/60)
                write(out/'m0-acceptance.json',sign(acceptance,key))
                report['qualification_passed']=acceptance['passed']
            except Exception as ex:
                report['fatal']={'type':type(ex).__name__,'message':str(ex),'traceback':traceback.format_exc()}
                fatal=report['fatal']
        report['files']={f.relative_to(out).as_posix():sha(f.read_bytes()) for f in sorted(out.rglob('*')) if f.is_file()}
        write(out/'report.json',sign(report,key))
        print(json.dumps({k:report[k] for k in ('counts','fatal','cleanup_passed','elapsed_seconds','qualification_passed')}),flush=True)
    return 1 if fatal or not report['cleanup_passed'] else 0


if __name__=='__main__': raise SystemExit(main())
