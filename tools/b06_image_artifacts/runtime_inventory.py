"""Measure only paths observed at launch, including lib/modules via jimage.

This worker is not the inventory-only program: jimage starts a JVM and requires
separate explicit Tower runtime/extraction authority. No Maven-cache traversal.
"""
import hashlib,json,subprocess
from pathlib import Path
from urllib.parse import urlsplit,unquote
try:
    from .archive import folder_bytes,inspect as inspect_archive,MAX_BYTES
except ImportError:  # flat immutable worker mount
    from archive import folder_bytes,inspect as inspect_archive,MAX_BYTES

def measure(observation,output,booter_classpath=()):
    output=Path(output);output.mkdir(exist_ok=False)
    def path(url):
        try:from .resolved_runtime import file_path
        except ImportError:from resolved_runtime import file_path
        if observation.get('schema')=='b06-runtime-launch-observation/2':
            try:from .tycho_runtime import path as tycho_path
            except ImportError:from tycho_runtime import path as tycho_path
            return Path(tycho_path(url,tycho_path(observation['install_area'])))
        return Path(file_path(url))
    java=Path(observation['java_home']);tool=java/'bin/jimage';modules=java/'lib/modules'
    selected={path(b['location']) for b in observation['bundles'] if b['id']!=0}
    selected.update([path(observation['framework_url']),java/'bin/java',tool,modules])
    selected.update(map(Path,observation['java_class_path'].split(':')))
    selected.update(map(Path,booter_classpath))
    rows=[]
    for p in sorted(selected):
        if not p.is_absolute() or '..' in p.parts or p.is_symlink():raise ValueError('runtime-selected-path')
        if p.is_dir():
            raw,row=folder_bytes(p);row.update(inspect_archive(raw));rows.append(row);continue
        if p.stat().st_size>MAX_BYTES:raise ValueError('runtime-artifact-bound')
        raw=p.read_bytes();row=dict(path=p.as_posix(),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),class_entries=0,nested_archives=0)
        if p.suffix=='.jar':row.update(inspect_archive(raw))
        if p==modules:
            bound=output/'bound-modules';bound.write_bytes(raw);dest=output/'jimage'
            result=subprocess.run([str(tool),'extract','--dir',str(dest),str(bound)],capture_output=True,timeout=600)
            (output/'jimage.stdout').write_bytes(result.stdout);(output/'jimage.stderr').write_bytes(result.stderr)
            if result.returncode:raise ValueError('runtime-jimage-extract-failed')
            classes=[f for f in dest.rglob('*.class') if f.is_file()]
            row.update(expanded_class_entries=len(classes),expanded_class_bytes=sum(f.stat().st_size for f in classes))
            if not classes:raise ValueError('runtime-jimage-empty')
        rows.append(row)
    return dict(schema='b06-image-inventory/1',artifacts=rows,failure=None,measurement='selected actual runtime; includes native jimage extraction',model_calls=0,native_pairs=0)
