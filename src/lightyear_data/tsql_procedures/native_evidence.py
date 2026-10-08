"""Signed native artifacts and database-free, deterministic comparison/replay."""
from __future__ import annotations
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from .capture import state_changes


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def sha(raw): return hashlib.sha256(raw).hexdigest()


def write(path, value):
    raw = canonical(value) + b'\n'
    with Path(path).open('xb') as stream: stream.write(raw)
    return sha(raw)


def sign(body, key):
    raw = canonical(body)
    return dict(body, content_sha256=sha(raw), signature=base64.b64encode(key.sign(raw)).decode())


def verify(value, public):
    body = {k:v for k,v in value.items() if k not in ('signature','content_sha256')}
    raw = canonical(body)
    if sha(raw)!=value['content_sha256']: raise ValueError('envelope-hash')
    Ed25519PublicKey.from_public_bytes(public).verify(base64.b64decode(value['signature'],validate=True),raw)
    return body


def _sets(obs, engine):
    out = []
    for rs in obs['result_sets']:
        columns = []
        for c in rs['columns']:
            # Explicit public-corpus mapping, validated against driver metadata.
            # This does not normalize values, whitespace or numeric strings.
            allowed = ('167','175','231','239') if engine=='sqlserver' else ('25','1042','1043')
            if c['type_code'] not in allowed: raise ValueError('unmapped-result-type:'+c['type_code'])
            columns.append({'name':c['name'],'type':'variable-character'})
        out.append({'columns':columns,'rows':rs['rows']})
    return out


def _table_rows(state):
    return {name: {'columns':[c[0] for c in table['columns']],
                   'primary_key':table['primary_key'],
                   'rows':sorted(canonical(r).decode() for r in table['rows'])}
            for name,table in state['tables'].items()}


def compare(source, target, family):
    """Observed differences, not an equivalence certificate or policy approval."""
    for lane in (source,target):
        effects = state_changes(lane['before'],lane['after'])
        if canonical(effects)!=canonical(lane['observation']['side_effects']):
            raise ValueError('side-effect-replay-mismatch')
        if lane['reset']['outer_rollback'] is not False: raise ValueError('reset-policy')
    if source['reset']['method']!='golden-backup-restore' or target['reset']['method']!='fresh-database-from-template':
        raise ValueError('reset-method')
    a,b=source['observation'],target['observation']
    differences,unresolved=[],[]
    def diff(name,left,right):
        if canonical(left)!=canonical(right): differences.append({'observable':name,'source':left,'target':right,'trap_family':family})
    try: diff('result_sets',_sets(a,'sqlserver'),_sets(b,'postgresql'))
    except ValueError as ex: unresolved.append(str(ex))
    diff('output_parameters',a['output_parameters'],b['output_parameters'])
    diff('return_code',a['return_code'],b['return_code'])
    # Engine-specific error numbers remain intact; no undeclared error map.
    if bool(a['error'])!=bool(b['error']): diff('error-presence',bool(a['error']),bool(b['error']))
    elif a['error']: unresolved.append('both-engines-error: error-code-mapping-required')
    for state in ('before','after'):
        diff('all-table-'+state,_table_rows(source[state]),_table_rows(target[state]))
    diff('temp_objects',a['temp_objects'],b['temp_objects'])
    # Actual TDS token counts retained. PostgreSQL protocol does not expose the
    # counts of each nested PL/pgSQL statement; do not invent that stream.
    counts=[x['row_count'] for x in a['tds_tokens'] if 'row_count' in x and x['flags'] & 0x10]
    if counts: unresolved.append('TDS-row-count-stream-needs-target-instrumentation')
    info=[x['message']['message'] for x in a['tds_tokens'] if x['token']==171]
    notices=[x['message_primary'] for x in b['notices']]
    diff('informational-message-text',info,notices)
    if info or notices: unresolved.append('informational-severity-mapping-not-admitted')
    if a['transaction_after']!=[0,0] or b['transaction_after']!='IDLE':
        differences.append({'observable':'transaction-open-or-failed','source':a['transaction_after'],'target':b['transaction_after'],'trap_family':family})
    if source['after']['identity_sequence_state'] or target['after']['identity_sequence_state']:
        unresolved.append('identity-sequence-catalog-mapping-not-admitted')
    if family in (18,25): unresolved.append('unordered-choice-policy-required')
    return {'schema':'tsql-native-comparison/1','differences':differences,
            'observed_status':'divergent' if differences else 'match-on-compared-observables',
            'verdict':'insufficient-evidence' if family in (18,25) or not differences else 'divergent',
            'unresolved':unresolved,
            'mappings':['exact table/column/PK names inferred; operator review pending',
                        'varchar/nvarchar/text result columns -> variable-character; values unchanged',
                        'table rows compared as duplicate-preserving multisets'],
            'limitations':['statement/branch/error-path coverage not qualified',
                           'complete internal transaction-event stream not captured',
                           'PostgreSQL nested statement row-count stream not captured',
                           'public-fixture behavior only; security and performance not assessed'],
            'model_calls':0}


