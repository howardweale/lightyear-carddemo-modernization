"""Replay every retained IMS case against typed PostgreSQL adapters or name its gap.

The historical model supplies status expectations. Original generated segment
bytes independently supply returned-segment and full database-after-state oracles.
No native IMS, GSAM, checkpoint/restart or secondary-index equivalence is claimed.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import uuid

from lightyear_readiness.ims_qualification import execute_conformance_case
from .access import DliRepository
from .plan import build
from .proof import synthetic_segment
from .schema import ddl,quote


def key(raw,m):
    k=m['keys'][0];return raw[k['key_offset']:k['key_offset']+k['key_length']]


def dispatch(repo,request,roots,children,rm,cm,replacement):
    op=request['operation'];rn=request.get('root','R001');cn=request.get('child','D001')
    rk=key(roots[rn],rm);ck=key(children[cn],cm)
    if op in ('GU','GHU'):return repo.gu(rk,hold=op=='GHU')
    if op in ('GN','GHN'):
        result=('GB',None)
        for _ in range(int(request.get('position',0))+1):result=repo.gn(hold=op=='GHN')
        return result
    if op in ('GNP','GHNP'):
        if request.get('parent_established',True):repo.gu(rk)
        return repo.gnp(ck,hold=op=='GHNP')
    if op=='SSA':
        # Corpus supplies parsed qualifiers, not unrestricted textual SSA grammar.
        if request.get('syntax') not in ('QUALIFIED','UNQUALIFIED'):return 'AJ',None
        result=repo.gu(rk)
        return repo.gnp(ck) if result[0]=='  ' and request.get('child') else result
    if op in ('ISRT_ROOT','ISRT_CHILD'):
        return (repo.insert(rk,roots[rn]) if op=='ISRT_ROOT' else repo.insert(ck,children[cn],rk)),None
    if op in ('REPL','DLET'):
        if request.get('hold'):
            repo.gu(rk,hold=request.get('target','ROOT')=='ROOT')
            if request.get('target')=='CHILD':repo.gnp(ck,hold=True)
        return repo.mutate(replacement,delete=op=='DLET'),None
    if op=='PROCOPT':return ('  ' if repo.procopt in ('A','AP') else 'AM'),None
    if op=='SENSEG':return ('  ' if request['segment'] in (rm['segment']['name'],cm['segment']['name']) else 'GE'),None
    raise NotImplementedError('No migrated implementation for '+op)


# The fixture hierarchy is explicit and independent of the adapter's traversal.
PREORDER=(('R001',None),('R001','D001'),('R001','D002'),('R002',None),('R002','D003'))
CHILD_CASES=(
    dict(id='41-gn-second-child',request=dict(operation='GN',position=2),reference_scope='explicit-two-level-fixture'),
    dict(id='42-ghn-other-parent-child',request=dict(operation='GHN',position=4),reference_scope='explicit-two-level-fixture'),
)


def execution_scope(request):
    op=request['operation']
    if op in ('PROCOPT','SENSEG') or (op=='SSA' and request.get('syntax') not in ('QUALIFIED','UNQUALIFIED')):
        return 'replay-local'
    if op in ('GU','GHU','GN','GHN','GNP','GHNP','SSA','ISRT_ROOT','ISRT_CHILD','REPL','DLET'):
        return 'adapter'
    return 'unsupported'


def replay_counts(records):
    counts={scope:sum(r['execution_scope']==scope for r in records)
            for scope in ('adapter','replay-local','unsupported')}
    matched={scope:sum(r['execution_scope']==scope and r['verdict']=='matched' for r in records)
             for scope in counts}
    return dict(adapter_cases=counts['adapter'],adapter_matched=matched['adapter'],
                replay_local_cases=counts['replay-local'],replay_local_matched=matched['replay-local'],
                unsupported=counts['unsupported'],matched=sum(matched.values()))


def scope_text(counts):
    return (f"Adapter calls: {counts['adapter_matched']}/{counts['adapter_cases']}; "
            f"replay-local answers: {counts['replay_local_matched']}/{counts['replay_local_cases']}; "
            f"unsupported: {counts['unsupported']}. Replay-local cases earn no adapter credit.")


def replay(connection,source,corpus_path):
    plan,entries=build(source);corpus_raw=Path(corpus_path).read_bytes();corpus=json.loads(corpus_raw)
    _,rl,rm=next(e for e in entries if e[2]['table']=='pautsum0');_,cl,cm=next(e for e in entries if e[2]['table']=='pautdtl1')
    roots={f'R{i:03}':synthetic_segment(rl,rm,i) for i in (1,2,3,999)}
    children={f'D{i:03}':synthetic_segment(cl,cm,i) for i in (1,2,3,4)}
    records=[]
    for case in [*corpus['cases'],*CHILD_CASES]:
        q=case['request'];op=q['operation']
        if case.get('reference_scope')=='explicit-two-level-fixture':
            reference=dict(ims_status='  ',scope=case['reference_scope'])
        else:
            reference=execute_conformance_case(case)
        result=dict(id=case['id'],operation=op,reference=reference,execution_scope=execution_scope(q))
        with connection.transaction(force_rollback=True):
            schema='replay_'+uuid.uuid4().hex;connection.execute('CREATE SCHEMA '+quote(schema));connection.execute('SET LOCAL search_path TO '+quote(schema))
            connection.execute(ddl(rm));connection.execute(ddl(cm))
            repo=DliRepository(connection,rm,rl,cm,cl,'AP')
            expected={}
            for rn,cns in [('R001',['D001','D002']),('R002',['D003'])]:
                rk=key(roots[rn],rm);assert repo.insert(rk,roots[rn])=='  ';expected[('pautsum0',rk)]=roots[rn]
                for cn in cns:
                    ck=key(children[cn],cm);assert repo.insert(ck,children[cn],rk)=='  ';expected[('pautdtl1',rk+ck)]=children[cn]
            repo.boundary();repo.procopt=q.get('procopt','AP')
            rn=q.get('root','R001');cn=q.get('child','D001');rk=key(roots[rn],rm);ck=key(children[cn],cm)
            target=('pautdtl1',rk+ck) if q.get('target')=='CHILD' else ('pautsum0',rk)
            replacement=bytearray(expected.get(target,roots[rn]));replacement[-1]=0xc2;replacement=bytes(replacement)
            try:status,segment=dispatch(repo,q,roots,children,rm,cm,replacement)
            except NotImplementedError as error:
                result.update(verdict='unsupported',reason=str(error));records.append(result);continue
            expected_segment=None
            if status=='  ':
                if op in ('GU','GHU','SSA'):expected_segment=children[cn] if q.get('child') else roots[rn]
                elif op in ('GN','GHN'):
                    er,ec=PREORDER[int(q.get('position',0))]
                    expected_segment=roots[er] if ec is None else children[ec]
                elif op in ('GNP','GHNP'):expected_segment=children[cn]
                elif op=='ISRT_ROOT':expected[('pautsum0',rk)]=roots[rn]
                elif op=='ISRT_CHILD':expected[('pautdtl1',rk+ck)]=children[cn]
                elif op=='REPL':expected[target]=replacement
                elif op=='DLET':
                    expected.pop(target)
                    if target[0]=='pautsum0':expected={k:v for k,v in expected.items() if not(k[0]=='pautdtl1' and k[1].startswith(rk))}
            actual={(store.table,row['path_key']):store.bytes(row) for store in (repo.root,repo.child) for row in store.rows()}
            correction={'07-gnp-without-parent':'GP','28-procopt-g-denies-update':'AM'}.get(case['id'])
            wanted=correction or reference['ims_status']
            result.update(verdict='matched' if status==wanted and segment==expected_segment and actual==expected else 'divergent',
                adapter_status=status,status_equal_to_historical=status==reference['ims_status'],status_correction=correction,
                segment_compared=expected_segment is not None,segment_equal=segment==expected_segment,
                expected_segment_sha256=sha256(expected_segment).hexdigest() if expected_segment else None,
                actual_segment_sha256=sha256(segment).hexdigest() if segment else None,
                after_state_equal=actual==expected,after_state_segments=len(actual),
                after_state_sha256=sha256(b''.join(k[0].encode()+k[1]+v for k,v in sorted(actual.items()))).hexdigest())
            records.append(result)
    counts=replay_counts(records)
    return dict(schema='carddemo-typed-ims-replay/2',total=len(records),historical_corpus_cases=len(corpus['cases']),
        supplementary_cases=len(CHILD_CASES),**counts,execution_summary=scope_text(counts),
        segment_comparisons=sum(r.get('segment_compared',False) for r in records),
        unexpected_differences=[r['id'] for r in records if r['verdict']=='divergent'],
        corpus_sha256=sha256(corpus_raw).hexdigest(),plan_sha256=plan['content_sha256'],cases=records,
        scope='GN/GHN traverse roots and children in fixture preorder; historical case 02 name is retained but its returned segment now includes the child. Two-level typed PostgreSQL adapter against synthetic reference; parsed SSA qualifiers only. Historical DJ expectations corrected to GP/AM per October 16 work order. Unsupported cases count in the denominator.',
        signed=False,release_authorized=False)


if __name__=='__main__':
    import psycopg
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    with psycopg.connect(os.environ['CARDDEMO_DATA_DSN']) as c:
        result=replay(c,Path('spec/modernization/carddemo-data'),Path('readiness/ims-expiry/conformance/cases.json'));c.rollback()
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(1 if result['unexpected_differences'] else 0)
