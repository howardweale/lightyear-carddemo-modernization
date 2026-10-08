"""Copy ONLY hash-bound runtime archives from a retained image; no JVM/build."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def check(ok,reason):
    if not ok:raise ValueError(reason)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):h.update(block)
    return h.hexdigest()


def validate(spec):
    check(spec['schema']=='b06-selected-runtime-archives/1','selected-archive-schema')
    check(spec['content_sha256']==hashlib.sha256(canonical({k:v for k,v in spec.items() if k!='content_sha256'})).hexdigest(),'selected-archive-spec-hash')
    check(re.fullmatch('sha256:[a-f0-9]{64}',spec['image']) and re.fullmatch('[a-f0-9]{64}',spec['manifest_sha256']),'selected-image-binding')
    rows=spec['artifacts'];check(0<len(rows)<=300 and len({r['path'] for r in rows})==len(rows),'selected-archive-set')
    check(sum(r['bytes'] for r in rows)<=2*1024**3,'selected-archive-byte-bound')
    for r in rows:
        p=Path(r['path'])
        check(r['path'].startswith('/root/.m2/') and '..' not in r['path'].split('/') and r['path'].endswith('.jar'),'selected-archive-path')
        check(type(r['bytes']) is int and 0<r['bytes']<=512*1024**2 and re.fullmatch('[a-f0-9]{64}',r['sha256']),'selected-archive-descriptor')
    return rows


def replay(spec,output):
    rows=validate(spec);out=Path(output)
    record=json.loads((out/'catalogue.json').read_bytes())
    check(record['schema']=='b06-selected-runtime-archive-copy/1' and record['spec_sha256']==spec['content_sha256'] and record['artifacts']==rows,'selected-archive-report')
    check(record['model_calls']==record['native_pairs']==record['target_jvm_executions']==0,'selected-archive-scope')
    expected={r['sha256']+'.jar' for r in rows}
    check({p.name for p in (out/'archives').iterdir()}==expected,'selected-archive-files')
    for r in rows:
        p=out/'archives'/(r['sha256']+'.jar')
        check(p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],'selected-archive-copy-bytes')
    return {'archives':len(rows),'bytes':sum(r['bytes'] for r in rows),'native_admission':False}


def copy_selected(spec,output,resolve=Path):
    rows=validate(spec);out=Path(output);out.mkdir(parents=True,exist_ok=False);dest=out/'archives';dest.mkdir()
    try:
        for row in rows:
            source=resolve(row['path'])
            check(source.is_file() and not source.is_symlink() and source.stat().st_size==row['bytes'],'selected-source-file')
            target=dest/(row['sha256']+'.jar')
            if target.exists():check(sha(target)==row['sha256'],'selected-existing-copy');continue
            temporary=dest/(row['sha256']+'.partial');h=hashlib.sha256();size=0
            with source.open('rb') as src,temporary.open('xb') as dst:
                for block in iter(lambda:src.read(65536),b''):
                    size+=len(block);check(size<=row['bytes'],'selected-source-grew');h.update(block);dst.write(block)
            check(size==row['bytes'] and h.hexdigest()==row['sha256'],'selected-source-bytes')
            temporary.rename(target)
        record=dict(schema='b06-selected-runtime-archive-copy/1',spec_sha256=spec['content_sha256'],artifacts=rows,
            model_calls=0,native_pairs=0,target_jvm_executions=0,native_admission=False)
        with (out/'catalogue.json').open('xb') as f:f.write(canonical(record))
        return replay(spec,out)
    except BaseException as exc:
        with (out/'copy-error.json').open('xb') as f:f.write(canonical(dict(exception=type(exc).__name__,message=str(exc))))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--spec',required=True);parser.add_argument('--output',required=True);a=parser.parse_args()
    print(json.dumps(copy_selected(json.loads(Path(a.spec).read_bytes()),a.output)))