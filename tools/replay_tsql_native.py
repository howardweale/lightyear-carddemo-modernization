#!/usr/bin/env python3
"""Verify a completed native run without importing database drivers or Docker."""
import argparse
import json
from pathlib import Path
import time
from collections import Counter
from lightyear_data.tsql_procedures.native_evidence import sha,verify,replay_pair,write


def audit(root, expected_report, expected_key):
    root=Path(root).resolve(); tick=time.monotonic()
    public=(root/'evidence-public-key.bin').read_bytes()
    if sha(public)!=expected_key: raise ValueError('unexpected-recorder-key')
    report=json.loads((root/'report.json').read_bytes())
    if report['content_sha256']!=expected_report: raise ValueError('unexpected-report')
    body=verify(report,public)
    if body['schema']!='tsql-native-run-report/1' or body['model_calls']!=0: raise ValueError('report-contract')
    files=body['files']
    if {f.relative_to(root).as_posix() for f in root.rglob('*') if f.is_file()} != set(files)|{'report.json'}:
        raise ValueError('run-file-closure')
    for name,digest in files.items():
        path=root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or sha(path.read_bytes())!=digest:
            raise ValueError('run-file-changed:'+name)
    plan=verify(json.loads((root/'plan.json').read_bytes()),public)
    qualification=None
    if plan.get('coverage_collector_qualified'):
        from lightyear_data.tsql_procedures.coverage_qualification import qualify
        qpath=root/'coverage-qualification.json'
        if sha(qpath.read_bytes())!=plan['coverage_qualification_sha256']:raise ValueError('coverage-qualification-binding')
        qualification=json.loads(qpath.read_bytes())
        if qualify(root/'coverage-control-evidence',qualification['report_sha256'],qualification['public_key_sha256'])!=qualification:
            raise ValueError('coverage-qualification-replay')
        if qualification['images']!=plan['images'] or qualification['bridge_sha256']!=plan['coverage_bridge_sha256']:
            raise ValueError('coverage-qualification-runtime-binding')
    ready=verify(json.loads((root/'ready.json').read_bytes()),public)
    if plan['owner']!=body['owner'] or plan['pairs']!=body['planned_pairs']:
        raise ValueError('run-plan-binding')
    for engine,image in plan['images'].items():
        if image!=ready['images'][engine]['Id'] and image not in ready['images'][engine]['RepoDigests']:
            raise ValueError('runtime-image-binding')
    if body['counts']!=dict(Counter(r['status'] for r in body['records'])):
        raise ValueError('run-counts')
    replays=[]
    for record in body['records']:
        index=record['index']
        progress=verify(json.loads((root/f'progress-{index:03d}.json').read_bytes()),public)
        if progress!=record: raise ValueError('progress-mismatch')
        if record['status']=='failed': continue
        pair=root/f'pair-{index:03d}-{record["id"]}-{record["variant"]}-{record["repeat"]}'
        manifest=verify(json.loads((pair/'manifest.json').read_bytes()),public)
        if (manifest['plan_sha256']!=sha((root/'plan.json').read_bytes())
                or manifest['images']!=plan['images']
                or record['id'] not in plan['ids']): raise ValueError('pair-plan-binding')
        for lane in ('source','target'):
            capture=json.loads((pair/(lane+'.json')).read_bytes())
            procedure='source' if lane=='source' else record['variant']
            setup='source-setup' if lane=='source' else ('target-setup' if record['variant']=='correct' else 'wrong-setup')
            if (capture['baseline']['procedure_sha256']!=manifest['assets'][procedure]['sha256']
                    or capture['baseline']['setup_sha256']!=manifest['assets'][setup]['sha256']):
                raise ValueError('pair-input-binding')
        result=replay_pair(pair,public,record['manifest_sha256'])
        if result['comparison'].get('coverage_qualification')!=qualification:raise ValueError('pair-coverage-qualification-binding')
        saved=verify(json.loads((root/f'replay-{index:03d}.json').read_bytes()),public)
        if saved!=result: raise ValueError('saved-replay-mismatch')
        if record['status']!=result['comparison']['observed_status'] or record['verdict']!=result['comparison']['verdict']:
            raise ValueError('reported-verdict-mismatch')
        replays.append({'index':index,'manifest_sha256':record['manifest_sha256'],
                        'status':result['comparison']['observed_status'],'verified':True})
    qualified=False
    if (root/'m0-acceptance.json').exists():
        from lightyear_data.tsql_procedures.m0 import accept
        saved=verify(json.loads((root/'m0-acceptance.json').read_bytes()),public)
        reproduced=accept(root,json.loads((root/'corpus.json').read_bytes()),plan,body['records'],public)
        reproduced['native_elapsed_seconds']=body['elapsed_seconds']
        reproduced['pairs_per_minute']=len(body['records'])/(body['elapsed_seconds']/60)
        if saved!=reproduced:raise ValueError('M0-acceptance-replay')
        qualified=bool(saved['passed'] and not body['fatal'] and body['cleanup_passed'])
    if body['qualification_passed']!=qualified:raise ValueError('M0-report-verdict')
    return {'schema':'tsql-independent-offline-audit/1','report_sha256':expected_report,
            'public_key_sha256':expected_key,'file_count':len(files),'pairs_replayed':len(replays),
            'replays':replays,'cleanup_receipt_passed':body['cleanup_passed'],
            'actual_docker_check':'not performed by offline replay',
            'elapsed_seconds':time.monotonic()-tick,'database_calls':0,'model_calls':0,
            'qualification_passed':qualified,'claim':'Operator review; not independent attestation'}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('directory',type=Path)
    p.add_argument('--report-sha256',required=True)
    p.add_argument('--key-sha256',required=True)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    result=audit(a.directory,a.report_sha256,a.key_sha256)
    digest=write(a.output,result)
    print(json.dumps({'pairs_replayed':result['pairs_replayed'],'files_verified':result['file_count'],'audit_file_sha256':digest,'database_calls':0,'model_calls':0}))
