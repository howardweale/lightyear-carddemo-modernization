"""Operations diagnostics: compiler/API/footprint fields only, never judge values."""
import re
from .journey_repair import compile_diagnostics, public_api_matches, boolean_api_evidence

def diagnostics(run, source, api):
    """Read private native artifacts; export only allowlisted structural facts."""
    from .native_reconciliation import state
    from .application_effects import TABLES
    output = []
    # At a native run, ancestors resolve to the same root used by the gate.
    from .journey_order import RUNS
    root=run.parents[len(RUNS.parts)] if len(run.parents)>len(RUNS.parts) else run
    # Case and attempt names are controlled by the native controller.
    for folder in sorted((run/'cases/operations').glob('*')):
        for lane in ('oracle','postgresql'):
            log = folder/'execution'/lane/'maven.log'
            if log.exists():
                text = log.read_text(encoding='utf-8', errors='replace')
                parsed=compile_diagnostics(text.replace('LightyearOperationsTest.java','LightyearPartialInvoiceTest.java'))
                for item in parsed:item['file']='LightyearOperationsTest.java'
                output.extend(parsed)
                # A failed assertion at a typed API call is distinct from a money assertion.
                lines = source.splitlines()
                for frame in re.finditer(r'LightyearOperationsTest\.java:(\d+)', text):
                    n = int(frame[1])
                    if not 0<n<=len(lines):continue
                    # Include the enclosing failing Java method: the invalid type
                    # comparison can control a later assertion or posting call.
                    start=n-1
                    while start>0 and not re.search(r'\b(?:private|public|protected)\b.*\(',lines[start]):start-=1
                    reads=[i+1 for i in range(start,n) if 'get_ValueAsString("Posted")' in lines[i]]
                    if reads:
                        output.append({'category':'api-type-mismatch', 'file':'LightyearOperationsTest.java',
                            'line':reads[0], 'failure_frame_line':n,
                            'call':'PO.get_ValueAsString', 'field':'Posted',
                            'accessor_return_type':'String','field_java_type':'boolean',
                            'typed_accessor':'PO.get_ValueAsBoolean', 'typed_accessor_return_type':'boolean',
                            'basis':'Representation mismatch in the failing method; not an assertion expected/actual value or proof of the sole failure cause',
                            'type_evidence':boolean_api_evidence(root,source,api),
                            'api_source_sha256':api['po_sha256']})
            before, after = folder/'baseline'/lane/'entry', folder/'after'/lane
            if not (before/'state.json').exists() or not (after/'state.json').exists(): continue
            a,b = state(before,lane),state(after,lane)
            outside = sorted(t for t in set(a['tables']) & set(b['tables'])
                             if t not in TABLES and a['tables'][t]['row_multiset'] != b['tables'][t]['row_multiset'])
            for table in outside:
                # A source-verified call chain, not an inferred amount or a broadened footprint.
                if table == 't_fact_acct_history' and 'Doc.postImmediate(' in source:
                    output.append({'category':'outside-footprint', 'table':table, 'call':'Doc.postImmediate',
                        'source_call_path':['Doc.postImmediate','DocManager.postDocument','Doc.post','Doc.deleteAcct'],
                        'api_source_sha256':api['doc_sha256'], 'lane':lane})
    unique = []
    for item in output:
        if item['category']=='compile-error' and item.get('symbol'):
            available=public_api_matches(root,item['symbol'],api)
            if available:item['available_public_overloads']=available
        if item not in unique: unique.append(item)
    return [{'id':f'diagnostic-{i+1}', **item} for i,item in enumerate(unique)]

