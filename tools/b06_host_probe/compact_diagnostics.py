"""Measure a lossless diagnostic-wire conversion without rewriting host evidence."""
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import zlib
from tools.ms94_b06_observer_format import (DIAGNOSTIC_KINDS,DIAGNOSTIC_DICTIONARY,
    audit_detail,diagnostic_wire,java_json)
from tools.ms94_b06_observer_audit import Audit


def encode(event):
    logical=audit_detail(event)
    if logical.get('action')=='dispatch-refused':return logical
    body={k:v for k,v in logical.items() if k not in ('kind','sequence','checkpoint')}
    raw=java_json(body).encode('utf-8')
    if len(raw)>256*1024:raise ValueError('diagnostic-body-size')
    compressor=zlib.compressobj(zdict=DIAGNOSTIC_DICTIONARY)
    compressed=compressor.compress(raw)+compressor.flush()
    return {**{k:logical[k] for k in ('kind','sequence','checkpoint')},'d3':base64.b64encode(compressed).decode()}


def measure(path,expected_sha256=None,limit=None):
    counts=Counter();old_bytes=Counter();new_bytes=Counter();digest=hashlib.sha256()
    total=0;old=Audit();new=Audit()
    with Path(path).open('rb') as stream:
        while line:=stream.readline(4*1024*1024+1):
            if len(line)>4*1024*1024:raise ValueError('host-record-bound')
            digest.update(line);event=json.loads(line);total+=1
            if event['kind'] not in DIAGNOSTIC_KINDS:continue
            logical=audit_detail(event);converted=encode(event)
            if diagnostic_wire(converted)!=logical:raise ValueError('lossy-diagnostic-conversion')
            if event['kind']=='observer-audit':old.event(event);new.event(converted)
            else:old.metadata(event);new.metadata(converted)
            key=event['kind']+':'+logical.get('action','')
            counts[key]+=1;old_bytes[key]+=len(line.removesuffix(b'\n'))
            new_bytes[key]+=len(java_json(converted).encode('utf-8'))
            if limit and sum(counts.values())>=limit:break
    for key in ('count','diagnostic_count','set_id','position','size','resume_requested','resumed','refused','vm_started','vm_died'):
        if getattr(old,key)!=getattr(new,key):raise ValueError('changed-audit-state:'+key)
    if expected_sha256 and digest.hexdigest()!=expected_sha256:raise ValueError('changed-host-stream')
    return dict(schema='b06-compact-diagnostic-wire/1',host_only=True,model_calls=0,native_admission=False,
        source_stream_sha256=digest.hexdigest(),complete_input_scanned=limit is None,
        source_records=total,diagnostic_records=sum(counts.values()),old_wire_bytes=sum(old_bytes.values()),
        new_wire_bytes=sum(new_bytes.values()),new_to_old_ratio=sum(new_bytes.values())/sum(old_bytes.values()),
        fields_round_tripped=True,audit_state_equivalent_except_byte_quota=True,
        dictionary_sha256=hashlib.sha256(DIAGNOSTIC_DICTIONARY).hexdigest(),dictionary_bytes=len(DIAGNOSTIC_DICTIONARY),
        byte_cap_unchanged=128*1024*1024,record_cap_unchanged=500000,
        complete_observation=False,provenance_replayed=False,qualification_credit=False,measurement_credit=False,
        by_kind={key:dict(records=counts[key],old_wire_bytes=old_bytes[key],new_wire_bytes=new_bytes[key]) for key in counts})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-stream',type=Path,required=True)
    parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=measure(args.host_stream,args.expected_sha256)
    with args.out.open('x',encoding='utf-8',newline='\n') as output:json.dump(result,output,indent=2);output.write('\n')
