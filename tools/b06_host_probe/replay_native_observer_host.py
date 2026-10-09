"""Independent offline replay of production collector / public host fixture output."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from tools.ms94_b06_classfile import inspect_class
from tools.ms94_b06_observer_v2 import Replay


def inputs(events, classes, jdk, modules):
    definitions = {str(e['definition']['class_object_id']): e['definition'] for e in events
                   if e['kind']=='class-definition-v2'}
    rows=[]; seen=set(); unindexed=[]
    for d in definitions.values():
        name=d['class']; module=d.get('module')
        if '/' in name or 'methods' not in d or name in seen: continue
        seen.add(name); member=name.replace('.', '/')+'.class'
        if module:
            source=Path(modules)/module/member
            if not source.is_file():
                unindexed.append(name);continue
            raw=source.read_bytes()
            row={'kind':'jdk','module':module,'origin':str(Path(jdk)/'lib/modules')}
        else:
            raw=(Path(classes)/member).read_bytes()
            source=Path(classes).resolve().as_posix()+'/'
            if not source.startswith('/'):source='/'+source
            row={'kind':'ordinary','origin':str(Path(classes)/member),'code_source':source,
                 'loader_class':d['loader_class']}
        info=inspect_class(raw)
        rows.append({**row,'class':name,'bytes':raw,'sha256':hashlib.sha256(raw).hexdigest(),'methods':info['methods']})
    return rows,unindexed


def replay(events, rows):
    verifier=Replay(rows); checkpoints=0
    for e in events:
        if verifier.event(e):continue
        if e.get('frames'):
            verifier.frames(e['frames']);checkpoints+=1
        if e.get('catch_location'):verifier.frames([e['catch_location']])
    if not events or events[-1]['kind']!='vm-death':raise ValueError('host-replay-incomplete')
    return {**verifier.finish(), 'checkpoints_replayed':checkpoints}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture',required=True);p.add_argument('--classes',required=True);p.add_argument('--jdk',required=True);p.add_argument('--output',required=True);p.add_argument('--modules',required=True)
    a=p.parse_args();raw=Path(a.capture).read_bytes();events=[json.loads(line) for line in raw.splitlines()]
    rows,unindexed=inputs(events,a.classes,a.jdk,a.modules)
    try:result={'passed':True,**replay(events,rows)}
    except Exception as e:result={'passed':False,'error':type(e).__name__+': '+str(e)}
    result.update(schema='b06-observer-v2-host-replay/1',events_sha256=hashlib.sha256(raw).hexdigest(),
        jdk_modules_sha256=hashlib.sha256((Path(a.jdk)/'lib/modules').read_bytes()).hexdigest(),
        bound_sources=[{'class':r['class'],'sha256':r['sha256'],'origin':r['origin']} for r in rows],
        unindexed_metadata_classes=unindexed,model_calls=0,docker_commands=0,native_pairs=0,
        claim='External production collector on public host fixtures; not Linux native qualification')
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('bound_sources','generated_proofs')}))
    raise SystemExit(0 if result['passed'] else 1)
