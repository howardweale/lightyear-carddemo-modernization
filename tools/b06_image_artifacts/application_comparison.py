"""Saved-byte comparison only; no execution and no inference from absent classes."""
import hashlib,io,json,zipfile
from pathlib import Path
from .tycho_runtime import path

def sha(raw):return hashlib.sha256(raw).hexdigest()

def compare(a,b):
    common=sorted(a.keys() & b.keys())
    different=[n for n in common if a[n]!=b[n]]
    return dict(compared=len(common),identical=len(common)-len(different),different=len(different),
      only_previous=sorted(a.keys()-b.keys()),only_current=sorted(b.keys()-a.keys()),
      different_entries=different,previous_map_sha256=sha(json.dumps(a,sort_keys=True).encode()),
      current_map_sha256=sha(json.dumps(b,sort_keys=True).encode()),
      evidence_present=bool(a) and bool(b))

def loaded(root):
    raw=(root/'loaded/loaded.tsv').read_bytes();rows={}
    for line in raw.decode('utf-8').splitlines():
        name,digest,origin,loader=line.split('\t')
        if sha((root/'loaded'/(digest+'.class')).read_bytes())!=digest:raise ValueError('saved-loaded-class-hash')
        if name in rows:raise ValueError('ambiguous-saved-loaded-class')
        rows[name]=dict(sha256=digest,origin=path(origin),loader=loader)
    return raw,rows

def archive_classes(raw,prefix,result,depth=0):
    if depth>4:raise ValueError('nested-archive-depth')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('duplicate-archive-entry')
        for e in z.infolist():
            if e.file_size>128*1024*1024:raise ValueError('archive-entry-bound')
            if e.filename.endswith('.class'):result[prefix+e.filename]=sha(z.read(e))
            elif e.filename.endswith('.jar'):archive_classes(z.read(e),prefix+e.filename+'!/',result,depth+1)

def stored_classes(root):
    result={}
    for f in sorted(root.rglob('*')):
        if f.is_symlink():raise ValueError('saved-folder-symlink')
        if not f.is_file():continue
        n=f.relative_to(root).as_posix()
        if n.endswith('.class'):result[n]=sha(f.read_bytes())
        elif n.endswith('.jar'):archive_classes(f.read_bytes(),n+'!/',result)
    return result

def audit(previous,current,location_audit):
    previous,current=Path(previous),Path(current)
    ar,a=loaded(previous);br,b=loaded(current)
    obs=json.loads((current/'closure-observation.json').read_bytes())
    metadata={r['bundle_id']:r for r in location_audit['bundles']}
    result=[];retained=[]
    prefix='/application/org.idempiere.test/target/work/'
    for bundle in obs['bundles']:
        if bundle['id']==0:continue
        row=metadata[bundle['id']]
        if row['root']!='/application':continue
        current_path=row['location'];old_path=current_path
        manifests=[r for r in row['manifest_evidence'] if r['run']=='previous']
        if manifests:old_path=manifests[0]['path']
        aa={n:r['sha256'] for n,r in a.items() if r['origin']==old_path}
        bb={n:r['sha256'] for n,r in b.items() if r['origin']==current_path}
        result.append(dict(symbolic_name=bundle['symbolic_name'],previous_path=old_path,current_path=current_path,
          **compare(aa,bb),classes=[dict(name=n,previous_sha256=aa.get(n),current_sha256=bb.get(n)) for n in sorted(aa.keys()|bb.keys())],
          coverage='targeted-catalogue-only' if aa or bb else 'not-captured'))
        if current_path.startswith(prefix) and old_path.startswith(prefix):
            old_dir=previous/'runtime/work'/old_path.removeprefix(prefix);new_dir=current/'runtime/work'/current_path.removeprefix(prefix)
            if old_dir.is_dir() and new_dir.is_dir():
                retained.append(dict(symbolic_name=bundle['symbolic_name'],evidence_kind='retained-folder-class-entries-not-loaded-catalogue',**compare(stored_classes(old_dir),stored_classes(new_dir))))
    return dict(schema='b06-saved-application-comparison/1',
      previous_catalogue_sha256=sha(ar),current_catalogue_sha256=sha(br),
      application_bundles=result,retained_folder_comparisons=retained,
      loaded_application_totals={k:sum(r[k] for r in result) for k in ('compared','identical','different')},
      all_catalogued_classes=compare({n:r['sha256'] for n,r in a.items()},{n:r['sha256'] for n,r in b.items()}),
      complete_application_loaded_class_evidence=False,
      missing_coverage_means_identical=False,native_admission=False,model_calls=0,docker_commands=0)
