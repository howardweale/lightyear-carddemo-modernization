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
        promote_hybrid=b['recall_at_5']-a['recall_at_5']>=plan['minimum_recall5_gain'] and b['mrr']>=a['mrr'],
        authorship='declared identities; operator review, not independent attestation')
