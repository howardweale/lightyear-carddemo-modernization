"""Bounded in-memory archive inventory shared with scoped extraction."""
import io
import zipfile

MAX_BYTES=1024*1024*1024

def bundle_paths(z):
    try:raw=z.read('META-INF/MANIFEST.MF').decode('utf-8')
    except KeyError:return ['.']
    logical=[]
    for line in raw.replace('\r\n','\n').splitlines():
        if line.startswith(' ') and logical:logical[-1]+=line[1:]
        else:logical.append(line)
    values=[line.split(':',1)[1].strip() for line in logical if line.lower().startswith('bundle-classpath:')]
    if len(values)>1:raise ValueError('duplicate-bundle-class-path')
    paths=values[0].split(',') if values else ['.']
    paths=[p.strip() for p in paths]
    if any(not p or p.startswith('/') or '..' in p.split('/') or '\\' in p or ';' in p for p in paths):raise ValueError('bundle-class-path')
    if len(set(paths))!=len(paths):raise ValueError('duplicate-bundle-entry')
    return paths

def inspect(raw,*,budget=MAX_BYTES,depth=0):
    if depth>4 or len(raw)>budget:raise ValueError('archive-bound')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist()
        if len({e.filename for e in entries})!=len(entries):raise ValueError('duplicate-archive-entry')
        total=sum(e.file_size for e in entries)
        if total>budget or any(e.flag_bits&1 for e in entries):raise ValueError('expanded-archive-bound')
        classes=sum(e.filename.endswith('.class') for e in entries)
        class_bytes=sum(e.file_size for e in entries if e.filename.endswith('.class'))
        nested=0;expanded=classes;expanded_bytes=class_bytes
        for e in entries:
            if e.filename.endswith('.jar'):
                nested+=1
                inner=inspect(z.read(e),budget=budget-total,depth=depth+1)
                total+=inner['archive_expanded_bytes']
                expanded+=inner['expanded_class_entries'];expanded_bytes+=inner['expanded_class_bytes']
                if total>budget:raise ValueError('nested-expanded-bound')
        return dict(class_entries=classes,nested_archives=nested,expanded_class_entries=expanded,
            expanded_class_bytes=expanded_bytes,archive_expanded_bytes=total,bundle_class_path=bundle_paths(z))


def folder_bytes(path, *, deadline=None):
    """Bind a folder bundle by its complete relative-path/byte manifest.

    The in-memory ZIP is only a parser view, never the identity or persisted
    native evidence. Symlinks, races that change the manifest, and bounds fail.
    """
    import hashlib,json,os,time
    from pathlib import Path
    root=Path(path);rows=[];total=0;buffer=io.BytesIO()
    if root.is_symlink() or not root.is_dir():raise ValueError('folder-bundle-root')
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_STORED) as z:
        for directory,dirs,files in os.walk(root,followlinks=False):
            dirs.sort()
            if any((Path(directory)/d).is_symlink() for d in dirs):raise ValueError('folder-bundle-symlink')
            for name in sorted(files):
                if deadline is not None and time.monotonic()>deadline:raise TimeoutError('inventory-deadline')
                f=Path(directory)/name
                if f.is_symlink() or not f.is_file():raise ValueError('folder-bundle-file')
                if total+f.stat().st_size>MAX_BYTES:raise ValueError('folder-bundle-bound')
                raw=f.read_bytes();total+=len(raw)
                if total>MAX_BYTES:raise ValueError('folder-bundle-bound')
                relative=f.relative_to(root).as_posix()
                rows.append(dict(path=relative,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
                z.writestr(relative,raw)
    rows.sort(key=lambda r:r['path'])
    identity=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return buffer.getvalue(),dict(kind='folder-bundle',path=root.as_posix(),bytes=total,sha256=identity,files=rows)
