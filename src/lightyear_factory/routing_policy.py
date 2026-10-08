"""Deterministic proposal compiler; its output still needs a Tower decision."""
import math
from lightyear_control_tower.decisions import digest
from .evaluation_matrix import wilson


def paired_interval(left, right):
    """Newcombe paired Wilson interval (method 10), on matched binary outcomes.

    The correlation term uses the actual discordant pairs, not marginal totals.
    Constant identical outcomes use limiting correlation 1; unequal constants 0.
    """
    n=len(left)
    if not n or len(right)!=n or any(type(x) is not bool for x in left+right):
        raise ValueError('paired binary outcomes required')
    a=sum(left)/n;b=sum(right)/n
    joint=sum(x and y for x,y in zip(left,right))/n
    variance=a*(1-a)*b*(1-b)
    r=(joint-a*b)/math.sqrt(variance) if variance else (1 if left==right else 0)
    la,ua=wilson(sum(left),n);lb,ub=wilson(sum(right),n)
    low=math.sqrt(max(0,(a-la)**2+(ub-b)**2-2*r*(a-la)*(ub-b)))
    high=math.sqrt(max(0,(ua-a)**2+(b-lb)**2-2*r*(ua-a)*(b-lb)))
    return [max(-1,a-b-low),min(1,a-b+high)]


def compile_policy(matrix,*,margin,minimum_wilson_lower=.8):
    if not math.isfinite(margin) or not 0<=margin<=.2:raise ValueError('routing margin')
    if not math.isfinite(minimum_wilson_lower) or not 0<minimum_wilson_lower<=1:raise ValueError('absolute quality floor')
    if matrix['content_sha256']!=digest({k:v for k,v in matrix.items() if k!='content_sha256'}):
        raise ValueError('matrix hash')
    if matrix['false_acceptances']!=0:raise ValueError('false acceptances')
    if any(c.get('escalation_arm') for c in matrix['cells']):
        raise ValueError('escalation arm requires a separate reviewed policy; not a single-model route')
    routes={};versions={};decisions=[]
    tasks=sorted({c['task_type'] for c in matrix['cells']})
    for task in tasks:
        cells=[c for c in matrix['cells'] if c['task_type']==task]
        workloads={c['workload'] for c in cells};models={c['model'] for c in cells}
        eligible=[]
        for model in sorted(models):
            own=[c for c in cells if c['model']==model]
            if len(own)!=len(workloads) or {c['workload'] for c in own}!=workloads:raise ValueError('matrix cells missing')
            good=True;cost=0
            for c in own:
                n=c['run_count'];pair_ids=set(c['pair_ids']);s=c['passed']
                if n<35 or len(set(c['runs']))!=n or len(pair_ids)!=n or not 0<=s<=n:raise ValueError('matrix sample floor')
                peers=[p for p in cells if p['workload']==c['workload']]
                if any(set(p['pair_ids'])!=pair_ids for p in peers):raise ValueError('matrix unpaired cells')
                paired=[]
                for p in [c,*peers]:
                    outcomes=p.get('paired_outcomes',{})
                    if (set(outcomes)!=pair_ids or any(type(v) is not bool for v in outcomes.values())
                        or sum(outcomes.values())!=p['passed']):raise ValueError('recorded paired outcomes required')
                for p in peers:
                    ids=sorted(pair_ids)
                    ci=paired_interval([c['paired_outcomes'][i] for i in ids],[p['paired_outcomes'][i] for i in ids])
                    paired.append(dict(peer=p['model'],difference_95=ci))
                interval=wilson(s,n)
                qualifies=interval[0]>=minimum_wilson_lower and all(x['difference_95'][0]>=-margin for x in paired) and c['false_acceptances']==0
                if c['cost_per_verified_task'] is None or not math.isfinite(c['cost_per_verified_task']):qualifies=False
                good &= qualifies;cost+=c['cost_per_verified_task'] or 0
                previous=versions.setdefault(model,c['model_version'])
                if previous!=c['model_version']:raise ValueError('model version changed')
                decisions.append(dict(task=task,model=model,workload=c['workload'],wilson_95=interval,
                    paired_comparisons=paired,minimum_wilson_lower=minimum_wilson_lower,eligible=qualifies))
            if good:eligible.append((cost,model))
        if eligible:
            _,chosen=min(eligible)
            routes[task]=dict(primary=chosen,matrix_receipts=[matrix['content_sha256']])
            if len(eligible)>1:routes[task]['fallback']=sorted(eligible)[1][1]
    return dict(schema='factory-routing-policy/1',routes=routes,model_versions=versions,
        rule=dict(minimum_paired_runs_per_cell=35,margin=margin,minimum_wilson_lower=minimum_wilson_lower,
            selection='cheapest cost per verified task satisfying the absolute Wilson floor and paired non-inferiority rule on every workload',
            fallback='second cheapest eligible model, provider error only, same budget',
            no_eligible_model='retain configured default; no promoted route',false_acceptances=0),
        compiler_output=decisions,approval_required=True)
