"""Deterministic boundary/branch proposals and failure-preserving shrinking.

Cases remain proposals until executed with fresh resets. A shrink oracle must
return the exact original failure fingerprint, not merely any failure.
"""
from copy import deepcopy
from .native_evidence import canonical, sha

def generate(parameters, seeds, *, branch_values=None, trace_cases=()):
    cases=[deepcopy(seeds)]
    for p in parameters:
        name,kind=p['name'],p['type'].lower()
        values=([None,0,1,-1,-2147483648,2147483647] if kind=='int' else
                [None,'',' ','a','A'] if 'char' in kind else [None])
        for value in values+list((branch_values or {}).get(name,[])):
            c=deepcopy(seeds);c[name]=value;cases.append(c)
    cases.extend(deepcopy(list(trace_cases)))
    unique={canonical(c):c for c in cases}
    return [dict(id=sha(raw),parameters=c,source='proposed-not-executed') for raw,c in sorted(unique.items())]

def shrink(case, fingerprint, oracle, *, maximum_calls=100):
    current=deepcopy(case);calls=0;history=[]
    if not fingerprint:raise ValueError('failure-fingerprint-required')
    for key in sorted(current):
        old=current[key]
        candidates=([None,0,1,-1] if type(old) is int else [None,'',old[:len(old)//2]] if isinstance(old,str) else [None])
        for value in candidates:
            if calls>=maximum_calls:break
            if value==current[key]:continue
            trial=deepcopy(current);trial[key]=value
            # Never repeatedly cycle toward larger strings/integers.
            if len(canonical(trial))>=len(canonical(current)):continue
            observed=oracle(trial);calls+=1
            history.append(dict(case_sha256=sha(canonical(trial)),same_failure=observed==fingerprint))
            if observed==fingerprint:current=trial
    return dict(case=current,minimal_case_sha256=sha(canonical(current)),oracle_calls=calls,
        history=history,minimality='bounded coordinate reduction; not global minimum')
