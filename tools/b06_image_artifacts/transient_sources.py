"""Narrow, byte-inspected Tycho source exception; never a general /tmp allowlist."""
import hashlib,io,json,re,zipfile
from pathlib import Path,PurePosixPath
try:
    from .tycho_runtime import path
    from .archive import inspect as inspect_archive
except ImportError:
    from tycho_runtime import path
    from archive import inspect as inspect_archive

PATTERN=r'/tmp/tycho_wrapped_source[0-9]+\.jar'

def check(ok,reason):
    if not ok: raise ValueError(reason)

def copies_at(observation,root):
    result={}
    for b in observation['bundles']:
        c=b.get('preserved_copy')
        if c is not None:
            check(c['path']==f"/results/runtime-transient/{b['id']}.jar",'transient-copy-path')
            p=Path(root)/'runtime-transient'/f"{b['id']}.jar"
            check(not p.is_symlink() and p.is_file(),'transient-copy-missing')
            check(p.stat().st_size<=134217728,'transient-copy-bound')
            result[c['path']]=p.read_bytes()
    return result

def catalogue(raw):
    rows=[]
    for line in raw.decode('utf-8').splitlines():
        fields=line.split('\t')
        check(len(fields)==2 and all(fields),'runtime-catalogue-row')
        rows.append(dict(name=fields[0],origin=fields[1]))
    check(bool(rows),'runtime-catalogue-empty')
    return rows

def classify(observation,copies,loaded):
    check(observation.get('schema') in ('b06-runtime-launch-observation/3','b06-runtime-launch-observation/4','b06-runtime-launch-observation/5'),'transient-observation-required')
    check(isinstance(observation.get('loaded_bundle_classes'),list),'bundle-class-catalogue-required')
    check(isinstance(loaded,list) and bool(loaded),'runtime-catalogue-required')
    check(isinstance(copies,dict),'transient-copies-required')
    check(all(isinstance(r,dict) and set(r)=={'name','origin'} and all(isinstance(v,str) and v for v in r.values()) for r in loaded),'runtime-catalogue-row')
    install=path(observation['install_area']); tmp=PurePosixPath(observation['java_tmpdir'])
    check(tmp.is_absolute() and '..' not in tmp.parts,'runtime-tmpdir')
    records=[];used=set();identities=set()
    for b in observation['bundles']:
        check(isinstance(b.get('symbolic_name'),str) and bool(b['symbolic_name']) and isinstance(b.get('version'),str) and bool(b['version']) and type(b.get('eclipse_source_bundle')) is bool,'bundle-identity-required')
        if b['id']==0: continue
        loc=path(b['location'],install);c=b.get('preserved_copy')
        temporary=PurePosixPath(loc).is_relative_to(tmp) or loc.startswith('/tmp/')
        if not temporary:
            check(c is None,'unexpected-transient-copy');continue
        check(re.fullmatch(PATTERN,loc) is not None,'transient-source-location-refused')
        check(b['eclipse_source_bundle'] and b['symbolic_name'].endswith('.source'),'transient-source-header-required')
        check(isinstance(c,dict) and set(c)=={'path','sha256','bytes'} and c['path']==f"/results/runtime-transient/{b['id']}.jar",'transient-copy-required')
        check(c['path'] in copies and c['path'] not in used,'transient-copy-missing-or-duplicate');used.add(c['path'])
        raw=copies[c['path']]
        check(0<len(raw)<=134217728 and len(raw)==c['bytes'] and hashlib.sha256(raw).hexdigest()==c['sha256'],'transient-copy-bytes')
        inspection=inspect_archive(raw,budget=134217728)
        check(inspection['class_entries']==0 and inspection['nested_archives']==0,'transient-source-has-code')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            check(not any(e.filename.lower().endswith(('.class','.jar')) for e in z.infolist()),'transient-source-has-code')
            manifest=z.read('META-INF/MANIFEST.MF').decode('utf-8').replace('\r\n','\n')
        logical=[]
        for line in manifest.splitlines():
            if not line: break # main attributes only
            if line.startswith(' ') and logical: logical[-1]+=line[1:]
            else: logical.append(line)
        headers={}
        for line in logical:
            check(': ' in line,'transient-manifest-line');k,v=line.split(': ',1);k=k.lower()
            check(k not in headers,'transient-manifest-duplicate');headers[k]=v
        check('eclipse-sourcebundle' in headers and headers.get('bundle-symbolicname','').split(';')[0]==b['symbolic_name'] and headers.get('bundle-version')==b['version'],'transient-manifest-identity')
        check(not any(row.get('bundle_id')==b['id'] for row in observation['loaded_bundle_classes']),'transient-source-loaded-class')
        for row in loaded:
            origin=row['origin'].removeprefix('jar:').split('!',1)[0]
            if origin=='unavailable' or not origin.startswith(('file:','reference:','initial@')): continue
            check(path(origin,install) not in (loc,c['path']),'transient-source-loaded-class')
        identity=(b['symbolic_name'],b['version'])
        check(identity not in identities,'duplicate-transient-identity');identities.add(identity)
        records.append(dict(bundle_id=b['id'],symbolic_name=identity[0],version=identity[1],original_path=loc,
            preserved_copy=c,classification='transient-source-only',class_entries=0,nested_archives=0))
    check(used==set(copies),'unbound-transient-copy')
    return records

