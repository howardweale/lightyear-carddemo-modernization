"""Generic named tree/archive byte identity with explicit selection policy.

JAR entries are never filtered. Folder views enumerate all file entries beneath
root; directories themselves carry no byte content. Only named run-written paths
are omitted; the exact list and reasons are part of every folder proof.
"""
import hashlib,io,os,zipfile
from pathlib import Path,PurePosixPath

def require(ok,reason):
 if not ok:raise ValueError(reason)

def excluded(name, exclusions):
 return next((p for p in exclusions if name==p or name.startswith(p+'/')),None)

def safe(name):
 require(name and not name.startswith('/') and '..' not in PurePosixPath(name).parts and '\\' not in name,'bundle-view-path')

def stream_hash(f, limit=1024*1024*1024):
 h=hashlib.sha256();size=0
 for block in iter(lambda:f.read(65536),b''):
  size+=len(block);require(size<=limit,'bundle-view-file-bound');h.update(block)
 return dict(kind='file',bytes=size,sha256=h.hexdigest())

def content_view(source,*,kind,policy,exclusions=None,required_entries=(),limit=1024*1024*1024,validate_original_names=True,max_entries=100000):
 """Directory, JAR bytes or captured-folder ZIP -> identical named byte maps.

No extraction, subprocess, archive rewriting or recursive nested-JAR filtering.
"""
 exclusions = dict(exclusions or {})
 require(kind in ('folder','jar','folder-archive'),'bundle-view-kind')
 entries={};omitted={};paths={};total=0
 if kind=='folder':
  root=Path(source);require(root.is_dir() and not root.is_symlink(),'bundle-view-root')
  for directory,dirs,files in os.walk(root,followlinks=False):
   for name in sorted(dirs+files):
    p=Path(directory)/name;n=p.relative_to(root).as_posix();safe(n)
    reason=excluded(n, exclusions)
    if reason:
     omitted[reason]=exclusions[reason]
     if name in dirs:dirs.remove(name)
     continue
    require(not p.is_symlink(),'bundle-view-symlink')
    if name in dirs:continue
    require(p.is_file(),'bundle-view-file')
    with p.open('rb') as f:row=stream_hash(f, limit)
    entries[n]=row;paths[n]=p;total+=row['bytes'];require(total<=limit,'bundle-view-total-bound')
 elif kind in ('jar','folder-archive'):
  if not isinstance(source,bytes):
   require(Path(source).stat().st_size<=limit,'bundle-view-archive-bound')
  raw=source if isinstance(source,bytes) else Path(source).read_bytes()
  require(len(raw)<=limit,'bundle-view-archive-bound')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   infos=z.infolist()
   require(len(infos)<=max_entries,'bundle-view-entry-bound')
   require(sum(e.file_size for e in infos)<=limit,'bundle-view-total-bound')
   names=set()
   for e in infos:
    if validate_original_names:
     safe(e.orig_filename)  # Windows ZipInfo normalizes backslashes.
     require(':' not in e.orig_filename,'bundle-view-path')  # Portable drive/stream refusal.
    n=e.filename;safe(n);require(n not in names and not e.flag_bits&1 and (e.external_attr>>16)&0o170000!=0o120000,'bundle-view-entry');names.add(n)
    if kind=='folder-archive':
     reason=excluded(n.rstrip('/'), exclusions)
     if reason:omitted[reason]=exclusions[reason];continue
     if e.is_dir():continue
    with z.open(e) as f:row=stream_hash(f, limit)
    if e.is_dir():row['kind']='directory'
    entries[n]=row;total+=row['bytes'];require(total<=limit,'bundle-view-total-bound')
 require(len(entries)<=max_entries and set(required_entries) <= set(entries),'bundle-view-entry-bound')
 return dict(policy=policy,kind=kind,entries=entries,omitted=omitted,exclusions=dict(exclusions) if kind!='jar' else {},paths=paths)
