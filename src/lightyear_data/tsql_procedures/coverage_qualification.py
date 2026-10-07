"""Offline acceptance of the five explicit native collector controls.

Caller pins report/key hashes from the trusted run handoff. This is an
engineering qualification on public controls, not independent attestation.
"""
import json
from pathlib import Path
from .native_evidence import sha,verify,replay_pair


def qualify(root,expected_report,expected_key):
    root=Path(root);public=(root/'evidence-public-key.bin').read_bytes()
    if sha(public)!=expected_key:raise ValueError('coverage-control-key')
    report=json.loads((root/'report.json').read_bytes())
    if report['content_sha256']!=expected_report:raise ValueError('coverage-control-report')
    body=verify(report,public)
    if body['fatal'] or not body['cleanup_passed'] or body['planned_pairs'] not in (5,7) or len(body['records'])!=body['planned_pairs']:
        raise ValueError('coverage-controls-incomplete')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual!=set(body['files'])|{'report.json'}:raise ValueError('coverage-control-file-closure')
    for name,digest in body['files'].items():
        p=root/name
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or sha(p.read_bytes())!=digest:
            raise ValueError('coverage-control-file-changed')
    plan=verify(json.loads((root/'plan.json').read_bytes()),public)
    expected={'coverage-straight':True,'coverage-both-edges':True,'coverage-missing-edge':False,
              'coverage-handler-hit':True,'coverage-handler-missing':False}
    if body['planned_pairs']==7:expected.update({'coverage-scalar-declaration':True,'coverage-table-declaration':True})
    if set(plan['ids'])!=set(expected) or plan['variants']!=['correct']:raise ValueError('coverage-control-plan')
    rows=[]
    for record in body['records']:
        index=record['index'];name=record['id']
        pair=root/f'pair-{index:03d}-{name}-correct-1'
        m=verify(json.loads((pair/'manifest.json').read_bytes()),public)
        if m['plan_sha256']!=sha((root/'plan.json').read_bytes()):raise ValueError('control-plan-binding')
        result=replay_pair(pair,public,record['manifest_sha256'])
        coverage=result['comparison']['coverage']
        for lane,c in coverage.items():
            if c['eligible'] is not expected[name]:raise ValueError('coverage-control-outcome:'+name+':'+lane)
            if name=='coverage-both-edges' and c['minimum_module_branch_fraction']!=1:raise ValueError('both-edges-unproven')
            if name=='coverage-handler-missing' and not c['missing_error_paths']:raise ValueError('missing-handler-unproven')
        if set(coverage)!={'source','target'}:raise ValueError('coverage-control-lanes')
        rows.append({'id':name,'manifest_sha256':record['manifest_sha256'],'passed':True,
                     'business_status':record['status'],'business_verdict_not_control_acceptance':True})
    if len({r['id'] for r in rows})!=len(expected):raise ValueError('duplicate-coverage-control')
    result={'schema':'tsql-coverage-qualification/1','passed':True,'report_sha256':expected_report,
        'public_key_sha256':expected_key,'controls':rows,'images':plan['images'],
        'bridge_sha256':plan['coverage_bridge_sha256'],
        'collector_sha256':plan['code_sha256']['src/lightyear_data/tsql_procedures/coverage.py'],
        'limitations':['procedural coverage only; SQL expression and dynamic-body branch coverage excluded',
          'PostgreSQL native branch fraction retained; per-handler proof conservative at 100%',
          'five public controls, not universal instrumentation proof'],
        'model_calls':0,'claim':'Operator review; not independent attestation'}
    if len(expected)==7:result['limitations'][-1]='seven public controls, not universal instrumentation proof'
    return result
