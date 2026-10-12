"""Paired B07 planning simulation only: no models or trial execution.

Within each journey G/S share each slot; the pooled stratified sign-randomization
null conditions on each discordant pair. Summing those signs gives the exact
binomial McNemar test. Conservative paired-difference intervals use a union
bound on Clopper-Pearson limits for the two discordance probabilities.
"""
import json, math, random
from functools import lru_cache
from pathlib import Path
from lightyear_control_tower.decisions import digest

SEED=20261011
N=72

def binomial_tail(k,n,p):
    return sum(math.comb(n,i)*p**i*(1-p)**(n-i) for i in range(k,n+1))

@lru_cache(None)
def cp_lower(k,n,alpha):
    if not k:return 0.0
    lo,hi=0.0,1.0
    for _ in range(50):
        mid=(lo+hi)/2
        if binomial_tail(k,n,mid)>alpha:hi=mid
        else:lo=mid
    return (lo+hi)/2

@lru_cache(None)
def paired_lower(g_only,s_only,n,alpha=.05):
    # P(p10<L10 or p01>U01) <= alpha/2+alpha/2.
    return cp_lower(g_only,n,alpha/2)-(1-cp_lower(n-s_only,n,alpha/2))

def effect_interval(g_only,s_only,n):
    return [paired_lower(g_only,s_only,n,.025),-paired_lower(s_only,g_only,n,.025)]

def pvalue(g_only,s_only):
    d=g_only+s_only
    return min(1.0,2*sum(math.comb(d,i) for i in range(min(g_only,s_only)+1))/2**d) if d else 1.0

def simulate(repetitions=10000,seed=SEED):
    if type(repetitions)!=int or repetitions<100:raise ValueError('simulation-size')
    rng=random.Random(seed);rows=[]
    for discordance in (.2,.4,.6):
        for delta in (-.15,0,.05,.1,.15,.2):
            if abs(delta)>discordance:continue
            g=(discordance+delta)/2;s=(discordance-delta)/2
            superiority=ni=0; widths=[]
            for _ in range(repetitions):
                # 24 independent paired slots per journey; no drift arm or pilots.
                counts=[0,0]
                for journey in range(3):
                    for slot in range(24):
                        u=rng.random()
                        if u<g:counts[0]+=1
                        elif u<g+s:counts[1]+=1
                a,b=counts
                superiority+=pvalue(a,b)<.05 and a>b
                ni+=paired_lower(a,b,N)>-.15
                interval=effect_interval(a,b,N);widths.append(interval[1]-interval[0])
            rates=[superiority/repetitions,ni/repetitions]
            rows.append(dict(true_G_minus_S=delta,discordance_probability=discordance,
                superiority_probability=rates[0],noninferiority_probability=rates[1],
                monte_carlo_se=[math.sqrt(p*(1-p)/repetitions) for p in rates],mean_95_interval_width=sum(widths)/repetitions))
    value=dict(schema='b07-prefreeze-power/1',seed=seed,repetitions_per_scenario=repetitions,
        allocation='24 paired slots per journey,72 analyzed per arm; both arms on each of2 runners',
        primary='pooled journey-stratified two-sided exact paired sign-randomization/McNemar; graph superiority requires positive difference',
        secondary='G-S > -0.15; conservative one-sided95% lower bound from Bonferroni Clopper-Pearson discordances',
        effect_interval='conservative two-sided95% paired difference interval; not a claim of marginal Newcombe equivalence',
        scenarios=rows,adequacy_target_probability=.8,limitations=['No observed effect or discordance estimate; sensitivity grid only','Independent pairs assumed; within-pair outcomes dependent','No causal claim for historical B06 contrasts','No data-dependent sample-size reduction','This is an unsealed design proposal; statistical freeze and spending remain blocked'],
        freeze_ready=False,model_calls=0,native_runs=0)
    value['margin_not_assessable_at_80_percent_in_all_equal_performance_scenarios']=any(r['true_G_minus_S']==0 and r['noninferiority_probability']<.8 for r in rows)
    value['content_sha256']=digest(value)
    return value

if __name__=='__main__':
    result=simulate()
    path=Path('docs/factory/b07-prefreeze-power-2026-10-11.json')
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'seal':result['content_sha256'],'equal_performance':[r for r in result['scenarios'] if r['true_G_minus_S']==0]}))
