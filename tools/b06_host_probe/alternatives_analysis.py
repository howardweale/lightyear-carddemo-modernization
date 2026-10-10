"""Pure analysis of saved public/engineering records; never starts an experiment.

JDK package names do not prove image-only provenance. Classifications require an
explicit reviewed witness per captured entry. Unknown entries stay unknown.
"""
from collections import Counter
import json
from pathlib import Path
from tools.ms94_b06_engineering import LABEL, require, sha


def summarize(path, classifications=None):
    classifications=classifications or {}; kinds=Counter(); methods=Counter(); groups=Counter()
    sequences=[]; raw_bytes=0; refused=False; death=False; entries=[]
    with Path(path).open('rb') as stream:
        for raw in stream:
            require(len(raw)<=4*1024*1024+1,'analysis-line-cap'); raw_bytes+=len(raw)
            row=json.loads(raw); event=row.get('event',row)
            seq=event['sequence']; require(seq==len(sequences)+1,'analysis-sequence-gap');sequences.append(seq)
            kinds[event['kind']]+=1
            if event['kind']=='observer-audit' and event['action']=='dispatch-refused':refused=True
            if event['kind']=='vm-death':death=True
            if event['kind']=='generation-entry':
                record=event['record'];method=record['entry_method'];methods[method]+=1
                key=str(seq); classification=classifications.get(key)
                label='unresolved'
                if classification is not None:
                    require(classification.get('entry_record')==record and classification.get('witness_sha256') and
                            len(classification['witness_sha256'])==64,'classification-binding')
                    label=classification['category']
                    require(label in ('image-independent-proven','application-derived-proven'),'classification-category')
                groups[label]+=1;entries.append(key)
    require(set(classifications)<=set(entries),'classification-unknown-entry')
    count=sum(methods.values())
    return dict(**LABEL, stream_sha256=sha(path), stream_bytes=raw_bytes, events=len(sequences),
        counts=dict(kinds), watched_calls=count, methods=dict(methods), classifications=dict(groups),
        percentages={k:100*v/count if count else None for k,v in groups.items()},
        complete=death and not refused, refusal=refused, model_calls=0,
        limitation='Structural accounting only; verify the signed archive separately. JDK package is not provenance.')


def compare(before, after, before_workload, after_workload):
    require(before['complete'] and after['complete'],'comparison-incomplete-trace')
    require(before_workload==after_workload and set(before_workload)=={'fixture_sha256','input_sha256','iterations'},'comparison-workload')
    require(before['watched_calls']>0,'comparison-empty-baseline')
    removed=before['watched_calls']-after['watched_calls']
    return dict(**LABEL, before=before['watched_calls'],after=after['watched_calls'],
                calls_removed=removed,percentage_removed=100*removed/before['watched_calls'],
                extrapolation_to_native_allowed=False)
