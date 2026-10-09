"""Offline, origin-preserving class census. Never resolves a loader by name.

All duplicate and multi-release definitions are retained. This inventory is not
native admission and cannot substitute for external runtime origin evidence.
"""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from tools.ms94_b06_classfile import Reader
from .bundle_content import safe


def check(ok, reason):
    if not ok: raise ValueError(reason)


def class_name(raw):
    r=Reader(raw);check(r.u4()==0xcafebabe,'class-magic');r.take(4)
    count=r.u2();pool={};i=1
    while i<count:
        tag=r.u1()
        if tag==1:pool[i]=r.take(r.u2())
        elif tag==7:pool[i]=r.u2()
        elif tag in (8,16,19,20):r.take(2)
        elif tag in (3,4,9,10,11,12,17,18):r.take(4)
        elif tag in (5,6):r.take(8);i+=1
        elif tag==15:r.take(3)
        else:raise ValueError('class-pool-tag')
        i+=1
    r.u2();this=r.u2()
    name=pool.get(pool.get(this))
    check(isinstance(name,bytes),'class-name-reference')
    return name.decode('ascii').replace('/','.')


def archive_classes(path, expected, origin, *, limit=1024**3):
    raw=Path(path).read_bytes()
    check(hashlib.sha256(raw).hexdigest()==expected,'catalogue-archive-hash')
    rows=[];total=0
    def visit(data, chain, depth):
        nonlocal total
        check(depth<=4,'catalogue-archive-depth')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names=set()
            for entry in z.infolist():
                safe(entry.filename)
                check(entry.filename not in names and not entry.flag_bits&1,'catalogue-duplicate-or-encrypted-entry')
                names.add(entry.filename)
                check(entry.file_size<=limit,'catalogue-entry-bound')
                if entry.is_dir() or not entry.filename.endswith(('.class','.jar')):continue
                total+=entry.file_size;check(total<=limit,'catalogue-expansion-bound')
                b=z.read(entry);member=chain+[entry.filename]
                if entry.filename.endswith('.jar'):visit(b,member,depth+1)
                else:
                    rows.append(dict(origin=origin,artifact_sha256=expected,members=member,
                        class_name=class_name(b),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),
                        multi_release=any(n.startswith('META-INF/versions/') for n in member)))
    visit(raw,[],0)
    return rows


def read_class(row, archive):
    """Re-extract by the complete artifact/member chain; no class-name search."""
    raw=Path(archive).read_bytes()
    check(hashlib.sha256(raw).hexdigest()==row['artifact_sha256'],'catalogue-archive-hash')
    for member in row['members']:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            matches=[e for e in z.infolist() if e.filename==member]
            check(len(matches)==1,'catalogue-member-ambiguous')
            raw=z.read(matches[0])
    check(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
          and class_name(raw)==row['class_name'],'catalogue-class-binding')
    return raw


def summarize(rows):
    by_name={}
    for i,row in enumerate(rows):by_name.setdefault(row['class_name'],[]).append(i)
    conflicts={n:ids for n,ids in by_name.items() if len({rows[i]['sha256'] for i in ids})>1}
    return dict(class_entries=len(rows),unique_names=len(by_name),
        duplicate_names=sum(len(ids)>1 for ids in by_name.values()),
        differing_definition_names=len(conflicts),conflicts=conflicts,
        native_admission=False,loader_resolution_claim=False)


def select_exact(rows, name, *, artifact_sha256, members):
    candidates=[r for r in rows if r['class_name']==name and
                r['artifact_sha256']==artifact_sha256 and r['members']==members]
    check(len(candidates)==1,'catalogue-exact-origin-required')
    return candidates[0]
