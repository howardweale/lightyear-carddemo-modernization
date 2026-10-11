"""Streaming compatibility comparison of trusted audit readers on signed prefixes.

Only structural audit events are replayed. Signed historical failures remain
incomplete; this tool cannot grant generation provenance or qualification credit.
"""
import argparse,hashlib,json,re
from pathlib import Path
from lightyear_calibration.contracts import read_json,verify
from lightyear_control_tower.decisions import verify_envelope

STATE=('count','bytes','set_id','position','size','resume_requested','resumed','refused','vm_started','vm_died')
def load_audit(source):
    namespace={'__name__':'b06_trusted_audit_snapshot'}
    exec(compile(source,'<trusted-audit-snapshot>','exec'),namespace)
    return namespace['Audit']

def error_summary(error):
    message=str(error)
    return {'type':type(error).__name__,**({'code':message} if re.fullmatch(r'[A-Za-z0-9-]+',message) else {'message_sha256':hashlib.sha256(message.encode()).hexdigest()})}

def compare_events(events,old_factory,new_factory):
    readers=[old_factory(),new_factory()];failures=[None,None];counts=[0,0];total=0;audit_events=0
    for event in events:
        total+=1
        if event['kind']!='observer-audit':continue
        audit_events+=1
        for i,reader in enumerate(readers):
            if failures[i] is not None:continue
            counts[i]+=1
            try:reader.event(event)
            except Exception as error:failures[i]={'event_sequence':event['sequence'],**error_summary(error)}
    results=[]
    for i,reader in enumerate(readers):
        completion=None
        try:reader.complete()
        except Exception as error:completion=error_summary(error)
        results.append(dict(event_attempts=counts[i],event_error=failures[i],completion_error=completion,
                            shared_terminal_state={name:getattr(reader,name) for name in STATE}))
    return dict(event_count=total,audit_event_count=audit_events,old=results[0],new=results[1],equivalent=results[0]==results[1],
                complete_observation=False,provenance_replayed=False,qualification_credit=False,measurement_credit=False,model_calls=0)

def compare_authenticated(folder,public_key,old_source,new_source):
    census=read_json(folder/'frame-census.json');failure=read_json(folder/'failure.json')
    for envelope in (census,failure):
        if not verify_envelope(envelope,public_key) or envelope['complete'] is not False:raise ValueError('compatibility-signature-or-scope')
    digest=hashlib.sha256();tail={'events':0,'previous':None}
    def events():
        with (folder/'events.jsonl').open('rb') as stream:
            while line:=stream.readline(4*1024*1024+1):
                if len(line)>4*1024*1024:raise ValueError('compatibility-line-cap')
                digest.update(line);row=json.loads(line);verify(row);event=row['event'];tail['events']+=1
                if event['sequence']!=tail['events'] or row['previous_sha256']!=tail['previous']:raise ValueError('compatibility-chain')
                tail['previous']=row['content_sha256'];yield event
    result=compare_events(events(),load_audit(old_source),load_audit(new_source))
    for envelope in (census,failure):
        if tail['events']!=envelope['event_count'] or tail['previous']!=envelope['last_event_sha256']:raise ValueError('compatibility-tail-binding')
    if digest.hexdigest()!=census['event_file_sha256'] or census['plan_sha256']!=failure['plan_sha256'] or census['lane']!=failure['lane']:raise ValueError('compatibility-stream-binding')
    return dict(result,schema='b06-historical-audit-compatibility/1',stream_sha256=digest.hexdigest(),
        old_reader_sha256=hashlib.sha256(old_source).hexdigest(),new_reader_sha256=hashlib.sha256(new_source).hexdigest(),
        census_sha256=census['content_sha256'],failure_sha256=failure['content_sha256'],signatures_verified=2,
        public_key_sha256=hashlib.sha256(public_key).hexdigest(),review='Operator review, not independent attestation')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('folder','public-key','old-source','new-source','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.out.resolve().is_relative_to(a.folder.resolve()):raise ValueError('compatibility-output-inside-evidence')
    result=compare_authenticated(a.folder,a.public_key.read_bytes(),a.old_source.read_bytes(),a.new_source.read_bytes())
    with a.out.open('x',encoding='utf-8') as output:json.dump(result,output,indent=2);output.write('\n')
    if not result['equivalent']:raise SystemExit('historical-audit-behavior-changed')
