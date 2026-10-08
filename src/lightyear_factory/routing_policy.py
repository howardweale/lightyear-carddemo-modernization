"""Deterministic proposal compiler; its output still needs a Tower decision."""
import math
from lightyear_control_tower.decisions import digest
from .evaluation_matrix import wilson


def compile_policy(matrix,*,margin):
    if not math.isfinite(margin) or not 0<=margin<=.2:raise ValueError('routing margin')
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
                interval=wilson(s,n);best=max(p['passed']/p['run_count'] for p in peers)
                qualifies=interval[0]>=best-margin and c['false_acceptances']==0
                if c['cost_per_verified_task'] is None or not math.isfinite(c['cost_per_verified_task']):qualifies=False
                good &= qualifies;cost+=c['cost_per_verified_task'] or 0
                previous=versions.setdefault(model,c['model_version'])
                if previous!=c['model_version']:raise ValueError('model version changed')
                decisions.append(dict(task=task,model=model,workload=c['workload'],wilson_95=interval,
                    best_pass_rate=best,minimum_lower_bound=best-margin,eligible=qualifies))
            if good:eligible.append((cost,model))
        if eligible:
            _,chosen=min(eligible)
            routes[task]=dict(primary=chosen,matrix_receipts=[matrix['content_sha256']])
            if len(eligible)>1:routes[task]['fallback']=sorted(eligible)[1][1]
    return dict(schema='factory-routing-policy/1',routes=routes,model_versions=versions,
        rule=dict(minimum_paired_runs_per_cell=35,margin=margin,
            selection='cheapest cost per verified task satisfying the Wilson lower-bound rule on every workload',
            fallback='second cheapest eligible model, provider error only, same budget',
            no_eligible_model='retain configured default; no promoted route',false_acceptances=0),
        compiler_output=decisions,approval_required=True)
