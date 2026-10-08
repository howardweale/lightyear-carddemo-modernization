"""Prospective scoped extraction after inventory and separate Tower approval.

No traversal of a Maven cache. All inputs must be selected by the saved resolved
runtime and inventory hashes. lib/modules is authoritative; jmods corroborate.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile
from .inventory import digest
from .resolved_runtime import read as read_resolution

def check(v,reason):
    if not v:raise ValueError(reason)

def assemble(inventory,resolution):
    check(inventory['schema']=='b06-image-inventory/1' and inventory['failure'] is None,'inventory-required')
    check(resolution['schema']=='b06-resolved-runtime/1' and resolution['resolved'] is True,'resolved-runtime-required')
    raw=resolution['configuration_utf8']
    parsed=read_resolution(raw['config.ini'].encode(),raw['surefire.properties'].encode())
    check(all(resolution[k]==v for k,v in parsed.items()),'resolved-configuration-differs')
    records={r['path']:r for r in inventory['artifacts']}
    paths=list(dict.fromkeys(resolution['equinox_bundles']+resolution['surefire_booter_classpath']+[resolution['jdk_modules']]))
    check(paths,'runtime-closure-empty')
    check(all(p in records for p in paths),'runtime-artifact-not-in-inventory')
    check(all(resolution['artifact_sha256'].get(p)==records[p]['sha256'] for p in paths),'resolution-inventory-bytes')
    artifacts=[records[p] for p in paths]
    # Directory counts alone cannot bound nested jar class contents: stop until
    # the resolution inventory supplies their measured expanded entry counts.
    check(all(not r['nested_archives'] or r.get('expanded_class_entries') is not None for r in artifacts),'nested-inventory-count-required')
    check(type(resolution.get('jdk_class_entries')) is int and resolution['jdk_class_entries']>0,'jimage-list-count-required')
    tool=resolution['jimage_tool']
    check(tool['path'] in records and tool['sha256']==records[tool['path']]['sha256'],'bound-jimage-tool-required')
    check(type(resolution.get('expanded_byte_limit')) is int and resolution['expanded_byte_limit']>0,
          'measured-expanded-byte-limit-required')
    return dict(schema='b06-runtime-closure/1',artifacts=artifacts,
        resolution_sha256=hashlib.sha256(json.dumps(resolution,sort_keys=True).encode()).hexdigest(),
        maximum_archive_bytes=sum(r['bytes'] for r in artifacts),
        maximum_expanded_bytes=resolution['expanded_byte_limit'],jimage_tool=tool,
        maximum_classes=sum(r.get('expanded_class_entries',r['class_entries']) for r in artifacts)+resolution['jdk_class_entries'],
        jdk_modules=resolution['jdk_modules'],jdk_method='jimage extract from bound lib/modules',
        jmods_authoritative=False,native_admission=False)

def extract(closure,output,jimage,*,run=subprocess.run):
    check(closure['schema']=='b06-runtime-closure/1','closure-schema')
    check(str(jimage)==closure['jimage_tool']['path'] and digest(Path(jimage))==closure['jimage_tool']['sha256'],
          'jimage-tool-changed')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    blobs=output/'classes';blobs.mkdir();rows=[];expanded=0
    def retain(raw,origin,member):
        nonlocal expanded
        check(len(rows)<closure['maximum_classes'],'measured-class-bound')
        expanded+=len(raw)
        check(expanded<=closure['maximum_expanded_bytes'],'measured-expanded-byte-bound')
        h=hashlib.sha256(raw).hexdigest();dest=blobs/h
        if not dest.exists():dest.write_bytes(raw)
        rows.append(dict(origin=origin,member=member,sha256=h,bytes=len(raw)))
    def archive(raw,origin,depth=0):
        check(depth<=4,'nested-archive-depth')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for e in z.infolist():
                check(e.file_size<=closure['maximum_expanded_bytes'] and not e.flag_bits&1,'archive-entry-bound')
                if e.filename.endswith('.class'):retain(z.read(e),origin,e.filename)
                elif e.filename.startswith('lib/') and e.filename.endswith('.jar'):
                    archive(z.read(e),origin+'!/'+e.filename,depth+1)
    progress=output/'progress.jsonl'
    try:
        for row in closure['artifacts']:
            p=Path(row['path']);check(digest(p)==row['sha256'] and p.stat().st_size==row['bytes'],'scoped-artifact-changed')
            if str(p)==closure['jdk_modules']:
                dest=output/'jimage';dest.mkdir()
                done=run([str(jimage),'extract','--dir',str(dest),str(p)],capture_output=True,timeout=600,check=False)
                (output/'jimage.stdout').write_bytes(done.stdout);(output/'jimage.stderr').write_bytes(done.stderr)
                check(done.returncode==0,'jimage-extract-failed')
                for f in sorted(dest.rglob('*.class')):retain(f.read_bytes(),row['sha256'],f.relative_to(dest).as_posix())
            else:archive(p.read_bytes(),row['sha256'])
            with progress.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(path=row['path'],classes=len(rows)))+'\n')
    finally:
        (output/'classes.json').write_text(json.dumps(rows,sort_keys=True),encoding='utf-8')
    return dict(classes=rows,jdk_source='lib/modules',native_admission=False)
