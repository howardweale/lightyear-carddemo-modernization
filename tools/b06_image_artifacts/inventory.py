"""Inventory-only phase. No class/blob copies, JVM, Docker or network calls.

Append-only progress survives a failure. Archive members are counted from their
directory; nested jars are identified but not decompressed in this cheap pass.
"""
import hashlib
import json
import os
from pathlib import Path
import time
import zipfile

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def inventory(roots,output,*,maximum_seconds=900):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    tick=time.monotonic();rows=[];counts={};failure=None
    with (output/'progress.jsonl').open('x',encoding='utf-8') as progress:
        try:
            for root in map(Path,roots):
                if not root.is_dir() or root.is_symlink():raise ValueError('inventory-root')
                stats=dict(files=0,bytes=0,class_entries=0,nested_archives=0);counts[str(root)]=stats
                def error(e):raise e
                for directory,dirs,names in os.walk(root,followlinks=False,onerror=error):
                    if any((Path(directory)/d).is_symlink() for d in dirs):raise ValueError('inventory-symlink')
                    dirs.sort()
                    for name in sorted(names):
                        if time.monotonic()-tick>maximum_seconds:raise TimeoutError('inventory-deadline')
                        p=Path(directory)/name
                        if p.suffix not in ('.jar','.class','.jmod','.so') and name not in ('modules','release','config.ini','java','jimage'):continue
                        if p.is_symlink():raise ValueError('inventory-file-symlink')
                        size=p.stat().st_size;h=digest(p);classes=nested=0
                        if p.suffix in ('.jar','.jmod'):
                            with zipfile.ZipFile(p) as z:
                                classes=sum(e.filename.endswith('.class') for e in z.infolist())
                                nested=sum(e.filename.startswith('lib/') and e.filename.endswith('.jar') for e in z.infolist())
                        if p.stat().st_size!=size:raise ValueError('inventory-file-changed')
                        row=dict(path=p.as_posix(),bytes=size,sha256=h,class_entries=classes,nested_archives=nested)
                        rows.append(row);stats['files']+=1;stats['bytes']+=size;stats['class_entries']+=classes;stats['nested_archives']+=nested
                        progress.write(json.dumps(dict(artifact=row,root_counts=counts),sort_keys=True)+'\n');progress.flush();os.fsync(progress.fileno())
        except Exception as ex:
            failure=dict(type=type(ex).__name__,reason=str(ex))
        report=dict(schema='b06-image-inventory/1',artifacts=rows,roots=counts,failure=failure,
            elapsed_seconds=time.monotonic()-tick,class_bytes_copied=0,model_calls=0,native_pairs=0,
            runtime_resolution_claim=False)
        (output/'inventory.json').write_text(json.dumps(report,sort_keys=True),encoding='utf-8')
    if failure:raise ValueError('inventory-failed-preserved:'+failure['reason'])
    return report

if __name__=='__main__':
    import argparse
    import shutil
    p=argparse.ArgumentParser();p.add_argument('--root',action='append',required=True);p.add_argument('--output',required=True)
    p.add_argument('--jdk-auto',action='store_true')
    a=p.parse_args()
    if a.jdk_auto:
        java=shutil.which('java')
        if java is None:raise ValueError('image-java-missing')
        a.root.append(str(Path(java).resolve(strict=True).parent.parent))
    inventory(a.root,a.output)
