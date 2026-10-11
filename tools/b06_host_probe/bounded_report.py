"""Aggregate bounded host evidence. No native admission and no payload publication."""
import csv
import json
import math
from collections import Counter
from pathlib import Path
from tools.b06_host_probe.native_memory import digest


def fitted_growth(rows, *, minimum_events=50000, lag=10):
    """OLS slope with a Newey-West interval for successive, correlated GC samples."""
    rows=[r for r in rows if r['events'] >= minimum_events]
    if len(rows) < 25: raise ValueError('insufficient-post-warmup-samples')
    x=[r['events'] for r in rows]; y=[r['heap_used_after_gc'] for r in rows]
    n=len(x); mx=sum(x)/n; my=sum(y)/n
    z=[v-mx for v in x]; xx=sum(v*v for v in z)
    if xx == 0: raise ValueError('constant-event-count')
    slope=sum(a*(b-my) for a,b in zip(z,y))/xx
    residual=[b-my-slope*a for a,b in zip(z,y)]
    scores=[a*b for a,b in zip(z,residual)]
    variance=sum(v*v for v in scores)
    for k in range(1,min(lag,n-1)+1):
        variance+=2*(1-k/(lag+1))*sum(scores[i]*scores[i-k] for i in range(k,n))
    se=math.sqrt(max(0,variance)*n/(n-2))/xx
    low,high=slope-1.96*se,slope+1.96*se
    return dict(method='OLS; Newey-West Bartlett lag 10; asymptotic two-sided 95% interval',
                warmup_events=minimum_events,sample_count=n,first_event=x[0],last_event=x[-1],
                bytes_per_emitted_event=slope,slope_95_percent=[low,high],
                significantly_positive=low>0,intercept_bytes=my-slope*mx)


def summarize(folder):
    folder=Path(folder)
    result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
    for name in ('heap.csv','observer.stdout','observer.stderr','peak-histogram.txt'):
        if digest(folder/name)!=result['output_sha256'][name]:raise ValueError('changed-host-output:'+name)
    with (folder/'heap.csv').open() as stream:rows=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(stream)]
    if rows != result['heap_samples']:raise ValueError('changed-host-samples')
    counts=Counter(); diagnostic_bytes=0
    diagnostic={'observer-audit','breakpoint-lifecycle','watched-class-prepare','observer-heap-telemetry'}
    with (folder/'observer.stdout').open('rb') as stream:
        for line in stream:
            if len(line)>4*1024*1024:raise ValueError('host-event-size')
            event=json.loads(line);counts[event['kind']]+=1
            if event['kind'] in diagnostic:diagnostic_bytes+=len(line.rstrip(b'\r\n'))
    try: fit=fitted_growth(rows)
    except ValueError as error: fit={'unavailable':str(error),'significantly_positive':None}
    completed=result['workload_completed'] and result['observer_returncode']==result['target_returncode']==0
    return dict(schema='b06-bounded-host-memory/1',host_only=True,model_calls=0,
                qualification_credit=False,measurement_credit=False,completed=completed,
                accepted=completed and not result['oom_reproduced'] and fit['significantly_positive'] is False,
                event_denominator='emitted records; compare generation counts separately because audit volume changed',
                generation_entries=counts['generation-entry'],event_counts=dict(counts),
                diagnostic_records=sum(counts[k] for k in diagnostic),diagnostic_bytes=diagnostic_bytes,
                diagnostic_records_per_generation=sum(counts[k] for k in diagnostic)/counts['generation-entry'],
                heap_bytes=192*1024*1024,peak_after_gc_bytes=result['sample_peak'],growth_fit=fit,
                elapsed_seconds=result['elapsed_seconds'],last_sample=rows[-1],
                observer_source_sha256=result['observer_source_sha256'],compiled_observer_sha256=result['compiled_observer_sha256'],
                mirror_adapter_sha256=result.get('mirror_adapter_sha256'),
                soft_reference_policy_ms_per_mib=result.get('soft_reference_policy_ms_per_mib','JVM-default'),
                result_sha256=digest(folder/'result.json'),output_sha256=result['output_sha256'])
