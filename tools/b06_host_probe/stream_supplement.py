"""Read-only, bounded-memory structural supplement for a sealed failed stream.

Only counts, code locations and hashes leave the preserved stream. This does not
replay provenance, grant credit, or rewrite/repair an incomplete observation.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from lightyear_calibration.contracts import read_json, verify
from lightyear_control_tower.decisions import verify_envelope


def scan(stream):
    counts = Counter(); sizes = defaultdict(list); unmatched = []
    last_audit = last_jdi = None; previous = None; digest = hashlib.sha256()
    classes = set(); total = 0
    while line := stream.readline(4*1024*1024+1):
        if len(line)>4*1024*1024:
            raise ValueError('supplement-record-bound')
        digest.update(line); item=json.loads(line); verify(item)
        event=item['event']; total+=1
        if total>550000 or item['previous_sha256']!=previous or event['sequence']!=total:
            raise ValueError('supplement-event-chain')
        previous=item['content_sha256']; counts[event['kind']]+=1
        if event['kind']=='observer-audit':
            last_audit={k:event[k] for k in ('sequence','audit_index','event_set_id','event_position','action')}
            if event['action']=='jdi-event':
                last_jdi={k:event['detail'].get(k) for k in ('event_type','thread_id','depth','location')}
        if event['kind']=='diagnostic-unmatched-return':
            unmatched.append(event['sequence'])
        if event['kind']=='generation-entry':
            record=event['record'];sizes['entry_bytes'].append(len(line))
            sizes['depth'].append(record['entry_depth'])
            sizes['definition_input_bytes'].append(len(record.get('definition_input_hex',''))//2)
            for frame in record.get('stack',[]):
                classes.add(frame['class_object_id'])
            for name in ('lambda_form_graph','class_data_graph'):
                if isinstance(record.get(name),dict):
                    sizes[name+'_nodes'].append(len(record[name].get('nodes',{})))
    def distribution(values):
        ordered=sorted(values);n=len(ordered)
        return dict(count=n,min=ordered[0],median=ordered[n//2],p90=ordered[int((n-1)*.9)],
                    p99=ordered[int((n-1)*.99)],max=ordered[-1])
    return dict(schema='b06-failed-stream-supplement/1',stream_sha256=digest.hexdigest(),
                event_count=total,last_event_sha256=previous,event_counts=dict(counts),last_audit=last_audit,
                last_jdi_event=last_jdi,accepted_unmatched_return_sequences=unmatched,
                distinct_stack_class_objects=len(classes),payload_sizes={k:distribution(v) for k,v in sizes.items()},
                qualification_credit=False,measurement_credit=False,model_calls=0,
                review='operator review; not independent attestation')


def supplement(folder, public_key):
    census=read_json(folder/'frame-census.json');failure=read_json(folder/'failure.json')
    for record in (census,failure):
        if not verify_envelope(record,public_key):
            raise ValueError('supplement-signature-invalid')
        if record['complete'] is not False:
            raise ValueError('supplement-requires-incomplete-stream')
    with (folder/'events.jsonl').open('rb') as stream:
        result=scan(stream)
    if (result['stream_sha256']!=census['event_file_sha256'] or
        result['event_count']!=census['event_count'] or result['event_count']!=failure['event_count'] or
        result['last_event_sha256']!=census['last_event_sha256'] or result['last_event_sha256']!=failure['last_event_sha256'] or
        census['plan_sha256']!=failure['plan_sha256'] or census['lane']!=failure['lane']):
        raise ValueError('supplement-sealed-binding')
    return dict(result,census_sha256=census['content_sha256'],failure_sha256=failure['content_sha256'],
                public_key_sha256=hashlib.sha256(public_key).hexdigest(),signatures_verified=2,
                complete_observation=False,provenance_replayed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--public-key',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    # Output must not overwrite preserved evidence, even accidentally.
    if args.out.resolve().is_relative_to(args.folder.resolve()):
        raise ValueError('supplement-output-inside-evidence')
    result=supplement(args.folder,args.public_key.read_bytes())
    with args.out.open('x',encoding='utf-8',newline='\n') as output:
        json.dump(result,output,indent=2);output.write('\n')
