"""Post-Maven streamed runtime capture; never walk live build directories."""
import copy,hashlib,json,os,shutil,tempfile,traceback,zipfile
from pathlib import Path,PurePosixPath
try:
 from .tycho_runtime import path,properties
 from .application_identity import manifest
except ImportError:
 from tycho_runtime import path,properties
 from application_identity import manifest

LIMIT=1024*1024*1024
EXCLUDED={'target','work','surefire','surefire-reports','test-runtime','configuration','.git','.mvn','.settings','src'}
BUILD_FILES={'pom.xml','build.properties','.project','.classpath','bnd.bnd'}
LEGACY_POLICY='b06-runtime-folder-selection/1'
PREVIOUS_POLICY='b06-runtime-folder-selection/2'
POLICY='b06-runtime-folder-selection/3'
try:
 from .bundle_content import bundle_content_view,EXCLUSIONS,excluded
except ImportError:
 from bundle_content import bundle_content_view,EXCLUSIONS,excluded
def require(ok,reason):
 if not ok:raise ValueError(reason)
def digest_file(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(65536),b''):h.update(block)
 return h.hexdigest()
def atomic_json(p,v):
 p=Path(p);require(not p.exists(),'capture-output-exists')
 temp=p.with_name('.'+p.name+'.tmp')
 with temp.open('x',encoding='utf-8') as f:json.dump(v,f,sort_keys=True)
 temp.rename(p)
def failure(out,stage,error):
 p=Path(out)/'worker-error.json'
 if not p.exists():atomic_json(p,dict(schema='b06-closure-error/1',exception_class=type(error).__name__,message=str(error),stack_trace=traceback.format_exc(),stage=stage))
def probe_result(out):
 out=Path(out);err=out/'closure-error.json'
 if err.exists():
  # Exact bytes to stderr, not a replacement generic exception.
  import sys
  raw=err.read_bytes();sys.stderr.buffer.write(raw);sys.stderr.buffer.write(b'\n');sys.stderr.buffer.flush()
  raise ValueError('closure-error.json (verbatim above)')
 marker=json.loads((out/'closure-complete.json').read_bytes())
 raw=(out/'closure-observation.json').read_bytes()
 require(marker=={'status':'complete','observation_sha256':hashlib.sha256(raw).hexdigest()},'closure-completion-binding')
 obs=json.loads(raw);require(obs.get('schema')=='b06-runtime-launch-observation/5','closure-observation-required')
 return obs

def selection(root,dev,*,absent=None):
 root=Path(root);require((root/'META-INF/MANIFEST.MF').stat().st_size<=1048576,'folder-manifest-bound');raw=(root/'META-INF/MANIFEST.MF').read_bytes();_,headers,_=manifest(raw)
 cp=[v.strip() for v in headers.get('bundle-classpath','.').split(',')]
 roots=cp+dev+['META-INF'];names={}
 for value in roots:
  rel=PurePosixPath(value)
  require(value and not rel.is_absolute() and '..' not in rel.parts and '\\' not in value and ';' not in value,'runtime-folder-classpath')
  # Only explicit dev output folders may enter target; never target/work.
  require(excluded(value) is None,'runtime-folder-live-root')
  start=root.joinpath(*rel.parts)
  require(not any(p.is_symlink() for p in (start,*start.parents) if p==root or root in p.parents),'runtime-folder-symlink')
  # Tycho lists optional dev outputs even when no separate test source set exists.
  # Only these exact dev-only roots may be absent; manifest roots remain mandatory.
  if not start.exists() and value in dev and value not in cp and value in ('target/classes','target/test-classes'):
   if absent is not None:absent.append(value)
   continue
  require(start.exists() and not start.is_symlink(),f'runtime-folder-root-missing: bundle={root.as_posix()}; root={value}; path={start.as_posix()}')
  require(not any(p.is_symlink() for p in (start,*start.parents) if p==root or root in p.parents),'runtime-folder-symlink')
 names=bundle_content_view(root,kind='folder')['paths']
 require(len(names)<=100000 and 'META-INF/MANIFEST.MF' in names,'runtime-folder-entry-bound')
 return names,list(dict.fromkeys(cp+dev))

def fingerprint(p):
 s=p.stat();return s.st_size,s.st_mtime_ns,s.st_ino

