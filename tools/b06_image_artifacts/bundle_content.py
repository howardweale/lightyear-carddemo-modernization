"""One prospective bundle byte view for capture, production, replay and comparison.

JAR entries are never filtered. Folder views enumerate all file entries beneath
root; directories themselves carry no byte content. Only named run-written paths
are omitted; the exact list and reasons are part of every folder proof.
"""
import hashlib,io,os,zipfile
from pathlib import Path,PurePosixPath

POLICY='b06-bundle-content-view/1'
EXCLUSIONS={
 'target/work':'Tycho test workspace, runtime installation and mutable OSGi state',
 'target/surefire-reports':'Test reports written by the fork',
 'target/surefire':'Surefire transient test execution output',
 'target/test-runtime':'Tycho generated test runtime',
 'target/configuration':'Generated test OSGi configuration',
 'target/surefire.properties':'Tycho per-run launch properties; retained and bound separately',
}
LIMIT=1024*1024*1024

def require(ok,reason):
 if not ok:raise ValueError(reason)

def excluded(name):
 return next((p for p in EXCLUSIONS if name==p or name.startswith(p+'/')),None)

def safe(name):
 require(name and not name.startswith('/') and '..' not in PurePosixPath(name).parts and '\\' not in name,'bundle-view-path')

def stream_hash(f):
 h=hashlib.sha256();size=0
 for block in iter(lambda:f.read(65536),b''):
  size+=len(block);require(size<=LIMIT,'bundle-view-file-bound');h.update(block)
 return dict(kind='file',bytes=size,sha256=h.hexdigest())

def bundle_content_view(source,*,kind):
 """Directory, JAR bytes or captured-folder ZIP -> identical named byte maps.

No extraction, subprocess, archive rewriting or recursive nested-JAR filtering.
"""
 require(kind in ('folder','jar','folder-archive'),'bundle-view-kind')
 entries={};omitted={};paths={};total=0
 if kind=='folder':
  root=Path(source);require(root.is_dir() and not root.is_symlink(),'bundle-view-root')
  for directory,dirs,files in os.walk(root,followlinks=False):
   for name in sorted(dirs+files):
    p=Path(directory)/name;n=p.relative_to(root).as_posix();safe(n)
    reason=excluded(n)
    if reason:
     omitted[reason]=EXCLUSIONS[reason]
     if name in dirs:dirs.remove(name)
     continue
    require(not p.is_symlink(),'bundle-view-symlink')
    if name in dirs:continue
    require(p.is_file(),'bundle-view-file')
    with p.open('rb') as f:row=stream_hash(f)
    entries[n]=row;paths[n]=p;total+=row['bytes'];require(total<=LIMIT,'bundle-view-total-bound')
 elif kind in ('jar','folder-archive'):
  raw=source if isinstance(source,bytes) else Path(source).read_bytes()
  require(len(raw)<=LIMIT,'bundle-view-archive-bound')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   names=set()
   for e in z.infolist():
    n=e.filename;safe(n);require(n not in names and not e.flag_bits&1 and (e.external_attr>>16)&0o170000!=0o120000,'bundle-view-entry');names.add(n)
    if kind=='folder-archive':
     reason=excluded(n.rstrip('/'))
     if reason:omitted[reason]=EXCLUSIONS[reason];continue
     if e.is_dir():continue
    with z.open(e) as f:row=stream_hash(f)
    if e.is_dir():row['kind']='directory'
    entries[n]=row;total+=row['bytes'];require(total<=LIMIT,'bundle-view-total-bound')
 require(len(entries)<=100000 and 'META-INF/MANIFEST.MF' in entries,'bundle-view-entry-bound')
 return dict(policy=POLICY,kind=kind,entries=entries,omitted=omitted,exclusions=dict(EXCLUSIONS) if kind!='jar' else {},paths=paths)