def seal_pair(directory, body, key):
    directory=Path(directory)
    files={p.name:sha(p.read_bytes()) for p in sorted(directory.iterdir()) if p.is_file()}
    manifest=sign(dict(body,schema='tsql-native-pair/1',files=files,model_calls=0),key)
    write(directory/'manifest.json',manifest)
    return manifest


def compare_v2(source,target,mapping,qualification=None,revision=2,coverage_module=None):
    from .policy import validate,table_contract,identity_contract
    if coverage_module is None:
        from . import coverage as coverage_module
    replay_coverage=coverage_module.replay_coverage
    validate(mapping)
    family=mapping['trap_family']
    original=compare(source,target,family) # includes delta and reset validation
    differences=[dict(d,classification='lossy') for d in original['differences']]
    unresolved=[]
    normalized=[]
    def diff(name,left,right):
        if canonical(left)!=canonical(right):differences.append({
            'observable':name,'source':left,'target':right,'trap_family':family,'classification':'lossy'})
    def pending(name,classification='policy-decision-required'):
        unresolved.append({'observable':name,'classification':classification,'trap_family':family})
    # Set order is preserved, row order is explicitly mapped per public profile.
    differences=[d for d in differences if d['observable']!='result_sets']
    try:
        a,b=_sets(source['observation'],'sqlserver'),_sets(target['observation'],'postgresql')
        for sets in (a,b):
            for rs in sets:rs['rows']=sorted(rs['rows'],key=canonical)
        diff('result_sets',a,b)
        normalized.append('result column character representation; row multisets; values unchanged')
    except ValueError as ex:pending(str(ex),'unsupported')
    for state in ('before','after'):
        try:diff('table-contract-'+state,table_contract(source[state]),table_contract(target[state]))
        except ValueError as ex:pending(str(ex),'unsupported')
        try:diff('identity-sequence-'+state,identity_contract(source[state]),identity_contract(target[state]))
        except (ValueError,KeyError) as ex:pending('identity-map:'+str(ex),'unsupported')
    normalized.extend(['int -> integer; varchar(n) -> character varying(n); nullability retained',
        'exact-name schema/table/column inference flagged',
        'identity -> owned sequence; unconsumed value -> null, exact seed/increment/last consumed'])
    a,b=source['observation'],target['observation']
    if a['error'] and b['error']:
        error_contract=mapping['calling_convention'].get('public_error_equivalence')
        if (revision>=4 and error_contract=='check-constraint-547-23514' and
                a['error'].get('number')==547 and b['error'].get('sqlstate')=='23514'):
            normalized.append('public supplemental CHECK violation: SQL Server 547 -> PostgreSQL 23514; raw messages retained')
        else:pending('error-map-required')
    if any(t.get('flags',0)&0x10 for t in a['tds_tokens']):pending('row-count-policy-required')
    infos=[t['message'] for t in a['tds_tokens'] if t['token']==171]
    if any(not 0<=t['severity']<=10 for t in infos) or any(
        n['severity_nonlocalized']!='NOTICE' or n['sqlstate']!='00000' for n in b['notices']):
        pending('unmapped-informational-severity')
    if infos or b['notices']:normalized.append('TDS INFO severity 0..10 -> NOTICE/00000; exact message text')
    if family in (18,25):pending('unordered-choice-policy-required')
    coverage={}
    for lane,value in (('source',source),('target',target)):
        record=value['observation'].get('coverage')
        if record is None:pending(lane+'-coverage-missing','unsupported')
        else:coverage[lane]=replay_coverage(record)
    eligible=len(coverage)==2 and all(c['eligible'] for c in coverage.values())
    qualified=qualification is not None and qualification.get('schema') in ('tsql-coverage-qualification/1','tsql-coverage-qualification/2') and qualification.get('passed') is True
    if qualification is not None and not qualified:raise ValueError('coverage-qualification-contract')
    if qualified:
        if (sha(Path(coverage_module.__file__).read_bytes())!=qualification['collector_sha256']
                or source['observation']['coverage']['raw']['bridge_sha256']!=qualification['bridge_sha256']):
            raise ValueError('coverage-qualification-code-binding')
    verdict=('divergent' if differences and family not in (18,25) else
             'equivalent' if not differences and not unresolved and eligible and qualified else 'insufficient-evidence')
    result={'schema':'tsql-native-comparison/'+str(revision),'mapping':mapping,
        'differences':differences,'unresolved':unresolved,'coverage':coverage,
        'coverage_thresholds_met':eligible,'coverage_qualification':qualification,
        'collector_qualification':({5:'five',7:'seven',9:'nine'}[len(qualification['controls'])]+'-native-controls-passed') if qualified else 'pending-native-controls',
        'observed_status':'divergent' if differences else 'match-on-compared-observables',
        'verdict':verdict,
        'normalized_fields':normalized,'inferred_mappings_flagged':True,
        'gates':{'inventory-completeness':'public-corpus-bound','dependency-closure':'all-user-modules-captured',
            'result-and-side-effect-equivalence':'failed' if differences else 'observed-match',
            'transaction-and-exception-behavior':'exit-state-and-all-table-effects-compared',
            'security-context':'not-assessed','performance-and-operability':'not-assessed'},
        'limitations':['public-fixture behavior only','Tower certificate release not authorized',
            'complete internal transaction event stream not captured',
            'PostgreSQL error paths conservatively require 100% native branch coverage'],
        'model_calls':0}
    if revision==2:
        if qualification is not None:raise ValueError('legacy-comparison-cannot-qualify')
        result.pop('coverage_qualification')
        result['limitations'][1]='coverage collector qualification pending'
    return result