def binding(resolution):
    """Comparison representation; only proven source-only rows lose path/hash."""
    check(resolution.get('schema') in ('b06-resolved-runtime/4','b06-resolved-runtime/5','b06-resolved-runtime/6'),'transient-resolution-required')
    sources={r['bundle_id']:r for r in resolution['transient_source_bundles']};rows=[]
    applications={r['bundle_id']:r for r in resolution.get('application_content_bundles',[])}
    obs=json.loads(resolution['observation_utf8']);install=path(obs['install_area'])
    for b in resolution['resolved_bundle_states']:
        if b['id']==0: continue
        loc=path(b['location'],install)
        if b['id'] in sources:
            r=sources[b['id']]
            check((r['symbolic_name'],r['version'],r['original_path'])==(b['symbolic_name'],b['version'],loc),'transient-binding-identity')
            row=('source-only',b['symbolic_name'],b['version'])
        elif b['id'] in applications:
            r=applications[b['id']]
            check(r['original_path']==loc,'application-binding-path')
            row=('application-content',b['symbolic_name'],r['identity']['base_version'],r['content_sha256'])
        else:
            row=('exact',b['symbolic_name'],b['version'],loc,resolution['artifact_sha256'][loc])
        rows.append(row)
    check(len(rows)==len(set(rows)),'duplicate-runtime-binding')
    return sorted(rows)

def bind_measured(closure,measured,*,closure_inventory,measured_inventory,closure_key,measured_key,closure_expected,measured_expected,closure_copies,measured_copies,closure_application_copies=None,measured_application_copies=None):
    # Re-run signed producer/byte inspection before applying the narrow equivalence.
    from .runtime_closure import assemble
    assemble(closure_inventory,closure,launch_key=closure_key,expected_launch=closure_expected,transient_copies=closure_copies,application_copies=closure_application_copies)
    assemble(measured_inventory,measured,launch_key=measured_key,expected_launch=measured_expected,transient_copies=measured_copies,application_copies=measured_application_copies)
    check(binding(closure)==binding(measured),'closure-measured-bundles-differ')
    for field in ('boot_classpath','framework_jar','jdk_modules','jimage_tool'):
        check(closure[field]==measured[field],'closure-measured-runtime-differs')
    # Every non-source artifact, including JVM/launcher, stays exact.
    def exact_artifacts(r):
        protected=set(r['boot_classpath'])|{r['framework_jar'],r['jdk_modules'],r['jimage_tool']['path']}
        exempt={b['original_path'] for b in r.get('application_content_bundles',[])}-protected
        return {p:h for p,h in r['artifact_sha256'].items() if p not in exempt}
    check(exact_artifacts(closure)==exact_artifacts(measured),'closure-measured-artifacts-differ')
    return True
