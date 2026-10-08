"""Held-out retrieval evaluation; authorship is recorded, never self-attested."""
from lightyear_control_tower.decisions import digest


def evaluate(plan,labels,keyword,hybrid):
    if (plan['label_author']==plan['search_tuner'] or not plan['label_author'] or
            len(labels)!=plan['query_count'] or not 50<=len(labels)<=100 or
            digest(labels)!=plan['labels_sha256'] or not 0<plan['minimum_recall5_gain']<1):
        raise ValueError('held-out benchmark binding')
    ids=[r['id'] for r in labels]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate query')
    def score(results):
        if set(results)!=set(ids):raise ValueError('query results incomplete')
        recall=[];rr=[]
        for row in labels:
            relevant=set(row['relevant_ids']);found=results[row['id']]
            if not relevant or len(found)!=len(set(found)):raise ValueError('query labels or duplicate ranks')
            recall.append(len(relevant&set(found[:5]))/len(relevant))
            rr.append(next((1/i for i,n in enumerate(found,1) if n in relevant),0))
        return dict(recall_at_5=sum(recall)/len(recall),mrr=sum(rr)/len(rr))
    a,b=score(keyword),score(hybrid)
    return dict(schema='graph-search-benchmark/1',plan_sha256=digest(plan),keyword=a,hybrid=b,
        measured_gain_eligible=b['recall_at_5']-a['recall_at_5']>=plan['minimum_recall5_gain'] and b['mrr']>=a['mrr'],
        promote_hybrid=False,
        authorship='declared identities; operator review, not independent attestation')


def run(plan,labels,projection,provider,proof,trust,*,now=None):
    """Compute rankings from a frozen projection and Tower-bound labels.

    Distinct label-owner and tuner identities are operator review, not proof
    of independent attestation. No caller-supplied rankings may promote search.
    """
    from copy import deepcopy
    from lightyear_factory.knowledge_trust import approve
    from .hybrid import build_index,search,LocalEmbedding
    if digest(projection)!=plan['projection_sha256']:raise ValueError('benchmark projection changed')
    decision=approve(proof,trust,'graph-search-labels',
        dict(plan=digest(plan),labels=digest(labels),projection=digest(projection)),['approved'],now=now)
    if decision['named_owner']!=plan['label_author'] or plan['label_author']==plan['search_tuner']:
        raise ValueError('label owner not bound or also search tuner')
    if not provider.local:raise ValueError('benchmark requires pinned local provider')
    if dict(id=provider.provider_id,version=provider.version)!=plan['provider']:raise ValueError('benchmark provider changed')
    keyword=deepcopy(projection);hybrid=deepcopy(projection)
    keyword['search_index']=build_index(keyword)
    hybrid['search_index']=build_index(hybrid,provider)
    results=[]
    for p,engine in ((keyword,LocalEmbedding()),(hybrid,provider)):
        results.append({row['id']:[v['id'] for v in search(p,row['query'],top_k=5,provider=engine)] for row in labels})
    result=evaluate(plan,labels,*results)
    result.update(promote_hybrid=result['measured_gain_eligible'],rankings_sha256=[digest(x) for x in results],
        decision_proof_sha256=digest(proof),projection_sha256=digest(projection),
        authorship='Tower-bound label owner distinct from tuner; operator review, not independent attestation')
    return result
