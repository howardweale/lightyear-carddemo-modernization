"""Prospective application content identity; execution/resource bytes stay exact."""
import hashlib,io,json,re,zipfile
from pathlib import Path,PurePosixPath
try:
    from .archive import MAX_BYTES
except ImportError:
    from archive import MAX_BYTES

NORMALIZED_HEADERS=('Bundle-Version','Built-By','Bnd-LastModified','Build-Timestamp')
VOLATILE={n.lower() for n in NORMALIZED_HEADERS[1:]}

def check(ok,reason):
    if not ok:raise ValueError(reason)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def base_version(version):
    m=re.fullmatch(r'([0-9]+\.[0-9]+\.[0-9]+)(?:\.([A-Za-z0-9_-]+))?',version)
    check(m is not None,'application-bundle-version')
    return m[1],m[2]

def manifest(raw):
    # Preserve all bytes/order/wrapping except explicitly permitted main header
    # values. Section headers, Import-Package/Require-Bundle and named sections
    # receive no normalization, nor do line endings or attribute order.
    lines=raw.splitlines(keepends=True);groups=[]
    for line in lines:
        if line.startswith(b' '):
            check(bool(groups) and groups[-1].strip(),'application-manifest-continuation')
            groups[-1]+=line
        else:groups.append(line)
    main=True;seen=set();identity={};normalized=[];out=[]
    for group in groups:
        first=group.splitlines()[0] if group.splitlines() else b''
        if not first:main=False;out.append(group);continue
        check(b': ' in first,'application-manifest-header')
        key=first.split(b': ',1)[0].decode('ascii');lower=key.lower()
        value=b''.join([first.split(b': ',1)[1]]+[v[1:] for v in group.splitlines()[1:]]).decode('utf-8')
        if main:
            check(lower not in seen,'application-manifest-duplicate');seen.add(lower)
            identity[lower]=value
        if main and lower in VOLATILE|{'bundle-version'}:
            replacement=base_version(value)[0] if lower=='bundle-version' else '<build-metadata>'
            # Keep header name, position, presence and line ending exact.
            end=b'\r\n' if group.endswith(b'\r\n') else b'\n' if group.endswith(b'\n') else b''
            out.append(key.encode()+b': '+replacement.encode()+end)
            normalized.append(dict(header=key,original_value=value,normalized_value=replacement))
        else:out.append(group)
    check('bundle-version' in identity and 'bundle-symbolicname' in identity,'application-manifest-identity')
    return b''.join(out),identity,normalized

def content(raw,origin,symbolic_name,version):
    check(PurePosixPath(origin).is_absolute() and origin.startswith('/application/') and '..' not in PurePosixPath(origin).parts,'application-origin-required')
    check(len(raw)<=MAX_BYTES,'application-archive-bound')
    entries={};total=0;manifest_bytes=None
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        check(len(z.infolist())<=100000,'application-entry-count')
        for e in z.infolist():
            n=e.filename
            check(n not in entries and n and not n.startswith('/') and '..' not in PurePosixPath(n).parts and '\\' not in n and not e.flag_bits&1,'application-entry-refused')
            check((e.external_attr>>16)&0o170000!=0o120000,'application-entry-symlink')
            total+=e.file_size;check(total<=MAX_BYTES,'application-expanded-bound')
            data=z.read(e)
            if n=='META-INF/MANIFEST.MF':manifest_bytes=data
            entries[n]=dict(kind='directory' if e.is_dir() else 'file',bytes=len(data),sha256=sha(data))
    check(manifest_bytes is not None,'application-manifest-required')
    try:from .bundle_content import bundle_content_view
    except ImportError:from bundle_content import bundle_content_view
    check(entries==bundle_content_view(raw,kind='jar')['entries'],'application-shared-view-differs')
    normal,headers,changes=manifest(manifest_bytes)
    check(headers['bundle-symbolicname'].split(';',1)[0]==symbolic_name and headers['bundle-version']==version,'application-observed-identity-mismatch')
    base,qualifier=base_version(version)
    # Physical manifest hash retained as evidence; identity uses normalized bytes.
    entries['META-INF/MANIFEST.MF']=dict(kind='file',bytes=len(normal),sha256=sha(normal))
    body=dict(symbolic_name=symbolic_name,base_version=base,entries=entries)
    return dict(schema='b06-application-content/1',identity=body,content_sha256=sha(json.dumps(body,sort_keys=True,separators=(',',':')).encode()),
        original_path=origin,original_version=version,qualifier=qualifier,archive_sha256=sha(raw),archive_bytes=len(raw),
        manifest_sha256=sha(manifest_bytes),normalized_manifest_sha256=sha(normal),normalized_headers=changes,
        permitted_normalized_headers=list(NORMALIZED_HEADERS))

