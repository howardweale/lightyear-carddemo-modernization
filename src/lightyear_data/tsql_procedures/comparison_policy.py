"""Explicit Tower policy admission and deterministic float tolerance comparison.

Only representation tolerance is implemented. Unordered choices, unresolved
callees, row-count suppression and unsupported facts cannot be waived here.
"""
import math
from .native_evidence import canonical,sha
from .tower_policy import admit,bindings

def validate(policy):
    if set(policy)!={'schema','absolute_tolerance','relative_tolerance'} or policy['schema']!='tsql-float-tolerance/1':
        raise ValueError('unsupported-procedure-policy')
    for k in ('absolute_tolerance','relative_tolerance'):
        if type(policy[k]) not in (int,float) or not math.isfinite(policy[k]) or policy[k]<0:raise ValueError('invalid-float-tolerance')
    if policy['relative_tolerance']>=1:raise ValueError('relative-tolerance-must-be-less-than-one')
    return policy

def context(corpus,item,variant):
    return dict(inventory={'corpus_sha256':sha(canonical(corpus))},
                procedure={'source':item['assets']['source']['sha256'],'target':item['assets'][variant]['sha256']},
                evidence={'assets':item['assets'],'calling_convention':item['calling_convention']})

def prepare(entry,public,expected_key_sha256,*,scope,head,now,bound_context):
    if sha(public)!=expected_key_sha256:raise ValueError('policy-authority-hash')
    policy=validate(entry['policy']);bound=bindings(policy=policy,**bound_context)
    admitted=admit(entry['proof'],public,bound,scope=scope,head=head,now=now)
    return dict(schema='tsql-policy-admission/1',policy=policy,proof=entry['proof'],public_key_hex=public.hex(),
                trusted_key_sha256=expected_key_sha256,scope=scope,journal_head=head,checked_at=now.isoformat(),
                bound_context=bound_context,admission=admitted)

def replay(record):
    from datetime import datetime
    result=prepare({'policy':record['policy'],'proof':record['proof']},bytes.fromhex(record['public_key_hex']),
        record['trusted_key_sha256'],scope=record['scope'],head=record['journal_head'],now=datetime.fromisoformat(record['checked_at']),
        bound_context=record['bound_context'])
    if canonical(result)!=canonical(record):raise ValueError('policy-admission-replay')
    return result['policy']

def equal(a,b,policy):
    if a==b:return True
    if isinstance(a,dict) and isinstance(b,dict):
        if set(a)==set(b)=={'type','value'} and a['type']==b['type']=='binary-float':
            x,y=float.fromhex(a['value']),float.fromhex(b['value'])
            if not math.isfinite(x) or not math.isfinite(y):raise ValueError('nonfinite-float-evidence')
            return math.isclose(x,y,rel_tol=policy['relative_tolerance'],abs_tol=policy['absolute_tolerance'])
        return set(a)==set(b) and all(equal(a[k],b[k],policy) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(equal(x,y,policy) for x,y in zip(a,b))
    return False

def multiset_equal(a,b,policy):
    # Tolerance is nontransitive. Find a complete bipartite matching, never
    # round values into buckets or use greedy matching that can lose a match.
    if len(a)!=len(b):return False
    if len(a)>1000:raise ValueError('tolerance-matching-bound')
    edges=[[j for j,y in enumerate(b) if equal(x,y,policy)] for x in a];matched={}
    def visit(i,seen):
        for j in edges[i]:
            if j in seen:continue
            seen.add(j)
            if j not in matched or visit(matched[j],seen):matched[j]=i;return True
        return False
    return all(visit(i,set()) for i in range(len(a)))

def observable_equal(name,a,b,policy):
    if name.startswith('all-table-'):
        if set(a)!=set(b):return False
        return all({k:v for k,v in a[t].items() if k!='rows'}=={k:v for k,v in b[t].items() if k!='rows'}
                   and multiset_equal(a[t]['rows'],b[t]['rows'],policy) for t in a)
    if name=='result_sets':
        return len(a)==len(b) and all(x['columns']==y['columns'] and multiset_equal(x['rows'],y['rows'],policy) for x,y in zip(a,b))
    if name=='ordered-result-sets':return equal(a,b,policy)
    return False
