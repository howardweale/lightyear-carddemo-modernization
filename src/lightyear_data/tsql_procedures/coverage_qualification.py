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
    if body['fatal'] or not body['cleanup_passed'] or body['planned_pairs'] not in (5,7,9) or len(body['records'])!=body['planned_pairs']:
        raise ValueError('coverage-controls-incomplete')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual!=set(body['files'])|{'report.json'}:raise ValueError('coverage-control-file-closure')
    for name,digest in body['files'].items():
        p=root/name
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or sha(p.read_bytes())!=digest:
            raise ValueError('coverage-control-file-changed')
    plan=verify(json.loads((root/'plan.json').read_bytes()),public)
    revision=plan.get('coverage_revision',1)
    expected={'coverage-straight':True,'coverage-both-edges':True,'coverage-missing-edge':False,
              'coverage-handler-hit':True,'coverage-handler-missing':False}
    if body['planned_pairs']==7:expected.update({'coverage-scalar-declaration':True,'coverage-table-declaration':True})
    if revision==2:
        from tools.tsql_scriptdom.coverage_controls_v2 import EXPECTED,SCHEMAS,controls
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary:
            expected_corpus=controls(Path(temporary))
        corpus_bytes=(root/'corpus.json').read_bytes()
        if sha(corpus_bytes)!=plan['corpus_sha256'] or json.loads(corpus_bytes)!=expected_corpus:
            raise ValueError('coverage-v2-authored-control-bytes')
        expected=EXPECTED
        if body['planned_pairs']!=9 or plan['coverage_schemas']!=SCHEMAS:raise ValueError('coverage-v2-control-scope')
    elif body['planned_pairs']==9 or revision!=1:raise ValueError('coverage-control-revision')
    if set(plan['ids'])!=set(expected) or plan['variants']!=['correct']:raise ValueError('coverage-control-plan')
    rows=[]
    for record in body['records']:
        index=record['index'];name=record['id']
        pair=root/f'pair-{index:03d}-{name}-correct-1'
        m=verify(json.loads((pair/'manifest.json').read_bytes()),public)
        if m['plan_sha256']!=sha((root/'plan.json').read_bytes()):raise ValueError('control-plan-binding')
        result=replay_pair(pair,public,record['manifest_sha256'])
        coverage=result['comparison']['coverage']
        if revision==2:
            progress=verify(json.loads((root/f'progress-{index:03d}.json').read_bytes()),public)
            if progress!=record:raise ValueError('coverage-control-progress-binding')
            item=next(v for v in expected_corpus['procedures'] if v['id']==name)
            if m['assets']!=item['assets'] or record['variant']!='correct' or record['repeat']!=1:
                raise ValueError('coverage-v2-control-assets')
            for lane in ('source','target'):
                captured=json.loads((pair/(lane+'.json')).read_bytes())
                role='source' if lane=='source' else 'correct'
                if (captured['baseline']['procedure_sha256']!=m['assets'][role]['sha256'] or
                    captured['baseline']['setup_sha256']!=m['assets'][lane+'-setup']['sha256']):
                    raise ValueError('coverage-control-input-binding')
                raw=captured['observation']['coverage']['raw']
                if raw['schema']!=('tsql-sqlserver-coverage-input/2' if lane=='source' else 'tsql-postgresql-coverage-input/2'):
                    raise ValueError('coverage-v2-record-required')
                if lane=='target' and raw['schemas']!=SCHEMAS:raise ValueError('coverage-schema-binding')
                if name=='coverage-non-dbo-schema' and not all(x['name'].startswith('business.') for x in raw['modules']):
                    raise ValueError('coverage-custom-schema-not-observed')
                if name=='coverage-view-excluded' and lane=='source':
                    if ([x['name'] for x in raw['excluded_views']]!=['dbo.coverage_view'] or
                        any(x['name']=='dbo.coverage_view' for x in raw['modules'])):
                        raise ValueError('coverage-view-exclusion-not-observed')
        for lane,c in coverage.items():
            if c['eligible'] is not expected[name]:raise ValueError('coverage-control-outcome:'+name+':'+lane)
            if name=='coverage-both-edges' and c['minimum_module_branch_fraction']!=1:raise ValueError('both-edges-unproven')
            if name=='coverage-handler-missing' and not c['missing_error_paths']:raise ValueError('missing-handler-unproven')
        if set(coverage)!={'source','target'}:raise ValueError('coverage-control-lanes')
        rows.append({'id':name,'manifest_sha256':record['manifest_sha256'],'passed':True,
                     'business_status':record['status'],'business_verdict_not_control_acceptance':True})
    if len({r['id'] for r in rows})!=len(expected):raise ValueError('duplicate-coverage-control')
    result={'schema':'tsql-coverage-qualification/'+str(revision),'passed':True,'report_sha256':expected_report,
        'public_key_sha256':expected_key,'controls':rows,'images':plan['images'],
        'bridge_sha256':plan['coverage_bridge_sha256'],
        'collector_sha256':plan['code_sha256']['src/lightyear_data/tsql_procedures/'+('coverage.py' if revision==1 else 'coverage_v2.py')],
        'limitations':['procedural coverage only; SQL expression and dynamic-body branch coverage excluded',
          'PostgreSQL native branch fraction retained; per-handler proof conservative at 100%',
          'five public controls, not universal instrumentation proof'],
        'model_calls':0,'claim':'Operator review; not independent attestation'}
    if len(expected)==7:result['limitations'][-1]='seven public controls, not universal instrumentation proof'
    if revision==2:
        result['coverage_schemas']=SCHEMAS
        result['limitations'][-1]='nine public controls including custom schema and view exclusion; not universal proof'
    return result
