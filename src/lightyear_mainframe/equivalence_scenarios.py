"""Deterministic solver-model adapter to the existing public scenario generator."""
import base64
import json
from decimal import Decimal
from .equivalence_automation import refs


def identifier(job, local, model):
    required=refs(local['original'].get('expression',{'kind':'noop'})) | refs(local['mutant'].get('expression',{'kind':'noop'}))
    values={n:str(Decimal(model[n]).scaleb(-local['fields'][n]['scale'])) for n in sorted(required)}
    for name in values:
        if not name.startswith(('ACCT-', 'DALYTRAN-', 'TRANCAT-')):
            raise ValueError('counterexample-input-has-no-public-dataset-binding:'+name)
    raw=json.dumps(values,sort_keys=True,separators=(',',':')).encode()
    return 'equivalence-cex:'+job+':'+base64.urlsafe_b64encode(raw).decode()


def case(name):
    from .scenario_generation import case as generated
    from .records import load_copybook
    from .zos_bindings import ROOT, load_bindings, dataset_binding
    from carddemo_oracle.records import encode_zoned
    prefix,job,payload=name.split(':',2)
    if prefix!='equivalence-cex' or job not in ('INTCALC','POSTTRAN') or len(payload)>4096: raise ValueError('counterexample-format')
    values=json.loads(base64.b64decode(payload,altchars=b'-_',validate=True))
    if not isinstance(values,dict) or len(values)>20:raise ValueError('counterexample-field-count')
    _,meta,images,_=generated('intcalc-two-accounts' if job=='INTCALC' else 'posttran-positive')
    images=dict(images);changes=[]
    for field,value in sorted(values.items()):
        dd='ACCTFILE' if field.startswith('ACCT-') else 'DALYTRAN' if field.startswith('DALYTRAN-') and job=='POSTTRAN' else 'TCATBALF' if field.startswith('TRANCAT-') else None
        if dd is None: raise ValueError('counterexample-unmapped-field')
        layout=load_copybook(ROOT/dataset_binding(load_bindings(),job,'STEP15',dd)['copybook'])
        item=next((f for f in layout.fields if f.path.split('.')[-1]==field),None)
        if item is None or not item.digits or item.usage!='DISPLAY':raise ValueError('counterexample-nonnumeric-field')
        number=Decimal(value)
        if not number.is_finite() or number*10**item.scale!=int(number*10**item.scale) or abs(number)>=Decimal(10)**(item.digits-item.scale) or (number<0 and not item.signed):raise ValueError('counterexample-outside-PIC')
        encoded=encode_zoned(number,item.digits,item.scale) if item.signed else str(int(number*10**item.scale)).zfill(item.length)
        raw=encoded.encode(); rows=bytearray(images[dd])
        if not rows:raise ValueError('counterexample-no-input-record')
        for start in range(0,len(rows),layout.record_length+1):rows[start+item.offset:start+item.offset+item.length]=raw
        images[dd]=bytes(rows);changes.append(dict(dataset=dd,field=field,value=value))
    return job,dict(meta,public_input_variant=name),images,dict(generator='solver-public-adapter/1',changes=changes,model_calls=0)