def replay_pair(directory, public, expected_hash):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_bytes())
    if manifest['content_sha256']!=expected_hash: raise ValueError('unexpected-manifest')
    body=verify(manifest,public)
    if body['schema']!='tsql-native-pair/1' or body['model_calls']!=0: raise ValueError('manifest-contract')
    if set(body['files'])!={'source.json','target.json','comparison.json'}: raise ValueError('file-closure')
    if {p.name for p in directory.iterdir()}!=set(body['files'])|{'manifest.json'}: raise ValueError('extra-evidence-file')
    values={}
    for name,digest in body['files'].items():
        path=directory/name
        if path.is_symlink() or not path.is_file(): raise ValueError('evidence-path')
        raw=path.read_bytes()
        if sha(raw)!=digest: raise ValueError('evidence-changed')
        values[name]=json.loads(raw)
    saved=values['comparison.json']
    if saved['schema']=='tsql-native-comparison/5':
        from .comparison_v5 import compare as compare_v5
        if saved['mapping']['assets']!=body['assets']:raise ValueError('mapping-asset-binding')
        result=compare_v5(values['source.json'],values['target.json'],saved['mapping'],saved.get('coverage_qualification'))
    elif saved['schema'] in ('tsql-native-comparison/2','tsql-native-comparison/3','tsql-native-comparison/4'):
        if saved['mapping']['assets']!=body['assets']:raise ValueError('mapping-asset-binding')
        result=compare_v2(values['source.json'],values['target.json'],saved['mapping'],saved.get('coverage_qualification'),int(saved['schema'][-1]))
    else:result=compare(values['source.json'],values['target.json'],body['trap_family'])
    if canonical(result)!=canonical(values['comparison.json']): raise ValueError('comparison-replay-mismatch')
    return {'schema':'tsql-native-replay/1','manifest_sha256':expected_hash,
            'signature_verified':True,'all_files_verified':True,'all_table_deltas_recomputed':True,
            'comparison_recomputed':True,'comparison':result,'database_calls':0,'model_calls':0}