def stream_file(src,out):
 before=fingerprint(src);count=0;h=hashlib.sha256()
 require(before[0]<=LIMIT,'capture-file-bound')
 with src.open('rb') as f:
  for block in iter(lambda:f.read(65536),b''):
   count+=len(block);require(count<=LIMIT,'capture-file-bound');h.update(block);out.write(block)
 require(count==before[0] and fingerprint(src)==before,'runtime-file-changed-during-capture')
 return dict(bytes=count,sha256=h.hexdigest())

def capture_folder(root,dest,dev):
 absent=[];names,classpath=selection(root,dev,absent=absent);before={n:fingerprint(p) for n,p in names.items()};rows={};total=0
 with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_STORED) as z:
  for n,p in sorted(names.items()):
   with z.open(n,'w') as out:rows[n]=stream_file(p,out)
   total+=rows[n]['bytes'];require(total<=LIMIT,'runtime-folder-byte-bound')
 absent_after=[];after,_=selection(root,dev,absent=absent_after)
 require(absent_after==absent,'runtime-dev-presence-changed')
 require(set(after)==set(names) and all(fingerprint(after[n])==before[n] for n in names),'runtime-folder-changed-during-capture')
 require(all(digest_file(after[n])==rows[n]['sha256'] for n in names),'runtime-folder-changed-during-capture')
 return dict(policy=POLICY,classpath=classpath,absent_dev_roots=sorted(set(absent)),exclusions=dict(EXCLUSIONS),files=rows)

def dev_configuration(obs,resolve):
 command=obs['fork_command'];values=[command[i+1] for i,v in enumerate(command[:-1]) if v=='-dev']
 require(len(values)<=1,'ambiguous-dev-properties')
 value=values[0] if values else obs.get('osgi_dev') or None
 require(not values or not obs.get('osgi_dev') or values[0]==obs['osgi_dev'],'dev-properties-observation-mismatch')
 if value is None:return {},None
 original=path(value) if value.startswith('file:') else value
 require(original.startswith('/application/'),'dev-properties-origin')
 raw=resolve(original).read_bytes()
 return properties(raw),dict(path=original,utf8=raw.decode('iso-8859-1'),sha256=hashlib.sha256(raw).hexdigest())

def capture_application(obs,out,*,resolve=Path):
 """resolve is a filesystem mapping only for offline fixtures; native uses Path."""
 out=Path(out);require(not (out/'runtime-application').exists(),'application-capture-already-exists')
 staging=Path(tempfile.mkdtemp(prefix='.runtime-application-',dir=out))
 result=copy.deepcopy(obs);dev,proof=dev_configuration(obs,resolve)
 result['agent_observation']=copy.deepcopy(obs);result['application_capture_policy']=POLICY;result['dev_properties']=proof
 result['agent_observation_utf8']=(out/'closure-observation.json').read_text(encoding='utf-8')
 result['probe_completion']=json.loads((out/'closure-complete.json').read_bytes())
 install=path(obs['install_area'])
 for b in result['bundles']:
  if b['id']==0:continue
  origin=path(b['location'],install)
  require('application_copy' not in b,'agent-application-side-effect')
  if not origin.startswith('/application/'):continue
  original=resolve(origin);require(not original.is_symlink(),'application-symlink')
  dest=staging/(str(b['id'])+'.jar');info=None
  if original.is_dir():
   declared=dev.get(b['symbolic_name'],dev.get('*',''))
   devpaths=[]
   for v in filter(None,declared.split(',')):
    v=v.strip()
    if v.startswith('/'):
     require(v.startswith(origin.rstrip('/')+'/'),'external-dev-folder-refused');v=v[len(origin.rstrip('/'))+1:]
    devpaths.append(v)
   info=capture_folder(original,dest,devpaths);kind='folder-runtime-archive'
  else:
   require(original.is_file(),'application-bundle-missing')
   with dest.open('xb') as f:row=stream_file(original,f)
   require(digest_file(original)==row['sha256'],'application-jar-changed-during-capture')
   kind='jar'
  b['application_copy']=dict(path='/results/runtime-application/'+dest.name,sha256=digest_file(dest),bytes=dest.stat().st_size,kind=kind)
  if info is not None:b['runtime_selection']=info
 from_path=out/'runtime-catalogue.tsv'
 if any(b.get('runtime_selection',{}).get('absent_dev_roots') for b in result['bundles']):
  try:from .transient_sources import catalogue
  except ImportError:from transient_sources import catalogue
  validate_absent_origins(result,catalogue(from_path.read_bytes()))
 staging.rename(out/'runtime-application')
 atomic_json(out/'worker-observation.json',result)
 return result

