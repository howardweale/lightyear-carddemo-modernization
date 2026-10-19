"""Controller-only leakage scan; never return matching private values to workers."""
from hashlib import sha256
import json
from .contracts import ContractError


def scan(artifacts,canaries,expected_values):
    if set(canaries)!={'expected-state','reference-output','session-answer'}:
        raise ContractError('isolation-canary-classes')
    tokens=list(canaries.values())
    if any(not isinstance(t,str) or len(t)<32 for t in tokens) or len(set(tokens))!=3:
        raise ContractError('isolation-canary-tokens')
    windows={value[i:i+40] for value in expected_values for i in range(max(0,len(value)-39))}
    rows=[]
    for name,data in artifacts:
        text=data.decode('utf-8',errors='replace') if isinstance(data,bytes) else data
        views=[text]
        def strings(value):
            if isinstance(value,str):views.append(value)
            elif isinstance(value,list):
                for item in value:strings(item)
            elif isinstance(value,dict):
                for key,item in value.items():strings(key);strings(item)
        try:strings(json.loads(text))
        except (ValueError,TypeError):pass
        if any(token in view for view in views for token in tokens) or any(window in view for view in views for window in windows):
            # No token, expected value or matching private text in the error.
            raise ContractError('isolation-breach')
        rows.append(dict(artifact=name,sha256=sha256(text.encode()).hexdigest()))
    return dict(status='passed',scanned=rows,canary_classes=sorted(canaries),expected_window_count=len(windows))