def compare(left,right):
    check(left['identity']==right['identity'],'application-content-differs')
    return True

def copies_at(observation,root):
    copies={}
    for b in observation['bundles']:
        c=b.get('application_copy')
        if c is None:continue
        check(c['path']==f"/results/runtime-application/{b['id']}.jar",'application-copy-path')
        p=Path(root)/'runtime-application'/f"{b['id']}.jar"
        check(not p.is_symlink() and p.is_file() and p.stat().st_size<=MAX_BYTES,'application-copy-missing-or-bound')
        copies[c['path']]=p.read_bytes()
    return copies

def records(observation,copies):
    try:from .tycho_runtime import path
    except ImportError:from tycho_runtime import path
    check(isinstance(copies,dict),'application-copies-required')
    if observation.get('schema')=='b06-runtime-launch-observation/5':
        try:from .runtime_capture import validate_capture
        except ImportError:from runtime_capture import validate_capture
        validate_capture(observation,copies)
    install=path(observation['install_area']);rows=[];used=set();identities=set()
    for b in observation['bundles']:
        if b['id']==0:continue
        origin=path(b['location'],install);c=b.get('application_copy')
        if not origin.startswith('/application/'):
            check(c is None,'nonapplication-copy-refused');continue
        check(isinstance(c,dict) and set(c)=={'path','sha256','bytes','kind'},'application-copy-required')
        check(c['kind'] in ('jar','folder-archive','folder-runtime-archive') and c['path']==f"/results/runtime-application/{b['id']}.jar",'application-copy-path')
        check(c['path'] in copies and c['path'] not in used,'application-copy-missing-or-duplicate');used.add(c['path'])
        raw=copies[c['path']];check(sha(raw)==c['sha256'] and len(raw)==c['bytes'],'application-copy-bytes')
        row=content(raw,origin,b['symbolic_name'],b['version'])
        identity=(row['identity']['symbolic_name'],row['identity']['base_version'])
        check(identity not in identities,'duplicate-application-identity');identities.add(identity)
        rows.append(dict(bundle_id=b['id'],copy=c,**row))
    check(used==copies.keys(),'unbound-application-copy')
    return rows

def bind_posting_class(resolution,class_name,defining_path,class_bytes,*,inventory,launch_key,expected_launch,transient_copies,application_copies):
    # The consumer replays the closure and verifies the actual loaded class bytes.
    from .runtime_closure import assemble
    assemble(inventory,resolution,launch_key=launch_key,expected_launch=expected_launch,transient_copies=transient_copies,application_copies=application_copies)
    matches=[r for r in resolution['application_content_bundles'] if r['original_path']==defining_path]
    check(len(matches)==1,'posting-application-origin')
    row=matches[0];raw=application_copies[row['copy']['path']]
    from .archive import bundle_paths
    found=[];member=class_name.replace('.','/')+'.class'
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        selected=next(b for b in json.loads(resolution['observation_utf8'])['bundles'] if b['id']==row['bundle_id'])
        for prefix in selected.get('runtime_selection',{}).get('classpath',bundle_paths(z)):
            if prefix.endswith('.jar'):
                with zipfile.ZipFile(io.BytesIO(z.read(prefix))) as inner:
                    if member in inner.namelist():found.append(inner.read(member))
            else:
                n=member if prefix=='.' else prefix.rstrip('/')+'/'+member
                if n in z.namelist():found.append(z.read(n))
    check(len(found)==1 and found[0]==class_bytes,'posting-application-class-bytes')
    return dict(bundle_content_sha256=row['content_sha256'],class_sha256=sha(class_bytes),symbolic_name=row['identity']['symbolic_name'])


def bind_measured_posting_classes(closure,measured,classes,**proofs):
    """Measured-run consumer: bundle equivalence AND each executed class exact.

    `classes` are the observer's actual readback bytes/origins, not class names
    inferred from a candidate trace. Admission remains separately gated.
    """
    from .transient_sources import bind_measured
    bind_measured(closure,measured,**proofs)
    check(isinstance(classes,dict) and bool(classes),'posting-class-readbacks-required')
    result={}
    for name,row in classes.items():
        check(set(row)=={'defining_path','class_bytes'},'posting-class-readback-shape')
        result[name]=bind_posting_class(measured,name,row['defining_path'],row['class_bytes'],
            inventory=proofs['measured_inventory'],launch_key=proofs['measured_key'],expected_launch=proofs['measured_expected'],
            transient_copies=proofs['measured_copies'],application_copies=proofs['measured_application_copies'])
    return dict(schema='b06-measured-application-class-binding/1',classes=result,native_admission=False)