def validate_capture(obs,copies):
 require(obs.get('application_capture_policy') in (POLICY,PREVIOUS_POLICY,LEGACY_POLICY),'runtime-selection-policy')
 original=obs.get('agent_observation');require(isinstance(original,dict) and original.get('schema')=='b06-runtime-launch-observation/5','agent-observation-binding')
 restored=copy.deepcopy(obs)
 for n in ('agent_observation','application_capture_policy','dev_properties','agent_observation_utf8','probe_completion'):restored.pop(n)
 for b in restored['bundles']:
  b.pop('application_copy',None);b.pop('runtime_selection',None)
 require(restored==original,'agent-observation-changed')
 raw=obs['agent_observation_utf8'].encode('utf-8')
 require(json.loads(raw)==original and obs['probe_completion']==dict(status='complete',observation_sha256=hashlib.sha256(raw).hexdigest()),'agent-completion-replay')
 dev=obs['dev_properties']
 if dev is not None:require(hashlib.sha256(dev['utf8'].encode('iso-8859-1')).hexdigest()==dev['sha256'],'dev-properties-changed')
 for b in obs['bundles']:
  c=b.get('application_copy')
  if not c or c['kind']!='folder-runtime-archive':continue
  proof=b.get('runtime_selection');require(proof and proof['policy']==obs['application_capture_policy'],'folder-selection-proof')
  import io
  with zipfile.ZipFile(io.BytesIO(copies[c['path']])) as z:
   require(set(z.namelist())==set(proof['files']),'folder-selection-entry-set')
   if proof['policy'] in (POLICY,PREVIOUS_POLICY):
    _,headers,_=manifest(z.read('META-INF/MANIFEST.MF'))
    cp=[v.strip() for v in headers.get('bundle-classpath','.').split(',')]
    declarations=properties(dev['utf8'].encode('iso-8859-1')) if dev else {}
    declared=declarations.get(b['symbolic_name'],declarations.get('*',''))
    origin=path(b['location'],path(obs['install_area'])).rstrip('/')
    devroots=[]
    for v in filter(None,declared.split(',')):
     v=v.strip()
     if v.startswith('/'):
      require(v.startswith(origin+'/'),'external-dev-folder-refused');v=v[len(origin)+1:]
     devroots.append(v)
    require(proof['classpath']==list(dict.fromkeys(cp+devroots)),'folder-classpath-proof')
    absent=proof.get('absent_dev_roots')
    require(isinstance(absent,list) and absent==sorted(set(absent)),'absent-dev-proof')
    for value in absent:
     require(value in ('target/classes','target/test-classes') and value in devroots and value not in cp,'absent-dev-root-refused')
     require(not any(n==value or n.startswith(value+'/') for n in z.namelist()),'absent-dev-has-content')

   if proof['policy']==POLICY:
    view=bundle_content_view(copies[c['path']],kind='folder-archive')
    require(proof.get('exclusions')==EXCLUSIONS and not view['omitted'],'folder-exclusion-proof')
    require({n:{k:r[k] for k in ('bytes','sha256')} for n,r in view['entries'].items()}==proof['files'],'folder-content-view-proof')
   for n,row in proof['files'].items():
    raw=z.read(n);require(row==dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),'folder-selection-file-binding')
    parts=PurePosixPath(n).parts
    if proof['policy']!=POLICY:require(not any(p in EXCLUDED for p in parts) or parts[:2] in (('target','classes'),('target','test-classes')),'folder-selection-live-file')


def validate_absent_origins(obs,loaded):
 """An absent dev output cannot have supplied a recorded loaded class."""
 for b in obs['bundles']:
  proof=b.get('runtime_selection',{})
  for rel in proof.get('absent_dev_roots',[]):
   base=path(b['location'],path(obs['install_area'])).rstrip('/')+'/'+rel
   for row in loaded:
    origin=row['origin']
    if origin.startswith(('file:','/')):
     actual=path(origin).rstrip('/')
     require(actual!=base and not actual.startswith(base+'/'),'loaded-class-from-absent-dev-root')
